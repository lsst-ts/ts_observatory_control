# This file is part of ts_observatory_control.
#
# Developed for the Vera Rubin Observatory Telescope and Site Systems.
# This product includes software developed by the LSST Project
# (https://www.lsst.org).
# See the COPYRIGHT file at the top-level directory of this distribution
# for details of code ownership.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License

__all__ = ["CalsysScriptIntention", "CalsysThroughputCalculationMixin", "BaseCalsys"]


import asyncio
import csv
import enum
import logging
from abc import ABCMeta, abstractmethod
from collections.abc import AsyncGenerator, Callable, Coroutine
from datetime import datetime
from functools import reduce
from importlib.resources import files
from itertools import count
from typing import (
    Any,
    Awaitable,
    Mapping,
    Optional,
    Sequence,
    TypeAlias,
    TypeVar,
    Union,
)

import astropy.units as un
from astropy.units import Quantity, ampere, nm, watt
from lsst.ts import salobj
from lsst.ts.idl.enums import Electrometer
from scipy.interpolate import InterpolatedUnivariateSpline

from .remote_group import RemoteGroup

Responsivity: TypeAlias = Quantity[ampere / watt]
T = TypeVar("T")


def _calsys_get_parameter(
    indct: dict[str, T],
    key: str,
    factory_callable: Callable,
    *factory_args: Any,
    **factory_kwargs: Any,
) -> T:
    if indct.get(key, None) is None:
        return factory_callable(*factory_args, **factory_kwargs)


class CalsysScriptIntention(enum.IntEnum):
    """Enum which indicates what a SAL script will be using the calsys for."""

    TURN_ON = 0
    TURN_OFF = 1
    QUICK_CALIBRATION_RUN = 2
    LONG_CALIBRATION_RUN = 3


TaskOrCoro = Union[asyncio.Task, Coroutine]


class CalsysThroughputCalculationMixin:
    """Mixin class to allow pluggable source for calculation of throughputs."""

    POWER_LINE_FREQUENCY = 60 / (un.s)

    @abstractmethod
    def detector_throughput(self, wavelen: float) -> float:
        """the throughput value will return (in appropriate units TBD) the detector throughput of the particular
        calibration system specified in the class for which this mixin class is specified as a base.

        Parameters
        ----------

        wavelen: float - wavelength of the calibration to be performed in nm


        Returns
        -------

        A value (units TBD, likely electrons per pixel per second), which can be used to
        either determine how long to integrate the sensor for to achieve a desired level of calibration
        field in electrons, or determine how many electrons will be obtained for a specific integration time

        """

    @abstractmethod
    def spectrograph_throughput(self, wavelen: float, calsys_power: float) -> float:
        """the throughput expected of the fiber spectrograph of the calibration system.
        
        To aid calculations  of total throughput
        """

    @abstractmethod
    def radiometer_responsivity(
        self, wavelen: Quantity[un.physical.length]
    ) -> Responsivity:
        """return the responsivity of the radiometer"""

    def end_to_end_throughput(self, wavelen: float, calsys_power: float) -> float:
        # intended to be SOMETHING LIKE
        return reduce(
            lambda t, f: t * f(wavelen, calsys_power),
            [
                self.detector_throughput,
                self.spectrograph_throughput,
                self.radiometer_responsivity,
            ],
        )

    def total_radiometer_exposure_time(
        self, rad_exposure_time: Quantity[un.physical.time], nplc: float
    ) -> Quantity[un.physical.time]:
        # Note comm from Parker:
        # "valid nplc values are from 0.01 to 10 (seconds)
        if not (0.01 <= nplc <= 10.0):
            raise ValueError(
                f"supplied valud for nplc: {nplc} is not within allowed values 0.01 <= nplc <= 10"
            )
        # Note: magic numbers from communication with Parker F.
        # To be added to electrometer CSC docs
        rad_int_time = nplc / self.POWER_LINE_FREQUENCY
        time_sep = (rad_int_time * 3.07) + 0.00254
        # NOTE: is 0.00254 a metric -> imperial conversion?
        max_exp_time = 16667 * time_sep
        n_meas: int = rad_exposure_time / time_sep
        total_time = n_meas * 0.01 + rad_exposure_time

        if total_time > max_exp_time:
            raise ValueError(
                f"total exposure time {total_time} is longer than max allowed {max_exp_time}"
            )

        return total_time


class ButlerCalsysThroughput(CalsysThroughputCalculationMixin):
    """Calculating throughput of the calibration system backed by measurements stored in  a DM butler"""


class HardcodeCalsysThroughput(CalsysThroughputCalculationMixin):
    """Calculating throughput of the calibration system with hardcoded values, i.e. which can be directly imported from python code"""

    BASERES: str = "lsst.ts.observatory.control.cal_curves"
    RADIOMETER_CALFILE: str = "hamamatsu_responsivity.csv"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._itps: dict[str, InterpolatedUnivariateSpline] = dict()

    @classmethod
    def load_calibration_csv(cls, fname: str) -> Mapping[str, Sequence[float]]:
        res = files(cls.BASERES).joinpath(fname)
        with res.open("r") as f:
            rdr = csv.DictReader(f)
            if rdr.fieldnames is None:
                raise ValueError("calibration curve has no fieldnames!")
            out: dict[str, list[float]] = {k: [] for k in rdr.fieldnames}
            for row in rdr:
                for k, v in row.items():
                    val: float = float(v) if len(v) > 0 else 0.0
                    out[k].append(val)
        return out

    def _ensure_itp(
        self, itpname: str, fname: Optional[str] = None, xaxis: Optional[str] = None,
            yaxis: Optional[str] = None, **itpargs) -> InterpolatedUnivariateSpline:
        """Obtain an interpolated spline from a calibration curve.

        If the calibration curve has already been loaded, returns the existing spline interpolation object.
        Otherwise, will load the calibration data from the filename supplied

        Parameters
        ----------
        itpname : Optional[str]
            The name from which to lookup the interpolation object.
            When object is first loaded, will lookup an interpolation object with this name
        fname : Optional[str]
            The file name from which to load the calibration data.
        xaxis : Optional[str]
            The column name of the x-axis interpolator
        yaxis : Optional[str]
            The column name of the y-axis interpolator
        **itpargs : 7
            Arguments which will be passed through to scipy InterpolatedUnivariateSpline

        Returns
        -------
        a scipy InterpolatedUnivariateSpline object which is callable and can be used to
        obtain interpolated calibration values.
        """

        if itpname not in self._itps:
            if any(_ is None for _ in [fname, xaxis, yaxis]):
                raise ValueError("missing required value to load calibration data")
            calres = self.load_calibration_csv(fname)
            itp = InterpolatedUnivariateSpline(calres[xaxis], calres[yaxis], **itpargs)
            self._itps[itpname] = itp
        else:
            return self._itps[itpname]

    def radiometer_responsivity(self, wavelen: Quantity[un.physical.length]) -> Responsivity:
        wlin: float = wavelen.to(nm).value

        itp = self._ensure_itp(
            "radiometer", self.RADIOMETER_CALFILE, "wavelength", "responsivity"
        )

        Rawout: float = itp(wlin)
        return Rawout << un.ampere / un.watt

    def maintel_throughput(
        self, wavelen: Quantity[un.physical.length], filter_band: str
    ) -> Quantity[un.dimensionless_unscaled]:
        calfilename: str = f"calibration_tput_init_{filter_band}.csv"
        itp = self._ensure_itp(
            f"maintel_{filter_band}", calfilename, "Wavelength[nm]", "Throughput"
        )

        wlin: float = wavelen.to(nm).value
        return Quantity(itp(wlin), un.dimensionless_unscaled)


class BaseCalsys(RemoteGroup, metaclass=ABCMeta):
    """Base class for calibration systems operation
    """

    CMD_TIMEOUT: Quantity[un.physical.time] = 30 << un.s
    EVT_TIMEOUT: Quantity[un.physical.time] = 30 << un.s
    TELEM_TIMEOUT: Quantity[un.physical.time] = 30 << un.s
    CAL_PROGRAM_NAME: str = "flats"

    def __init__(
        self,
        intention: CalsysScriptIntention,
        components: list[str],
        domain: Optional[salobj.domain.Domain] = None,
        cmd_timeout: Optional[int] = 10,
        log: Optional[logging.Logger] = None,
    ):
        """Construct a new BaseCalsys object

        NOTE: should not generally be constructed directly by a user either interactively or in a SAL script

        Parameters
        ----------
        intention : CalsysScriptIntention
            Configures the general behaviour of calls according to what the script is going to do
        components : list[str]
            SAL components to initialize, should be overridden in daughter class
        domain : Optional[salobj.domain.Domain]
            DDS OpenSplice domain to use
        cmd_timeout : Optional[int]
            timeout (measured in seconds) for DDS OpenSplice commands
        log : Optional[logging.Logger]
            existing logging object

        """
        super().__init__(
            components,
            domain,
            log=log,
            intended_usage=salobj.BaseUsages.StateTransition,
            concurrent_operation=False,
        )  # QUESTION: is this last one true????

        self._intention = intention

    def _sal_cmd(
        self, obj: salobj.Remote, cmdname: str, run_immediate: bool = True, **setargs
    ) -> TaskOrCoro:
        """Helper function that Runs a command on a remote SAL object

        This function is mainly here to avoid a lot of boilerplate that otherwise
        accumulates in the daughter classes

        Parameters
        ----------
        obj : salobj.Remote
            SAL remote object to call the command on
        cmdname : str
            the name of the command to call (look up in the generated XML
            definitions for the respective CSC), excluding the conventional 'cmd_' prefix
        run_immediate : bool
            chooses whether to return an event-loop posted future (which is done using
            asyncio.create_task, or whether to return an un-posted coroutine function

            if True, returns the future, if False, returns the coroutine

        **setargs
            extra arguments that are passed to the SAL remote object set function

        Returns
        -------
        TaskOrCoro
            the packaged future or coroutine (which type depends on the value of run_immediate)

        Examples
        --------

        # some function calls that get us the relevant objects, in this case an Electrometer
        calsys: BaseCalsys = get_calsys_object()
        salobj: sal.Remote = get_electrometer_object()
        assert type(salobj) is Electrometer

        # cal the "cmd_performZeroCalib" operation on the electrometer, returning a future,
        with the task having already been posted to the running event loop

        fut = calsys._sal_cmd(salobj, salobj, "performZeroCalib")

        """
        timeout = self.CMD_TIMEOUT.to(un.s).value
        cmdfun: salobj.topics.RemoteCommand = getattr(obj, f"cmd_{cmdname}")
        pkgtask = cmdfun.set_start(**setargs, timeout=timeout)
        if run_immediate:
            return asyncio.create_task(pkgtask)
        return pkgtask

    def _sal_waitevent(
        self,
        obj: salobj.Remote,
        evtname: str,
        run_immediate: bool = True,
        flush: bool = True,
        **evtargs,
    ) -> TaskOrCoro:
        """A helper function which waits for an event on a SAL remote object

        Parameters
        ----------
        obj : salobj.Remote
            SAL remote object to wait for the telemetry or event on            
        evtname : str
            name of the event to wait for (excluding the conventional prefix 'evt_')
        run_immediate : bool
            Whether to return a posted future or an un-posted coroutine,
            see documentation for BaseCalsys._sal_cmd
        flush : bool
            Whether to flush the remote SALobject DDS event queue for this
            particular event
            (i.e. whether to definitely force wait for a new event rather than popping
            from a queue) - see documentation for salobj.Remote
        **evtargs : 7
            extra arguments that get passed to the .next() method of the SAL object

        Returns
        -------
        TaskOrCoro
            posted future or unposted coro, according to value of run_immediate,
            as per BaseCalsys._sal_cmd
        """
        timeout = self.EVT_TIMEOUT.to(un.s).value
        cmdfun: salobj.topics.RemoteEvent = getattr(obj, f"evt_{evtname}")
        pkgtask = cmdfun.next(timeout=timeout, flush=flush)
        if run_immediate:
            return asyncio.create_task(pkgtask)
        return pkgtask

    def _lfa_event(
        self,
        obj: salobj.Remote,
        telname: str,
        run_immediate: bool = True,
        flush: bool = True,
        **evtargs,
    ) -> TaskOrCoro:
        return self._sal_waitevent(
            obj, "largeFileObjectAvailable", run_immediate, flush, **evtargs
        )

    def _sal_evt_gen(
        self, obj: salobj.Remote, evtname: str, flush: bool = True
    ) -> AsyncGenerator:
        pkgtask = self._sal_waitevent(obj, evtname, run_immediate=False, flush=flush)

        async def gen():
            while True:
                v = await pkgtask
                yield v

        return gen()

    def _sal_telem_gen(self, obj: salobj.Remote, telname: str) -> AsyncGenerator:
        timeout = self.TELEM_TIMEOUT.to(un.s).value
        cmdfun: salobj.topics.RemoteTelemetry = getattr(obj, f"tel_{telname}")

        async def gen():
            while True:
                v = await cmdfun.next(timeout=timeout, flush=True)
                yield v

        return gen()

    def _long_wait(
        self,
        gen: AsyncGenerator,
        timeout_seconds: float,
        validate_fun: Callable[[Any], bool],
        run_immediate: bool = True,
    ) -> TaskOrCoro:
        async def completer() -> None:
            async for value in gen:
                if validate_fun(value):
                    return

        coro = asyncio.wait_for(completer(), timeout_seconds)
        if run_immediate:
            return asyncio.create_task(coro)
        return coro

    async def _cal_expose_helper(
        self, obj, n: int, cmdname: str, **extra_kwargs
    ) -> list[str]:
        out_urls: list[str] = []
        for i in range(n):
            await self._sal_cmd(obj, cmdname, **extra_kwargs)
            lfa_obj = await self._sal_waitevent(obj, "largeFileObjectAvailable")
            out_urls.append(lfa_obj.url)
        return out_urls

    async def _long_wait_err_handle(
        self,
        gen: AsyncGenerator,
        timeout_seconds: float,
        validate_fun: Callable[[Any], bool],
        name_of_wait: str,
    ) -> tuple[datetime, datetime]:
        starttime = datetime.now()
        try:
            await self._long_wait(
                gen, timeout_seconds, validate_fun, run_immediate=False
            )
            endtime = datetime.now()
            return starttime, endtime
        except TimeoutError as err:
            nowfail = datetime.now()
            wait_time: float = (nowfail - starttime).total_seconds()
            self.log.error(
                f"waited {wait_time} seconds but {name_of_wait} did not succeed"
            )
            raise err

    @classmethod
    def log_event_timings(
        cls,
        logger,
        time_evt_name: str,
        start_time: datetime,
        end_time: datetime,
        expd_duration: Quantity[un.physical.time],
    ) -> None:
        logstr = (
            f"event: {time_evt_name} started at {start_time} and finished at {end_time}"
        )
        logger.info(logstr)
        duration = (start_time - end_time).total_seconds() << un.s
        logstr2 = f"the duration was: {duration}, and our timeout allowance was: {expd_duration}"
        logger.info(logstr2)


    def detector_exposure_time_for_nelectrons(
        self, wavelen: Quantity[un.physical.length], nelec: float
    ) -> float:
        """using the appropriate mixin for obtaining calibration data on throughput,
        will calculate and return the exposure time needed to obtain a flat field calibration of n
        electrons at the imager specified in the class definition

        Parameters
        ----------
        wavelen: float - wavelength (in nm??) of the intended calibration
        nelec: float - number of electrons (probably measured in ke-??) desired in calibration field

        Returns
        -------
        exposure time: float - time  (in seconds??) needed for the imager to obtain desired calibration field

        """

        # must have a way to access the calibration data
        assert issubclass(type(self), CalsysThroughputCalculationMixin)
        raise NotImplementedError("throughput calc for detector not implemented yet!")

    def spectrograph_exposure_time_for_nelectrons(self, nelec: float) -> float:
        raise NotImplementedError(
            "throughput calc for spectrograph not implemented yet!"
        )

    def spectrograph_n_exps_for_nelectrons(self, nelec: float) -> int:
        raise NotImplementedError(
            "throughput calc for spectrograph not implemented yet!"
        )

    def pd_exposure_time_for_nelectrons(self, nelec: float) -> float:
        raise NotImplementedError(
            "throughput calc for electrometer not implemented yet!"
        )

    def pd_n_exps_for_nelectrons(self, nelec: float) -> int:
        raise NotImplementedError(
            "throughput calc for electrometer not implemented yet"
        )

    @property
    @abstractmethod
    def _electrometer_object(self) -> Electrometer:
        pass

    @abstractmethod
    async def validate_hardware_status_for_acquisition(self) -> Awaitable:
        pass

    @abstractmethod
    async def power_sequence_run(self, scriptobj, **kwargs) -> Awaitable:
        pass

    @abstractmethod
    async def setup_for_wavelength(self, wavelen: float, **extra_params) -> None:
        """awaitable which sets up the various remote components of a calibration system
        to perform a calibration at a particular wavelength.

        Intended to be a 'high level' setup function, such that user doesn't have to worry about e.g. setting up integration times for spectrographs etc

        Parameters
        ----------

        wavelen: float - desired wavelength (in nm)

        extra_params: to handle things which are specific to individual calibration systems
        (e.g that the auxtel can also adjust spectral bandwidth)

        """
        pass

    @abstractmethod
    async def take_calibration_data(self):
        """awaitable which starts the exposures for the calibration instruments (i.e the spectrographs, electrometers etc) according to the setup. It does not take images with the instrument under test, it is intended that script components which use this class do that themselves"""
        pass

    async def generate_data_flats(
        self, instrobj, scriptobj, exposure_time_s: float, n_iter: Optional[int] = None
    ):
        """returns an async generator which yields sets of exposures from"""

        # Run forever if n_iter was not given, don't worry it's just a generator
        nrange = count() if n_iter is None else range(n_iter)

        for i in nrange:
            self.log.info("taking flats number %d", i)
            instr_task = instrobj.take_flats(
                exposure_time_s,
                nflats=1,
                groupid=scriptobj.group_id,
                program=self.CAL_PROGRAM_NAME,
                reason=self.program_reason,
                note=self.program_note,
            )
            instr_fut = asyncio.create_task(instr_task)
            aux_cal_fut = self.take_calibration_data()
            instr_results, aux_cal_results = await asyncio.gather(
                aux_cal_fut, instr_fut
            )
            yield instr_results, aux_cal_results

    @property
    @abstractmethod
    def program_reason(self) -> str:
        ...

    @property
    @abstractmethod
    def program_note(self) -> str:
        ...

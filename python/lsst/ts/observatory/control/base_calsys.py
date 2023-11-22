from abc import ABCMeta, abstractmethod
from dataclasses import dataclass
from .remote_group import RemoteGroup
from typing import Iterable, Optional, Tuple, List, Union
from typing import Sequence, Mapping, TypeAlias, Any
from typing import TypeVar
from functools import reduce
from collections.abc import Coroutine, Callable, AsyncGenerator
from operator import mul
from lsst.ts import salobj
import logging
import asyncio
from importlib.resources import files
import csv
from scipy.interpolate import InterpolatedUnivariateSpline
from astropy.units import ampere, watt, nm, Quantity
import astropy.units as un
import enum
from datetime import datetime

Responsivity: TypeAlias = Quantity[ampere / watt]

@dataclass
class CalibrationSequenceStepBase:
    wavelength: float
    n_exp: int
    exp_time: float


class CalsysScriptIntention(enum.IntEnum):
    TURN_ON = 0
    TURN_OFF = 1
    QUICK_CALIBRATION_RUN = 2
    LONG_CALIBRATION_RUN = 3

TaskOrCoro = Union[asyncio.Task, Coroutine]


class CalsysThroughputCalculationMixin:
    """mixin class to allow pluggable source for calculation of throughputs"""

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
    def radiometer_responsivity(self, wavelen: Quantity[un.physical.length]) -> Responsivity:
        """return the responsivity of the radiometer"""

    def end_to_end_throughput(self, wavelen: float, calsys_power: float) -> float:
        # intended to be SOMETHING LIKE
        return reduce(
            lambda t, f: t * f(wavelen, calsys_power),
            [
                self.detector_throughput,
                self.spectrograph_throughput,
                self.radiometer_throughput,
            ],
        )

    def total_radiometer_exposure_time(
        self, rad_exposure_time: Quantity[un.physical.time], nplc: float
    ) -> Quantity["time"]:
        # Note comm from Parker: "valid nplc values are from 0.01 to 10 (seconds)
        if not (0.01 <= nplc <= 10.0):
            raise ValueError(
                f"supplied valud for nplc: {nplc} is not within allowed values 0.01 <= nplc <= 10"
            )
        # Note: magic numbers from communication with Parker F. To be added to electrometer CSC docs
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
    """Mixin class for calculating throughput of the calibration system backed by measurements stored
    in  a DM butler"""


class HardcodeCalsysThroughput(CalsysThroughputCalculationMixin):
    """Mixin class for calculating throughput of the calibration system with hardcoded values,
    i.e. which can be directly imported from python code"""

    BASERES: str = "lsst.ts.observatory.control.cal_curves"
    RADIOMETER_CALFILE: str = "hamamatsu_responsivity.csv"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._itps: dict[str, InterpolatedUnivariateSpline] = dict()
        self._intention = intention

    @classmethod
    def load_calibration_csv(cls, fname: str) -> Mapping[str, Sequence[float]]:
        res = files(cls.BASERES).joinpath(fname)
        with res.open("r") as f:
            rdr = csv.DictReader(f)
            out = {k: [] for k in rdr.fieldnames}
            for row in rdr:
                for k, v in row.items():
                    val: float = float(v) if len(v) > 0 else 0.0
                    out[k].append(val)
        return out

    def _ensure_itp(
        self, itpname: str, fname: str, xaxis: str, yaxis: str, **itpargs
    ) -> InterpolatedUnivariateSpline:
        if itpname not in self._itps:
            calres = self.load_calibration_csv(fname)
            itp = InterpolatedUnivariateSpline(calres[xaxis], calres[yaxis], **itpargs)
            self._itps[itpname] = itp
        else:
            return self._itps[itpname]

    def radiometer_responsivity(self, wavelen: Quantity["length"]) -> Responsivity:
        wlin: float = wavelen.to(nm).value

        itp = self._ensure_itp(
            "radiometer", self.RADIOMETER_CALFILE, "wavelength", "responsivity"
        )

        wlin: float = wavelen.to(nm).value
        Rawout: float = itp(wlin)
        return Rawout << un.ampere / un.watt

    def maintel_throughput(
        self, wavelen: Quantity["length"], filter_band: chr
    ) -> Quantity[un.dimensionless_unscaled]:
        calfilename: str = f"calibration_tput_init_{filter_band}.csv"
        itp = self._ensure_itp(
            f"maintel_{filter_band}", calfilename, "Wavelength[nm]", "Throughput"
        )

        wlin: float = wavelen.to(nm).value
        return Quantity(itp(wlin), un.dimensionless_unscaled)


class BaseCalsys(RemoteGroup, metaclass=ABCMeta):
    """Base class for calibration systems"""
    CMD_TIMEOUT: Quantity[un.physical.time] = 30 << un.s
    EVT_TIMEOUT: Quantity[un.physical.time] = 30 << un.s
    TELEM_TIMEOUT: Quantity[un.physical.time] = 30 << un.s

    def __init__(
        self,
            intention: CalsysScriptIntention,
            components: Iterable[str],
            domain: Optional[salobj.domain] = None,
            cmd_timeout: Optional[int] = 10,
            log: Optional[logging.Logger] = None,
    ):
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
        timeout = self.CMD_TIMEOUT.to(un.s).value
        cmdfun: salobj.topics.RemoteCommand = getattr(obj, f"cmd_{cmdname}")
        pkgtask = cmdfun.set_start(**setargs, timeout=timeout)
        if run_immediate:
            return asyncio.create_task(pkgtask)
        return pkgtask

    def _sal_waitevent(self, obj: salobj.Remote, evtname: str, run_immediate: bool=True, flush: bool=True,
                              **evtargs) -> TaskOrCoro:
        timeout = self.EVT_TIMEOUT.to(un.s).value
        cmdfun: salobj.topics.RemoteEvent = getattr(obj, f"evt_{evtname}")
        pkgtask = cmdfun.next(timeout=timeout, flush=flush)
        if run_immediate:
            return asyncio.create_task(pkgtask)
        return pkgtask

    def _lfa_event(self, obj: salobj.Remote, telname: str, run_immediate: bool = True,
                   flush: bool=True,  **evtargs) -> TaskOrCoro:
        return self._sal_waitevent(obj, "largeFileObjectAvailable", run_immediate, flush, **evtargs)

    def _sal_evt_gen(self, obj:salobj.Remote, evtname: str, flush: bool=True) -> AsyncGenerator:
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

    def _long_wait(self, gen: AsyncGenerator, timeout_seconds, validate_fun: Callable[[Any], bool],
                   run_immediate: bool=True) -> TaskOrCoro:
        async def completer() -> None:
            async for value in gen:
                if(validate_fun(value)):
                    return

        coro = asyncio.wait_for(completer(), timeout_seconds)
        if run_immediate:
            return asyncio.create_task(coro)
        return coro

    async def _long_wait_err_handle(self, gen: AsyncGenerator, timeout_seconds,
                                    validate_fun: Callable[[Any], bool], name_of_wait: str) -> tuple[datetime,datetime]:
        starttime = datetime.now()
        try:
            await self._long_wait(gen, timeout_seconds, validate_fun, run_immediate=False)
            endtime = datetime.now()
            return starttime, endtime
        except TimeoutError as err:
            nowfail = datetime.now()
            wait_time: float = (nowfail - starttime).total_seconds()
            self.log.error(f"waited {wait_time} seconds but {name_of_wait} did not succeed")
            raise err


    @classmethod
    def log_event_timings(cls, logger, time_evt_name: str,
                          start_time: datetime, end_time: datetime,
                          expd_duration: Quantity[un.physical.time]) -> None:
        logstr = f"event: {time_evt_name} started at {start_time} and finished at {end_time}"
        logger.info(logstr)
        duration = (start_time - end_time).total_seconds() << un.s
        logstr2 = f"the duration was: {duration}, and our timeout allowance was: {expt_duration}" 
        logger.info(logstr2)
        
        

    async def take_electrometer_exposures(
        self, electrobj, exp_time_s: float, n: int
    ) -> List[str]:
        urlout: List[str] = []
        for i in range(n):
            await electrobj.cmd_StartScanDt.set_start(scanDuration=exp_time)
            lfaurl = await self._lfa_event_helper(electrobj)
            urlout.append(lfaurl)
        return urlout

    def detector_exposure_time_for_nelectrons(
        self, wavelen: Quantity["length"], nelec: float
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

    def spectrograph_exposure_time_for_nelectrons(self, nelec: float) -> float:
        pass

    def pd_exposure_time_for_nelectrons(self, nelec: float) -> float:
        pass


    @abstractmethod
    async def validate_hardware_status_for_acquisition(self) -> Awaitable:
        pass
    
    @abstractmethod
    async def power_sequence_run(self, scriptobj, **kwargs):
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
    async def take_calibration_instr_exposures(self) -> None:
        """awaitable which starts the exposures for the calibration instruments (i.e the spectrographs, electrometers etc) according to the setup. It does not take images with the instrument under test, it is intended that script components which use this class do that themselves"""
        pass

    @property
    @abstractmethod
    def wavelen(self) -> Quantity[nm]:
        """returns the currently configured wavelength"""

    @abstractmethod
    async def take_detector_data(self):
        """This will fire off all async tasks to take calibration data in sequence, and return locations a
        nd metadata about the files supplied etc"""


    @abstractmethod
    async def gen_calibration_auxiliaries(self):
        pass

    async def wait_ready(self):
        """ Method to wait for prepared state for taking data - e.g. lamps on, warmed up, laser warmed up etc"""


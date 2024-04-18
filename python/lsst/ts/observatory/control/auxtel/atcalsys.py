__all__ = ["ATSpectrographSlits", "ATCalibrationSequenceStep", "ATCalsys"]

import asyncio
from collections.abc import Awaitable
from dataclasses import dataclass
from datetime import datetime
from typing import List, NamedTuple, Optional

import astropy.units as un
from astropy.units import Quantity
from lsst.ts import salobj
from lsst.ts.idl.enums import ATMonochromator, ATWhiteLight

from ..base_calsys import (
    BaseCalsys,
    CalibrationSequenceStepBase,
    CalsysScriptIntention,
    HardcodeCalsysThroughput,
    _calsys_get_parameter,
)


class ATSpectrographSlits(NamedTuple):
    FRONTENTRANCE: float
    FRONTEXIT: float


@dataclass
class ATCalibrationSequenceStep(CalibrationSequenceStepBase):
    grating: ATMonochromator.Grating
    latiss_filter: str
    latiss_grating: str
    entrance_slit_width: float
    exit_slit_width: float
    fs_exp_time: float
    fs_n_exp: int
    em_exp_time: float
    em_n_exp: int


class ATCalsys(BaseCalsys, HardcodeCalsysThroughput):
    """class which specifically handles the calibration system for auxtel."""

    _AT_SAL_COMPONENTS: List[str] = [
        "ATMonochromator",
        "FiberSpectrograph",
        "Electrometer",
        "ATWhiteLight",
    ]
    CHANGE_GRATING_TIME: Quantity[un.physical.time] = 60 << un.s

    # these below numbers should be able to be loaded from a
    # (fairly static) config!
    GRATING_CHANGEOVER_WL: Quantity[un.physical.length] = 532.0 << un.nm
    GRATING_CHANGEOVER_BW: Quantity[un.physical.length] = (
        55.0 << un.nm
    )  # WARNING! PLACEHOLDER VALUE!!!

    CHILLER_COOLDOWN_TIMEOUT: Quantity[un.physical.time] = 15 << un.min
    CHILLER_SETPOINT_TEMP: Quantity[un.physical.temperature] = 20 << un.deg_C
    CHILLER_TEMP_REL_TOL: float = 0.2

    WHITELIGHT_POWER: Quantity[un.physical.power] = 910 << un.W
    WHITELIGHT_LAMP_WARMUP_TIMEOUT: Quantity[un.physical.time] = 15 << un.min

    SHUTTER_OPEN_TIMEOUT: Quantity[un.physical.time] = 15 << un.min
    CAL_PROGRAM_NAME: str = "AT_flats"

    def __init__(self, intention: CalsysScriptIntention, **kwargs):
        """ Initialise the ATCalsys System

        Parameters
        ----------
        intention: CalsysScriptIntention
            An instance of CalsysScriptIntention that tells us what the script will be doing
            this allows us to customise the various manipulation routines of the calibration system

        """ 
        super().__init__(intention, components=self._AT_SAL_COMPONENTS, **kwargs)

        # instance variables we'll set later
        self._specsposure_time: Optional[float] = None
        self._elecsposure_time: Optional[float] = None
        self._n_spec_exps: Optional[int] = None
        self._n_elec_exps: Optional[int] = None

    async def setup_for_wavelength(
        self, wavelen: float, nelec: float, spectral_res: float, **override_kwargs
    ) -> None:
        """Set up the calibration system for running flats of a particular wavelength

        Parameters
        ----------
        wavelen : float
            the wavelength to setup for (in nm)
        nelec : float
            the tarket number of electrons for flat exposure (in kelec)
        spectral_res : float
            the target spectral resolution
        **override_kwargs : FIXME: Add type.
            keyword arguments passed in here will be forwarded to `_calss_get_parameter`

        """

        grating = _calsys_get_parameter(
            override_kwargs,
            "grating",
            self.calculate_grating_type,
            wavelen,
            spectral_res,
        )
        slit_widths = _calsys_get_parameter(
            override_kwargs,
            "slit_widths",
            self.calculate_slit_width,
            wavelen,
            spectral_res,
            grating,
        )
        self.log.debug(
            f"setting up monochromtor with wavlength {wavelen} nm and spectral resolution {spectral_res}"
        )
        self.log.debug(f"calculated slit widthsare {slit_widths}")
        self.log.debug(f"calculated grating is {grating}")

        monoch_fut = self._sal_cmd(
            self.ATMonochromator,
            "updateMonochromatorSetup",
            gratingType=grating,
            frontExitSlitWidth=slit_widths.FRONTEXIT,
            frontEntranceSlitWdth=slit_widths.FRONTENTRACE,
            wavelength=wavelen,
        )

        elect_fut = self._sal_cmd(self.Electrometer, "performZeroCalib")
        elect_fut2 = self._sal_cmd(
            self.Electrometer,
            "setDigitalFilter",
            activateFilter=False,
            activateAvgFilter=False,
            activateMedFilter=False,
        )

        await asyncio.wait(
            [monoch_fut, elect_fut, elect_fut2], return_when=asyncio.ALL_COMPLETED
        )
        self.log.debug("all SAL setup commands returned")
        self._specsposure_time = _calsys_get_parameter(
            override_kwargs,
            "specsposure_time",
            self.spectrograph_exposure_time_for_nelectrons,
            nelec,
        )
        self._elecsposure_time = _calsys_get_parameter(
            override_kwargs,
            "elecsposure_time",
            self.pd_exposure_time_for_nelectrons,
            nelec,
        )
        self._n_spec_exps = _calsys_get_parameter(
            override_kwargs,
            "n_spec_exps",
            self.spectrograph_n_exps_for_nelectrons,
            nelec,
        )
        self._n_elec_exps = _calsys_get_parameter(
            override_kwargs, "n_elec_exps", self.pd_n_exps_for_nelectrons, nelec
        )

    def calculate_slit_width(self, wavelen: float, spectral_res: float,
                             grating: Optional[ATMonochromator.GRATING] = None
                             ) -> Optional[ATSpectrographSlits]:
        """Calculate the slit width needed to achieve given spectral resolution.
        NOTE: DO NOT USE! No calibration data available here yet!

        The fiber spectrograph output slit widths control the spectral bandwidth
        of the flat fields. This function converts a targeted spectral resolution
        into a slit width setting

        Parameters
        ----------
        wavelen : float
            the central wavelength of the spectrum (in units of nm)
        spectral_res : float
            the desired FWHM bandwidth of the spectrum (in units of nm)
        grating : Optional[ATMonochromator.GRATING]
            which grating to use - see ts enums. If not supplied, will be
            calculated using `calculate_grating_type`

        Returns
        -------
        Optional[ATSpectrographSlits]
            FIXME: Add docs.

        Raises
        ------
        NotImplementedError
            FIXME: Add docs.

        """

        if grating is None:
            grating = self.calculate_grating_type(wavelen, spectral_res)
        raise NotImplementedError(
            "calculation of slit widths not available yet, override in script parameters!"
        )

    def calculate_grating_type(
        self, wavelen: float, spectral_res: float
    ) -> ATMonochromator.Grating:
        # TODO: placeholder logic, in particular the exact numbers will be WRONG!
        # likely something like the below
        if spectral_res > self.GRATING_CHANGEOVER_BW:
            return ATMonochromator.Grating.MIRROR
        elif wavelen < self.GRATING_CHANGEOVER_WL:
            return ATMonochromator.Grating.BLUE
        return ATMonochromator.Grating.RED

    async def _electrometer_expose(self) -> Awaitable[list[str]]:
        """begin an exposure of the electrometer subsystem

        the electrometer scan is immediately started on calling this function,
        after coroutine suspension the caller may at a later point await
        the result. See documentation for BaseCalsys._cal_expose_helper for
        details.

        Returns
        -------
        Awaitable[list[str]] deferred result of the electormeter exposure
        """

        assert self._n_elec_exps is not None
        assert self._elecsposure_time is not None
        return self._cal_expose_helper(
            self.Electrometer,
            self._n_elec_exps,
            "startScanDt",
            scanDuration=self._elecsposure_time,
        )

    async def _spectrograph_expose(self) -> Awaitable[list[str]]:
        assert self._n_spec_exps is not None
        assert self._specsposure_time is not None

        return self._cal_expose_helper(
            self.ATSpectrograph,
            self._n_spec_exps,
            "expose",
            numExposures=1,
            duration=self._specsposure_time,
        )

    @property
    def _electrometer_object(self):
        return self.Electrometer

    @property
    def script_time_estimate_s(self) -> float:
        """Property that returns the estimated time for the script to run in units of seconds.

        For script time estimation purposes.
        For now just returns a default long time
        """
        match (self._intention):
            case CalsysScriptIntention.POWER_ON | CalsysScriptIntention.POWER_OFF:
                # for now just use fixed values from previous script
                # start out with chiller time maximum
                total_time: Quantity[un.physical.time] = self.CHILLER_COOLDOWN_TIMEOUT
                # add on the lamp warmup timeout
                total_time += self.WHITELIGHT_LAMP_WARMUP_TIMEOUT
                total_time += self.SHUTTER_OPEN_TIMEOUT
                return total_time.to(un.s).value
            case _:
                raise NotImplementedError(
                    "don't know how to handle this script intention"
                )

    async def power_sequence_run(self, scriptobj: salobj.BaseScript, **kwargs) -> None:
        """Run a power sequence operation

         A power sequence operation is, for example, turning on or off the calibration
        system preparing for daily calibration runs. The sequence run depends
        on the indicated intention of the current SAL script
        """
        match (self._intention):
            case CalsysScriptIntention.POWER_ON:
                await self._chiller_power(True)
                await scriptobj.checkpoint("Chiller started")
                chiller_start, chiller_end = await self._chiller_settle()
                self.log_event_timings(
                    self.log,
                    "chiller cooldown time",
                    chiller_start,
                    chiller_end,
                    self.CHILLER_COOLDOWN_TIMEOUT,
                )

                await scriptobj.checkpoint("Chiller setpoint temperature reached")
                shutter_wait_fut = asyncio.create_task(
                    self._lamp_power(True), name="lamp_start_shutter_open"
                )
                lamp_settle_fut = asyncio.create_task(
                    self._lamp_settle(True), name="lamp_power_settle"
                )
                shutter_start, shutter_end = await shutter_wait_fut
                self.log_event_timings(
                    self.log,
                    "shutter open time",
                    shutter_start,
                    shutter_end,
                    self.SHUTTER_OPEN_TIMEOUT,
                )

                await scriptobj.checkpoint("shutter open and lamp started")
                lamp_settle_start, lamp_settle_end = await lamp_settle_fut
                self.log_event_timings(
                    self.log,
                    "lamp warm up",
                    lamp_settle_start,
                    lamp_settle_end,
                    self.WHITELIGHT_LAMP_WARMUP_TIMEOUT,
                )
                self.log.info("lamp is warmed up, ATCalsys is powered on and ready")

            case CalsysScriptIntention.POWER_OFF:
                await self._lamp_power(False)
                await scriptobj.checkpoint(
                    "lamp commanded off and shutter commanded closed"
                )
                shutter_wait_fut = asyncio.create_task(
                    self._lamp_power(False), name="lamp stop shutter close"
                )
                lamp_settle_fut = asyncio.create_task(
                    self._lamp_settle(False), name="lamp power settle"
                )

                shutter_start, shutter_end = await shutter_wait_fut
                self.log_event_timings(
                    self.log,
                    "shutter close",
                    shutter_start,
                    shutter_end,
                    self.SHUTTER_OPEN_TIMEOUT,
                )
                await scriptobj.checkpoint("shutter closed annd lamp turned off")
                lamp_settle_start, lamp_settle_end = await lamp_settle_fut
                self.log_event_timings(
                    self.log,
                    "lamp cooldown",
                    lamp_settle_start,
                    lamp_settle_end,
                    self.WHITELIGHT_LAMP_WARMUP_TIMEOUT,
                )
                await scriptobj.checkpoint("lamp has cooled down")
                await self._chiller_power(False)
                self.log.info("chiller has been turned off, ATCalsys is powered down")

            case _:
                raise NotImplementedError(
                    "don't know how to handle this script intention"
                )

    async def validate_hardware_status_for_acquisition(self) -> Awaitable[bool]:
        """Calibration system readiness check.

        Check whether the calibration system hardware is nominally ready to perform
        calibration data acquisition runs
        """
        shutter_fut = self._sal_waitevent(self.ATWhiteLight, "shutterState")
        lamp_fut = self._sal_waitevent(self.ATWhiteLight, "lampState")

        shutter_state = await shutter_fut
        if shutter_state.commandedState != ATWhiteLight.ShutterState.OPEN:
            errmsg = f"shutter has not been commanded to open, likely a programming error. \
            Commanded state is {repr(shutter_state.commandedState)}"
            self.log.error(errmsg)
            raise RuntimeError(errmsg)

        if shutter_state.actualState != ATWhiteLight.ShutterState.OPEN:
            errmsg = f"shutter is not open, its state is reported as {repr(shutter_state.actualState)}"
            self.log.error(errmsg)
            raise RuntimeError(errmsg)

        lamp_state = await lamp_fut
        if lamp_state.basicState != ATWhiteLight.LampBasicState.ON:
            errmsg = f"lamp state is not on, its state is reported as {repr(lamp_state.basicState)}"
            self.log.error(errmsg)
            raise RuntimeError(errmsg)

        if not lamp_state.lightDetected:
            self.log.warning(
                "all states seem fine, but lamp is not reporting light detected!"
            )

    def _chiller_temp_check(self, temps) -> bool:
        """Validate the operating temperature of the calibration system chiller"""
        self.log.debug(
            f"Chiller supply temperature: {temps.supplyTemperature:0.1f} C "
            f"[set:{temps.setTemperature} deg]."
        )
        pct_dev: float = (
            temps.supplyTemperature - temps.setTemperature
        ) / temps.setTemperature

        if pct_dev <= self.CHILLER_TEMP_REL_TOL:
            self.log.info(
                f"Chiller reached target temperature, {temps.supplyTemperature:0.1f} deg "
            )
            return True
        return False

    async def _chiller_power(self, onoff: bool) -> None:
        """Start or stop the power of the calibration system chiller"""
        cmd_target = "startChiller" if onoff else "stopChiller"
        if onoff:
            chiller_setpoint_temp: float = self.CHILLER_SETPOINT_TEMP.to(un.s).value
            await self._sal_cmd(
                self.ATWhiteLight,
                "setChillerTemperature",
                temperature=chiller_setpoint_temp,
            )
        await self._sal_cmd(self.ATWhiteLight, cmd_target)

    async def _chiller_settle(self) -> Awaitable[tuple[datetime, datetime]]:
        """Wait for the calibration system chiller temperature to settle"""
        chiller_wait_timeout: float = self.CHILLER_COOLDOWN_TIMEOUT.to(un.s).value
        chiller_temp_gen = self._sal_telem_gen(self.ATWhiteLight, "chillerTemperatures")

        return self._long_wait_err_handle(
            chiller_temp_gen,
            chiller_wait_timeout,
            self._chiller_temp_check,
            "chiller temperature range settle",
        )

    async def _lamp_power(self, onoff: bool) -> Awaitable[bool]:
        """Control the shutter and the lamp power of the calibration system"""
        shutter_cmd_target = "openShutter" if onoff else "closeShutter"
        lamp_cmd_target = "turnLampOn" if onoff else "turnLampOff"
        # TODO: do we want asserts etc here to check the lamp state is correct first?
        # first, open the shutter
        shutter_task = self._sal_cmd(
            self.ATWhiteLight, shutter_cmd_target, run_immediate=False
        )

        # now start the lamp
        lamp_start_task = self._sal_cmd(
            self.ATWhiteLight,
            lamp_cmd_target,
            run_immediate=False,
            power=self.WHITELIGHT_POWER,
        )

        timeout = self.CMD_TIMEOUT.to(un.s)
        await asyncio.wait(
            [shutter_task, lamp_start_task],
            timeout=timeout,
            return_when=asyncio.FIRST_EXCEPTION,
        )

        # now run long wait for shutter
        shutter_evt_gen = self._sal_evt_gen(self.ATWhiteLight, "shutterState")
        shutter_wait_timeout: float = self.SHUTTER_OPEN_TIMEOUT.to(un.s).value

        # TODO: also probably bail out if this reports an unexpected state
        def shutter_verify(evt):
            return evt.actualState == evt.commandedState

        # TODO: this can be smarter, lamp reports time when it will be warm,
        # can use this to update scripts etc
        return self._long_wait_err_handle(
            shutter_evt_gen, shutter_wait_timeout, shutter_verify, "shutter state"
        )

    async def _lamp_settle(self, onoff: bool) -> Awaitable:
        """Wait for the lamp power to settle after a power on / off event"""
        lamp_evt_gen = self._sal_evt_gen(self.ATWhiteLight, "lampState")
        lamp_settle_timeout: float = self.WHITELIGHT_LAMP_WARMUP_TIMEOUT.to(un.s).value
        lamp_tgt_state = (
            ATWhiteLight.LampBasicState.On if onoff else ATWhiteLight.LampBasicState.Off
        )
        lamp_transition_name = "lamp warming up" if onoff else "lamp cooling down"

        def lamp_verify(evt):
            nonlocal lamp_tgt_state
            return evt.basicState == lamp_tgt_state

        return self._long_wait_err_handle(
            lamp_evt_gen, lamp_settle_timeout, lamp_verify, lamp_transition_name
        )

    async def take_calibration_data(self) -> dict[str, list[str]]:
        """Take the calibration data (i.e. the elecrometer and spectrometer data).
        NOTE: explicitly does NOT take the LATISS flats, those should be handled separately
        by the calling script """
        spec_fut = self._spectrograph_expose()
        elec_fut = self._electrometer_expose()

        spec_results, elec_results = await asyncio.gather(spec_fut, elec_fut)
        return {"spectrometer_urls": spec_results, "electrometer_urls": elec_results}

    @property
    def program_reason(self) -> str:
        return "AT_flats"

    @property
    def program_note(self) -> str:
        return "TODO"

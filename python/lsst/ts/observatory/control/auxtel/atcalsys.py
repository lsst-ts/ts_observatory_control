from typing import List, Optional, NamedTuple, TYPE_CHECKING
from ..base_calsys import BaseCalsys, HardcodeCalsysThroughput, CalibrationSequenceStepBase
from ..base_calsys import CalsysScriptIntention, _calsys_get_parameter
from lsst.ts import salobj
from lsst.ts.idl.enums import ATMonochromator, Electrometer
from lsst.ts.idl.enums import ATWhiteLight
import asyncio
import astropy.units as un
from astropy.units import Quantity
from datetime import datetime
from collections.abc import Awaitable
from dataclasses import dataclass


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
    """class which specifically handles the calibration system for auxtel"""

    _AT_SAL_COMPONENTS: List[str] = [
        "ATMonochromator",
        "FiberSpectrograph",
        "Electrometer",
        "ATWhiteLight"
    ]
    CHANGE_GRATING_TIME: Quantity[un.physical.time] = 60 << un.s

    # these below numbers should be able to be loaded from a (fairly static) config!
    GRATING_CHANGEOVER_WL: Quantity[un.physical.length] = 532.0 << un.nm
    GRATING_CHANGEOVER_BW: Quantity[un.physical.length] = 55.0 << un.nm  # WARNING! PLACEHOLDER VALUE!!!

    CHILLER_COOLDOWN_TIMEOUT: Quantity[un.physical.time] = 15 << un.min
    CHILLER_SETPOINT_TEMP: Quantity[un.physical.temperature] = 20 << un.deg_C
    CHILLER_TEMP_REL_TOL: float = 0.2

    WHITELIGHT_POWER: Quantity[un.physical.power] = 910 << un.W
    WHITELIGHT_LAMP_WARMUP_TIMEOUT: Quantity[un.physical.time] = 15 << un.min

    SHUTTER_OPEN_TIMEOUT: Quantity[un.physical.time] = 15 << un.min
    CAL_PROGRAM_NAME: str = "AT_flats"

    def __init__(self, intention: CalsysScriptIntention, **kwargs):
        super().__init__(intention, components=self._AT_SAL_COMPONENTS, **kwargs)

        #instance variables we'll set later
        self._specsposure_time: Optional[float] = None
        self._elecsposure_time: Optional[float] = None
        self._n_spec_exps: Optional[int] = None
        self._n_elec_exps: Optional[int] = None

    async def setup_for_wavelength(
            self, wavelen: float, nelec: float, spectral_res: float, **override_kwargs
    ) -> None:

        grating = _calsys_get_parameter(override_kwargs, "grating", self.calculate_grating_type,
                                        wavelen, spectral_res)
        slit_widths = _calsys_get_parameter(override_kwargs, "slit_widths", self.calculate_slit_widths,
                                            wavelen, spectral_res, grating)
        self.log.debug(
            f"setting up monochromtor with wavlength {wavelen} nm and spectral resolution {spectral_res}"
        )
        self.log.debug(f"calculated slit widthsare {slit_widths}")
        self.log.debug(f"calculated grating is {grating}")

        monoch_fut = self._sal_cmd(
            self.ATMonoChromator,
            "updateMonochromatorSetup",
            gratingType=grating,
            frontExitSlitWidth=slit_widths.FRONTEXIT,
            frontEntranceSlitWdth=slit_widths.FRONTENTRACE,
            wavelength=wavelen,
        )

        elect_fut = self._sal_cmd("electrometer", "performZeroCalib")
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
        self._specsposure_time = _calsys_get_parameter(override_kwargs, "specsposure_time",
                                                       self.spectrograph_exposure_time_for_nelectrons,
                                                       nelec)
        self._elecsposure_time = _calsys_get_parameter(override_kwargs, "elecsposure_time",
                                                       self.pd_exposure_time_for_nelectrons,
                                                       nelec)
        self._n_spec_exps = _calsys_get_parameter(override_kwargs, "n_spec_exps",
                                                  self.spectrograph_n_exps_for_nelectrons, nelec)
        self._n_elec_exps = _calsys_get_parameter(override_kwargs, "n_elec_exps",
                                                  self.pd_n_exps_for_nelectrons, nelec)
        


    def calculate_slit_width(self,wavelen: float, spectral_res: float, grating) -> Optional[ATSpectrographSlits]:
        # NOTE: this will either need to be derived by doing calculations on the Grating equation, or by loading in calibration data (which I couldn't find yet!). For now we just return the 
        raise NotImplementedError("calculation of slit widths not available yet, override in script parameters!")

    def calculate_grating_type(self, wavelen: float, spectral_res: float) -> ATMonochromator.Grating:
        # TODO: placeholder logic, in particular the exact numbers will be WRONG!
        # likely something like the below
        if spectral_res > self.GRATING_CHANGEOVER_BW:
            return ATMonochromator.Grating.MIRROR
        elif wavelen < self.GRATING_CHANGEOVER_WL:
            return ATMonochromator.Grating.BLUE
        return ATMonochromator.Grating.RED


    async def _electrometer_expose(self) -> Awaitable[list[str]]:
        assert self._n_elec_exps is not None
        assert self._elecsposure_time is not None
        out_urls: list[str] = []

        for i in range(self._n_elec_exps):
            await self._sal_cmd(self.Electrometer, "startScanDt", scanDuration=self._elecsposure_time)
            lfa_obj_fut =  await self._sal_waitevent(self.Electrometer, "largeFileObjectAvailable")
            out_urls.append(lfa_obj_fut.url)
        return out_urls

    async def _spectrograph_expose(self) -> Awaitable[list[str]]:
        assert self._n_spec_exps is not None
        assert self._specsposure_time is not None

        out_urls: list[str] = []
        for i in range(self._n_spec_exps):
            await self._sal_cmd(self.ATSpectrograph, "expose", numExposures = numExposures)
            lfa_obj_fut = await self._sal_waitevent(self.ATSpectrograph, "largeFileObjectAvailable",
                                                    run_immediate=true)

            out_urls.append(lfa_obj_fut.url)
        return out_urls

    @property
    def _electrometer_object(self):
        return self.Electrometer
    
    @property
    def script_time_estimate_s(self) -> float:
        """Property that returns the estimated time for the script to run in units of seconds
        For script time estimation purposes.
        For now just returns a default long time"""

        match(self._intention):
            case CalsysScriptIntention.POWER_ON | CalsysScriptIntention.POWER_OFF:
                #for now just use fixed values from previous script
                #start out with chiller time maximum
                total_time: Quantity[un.physical.time] = self.CHILLER_COOLDOWN_TIMEOUT
                #add on the lamp warmup timeout
                total_time += self.WHITELIGHT_LAMP_WARMUP_TIMEOUT
                total_time += self.SHUTTER_OPEN_TIMEOUT
                return total_time.to(un.s).value
            case _:
                raise NotImplementedError("don't know how to handle this script intention")

    async def power_sequence_run(self, scriptobj: salobj.BaseScript):
        match(self._intention):
            case CalsysScriptIntention.POWER_ON:
                await self._chiller_power(True)
                await scriptobj.checkpoint("Chiller started")
                chiller_start, chiller_end = await self._chiller_settle(True)
                self.log_event_timings(self.log, "chiller cooldown time", chiller_start, chiller_end,
                                       self.CHILLER_COOLDOWN_TIMEOUT)
                
                await scriptobj.checkpoint("Chiller setpoint temperature reached")
                shutter_wait_fut = asyncio.create_task(self._lamp_power(True), "lamp_start_shutter_open")
                lamp_settle_fut =  asyncio.create_task(self._lamp_settle(True), "lamp_power_settle")
                shutter_start, shutter_end = await shutter_wait_fut
                self.log_event_timings(self.log, "shutter open time", shutter_start, shutter_end,
                                       self.SHUTTER_OPEN_TIMEOUT)

                await scriptobj.checkpoint("shutter open and lamp started")
                lamp_settle_start, lamp_settle_end = await lamp_settle_fut
                self.log_event_timings(self.log, "lamp warm up", lamp_settle_start, lamp_settle_end,
                                       self.WHITELIGHT_LAMP_WARMUP_TIMEOUT)
                self.log.info("lamp is warmed up, ATCalsys is powered on and ready")

            case CalsysScriptIntention.POWER_OFF:
                await self._lamp_power(False)
                await scriptobj.checkpoint("lamp commanded off and shutter commanded closed")
                shutter_wait_fut = asyncio.create_task(self._lamp_power(False), "lamp stop shutter close")
                lamp_settle_fut = asyncio.create_task(self._lamp_settle(False), "lamp power settle")

                shutter_start, shutter_end = await shutter_wait_fut
                self.log_event_timings(self.log, "shutter close", shutter_start, shutter_end,
                                       self.SHUTTER_OPEN_TIMEOUT)
                await scriptobj.checkpoint("shutter closed annd lamp turned off")
                lamp_settle_start, lamp_settle_end = await lamp_settle_fut
                self.log_event_timings(self.log, "lamp cooldown", lamp_settle_start, lamp_settle_end,
                                       self.WHITELIGHT_LAMP_WARMUP_TIMEOUT)
                await scriptobj.checkpoint("lamp has cooled down")
                await self._chiller_power(False)
                self.log.info("chiller has been turned off, ATCalsys is powered down")

            case _:
                raise NotImplementedError("don't know how to handle this script intention")

    async def validate_hardware_status_for_acquisition(self) -> Awaitable:
        shutter_fut = self._sal_waitevent(self.ATWhiteLight, "shutterState")
        lamp_fut = self._sal_waitevent(self.ATWhiteLight, "lampState")

        shutter_state = await shutter_fut
        if shutter_state.commandedState != ATWhiteLight.ShutterState.OPEN:
            errmsg = f"shutter has not been commanded to open, likely a programming error. Commanded state is {repr(shutter_state.commandedState)}"
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
        
        if  not lamp_state.lightDetected:
            self.log.warning(f"all states seem fine, but lamp is not reporting light detected!")


    def _chiller_temp_check(self, temps) -> bool:
        self.log.debug(f"Chiller supply temperature: {temps.supplyTemperature:0.1f} C "
                       f"[set:{temps.setTemperature} deg].")
        pct_dev: float = (temps.supplyTemperature - temps.setTemperature) / temps.setTemperature

        if pct_dev <= self.CHILLER_TEMP_REL_TOL:
            self.log.info(
                f"Chiller reached target temperature, {temps.supplyTemperature:0.1f} deg ")
            return True
        return False

    async def _chiller_power(self, onoff: bool):
        cmd_target = "startChiller" if onoff else "stopChiller"
        if onoff:
            chiller_setpoint_temp: float = self.CHILLER_SETPOINT_TEMP.to(un.s).value
            await self._sal_cmd(self.ATWhiteLight, "setChillerTemperature",
                            temperature=chiller_setpoint_temp)
        await self._sal_cmd(self.ATWhiteLight, cmd_target)

    async def _chiller_settle(self) -> Awaitable[tuple[datetime,datetime]]:
        chiller_wait_timeout: float = self.CHILLER_COOLDOWN_TIMEOUT.to(un.s).value
        chiller_temp_gen = self._sal_telem_gen(self.ATWhiteLight, "chillerTemperatures")

        return await self._long_wait_err_handle(chiller_temp_gen, chiller_wait_timeout,
                                                self._chiller_temp_check, "chiller temperature range settle")

    async def _lamp_power(self, onoff:bool) -> Awaitable:
        shutter_cmd_target = "openShutter" if onoff else "closeShutter"
        lamp_cmd_target = "turnLampOn" if onoff else "turnLampOff"
        #TODO: do we want asserts etc here to check the lamp state is correct first?
        #first, open the shutter
        shutter_task = self._sal_cmd(self.ATWhiteLight, shutter_cmd_target, run_immediate=False)

        #now start the lamp
        lamp_start_task = self._sal_cmd(self.ATWhiteLight, lamp_cmd_target, run_immediate=False,
                                        power=self.WHITELIGHT_POWER)

        await asyncio.wait([shutter_task, lamp_start_task], timeout=self._cmd_timeout,
                           return_when=asyncio.FIRST_EXCEPTION)

        #now run long wait for shutter
        shutter_evt_gen = self._sal_evt_gen(self.ATWhiteLight, "shutterState")
        shutter_wait_timeout: float = self.SHUTTER_OPEN_TIMEOUT.to(un.s).value

        #TODO: also probably bail out if this reports an unexpected state
        def shutter_verify(evt):
            return evt.actualState == evt.commandedState

        #TODO: this can be smarter, lamp reports time when it will be warm,
        #can use this to update scripts etc
        return self._long_wait_err_handle(shutter_evt_gen, shutter_wait_timeout,
                                         shutter_verify, "shutter state")


    async def _lamp_settle(self, onoff: bool) -> Awaitable:
        lamp_evt_gen = self._sal_evt_gen(self.ATWhiteLight, "lampState")
        lamp_settle_timeout: float = self.WHITELIGHT_LAMP_WARMUP_TIMEOUT.to(un.s).value
        lamp_tgt_state = ATWhiteLight.LampBasicState.On if onoff else ATWhiteLight.LampBasicState.Off
        lamp_transition_name = "lamp warming up" if onoff else "lamp cooling down"
        
        def lamp_verify(evt):
            nonlocal lamp_tgt_state
            return evt.basicState == lamp_tgt_state

        return self._long_wait_err_handle(lamp_evt_gen, lamp_settle_timeout,
                                          lamp_verify, lamp_transition_name)


    async def take_calibration_data(self) -> Awaitable[dict[str, list[str]]]:
        spec_fut = self._spectrograph_expose()
        elec_fut = self._electrometer_expose()

        spec_results,  elec_results = await asyncio.gather(spec_fut, elec_fut)
        return {"spectrometer_urls" : spec_results,
                "electrometer_urls" : elec_results}


    @property
    def program_reason(self) -> str:
        return "AT_flats"

    @property
    def prgoram_note(self) -> str:
        return "TODO"
    
    

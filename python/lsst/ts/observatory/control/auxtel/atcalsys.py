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

__all__ = ["ATCalsys", "ATCalsysUsages"]

import asyncio
import logging
import time
import typing
from dataclasses import dataclass

import numpy as np
from lsst.ts import salobj, utils
from lsst.ts.xml.enums.ATMonochromator import Grating

from ..base_calsys import BaseCalsys
from ..remote_group import Usages
from ..utils import CalibrationType
from . import LATISS


class ATCalsysUsages(Usages):
    """ATCalsys usages definition.

    Notes
    -----

    Additional usages definition:

    * Setup: Enable ATWhitelight and perform warmup. Enable
             ATMonochromator, Electrometer, and FiberSpectrographs.
    * Configure: Adjust ATWhitelight and ATMonochromator for type of flat.
    * TakeFlat: Take flatfield image with LATISS, Electrometer and FiberSpec
    * DryTest: Disable CSCs and unit tests
    """

    Setup = 1 << 3
    Configure = 1 << 4
    TakeFlat = 1 << 5

    def __iter__(self) -> typing.Iterator[int]:
        return iter(
            [
                self.All,
                self.StateTransition,
                self.MonitorState,
                self.MonitorHeartBeat,
                self.Setup,
                self.Configure,
                self.TakeFlat,
                self.DryTest,
            ]
        )


@dataclass
class ATCalsysExposure:
    """Store Exposure information for ATCalsys.

    Attributes
    ----------
    wavelength : float
        Wavelength of the calibration exposure, in nm.
    camera : float
        Camera exposure time, in sec.
    fiberspectrograph : float | None
        Fiber spectrograph exposure time, in sec.
        If None, skip fiber spectrograph acquisition.
    electrometer : float | None
        Electrometer exposure time, in sec.
        If None, skip electrometer acquisition.
    """

    wavelength: float
    camera: float
    fiberspectrograph: float | None
    electrometer: float | None


class ATCalsys(BaseCalsys):
    """LSST Auxiliary Telescope Calibration System.

    ATCalsys encapsulates core functionality from the following CSCs:
    ATWhiteLight, ATMonochromoter, Fiberspectrograph, Electrometer.

    Parameters
    ----------
    domain : `lsst.ts.salobj.Domain`
        Domain for remotes. If `None` create a domain.
    log : `logging.Logger`
        Optional logging class to be used for logging operations. If `None`,
        creates a new logger. Useful to use in salobj.BaseScript and allow
        logging in the class use the script logging.
    intended_usage: `int`
        Optional integer that maps to a list of intended operations. This is
        used to limit the resources allocated by the class by gathering some
        knowledge about the usage intention. By default allocates all
        resources.
    latiss: LATISS
    """

    def __init__(
        self,
        domain: typing.Optional[salobj.Domain] = None,
        log: typing.Optional[logging.Logger] = None,
        intended_usage: typing.Optional[int] = None,
        latiss: typing.Optional[LATISS] = None,
    ) -> None:

        self.electrometer_index = 201
        self.fiberspectrograph_index = 3

        super().__init__(
            components=[
                "ATMonochromator",
                "ATWhiteLight",
                f"FiberSpectrograph:{self.fiberspectrograph_index}",
                f"Electrometer:{self.electrometer_index}",
            ],
            domain=domain,
            log=log,
            intended_usage=intended_usage,
        )

        self.latiss = latiss

        self.whitelight_startup_power = 1000

        self.chiller_temp_tolerance_relative = 0.2
        self.chiller_temperature = 20

        self.delay = 1

    async def change_wavelength(self, wavelength: float) -> None:
        """Change the ATMonochromator wavelength setting"""

        await self.rem.atmonochromator.cmd_changeWavelength.set_start(
            wavelength=wavelength, timeout=self.long_long_timeout
        )

    async def is_ready_for_flats(self) -> bool:
        """Add doctring"""
        # TODO (DM-44310): Implement method to check that the
        # system is ready for flats.
        return True

    async def setup_calsys(self, sequence_name: str) -> None:
        """Turn on the Chiller and the ATWhiteLight and wait for the
        warmup to complete. This is independent of Calibration Type.
        """
        await self.start_chiller()
        await self.wait_for_chiller_temp_within_tolerance()
        await self.switch_lamp_on()
        await self.wait_for_lamp_to_warm_up()

    async def prepare_for_flat(self, config_name: str) -> None:
        """Configure the ATMonochromator according to the flat parameters

        Parameters
        ----------
        config_name : `str`
            name of the type of configuration you will run, which is saved
            in the configuration.yaml files

        Raises
        ------
        RuntimeError:

        """
        config_data = self.get_calibration_configuration(config_name)

        wavelength = (
            float(config_data["wavelength"])
            - float(config_data.get("wavelength_width", 0.0)) / 2.0
        )

        grating_type = getattr(Grating, config_data["monochromator_grating"])
        task_setup_monochromator = (
            self.rem.atmonochromator.cmd_updateMonochromatorSetup.set_start(
                wavelength=wavelength,
                gratingType=grating_type.value,
                fontExitSlitWidth=config_data["exit_slit"],
                fontEntranceSlitWidth=config_data["entrance_slit"],
                timeout=self.long_long_timeout,
            )
        )

        if self.latiss is None and config_data["use_camera"]:
            raise RuntimeError(
                f"LATISS is not defined but {config_name} requires it. "
                "Make sure you are instantiating LATISS and passing it to ATCalsys."
            )
        task_setup_latiss = (
            self.latiss.setup_instrument(
                filter=config_data["atspec_filter"],
                grating=config_data["atspec_grating"],
            )
            if self.latiss is not None and config_data["use_camera"]
            else utils.make_done_future()
        )

        task_setup_electrometer = self.setup_electrometers(
            mode=str(config_data["electrometer_mode"]),
            range=float(config_data["electrometer_range"]),
            integration_time=float(config_data["electrometer_integration_time"]),
        )

        await asyncio.gather(
            task_setup_monochromator,
            task_setup_latiss,
            task_setup_electrometer,
        )

    async def calculate_optimized_exposure_times(
        self, wavelengths: list, config_data: dict
    ) -> list[ATCalsysExposure]:
        """Calculates the exposure times for the fiber spectrograph and
        the electrometer given camera exposure times and other
        relevant configuration paramaters.

        This includes wavelength dependent information for the fiber
        spectrograph and also includes the logic for the size of
        the electrometer buffer.

        Parameters
        ----------
        wavelengths : `list`
            List of all wavelengths for this exposure list
        config_data : `dict`
            All information from configuration file

        Returns
        -------
        exposure_list : `list`[ATCalsysExposure]
            List of exposure information saved in the dataclass
            ATCalsysExposure. Each exposure includes wavelength
            and camera, fiberspectrograph and electrometer exposure times.

        """

        exposures: list[ATCalsysExposure] = []
        for wavelength in wavelengths:
            electrometer_exptimes = await self._calculate_electrometer_exposure_times(
                exptimes=config_data["exposure_times"],
                electrometer_integration_time=config_data[
                    "electrometer_integration_time"
                ],
                use_electrometer=config_data["use_electrometer"],
            )
            fiberspectrograph_exptimes = (
                await self._calculate_fiberspectrograph_exposure_times(
                    exptimes=config_data["exposure_times"],
                    entrance_slit=config_data["entrance_slit"],
                    exit_slit=config_data["exit_slit"],
                    use_fiberspectrograph=config_data["use_fiberspectrograph"],
                )
            )

            for i, exptime in enumerate(config_data["exposure_times"]):
                exposures.append(
                    ATCalsysExposure(
                        wavelength=wavelength,
                        camera=exptime,
                        electrometer=electrometer_exptimes[i],
                        fiberspectrograph=fiberspectrograph_exptimes[i],
                    )
                )

        return exposures

    async def _calculate_electrometer_exposure_times(
        self,
        exptimes: list,
        electrometer_integration_time: float,
        use_electrometer: bool,
    ) -> list[float | None]:
        """Calculates the optimal exposure time for the electrometer

        Parameters
        ----------
        exptime : `list`
            List of Camera exposure times
        use_electrometer : `bool`
            Identifies if the electrometer will be used in the exposure

        Returns
        -------
        `list`[`float` | `None`]
            Exposure times for the electrometer
        """
        electrometer_buffer_size = 16667
        electrometer_integration_overhead = 0.00254
        electrometer_time_separation_vs_integration = 3.07

        electrometer_exptimes: list[float | None] = []
        for exptime in exptimes:
            if use_electrometer:
                time_sep = (
                    electrometer_integration_time
                    * electrometer_time_separation_vs_integration
                ) + electrometer_integration_overhead
                max_exp_time = electrometer_buffer_size * time_sep
                if exptime > max_exp_time:
                    electrometer_exptimes.append(max_exp_time)
                    self.log.info(
                        f"Electrometer exposure time reduced to {max_exp_time}"
                    )
                else:
                    electrometer_exptimes.append(exptime)
            else:
                electrometer_exptimes.append(None)
        return electrometer_exptimes

    async def _calculate_fiberspectrograph_exposure_times(
        self,
        exptimes: list,
        entrance_slit: float,
        exit_slit: float,
        use_fiberspectrograph: bool,
    ) -> list[float | None]:
        """Calculates the optimal exposure time for the electrometer

        Parameters
        ----------
        exptime : `list`
            List of Camera exposure times
        entrance_slit : `float`
        exit_slit : `float`
        use_fiberspectrograph : `bool`
            Identifies if the fiberspectrograph will be used in the exposure

        Returns
        -------
        `list`[`float` | `None`]
            Exposure times for the fiberspectrograph
        """
        fiberspectrograph_exptimes: list[float | None] = []
        for exptime in exptimes:
            if use_fiberspectrograph:
                base_exptime = 1  # sec
                entry_slit_multiplier = 6 / (entrance_slit + 1)
                exit_slit_multiplier = 6 / (exit_slit + 1)
                # TODO (DM-45235): Improve these multipliers with testing
                # Also, include some wavelength dependence based on testing
                fiberspectrograph_exptime = (
                    base_exptime * entry_slit_multiplier * exit_slit_multiplier
                )
                fiberspectrograph_exptimes.append(fiberspectrograph_exptime)
            else:
                fiberspectrograph_exptimes.append(None)
        return fiberspectrograph_exptimes

    async def run_calibration_sequence(
        self, sequence_name: str, exposure_metadata: dict
    ) -> dict:
        """Perform full calibration sequence, taking flats with the
        camera and all ancillary instruments.

        Parameters
        ----------
        sequence_name : `str`
            Name of the calibration sequence to execute.

        Returns
        -------
        calibration_summary : `dict`
            Dictionary with summary information about the sequence.
        """
        calibration_summary: dict = dict(
            steps=[],
            sequence_name=sequence_name,
        )

        config_data = self.get_calibration_configuration(sequence_name)

        calibration_type = getattr(CalibrationType, str(config_data["calib_type"]))
        if calibration_type == CalibrationType.WhiteLight:
            calibration_wavelengths = np.array([float(config_data["wavelength"])])
        else:
            wavelength = float(config_data["wavelength"])
            wavelength_width = float(config_data["wavelength_width"])
            wavelength_resolution = float(config_data["wavelength_resolution"])
            wavelength_start = wavelength - wavelength_width / 2.0
            wavelength_end = wavelength + wavelength_width / 2.0

            calibration_wavelengths = np.arange(
                wavelength_start,
                wavelength_end + wavelength_resolution,
                wavelength_resolution,
            )

        exposure_table = await self.calculate_optimized_exposure_times(
            wavelengths=calibration_wavelengths, config_data=config_data
        )

        for exposure in exposure_table:
            self.log.debug(
                f"Performing {calibration_type.name} calibration with {exposure.wavelength=}."
            )
            await self.change_wavelength(wavelength=exposure.wavelength)

            latiss_exposure_info: dict = dict()
            self.log.debug("Taking data sequence.")
            exposure_info = await self._take_data(
                latiss_exptime=exposure.camera,
                latiss_filter=str(config_data["atspec_filter"]),
                latiss_grating=str(config_data["atspec_grating"]),
                exposure_metadata=exposure_metadata,
                fiber_spectrum_exposure_time=exposure.fiberspectrograph,
                electrometer_exposure_time=exposure.electrometer,
                sequence_name=sequence_name,
            )
            latiss_exposure_info.update(exposure_info)

            if calibration_type == CalibrationType.Mono:
                self.log.debug(
                    "Taking data sequence without filter for monochromatic set."
                )
                exposure_info = await self._take_data(
                    latiss_exptime=exposure.camera,
                    latiss_filter="empty_1",
                    latiss_grating=str(config_data["atspec_grating"]),
                    exposure_metadata=exposure_metadata,
                    fiber_spectrum_exposure_time=exposure.fiberspectrograph,
                    electrometer_exposure_time=exposure.electrometer,
                    sequence_name=sequence_name,
                )
                latiss_exposure_info.update(exposure_info)

            step = dict(
                wavelength=exposure.wavelength,
                latiss_exposure_info=latiss_exposure_info,
            )

            calibration_summary["steps"].append(step)
        return calibration_summary

    async def _take_data(
        self,
        latiss_exptime: float,
        latiss_filter: str,
        latiss_grating: str,
        exposure_metadata: dict,
        fiber_spectrum_exposure_time: float | None,
        electrometer_exposure_time: float | None,
        sequence_name: str,
    ) -> dict:

        assert self.latiss is not None

        latiss_exposure_task = self.latiss.take_flats(
            latiss_exptime,
            nflats=1,
            filter=latiss_filter,
            grating=latiss_grating,
            **exposure_metadata,
        )
        exposures_done: asyncio.Future = asyncio.Future()

        fiber_spectrum_exposure_coroutine = self.take_fiber_spectrum(
            exposure_time=fiber_spectrum_exposure_time,
            exposures_done=exposures_done,
        )
        electrometer_exposure_coroutine = self.take_electrometer_scan(
            exposure_time=electrometer_exposure_time,
            exposures_done=exposures_done,
            sequence_name=sequence_name,
        )
        try:
            fiber_spectrum_exposure_task = asyncio.create_task(
                fiber_spectrum_exposure_coroutine
            )
            electrometer_exposure_task = asyncio.create_task(
                electrometer_exposure_coroutine
            )

            latiss_exposure_id = await latiss_exposure_task
        finally:
            exposures_done.set_result(True)
            fiber_spectrum_exposure_result, electrometer_exposure_result = (
                await asyncio.gather(
                    fiber_spectrum_exposure_task, electrometer_exposure_task
                )
            )

        return {
            latiss_exposure_id[0]: dict(
                fiber_spectrum_exposure_result=fiber_spectrum_exposure_result,
                electrometer_exposure_result=electrometer_exposure_result,
            )
        }

    async def take_electrometer_scan(
        self,
        exposure_time: float | None,
        exposures_done: asyncio.Future,
        sequence_name: str,
    ) -> list[str]:
        """Perform an electrometer scan for the specified duration.

        Parameters
        ----------
        exposure_time : `float` | None
            Exposure time for the fiber spectrum (seconds).
        exposures_done : `asyncio.Future`
            A future indicating when the camera exposures where complete.
        sequence_name : `str`
            The name of the sequence this electrometer scan is part of.
            This is used to reconfigure the electrometer in case it goes
            to fault during the sequence.
            DM-44634: Remove this work around.
        Returns
        -------
        electrometer_exposures : `list`[`str`]
            List of large file urls.
        """

        self.electrometer.evt_largeFileObjectAvailable.flush()

        electrometer_exposures = list()

        if exposure_time is not None:
            try:
                await self.electrometer.cmd_startScanDt.set_start(
                    scanDuration=exposure_time,
                    timeout=exposure_time + self.long_timeout,
                )
            except salobj.AckTimeoutError:
                self.log.exception("Timed out waiting for the command ack. Continuing.")

            # Make sure that a new lfo was created
            try:
                lfo = await self.electrometer.evt_largeFileObjectAvailable.next(
                    timeout=self.long_timeout, flush=False
                )
                electrometer_exposures.append(lfo.url)
            except asyncio.TimeoutError:
                # TODO (DM-44634): Remove this work around to electrometer
                # going to FAULT when issue is resolved.
                self.log.warning(
                    "Time out waiting for electrometer data. Making sure electrometer "
                    "is in enabled state, reconfiguring it and continuing."
                )
                await salobj.set_summary_state(self.electrometer, salobj.State.ENABLED)
                config_data = self.get_calibration_configuration(sequence_name)
                await self.setup_electrometers(
                    mode=str(config_data["electrometer_mode"]),
                    range=float(config_data["electrometer_range"]),
                    integration_time=float(
                        config_data["electrometer_integration_time"]
                    ),
                )
        return electrometer_exposures

    async def take_fiber_spectrum(
        self,
        exposure_time: float | None,
        exposures_done: asyncio.Future,
    ) -> list[str]:
        """Take exposures with the fiber spectrograph until
        the exposures with the camera are complete.

        This method will continue to take data with the fiber
        spectrograph until the exposures_done future is done.

        Parameters
        ----------
        exposure_time : `float` | None
            Exposure time for the fiber spectrum (seconds).
        exposures_done : `asyncio.Future`
            A future indicating when the camera exposures where complete.

        Returns
        -------
        fiber_spectrum_exposures : `list`[`str`]
            List of large file urls.
        """
        self.fiberspectrograph.evt_largeFileObjectAvailable.flush()

        fiber_spectrum_exposures = []

        if exposure_time is not None:
            try:
                await self.fiberspectrograph.cmd_expose.set_start(
                    duration=exposure_time,
                    numExposures=1,
                    timeout=exposure_time + self.long_timeout,
                )
            except salobj.AckTimeoutError:
                self.log.exception("Timed out waiting for the command ack. Continuing.")

            lfo = await self.fiberspectrograph.evt_largeFileObjectAvailable.next(
                timeout=self.long_timeout, flush=False
            )
            fiber_spectrum_exposures.append(lfo.url)
        return fiber_spectrum_exposures

    async def start_chiller(self) -> None:
        """Starts chiller to run at self.chiller_temperature"""

        await self.rem.atwhitelight.cmd_setChillerTemperature.set_start(
            temperature=self.chiller_temperature, timeout=self.long_timeout
        )
        await self.rem.atwhitelight.cmd_startChiller.set_start(
            timeout=self.long_timeout
        )

    async def switch_lamp_on(self) -> None:
        """Switches on the white light source with an output
        power of self.whitelight_power W
        """
        self.rem.atwhitelight.evt_lampState.flush()

        await self.rem.atwhitelight.cmd_turnLampOn.set_start(
            power=self.whitelight_startup_power, timeout=self.long_long_timeout * 8
        )

    async def wait_for_chiller_temp_within_tolerance(self) -> None:
        """Checks if chiller reaches set self.chiller_temperature within
        set self.chiller_temp_tolerance_relative in
        less than self.timeout_chiller_cool_down s.

        Raises
        ------
        TimeOutError:
            If the chiller doesn't reach self.chiller_temperature
            within tolerance in self.timeout_chiller_cool_down s.

        Note
        ----
        Taken from power_on_atcalsys.py
        PAF: I think this can be improved.
        """
        start_chill_time = time.time()
        while time.time() - start_chill_time < self.long_long_timeout * 8:
            chiller_temps = await self.rem.atwhitelight.tel_chillerTemperatures.next(
                flush=True, timeout=self.long_timeout
            )
            tel_chiller_temp = chiller_temps.supplyTemperature
            self.log.debug(
                f"Chiller supply temperature: {tel_chiller_temp:0.1f} deg "
                f"[set:{chiller_temps.setTemperature} deg]."
            )
            if (
                abs(chiller_temps.setTemperature - tel_chiller_temp)
                / chiller_temps.setTemperature
                <= self.chiller_temp_tolerance_relative
            ):
                chill_time = time.time() - start_chill_time
                self.log.info(
                    f"Chiller reached target temperature, {tel_chiller_temp:0.1f} deg "
                    f"within tolerance, in {chill_time:0.1f} s."
                )
                break
        else:
            raise TimeoutError(
                f"Timeout waiting after {self.long_long_timeout * 8} s "
                f"for the chiller to chill to {chiller_temps.setTemperature} deg. "
                f"Stayed at {tel_chiller_temp:0.1f} deg."
            )

    async def wait_for_lamp_to_warm_up(self) -> None:
        """Confirms the white light source has warmed up and is on.

        Raises:
        ------
        TimeOutError:
            If the lamp fails to turn on after self.timeout_lamp_warm_up

        Note
        ----
        Taken from power_on_atcalsys.py
        PAF: I think this can be improved.
        """
        lamp_state = await self.rem.atwhitelight.evt_lampState.aget(
            timeout=self.long_long_timeout, flush=True
        )
        self.log.info(
            f"Lamp state: {self.rem.atwhitelight.LampBasicState(lamp_state.basicState)!r}."
        )

        while lamp_state.basicState != self.rem.atwhitelight.LampBasicState.ON:
            try:
                lamp_state = await self.rem.atwhitelight.evt_lampState.next(
                    flush=False, timeout=self.long_long_timeout * 8
                )
                self.log.info(
                    f"Lamp state: {self.rem.atwhitelight.LampBasicState(lamp_state.basicState)!r}."
                )
            except asyncio.TimeoutError:
                raise RuntimeError(
                    f"White Light Lamp failed to turn on after {self.long_long_timeout * 8} s."
                )

    @property
    def electrometer(self) -> salobj.Remote:
        return getattr(self.rem, f"electrometer_{self.electrometer_index}")

    @property
    def fiberspectrograph(self) -> salobj.Remote:
        return getattr(self.rem, f"fiberspectrograph_{self.fiberspectrograph_index}")

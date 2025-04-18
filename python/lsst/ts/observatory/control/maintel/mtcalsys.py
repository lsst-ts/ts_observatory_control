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

__all__ = ["MTCalsys", "MTCalsysUsages"]

import asyncio
import logging
import typing
from dataclasses import dataclass

import numpy as np
from lsst.ts import salobj, utils

# TODO: (DM-46168) Revert workaround for TunableLaser XML changes
from lsst.ts.observatory.control.utils.enums import LaserOpticalConfiguration
from lsst.ts.xml.enums.TunableLaser import LaserDetailedState

from ..base_calsys import BaseCalsys
from ..remote_group import Usages
from ..utils import CalibrationType
from . import ComCam


class MTCalsysUsages(Usages):
    """MTCalsys usages definition.

    Notes
    -----

    Additional usages definition:

    * Setup: Turn on TunableLaser and adjust the projector output with
            linear stage select. Enable other CSCs: LEDProjector, Linear
            Stages, Electrometers and FiberSpectrographs.
    * Configure: Adjust LEDProjector or TunableLaser depending on filter.
    * TakeFlat: Take flatfield image with MTCamera (ComCam or LSSTCam),
                Electrometer and FiberSpec
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
class MTCalsysExposure:
    """Store Exposure information for MTCalsys.

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
    fiberspectrograph_red: float | None
    fiberspectrograph_blue: float | None
    electrometer: float | None


class MTCalsys(BaseCalsys):
    """LSST Simonyi Telescope Calibration System.

    MTCalsys encapsulates core functionality from the following CSCs:
    TunableLaser, LEDProjector, LinearStage, Fiberspectrograph, Electrometer.

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
    mtcamera: ComCam or LSSTCam
    """

    def __init__(
        self,
        domain: typing.Optional[salobj.Domain] = None,
        log: typing.Optional[logging.Logger] = None,
        intended_usage: typing.Optional[int] = None,
        mtcamera: typing.Optional[ComCam] = None,
    ) -> None:

        self.electrometer_projector_index = 103
        self.fiberspectrograph_blue_index = 101
        self.fiberspectrograph_red_index = 102
        self.linearstage_led_select_index = 102
        self.linearstage_led_focus_index = 104
        self.linearstage_laser_focus_index = 101
        self.linearstage_select_index = 103

        super().__init__(
            components=[
                "TunableLaser",
                "LEDProjector",
                f"FiberSpectrograph:{self.fiberspectrograph_blue_index}",
                f"FiberSpectrograph:{self.fiberspectrograph_red_index}",
                f"Electrometer:{self.electrometer_projector_index}",
                f"LinearStage:{self.linearstage_led_select_index}",
                f"LinearStage:{self.linearstage_led_focus_index}",
                f"LinearStage:{self.linearstage_laser_focus_index}",
                f"LinearStage:{self.linearstage_select_index}",
            ],
            domain=domain,
            log=log,
            intended_usage=intended_usage,
        )

        self.mtcamera = mtcamera
        self.linearstage_projector_locations = {"led": 9.96, "laser": 79.96}
        self.led_rest_position = 90.0  # mm
        self.linearstage_projector_pos_tolerance = 0.2
        self.led_focus_axis = 0
        self.linearstage_axis = 0

        self.laser_enclosure_temp = 20.0  # C
        self.laser_warmup = 20.0  # sec
        self.stage_homing_timeout = 60.0  # sec

        self.exptime_dict: dict[str, float] = dict(
            camera=0.0,
            electrometer=0.0,
            fiberspectrograph=0.0,
        )

    async def is_ready_for_flats(self) -> bool:
        """Designates if the calibration hardware is in a state
        to take flats.
        """
        # TODO (DM-44310): Implement method to check that the
        # system is ready for flats.
        return True

    async def setup_calsys(self, sequence_name: str) -> None:
        """Setup the calibration system.

        If monochromatic flats, check that laser can be enabled,
        check temperature, and turn on laser to warm up.
        Move linearstage_select to correct location for
        Mono or Whitelight flats. If Monochromatic flats
        make sure that LED stage is in the correct place.

        Parameters
        ----------
        sequence_name : `str`
            name of the type of configuration you will run, which is saved
            in the configuration.yaml files

        """
        config_data = self.get_calibration_configuration(sequence_name)

        calibration_type = getattr(CalibrationType, str(config_data["calib_type"]))

        # Home all linear stages.
        await self.linearstage_projector_select.cmd_getHome.set_start(
            axis=self.linearstage_axis, timeout=self.stage_homing_timeout
        )
        await self.linearstage_led_select.cmd_getHome.set_start(
            axis=self.linearstage_axis, timeout=self.long_timeout
        )
        led_focus_home = self.linearstage_led_focus.cmd_getHome.set_start(
            axis=self.linearstage_axis, timeout=self.stage_homing_timeout
        )
        laser_focus_home = self.linearstage_laser_focus.cmd_getHome.set_start(
            axis=self.linearstage_axis, timeout=self.stage_homing_timeout
        )

        await asyncio.gather(
            led_focus_home,
            laser_focus_home,
        )

        # Move LED Select stage to a safe position
        self.log.debug("Moving LED select stage to safe position.")
        await self.linearstage_led_select.cmd_moveAbsolute.set_start(
            distance=self.led_rest_position,
            axis=self.linearstage_axis,
            timeout=self.long_timeout,
        )

        if calibration_type == CalibrationType.WhiteLight:
            self.log.debug("Moving vertical projector selection stage to LED position")
            await self.linearstage_projector_select.cmd_moveAbsolute.set_start(
                distance=self.linearstage_projector_locations["led"],
                axis=self.linearstage_axis,
                timeout=self.long_timeout,
            )
            await self.rem.ledprojector.cmd_adjustAllDACPower.set_start(
                dacValue=config_data.get("dac_value")
            )
        else:
            self.log.debug(
                "Moving vertical projector selection stage to Laser position"
            )
            await self.linearstage_projector_select.cmd_moveAbsolute.set_start(
                distance=self.linearstage_projector_locations["laser"],
                axis=self.linearstage_axis,
                timeout=self.long_timeout,
            )
            await self.setup_laser(
                config_data["laser_mode"],
                config_data["wavelength"],
                config_data["optical_configuration"],
            )
            await self.laser_start_propagate()

    async def park_projector(self) -> None:
        """Put the LEDProjector into a safe state and turn off all LEDs.
        This will not turn off the TunableLaser
        """
        # Move vertical and LED Select stages to a safe position (not Home)
        await self.linearstage_led_select.cmd_moveAbsolute.set_start(
            distance=self.led_rest_position,
            axis=self.linearstage_axis,
            timeout=self.long_timeout,
        )
        await self.linearstage_projector_select.cmd_moveAbsolute.set_start(
            distance=self.linearstage_projector_locations["led"],
            axis=self.linearstage_axis,
            timeout=self.long_timeout,
        )
        # Home the focus stages
        led_focus_home = self.linearstage_led_focus.cmd_getHome.set_start(
            axis=self.linearstage_axis, timeout=self.stage_homing_timeout
        )
        laser_focus_home = self.linearstage_laser_focus.cmd_getHome.set_start(
            axis=self.linearstage_axis, timeout=self.stage_homing_timeout
        )
        await asyncio.gather(
            led_focus_home,
            laser_focus_home,
        )
        # Turn off the LEDs
        # TO-DO (DM-50206): Swap switchON/OFF
        await self.rem.ledprojector.cmd_switchAllOn.start(
            timeout=self.long_timeout,
        )

    def calculate_laser_focus_location(self, wavelength: float = 500.0) -> float:
        """Calculates the location of the linear stage that provides the focus
        for the laser projector. This location is dependent on the
        wavelength of the laser.

        Parameters
        ----------
        wavelength : `float`
            wavelength of the laser projector in nm
            Default 500.0

        Returns
        ------
        location of the linear stage for the laser projector focus in mm

        """
        # TODO (DM-44772): implement the actual function
        return 10.0

    async def change_laser_wavelength(
        self,
        wavelength: float,
        use_projector: bool = True,
    ) -> None:
        """Change the TunableLaser wavelength setting

        Parameters
        ----------
        wavelength : `float`
            wavelength of the laser in nm
        use_projector : `bool`
            identifies if you are using the projector while
            changing the wavelength.
            Default True
        """
        task_wavelength = self.rem.tunablelaser.cmd_changeWavelength.set_start(
            wavelength=wavelength, timeout=self.long_long_timeout
        )

        if use_projector:
            task_focus = self.linearstage_laser_focus.cmd_moveAbsolute.set_start(
                distance=self.calculate_laser_focus_location(wavelength),
                axis=self.linearstage_axis,
                timeout=self.long_long_timeout,
            )
            await asyncio.gather(task_wavelength, task_focus)

        else:
            await task_wavelength

    async def change_laser_optical_configuration(
        self, optical_configuration: LaserOpticalConfiguration
    ) -> None:
        """Change the output of the laser.

        Parameters
        ----------
        optical_configuration : LaserOpticalConfiguration
        """
        assert optical_configuration in list(LaserOpticalConfiguration)

        current_configuration = (
            await self.rem.tunablelaser.evt_opticalConfiguration.aget()
        )
        if current_configuration.configuration != optical_configuration:
            self.log.debug(
                f"Changing optical configuration from {current_configuration} to {optical_configuration}"
            )
            await self.rem.tunablelaser.cmd_setOpticalConfiguration.set_start(
                configuration=optical_configuration, timeout=self.long_timeout
            )

        else:
            self.log.debug("Laser Optical Configuration already in place.")

    async def setup_laser(
        self,
        mode: LaserDetailedState,
        wavelength: float,
        optical_configuration: LaserOpticalConfiguration = LaserOpticalConfiguration.SCU,
        use_projector: bool = True,
    ) -> None:
        """Perform all steps for preparing the laser for monochromatic flats.
        This includes confirming that the thermal system is
        turned on and set at the right temperature. It also checks
        the interlockState to confirm it's ready to propagate.

        Parameters
        ----------
        mode : LaserDetailedState
            Mode of the TunableLaser
            Options: CONTINUOUS, BURST
        wavelength : `float`
            Wavelength fo the laser in nm
        optical_configuration : LaserOpticalConfiguration
            Output of laser
            Default LaserOpticalConfiguration.SCU
        use_projector : `bool`
            identifies if you are using the projector while
            changing the wavelength
            Default True
        """
        # TO-DO: DM-45693 implement thermal system checks

        if mode in {
            LaserDetailedState.NONPROPAGATING_CONTINUOUS_MODE,
            LaserDetailedState.PROPAGATING_CONTINUOUS_MODE,
        }:
            await self.rem.tunablelaser.cmd_setContinuousMode.start(
                timeout=self.long_timeout
            )
        elif mode in {
            LaserDetailedState.NONPROPAGATING_BURST_MODE,
            LaserDetailedState.PROPAGATING_BURST_MODE,
        }:
            await self.rem.tunablelaser.cmd_setBurstMode.start(
                timeout=self.long_timeout
            )
        else:
            raise RuntimeError(
                f"{mode} not an acceptable LaserDetailedState [CONTINOUS, BURST, TRIGGER]"
            )

        await self.change_laser_optical_configuration(optical_configuration)
        await self.change_laser_wavelength(wavelength, use_projector)

    async def get_projector_setup(
        self,
    ) -> tuple[str, float, float, float, str]:
        """Get configuration of flatfield projector largely for
        debugging purposes

        Return
        ------
            tuple:
                projector_location: whether or not the vertical stage is
                aligned with led or laser output or neither
                led_location: which LED system is aligned with teh optical path
                led_focus: value of the led focus stage
                laser_focus: value of the laser focus stage
                led_state: shows whether LEDs are ON/OFF
        """

        select_location = await self.linearstage_projector_select.tel_position.next(
            flush=True
        )
        self.log.debug(select_location)
        led_location = await self.linearstage_led_select.tel_position.next(flush=True)
        led_focus = await self.linearstage_led_focus.tel_position.next(flush=True)
        laser_focus = await self.linearstage_laser_focus.tel_position.next(flush=True)
        led_state = await self.rem.ledprojector.evt_ledState.aget(
            timeout=self.fast_timeout
        )

        for location, value in self.linearstage_projector_locations.items():
            if (
                abs(float(select_location.position) - float(value))
                < self.linearstage_projector_pos_tolerance
            ):
                projector_location = location
            else:
                projector_location = "misaligned"

        self.log.info(
            f"Projector Location is {projector_location}, \n"
            f"LED Location stage pos @: {led_location.position}, \n"
            f"LED Focus stage pos @: {led_focus.position}, \n"
            f"Laser Focus stage pos @: {laser_focus.position}, \n"
            f"LED State stage pos @: {led_state}"
        )

        return (
            projector_location,
            float(led_location.position),
            float(led_focus.position),
            float(laser_focus.position),
            str(led_state),
        )

    async def get_laser_parameters(self) -> tuple:
        """Get laser configuration

        Returns
        -------
            list : configuration details

        """

        return await asyncio.gather(
            self.rem.tunablelaser.evt_opticalConfiguration.aget(
                timeout=self.long_timeout
            ),
            self.rem.tunablelaser.evt_wavelengthChanged.aget(timeout=self.long_timeout),
            self.rem.tunablelaser.evt_interlockState.aget(timeout=self.long_timeout),
            self.rem.tunablelaser.evt_burstModeSet.aget(timeout=self.long_timeout),
            self.rem.tunablelaser.evt_continuousModeSet.aget(timeout=self.long_timeout),
        )

    async def laser_start_propagate(self) -> None:
        """Start the propagation of the Tunable Laser"""

        laser_state = await self.rem.tunablelaser.evt_detailedState.next(
            flush=True, timeout=self.long_timeout
        )
        self.log.debug(f"HERE: {laser_state.DetailedState}")

        if laser_state.DetailedState not in {
            LaserDetailedState.PROPAGATING_CONTINUOUS_MODE,
            LaserDetailedState.PROPAGATING_BURST_MODE,
        }:
            try:
                await self.rem.tunablelaser.cmd_startPropagateLaser.start(
                    timeout=self.laser_warmup
                )
                laser_state = await self.rem.tunablelaser.evt_detailedState.next(
                    flush=True, timeout=self.long_timeout
                )
                self.log.info(f"Laser state: {laser_state.DetailedState}")
            except asyncio.TimeoutError:
                raise RuntimeError(
                    "Tunable Laser did not start propagating when commanded"
                )

    async def laser_stop_propagate(self) -> None:
        """Stop the propagation of the Tunable Laser"""

        laser_state = await self.rem.tunablelaser.evt_detailedState.next(
            flush=True, timeout=self.long_timeout
        )

        if laser_state.DetailedState not in {
            LaserDetailedState.NONPROPAGATING_CONTINUOUS_MODE,
            LaserDetailedState.NONPROPAGATING_BURST_MODE,
        }:
            try:
                await self.rem.tunablelaser.cmd_stopPropagateLaser.start(
                    timeout=self.laser_warmup
                )
                laser_state = await self.rem.tunablelaser.evt_detailedState.next(
                    flush=True, timeout=self.long_timeout
                )
                self.log.info(f"Laser state: {laser_state.DetailedState}")
            except asyncio.TimeoutError:
                raise RuntimeError(
                    "Tunable Laser did not stop propagating when commanded"
                )

    async def prepare_for_flat(self, sequence_name: str) -> None:
        """Configure the ATMonochromator according to the flat parameters

        Parameters
        ----------
        sequence_name : `str`
            name of the type of configuration you will run, which is saved
            in the configuration.yaml files

        Raises
        ------
        RuntimeError:

        """
        config_data = self.get_calibration_configuration(sequence_name)

        calibration_type = getattr(CalibrationType, str(config_data["calib_type"]))

        task_setup_camera = (
            self.mtcamera.setup_instrument(
                filter=config_data["mtcamera_filter"],
            )
            if self.mtcamera is not None and config_data["use_camera"]
            else utils.make_done_future()
        )
        if self.mtcamera is None and config_data["use_camera"]:
            raise RuntimeError(
                f"MTCamera is not defined but {sequence_name} requires it. "
                "Make sure you are instantiating ComCam and passing it to MTCalsys."
            )

        if calibration_type == CalibrationType.WhiteLight:
            # Turn off all LEDs
            # TO-DO (DM-50206): Swap switchON/OFF
            await self.rem.ledprojector.cmd_switchAllOn.start(
                timeout=self.long_timeout,
            )

            # Confirm that Projector selection is at the LED location
            vertical_pos = await self.linearstage_projector_select.tel_position.next(
                flush=True, timeout=self.long_timeout
            )
            if vertical_pos.position != self.linearstage_projector_locations["led"]:
                self.log.info("Projector select stage is not aligned with LED position")
                self.linearstage_projector_select.cmd_moveAbsolute.set_start(
                    distance=self.linearstage_projector_locations["led"],
                    axis=self.linearstage_axis,
                    timeout=self.long_timeout,
                )

            # Move stages to properly align the selected LED and focus
            task_select_led = self.linearstage_led_select.cmd_moveAbsolute.set_start(
                distance=config_data.get("led_location"),
                axis=self.linearstage_axis,
                timeout=self.long_timeout,
            )
            task_adjust_led_focus = (
                self.linearstage_led_focus.cmd_moveAbsolute.set_start(
                    distance=config_data.get("led_focus"),
                    axis=self.led_focus_axis,
                    timeout=self.long_timeout,
                )
            )
            task_adjust_led_level = (
                self.rem.ledprojector.cmd_adjustAllDACPower.set_start(
                    dacValue=config_data.get("dac_value")
                )
            )
            task_turn_led_on = self.rem.ledprojector.cmd_switchOn.set_start(
                serialNumbers=config_data.get("led_name"),
                timeout=self.long_timeout,
            )
            await asyncio.gather(
                task_select_led,
                task_adjust_led_focus,
                task_adjust_led_level,
                task_turn_led_on,
                task_setup_camera,
            )

        elif calibration_type == CalibrationType.Mono:
            wavelengths = [400.0]  # function of filter_name
            task_select_wavelength = self.change_laser_wavelength(
                wavelength=wavelengths[0]
            )

            await asyncio.gather(task_select_wavelength, task_setup_camera)

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
                wavelength_start, wavelength_end, wavelength_resolution
            )

        exposure_table = await self.calculate_optimized_exposure_times(
            wavelengths=calibration_wavelengths, config_data=config_data
        )

        for exposure in exposure_table:
            self.log.debug(
                f"Performing {calibration_type.name} calibration with {exposure.wavelength=}."
            )

            mtcamera_exposure_info: dict = dict()

            for exptime in config_data["exposure_times"]:
                self.log.debug("Taking data sequence.")
                exposure_info = await self._take_data(
                    mtcamera_exptime=exposure.camera,
                    mtcamera_filter=str(config_data["mtcamera_filter"]),
                    exposure_metadata=exposure_metadata,
                    fiber_spectrum_red_exposure_time=exposure.fiberspectrograph_red,
                    fiber_spectrum_blue_exposure_time=exposure.fiberspectrograph_blue,
                    electrometer_exposure_time=exposure.electrometer,
                )
                mtcamera_exposure_info.update(exposure_info)

                if calibration_type == CalibrationType.Mono:
                    await self.change_laser_wavelength(wavelength=exposure.wavelength)
                    self.log.debug(
                        "Taking data sequence without filter for monochromatic set."
                    )
                    exposure_info = await self._take_data(
                        mtcamera_exptime=exposure.camera,
                        mtcamera_filter="empty_1",
                        exposure_metadata=exposure_metadata,
                        fiber_spectrum_red_exposure_time=exposure.fiberspectrograph_red,
                        fiber_spectrum_blue_exposure_time=exposure.fiberspectrograph_blue,
                        electrometer_exposure_time=exposure.electrometer,
                    )
                    mtcamera_exposure_info.update(exposure_info)

            step = dict(
                wavelength=exposure.wavelength,
                mtcamera_exposure_info=mtcamera_exposure_info,
            )

            calibration_summary["steps"].append(step)
        return calibration_summary

    async def calculate_optimized_exposure_times(
        self, wavelengths: list, config_data: dict
    ) -> list[MTCalsysExposure]:
        """Calculates the exposure times for the electrometer and
        fiber spectrograph given the type and wavelength of the exposure
        and the length of the camera exposure time

        Parameters
        ----------
        wavelengths : `list`
            List of all wavelengths for this exposure list
        config_data : `dict`
            All information from configuration file

        Returns
        -------
        exposure_list : `list`[ATCalsysExposure|MTCalsysExposure]
            List of exposure information, includes wavelength
            and camera, fiberspectrograph and electrometer exposure times.
        """
        exposures: list[MTCalsysExposure] = []
        for wavelength in wavelengths:
            electrometer_exptimes = await self._calculate_electrometer_exposure_times(
                exptimes=config_data["exposure_times"],
                electrometer_integration_time=config_data[
                    "electrometer_integration_time"
                ],
                use_electrometer=config_data["use_electrometer"],
            )
            fiberspectrograph_exptimes_red = (
                await self._calculate_fiberspectrograph_exposure_times(
                    exptimes=config_data["exposure_times"],
                    use_fiberspectrograph=config_data["use_fiberspectrograph_red"],
                )
            )
            fiberspectrograph_exptimes_blue = (
                await self._calculate_fiberspectrograph_exposure_times(
                    exptimes=config_data["exposure_times"],
                    use_fiberspectrograph=config_data["use_fiberspectrograph_blue"],
                )
            )

            for i, exptime in enumerate(config_data["exposure_times"]):
                exposures.append(
                    MTCalsysExposure(
                        wavelength=wavelength,
                        camera=exptime,
                        electrometer=electrometer_exptimes[i],
                        fiberspectrograph_red=fiberspectrograph_exptimes_red[i],
                        fiberspectrograph_blue=fiberspectrograph_exptimes_blue[i],
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
        # TODO (DM-44777): Update optimized exposure times
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
        # TODO (DM-44777): Update optimized exposure times
        fiberspectrograph_exptimes: list[float | None] = []
        for exptime in exptimes:
            if use_fiberspectrograph:
                base_exptime = 1  # sec
                fiberspectrograph_exptimes.append(base_exptime)
            else:
                fiberspectrograph_exptimes.append(None)
        return fiberspectrograph_exptimes

    async def _take_data(
        self,
        mtcamera_exptime: float,
        mtcamera_filter: str,
        exposure_metadata: dict,
        fiber_spectrum_red_exposure_time: float | None,
        fiber_spectrum_blue_exposure_time: float | None,
        electrometer_exposure_time: float | None,
    ) -> dict:

        assert self.mtcamera is not None

        mtcamera_exposure_task = self.mtcamera.take_flats(
            mtcamera_exptime,
            nflats=1,
            filter=mtcamera_filter,
            **exposure_metadata,
        )
        exposures_done: asyncio.Future = asyncio.Future()

        group_id = exposure_metadata.get("group_id", "")

        if group_id == "":
            self.log.warning(
                "No Group ID for Electrometer/Fiber Spectrograph exposures. Continuing."
            )

        fiber_spectrum_red_exposure_coroutine = self.take_fiber_spectrum(
            fiberspectrograph_color="red",
            exposure_time=fiber_spectrum_red_exposure_time,
            exposures_done=exposures_done,
            group_id=group_id,
        )
        fiber_spectrum_blue_exposure_coroutine = self.take_fiber_spectrum(
            fiberspectrograph_color="blue",
            exposure_time=fiber_spectrum_blue_exposure_time,
            exposures_done=exposures_done,
            group_id=group_id,
        )
        electrometer_exposure_coroutine = self.take_electrometer_scan(
            exposure_time=electrometer_exposure_time,
            exposures_done=exposures_done,
            group_id=group_id,
        )
        try:
            fiber_spectrum_red_exposure_task = asyncio.create_task(
                fiber_spectrum_red_exposure_coroutine
            )
            fiber_spectrum_blue_exposure_task = asyncio.create_task(
                fiber_spectrum_blue_exposure_coroutine
            )
            electrometer_exposure_task = asyncio.create_task(
                electrometer_exposure_coroutine
            )

            mtcamera_exposure_id = await mtcamera_exposure_task
        finally:
            exposures_done.set_result(True)
            (
                fiber_spectrum_red_exposure_result,
                fiber_spectrum_blue_exposure_result,
                electrometer_exposure_result,
            ) = await asyncio.gather(
                fiber_spectrum_red_exposure_task,
                fiber_spectrum_blue_exposure_task,
                electrometer_exposure_task,
            )

        return {
            mtcamera_exposure_id[0]: dict(
                fiber_spectrum_red_exposure_result=fiber_spectrum_red_exposure_result,
                fiber_spectrum_blue_exposure_result=fiber_spectrum_blue_exposure_result,
                electrometer_exposure_result=electrometer_exposure_result,
            )
        }

    async def take_electrometer_scan(
        self,
        exposure_time: float | None,
        group_id: str,
        exposures_done: asyncio.Future,
    ) -> list[str]:
        """Perform an electrometer scan for the specified duration.

        Parameters
        ----------
        exposure_time : `float`
            Exposure time for the fiber spectrum (seconds).
        exposures_done : `asyncio.Future`
            A future indicating when the camera exposures where complete.

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
                    groupId=group_id,
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
                    "is in enabled state and continuing."
                )
                await salobj.set_summary_state(self.electrometer, salobj.State.ENABLED)
        return electrometer_exposures

    async def take_fiber_spectrum(
        self,
        fiberspectrograph_color: str,
        exposure_time: float | None,
        group_id: str,
        exposures_done: asyncio.Future,
    ) -> list[str]:
        """Take exposures with the fiber spectrograph until
        the exposures with the camera are complete.

        This method will continue to take data with the fiber
        spectrograph until the exposures_done future is done.

        Parameters
        ----------
        exposure_time : `float`
            Exposure time for the fiber spectrum (seconds).
        exposures_done : `asyncio.Future`
            A future indicating when the camera exposures where complete.

        Returns
        -------
        fiber_spectrum_exposures : `list`[`str`]
            List of large file urls.
        """
        if fiberspectrograph_color == "blue":
            fiberspec = self.fiberspectrograph_blue
        elif fiberspectrograph_color == "red":
            fiberspec = self.fiberspectrograph_red

        fiberspec.evt_largeFileObjectAvailable.flush()

        fiber_spectrum_exposures = []

        if exposure_time is not None:

            try:
                await fiberspec.cmd_expose.set_start(
                    duration=exposure_time,
                    numExposures=1,
                    groupId=group_id,
                    timeout=exposure_time + self.long_timeout,
                )

            except salobj.AckTimeoutError:
                self.log.exception("Timed out waiting for the command ack. Continuing.")

            lfo = await fiberspec.evt_largeFileObjectAvailable.next(
                timeout=self.long_timeout, flush=False
            )

            fiber_spectrum_exposures.append(lfo.url)

        return fiber_spectrum_exposures

    @property
    def electrometer(self) -> salobj.Remote:
        return getattr(self.rem, f"electrometer_{self.electrometer_projector_index}")

    @property
    def fiberspectrograph_red(self) -> salobj.Remote:
        return getattr(
            self.rem, f"fiberspectrograph_{self.fiberspectrograph_red_index}"
        )

    @property
    def fiberspectrograph_blue(self) -> salobj.Remote:
        return getattr(
            self.rem, f"fiberspectrograph_{self.fiberspectrograph_blue_index}"
        )

    @property
    def linearstage_led_focus(self) -> salobj.Remote:
        """Horizontal linear stage that moves the mirror, extending
        the distance between the 3rd and 4th lenses.
        """
        return getattr(self.rem, f"linearstage_{self.linearstage_led_focus_index}")

    @property
    def linearstage_laser_focus(self) -> salobj.Remote:
        """Horizontal linear stage that moves a lens to focus the
        laser light from the fiber
        """
        return getattr(self.rem, f"linearstage_{self.linearstage_laser_focus_index}")

    @property
    def linearstage_led_select(self) -> salobj.Remote:
        """Horizontal linear stage that moves between LED modules"""
        return getattr(self.rem, f"linearstage_{self.linearstage_led_select_index}")

    @property
    def linearstage_projector_select(self) -> salobj.Remote:
        """Vertical linear stage that selects between the LED
        or laser projectors
        """
        return getattr(self.rem, f"linearstage_{self.linearstage_select_index}")

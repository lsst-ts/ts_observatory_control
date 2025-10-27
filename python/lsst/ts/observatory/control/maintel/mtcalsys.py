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
import time
import typing
from dataclasses import dataclass

import numpy as np
from lsst.ts import salobj, utils

# TODO: (DM-46168) Revert workaround for TunableLaser XML changes
from lsst.ts.observatory.control.utils.enums import LaserOpticalConfiguration
from lsst.ts.xml.enums.TunableLaser import LaserDetailedState
from numpy.typing import NDArray

from ..base_calsys import BaseCalsys
from ..remote_group import Usages
from ..utils import CalibrationType
from . import LSSTCam


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
    dacValue: float | None


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
        mtcamera: typing.Optional[LSSTCam] = None,
    ) -> None:

        self.electrometer_projector_index = 103
        self.electrometer_cbp_index = 102
        self.electrometer_cbpcal_index = 101
        self.fiberspectrograph_blue_index = 102
        self.fiberspectrograph_red_index = 101
        self.linearstage_led_select_index = 102
        self.linearstage_led_focus_index = 101
        self.linearstage_laser_focus_index = 104
        self.linearstage_select_index = 103
        self.npulse_lookup = [
            ((None, 410), 4000),
            ((410, 420), 2000),
            ((420, 540), 40),
            ((540, 570), 100),
            ((570, 600), 400),
            ((600, 650), 500),
            ((650, 700), 1000),
            ((700, 720), 2000),
            ((720, 770), 1000),
            ((770, 1070), 400),
            ((1070, 1100), 2000),
            ((1100, None), 3000),
        ]

        super().__init__(
            components=[
                "TunableLaser",
                "LEDProjector",
                "CBP",
                f"FiberSpectrograph:{self.fiberspectrograph_blue_index}",
                f"FiberSpectrograph:{self.fiberspectrograph_red_index}",
                f"Electrometer:{self.electrometer_cbp_index}",
                f"Electrometer:{self.electrometer_cbpcal_index}",
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
        self.led_focus_axis = 2
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

        if calibration_type == CalibrationType.CBP:
            if config_data["use_cbp"]:
                await self.setup_cbp(
                    azimuth=config_data["cbp_azimuth"],
                    elevation=config_data["cbp_elevation"],
                    mask=config_data["cbp_mask"],
                    focus=config_data["cbp_focus"],
                    rotation=config_data["cbp_rotation"],
                )

            if config_data["use_cbp_electrometer"]:
                await self.setup_electrometers(
                    mode=str(config_data["electrometer_mode"]),
                    range=float(config_data["electrometer_range"]),
                    integration_time=float(
                        config_data["electrometer_integration_time"]
                    ),
                    electrometer_names=[f"electrometer_{self.electrometer_cbp_index}"],
                )

            await self.setup_laser(
                config_data["laser_mode"],
                config_data["wavelength"],
                config_data["optical_configuration"],
            )
            await self.laser_start_propagate()

        else:

            if config_data["use_flatfield_electrometer"]:
                await self.setup_electrometers(
                    mode=str(config_data["electrometer_mode"]),
                    range=float(config_data["electrometer_range"]),
                    integration_time=float(
                        config_data["electrometer_integration_time"]
                    ),
                    electrometer_names=[
                        f"electrometer_{self.electrometer_projector_index}"
                    ],
                )

            # Home all linear stages.
            await self.linearstage_projector_select.cmd_getHome.set_start(
                axis=self.linearstage_axis, timeout=self.stage_homing_timeout
            )
            await self.linearstage_led_select.cmd_getHome.set_start(
                axis=self.linearstage_axis, timeout=self.long_timeout
            )
            led_focus_home = self.linearstage_led_focus.cmd_getHome.set_start(
                axis=self.led_focus_axis, timeout=self.stage_homing_timeout
            )

            laser_focus_home = self.linearstage_laser_focus.cmd_getHome.set_start(
                axis=self.linearstage_axis, timeout=self.stage_homing_timeout
            )

            await asyncio.gather(led_focus_home, laser_focus_home)

            # Move LED Select stage to a safe position
            self.log.debug("Moving LED select stage to safe position.")
            await self.linearstage_led_select.cmd_moveAbsolute.set_start(
                distance=self.led_rest_position,
                axis=self.linearstage_axis,
                timeout=self.long_timeout,
            )

            if calibration_type == CalibrationType.WhiteLight:
                self.log.debug(
                    "Moving vertical projector selection stage to LED position"
                )
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

    async def setup_cbp(
        self,
        azimuth: float,
        elevation: float,
        mask: int | None = None,
        focus: float | None = None,
        rotation: float | None = None,
    ) -> None:
        """Perform all steps for preparing the CBP for measurements.
        Parameters
        ----------
        azimuth : `float`
            Azimuth of CBP in degrees
        elevation : `float`
            Elevation of CBP in degrees
        mask : `int`
            Mask number to use
        focus: `float`
            Focus position in um
        rotation: `int`
            Rotator position of mask in degrees
            Default 0
        """

        self.log.info("Beginning CBP setup")

        self.log.debug(f"Setting CBP az and el to {azimuth} and {elevation}")
        await self.rem.cbp.cmd_move.set_start(
            azimuth=azimuth,
            elevation=elevation,
            timeout=self.long_long_timeout,
        )
        if focus is not None:
            self.log.debug(f"Setting focus to {focus}")
            await self.rem.cbp.cmd_setFocus.set_start(
                focus=focus, timeout=self.long_long_timeout
            )
        if mask is not None:
            self.log.debug(f"Setting mask to {mask}")
            await self.rem.cbp.cmd_changeMask.set_start(
                mask=mask, timeout=self.long_long_timeout
            )
        if rotation is not None:
            self.log.debug(f"Setting mask rotation to {rotation}")
            await self.rem.cbp.cmd_changeMaskRotation.set_start(
                mask_rotation=rotation, timeout=self.long_long_timeout
            )
        self.log.info("Done setting up CBP")

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
            axis=self.led_focus_axis, timeout=self.stage_homing_timeout
        )

        laser_focus_home = self.linearstage_laser_focus.cmd_getHome.set_start(
            axis=self.linearstage_axis, timeout=self.stage_homing_timeout
        )

        await asyncio.gather(led_focus_home, laser_focus_home)
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
        laser_focus_offset = 17.343
        a = 77.092
        b = 0.005
        c = 39.048
        separation = a * np.exp(-(b * float(wavelength))) + c
        return separation - laser_focus_offset

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
        await self.rem.tunablelaser.cmd_changeWavelength.set_start(
            wavelength=wavelength, timeout=self.long_long_timeout
        )
        if use_projector:
            laser_focus_location = self.calculate_laser_focus_location(wavelength)
            await self.linearstage_laser_focus.cmd_moveAbsolute.set_start(
                distance=laser_focus_location,
                axis=self.linearstage_axis,
                timeout=self.long_long_timeout,
            )

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
                abs(float(select_location.position[0]) - float(value))
                < self.linearstage_projector_pos_tolerance
            ):
                projector_location = location
            else:
                projector_location = "misaligned"

        self.log.info(
            f"Projector Location is {projector_location}, {select_location.position[0]} \n"
            f"LED Location stage pos @: {led_location.position[0]}], \n"
            f"LED Focus stage pos @: {led_focus.position[0]}, \n"
            f"LED State stage pos @: {led_state}, \n"
            f"Laser Focus stage pos @: {laser_focus.position[0]}"
        )

        return (
            projector_location,
            float(led_location.position[0]),
            float(led_focus.position[0]),
            float(laser_focus.position[0]),
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
            flush=False, timeout=self.long_timeout
        )
        self.log.debug(f"HERE: {laser_state.detailedState}")

        if laser_state.detailedState not in {
            LaserDetailedState.PROPAGATING_CONTINUOUS_MODE,
            LaserDetailedState.PROPAGATING_BURST_MODE,
        }:
            try:
                await self.rem.tunablelaser.cmd_startPropagateLaser.start(
                    timeout=self.laser_warmup
                )
                laser_state = await self.rem.tunablelaser.evt_detailedState.next(
                    flush=False, timeout=self.long_timeout
                )
                self.log.info(f"Laser state: {laser_state.detailedState}")
            except asyncio.TimeoutError:
                raise RuntimeError(
                    "Tunable Laser did not start propagating when commanded"
                )

    async def laser_stop_propagate(self) -> None:
        """Stop the propagation of the Tunable Laser"""

        laser_state = await self.rem.tunablelaser.evt_detailedState.next(
            flush=False, timeout=self.long_timeout
        )

        if laser_state.detailedState not in {
            LaserDetailedState.NONPROPAGATING_CONTINUOUS_MODE,
            LaserDetailedState.NONPROPAGATING_BURST_MODE,
        }:
            try:
                await self.rem.tunablelaser.cmd_stopPropagateLaser.start(
                    timeout=self.laser_warmup
                )
                laser_state = await self.rem.tunablelaser.evt_detailedState.next(
                    flush=False, timeout=self.long_timeout
                )
                self.log.info(f"Laser state: {laser_state.detailedState}")
            except asyncio.TimeoutError:
                raise RuntimeError(
                    "Tunable Laser did not stop propagating when commanded"
                )

    def get_npulse_for_wavelength(self, wavelength: float) -> int:
        """Return npulse value for a given wavelength based on defined ranges.

        Parameters
        ----------
        wavelength : float
            The wavelength in nanometers.

        Returns
        -------
        int
            The corresponding npulse value.
        """

        for (low, high), npulse in self.npulse_lookup:
            if (low is None or wavelength >= low) and (
                high is None or wavelength < high
            ):
                return npulse
        return 0

    async def take_bursts(
        self,
        nburst: int = 5,
        delay_before: float = 5,
        delay_after: float = 5,
        wait_time: float = 10,
    ) -> None:
        """Take pulsed bursts with the laser

        Parameters
        ----------
        nburst : 'int`
            number of bursts
        delay_before : 'float`
            delay before pulse
        delay_after : 'float`
            delay after pulse
        wait_time : 'float`
            wait time before pulse train

        """
        await asyncio.sleep(wait_time)
        await asyncio.sleep(delay_before)
        for n in range(nburst):
            await asyncio.sleep(delay_before)
            await self.rem.tunablelaser.cmd_triggerBurst.start()
            await asyncio.sleep(delay_after)
        await asyncio.sleep(delay_after)

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
                "Make sure you are instantiating LSSTCam and passing it to MTCalsys."
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
            if vertical_pos.position[0] != self.linearstage_projector_locations["led"]:
                self.log.info("Projector select stage is not aligned with LED position")
                await self.linearstage_projector_select.cmd_moveAbsolute.set_start(
                    distance=self.linearstage_projector_locations["led"],
                    axis=self.linearstage_axis,
                    timeout=self.long_timeout,
                )

            # Move stages to properly align the selected LED and focus
            task_select_led = self.linearstage_led_select.cmd_moveAbsolute.set_start(
                distance=config_data.get("led_location"),
                axis=self.linearstage_axis,
                timeout=self.long_long_timeout,
            )
            task_adjust_led_focus = (
                self.linearstage_led_focus.cmd_moveAbsolute.set_start(
                    distance=config_data.get("led_focus"),
                    axis=self.led_focus_axis,
                    timeout=self.long_long_timeout,
                )
            )
            task_adjust_led_level = (
                self.rem.ledprojector.cmd_adjustAllDACPower.set_start(
                    dacValue=config_data.get("dac_value"),
                    timeout=self.long_timeout,
                )
            )

            led_names: typing.Iterable[str] = config_data.get("led_name", [])
            task_turn_led_on = self.rem.ledprojector.cmd_switchOff.set_start(
                serialNumbers=",".join(led_names),
                timeout=self.long_timeout,
            )

            results = await asyncio.gather(
                task_select_led,
                task_adjust_led_focus,
                task_adjust_led_level,
                task_turn_led_on,
                task_setup_camera,
                return_exceptions=True,
            )

            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    self.log.info(
                        f"Task {i} raised an exception: {type(result).__name__}: {result}"
                    )

                    raise result

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

            if config_data["set_wavelength_range"]:
                wavelength = float(config_data["wavelength"])
                wavelength_width = float(config_data["wavelength_width"])
                wavelength_resolution = float(config_data["wavelength_resolution"])
                wavelength_start = wavelength - wavelength_width / 2.0
                wavelength_end = wavelength + wavelength_width / 2.0

                calibration_wavelengths = np.arange(
                    wavelength_start, wavelength_end, wavelength_resolution
                )

            else:
                calibration_wavelengths = config_data["wavelength_list"]

        exposure_table = await self.calculate_optimized_exposure_times(
            wavelengths=calibration_wavelengths, config_data=config_data
        )
        self.log.debug(f"Exposure Table: {exposure_table}")
        for i, exposure in enumerate(exposure_table):
            self.log.debug(
                f"Performing {calibration_type.name} calibration with {exposure.wavelength=}."
            )

            _exposure_metadata = exposure_metadata.copy()
            if "group_id" in _exposure_metadata:
                _exposure_metadata["group_id"] += f"#{i+1}"

            mtcamera_exposure_info: dict = dict()

            if (
                calibration_type == CalibrationType.CBP
                and int(config_data["laser_mode"]) == 4
            ):
                npulse = self.get_npulse_for_wavelength(wavelength=exposure.wavelength)
                self.log.debug(f"Number of pulses is {npulse}")
                await self.rem.tunablelaser.cmd_setBurstMode.set_start(
                    count=int(npulse)
                )

            self.log.debug("Taking data sequence.")
            if calibration_type == CalibrationType.Mono:
                await self.change_laser_wavelength(wavelength=exposure.wavelength)
                exposure_info = await self._take_data(
                    mtcamera_exptime=exposure.camera,
                    mtcamera_filter=str(config_data["mtcamera_filter"]),
                    exposure_metadata=_exposure_metadata,
                    calibration_type=calibration_type,
                    fiber_spectrum_red_exposure_time=exposure.fiberspectrograph_red,
                    fiber_spectrum_blue_exposure_time=exposure.fiberspectrograph_blue,
                    electrometer_exposure_time=exposure.electrometer,
                    nburst=config_data["nburst"],
                    laser_mode=config_data["laser_mode"],
                )

            elif calibration_type == CalibrationType.CBP:
                await self.change_laser_wavelength(wavelength=exposure.wavelength)
                if exposure.wavelength < 410:
                    camera_exposure_time = exposure.camera + 8
                    if exposure.electrometer is not None:
                        electrometer_exposure_time = exposure.electrometer + 8
                    else:
                        electrometer_exposure_time = None
                else:
                    camera_exposure_time = exposure.camera
                    electrometer_exposure_time = exposure.electrometer
                exposure_info = await self._take_data(
                    mtcamera_exptime=camera_exposure_time,
                    mtcamera_filter=str(config_data["mtcamera_filter"]),
                    exposure_metadata=_exposure_metadata,
                    calibration_type=calibration_type,
                    fiber_spectrum_red_exposure_time=exposure.fiberspectrograph_red,
                    fiber_spectrum_blue_exposure_time=exposure.fiberspectrograph_blue,
                    electrometer_exposure_time=electrometer_exposure_time,
                    nburst=config_data["nburst"],
                    laser_mode=config_data["laser_mode"],
                    sequence_name=sequence_name,
                    wavelength=int(exposure.wavelength),
                    wait_time=config_data["laser_wait_time"],
                    delay_after=float(round(1 + npulse / 1000, 2)),
                )
            else:
                self.log.info("Calibration Type is WhiteLight")
                await self.rem.ledprojector.cmd_adjustAllDACPower.set_start(
                    dacValue=exposure.dacValue
                )
                exposure_info = await self._take_data(
                    mtcamera_exptime=exposure.camera,
                    mtcamera_filter=str(config_data["mtcamera_filter"]),
                    calibration_type=calibration_type,
                    exposure_metadata=_exposure_metadata,
                    fiber_spectrum_red_exposure_time=exposure.fiberspectrograph_red,
                    fiber_spectrum_blue_exposure_time=exposure.fiberspectrograph_blue,
                    electrometer_exposure_time=exposure.electrometer,
                )

            mtcamera_exposure_info.update(exposure_info)

            step = dict(
                wavelength=exposure.wavelength,
                dacValue=exposure.dacValue,
                mtcamera_exposure_info=mtcamera_exposure_info,
            )

            calibration_summary["steps"].append(step)
        return calibration_summary

    def generate_random_exposure_times(
        self,
        samples_per_bin: list[int],
        bin_edges: list[list[float]],
        bin_dac_values: list[float],
        random_seed: int | None,
    ) -> tuple[list[float], list[float]]:
        """
        Generate a list of random exposure times based on bin edges and the
        number of samples per bin.
        Parameters
        ----------
        samples_per_bin : list of int
            The number of random samples to generate within each bin.
        bin_edges : list of float
            List of bin edges, with each element having a min and max value.
            Each element must contain two values
        bin_dac_values : list of float
            List of dac values for each exposure bin
        random_seed : int
            Integer value that determines the randomization of the samples
        Returns
        -------
        exposure_times : `list`
            A list of random exposure times, rounded to 1 decimal place.
            The length of the list will be: (len(bin_edges) - 1) *
            samples_per_bin.
        ptc_dac_values : `list`
        Raises
        ------
        ValueError
            If fewer than two bin edges are provided.
        """
        exposure_times_list: list[NDArray[np.float_]] = []
        bin_edges = np.array(bin_edges, dtype=float)
        self.log.debug(f"Bin Edges: {bin_edges}")
        self.log.debug(f"Dac Values: {bin_dac_values}")
        assert len(bin_dac_values) == len(bin_edges)

        for i, bin_ in enumerate(bin_edges):
            if len(bin_) < 2:
                raise ValueError(
                    "At least two bin edges are required to define one bin."
                )
            rng = np.random.RandomState(seed=random_seed)
            samples = rng.uniform(low=bin_[0], high=bin_[1], size=samples_per_bin[i])
            samples = np.round(samples, 1)
            paired = np.column_stack(
                (samples, np.full(samples_per_bin[i], bin_dac_values[i]))
            )
            exposure_times_list.append(paired)

        exposure_times: NDArray[np.float_] = np.vstack(exposure_times_list)
        np.random.shuffle(exposure_times)
        self.log.debug(exposure_times)
        return exposure_times[:, 0].tolist(), exposure_times[:, 1].tolist()

    def get_calibration_configuration(self, name: str) -> dict[str, typing.Any]:
        """
        Return the calibration configuration for a given configuration name,
        with optional post-processing to generate exposure times from a
        constrained random distribution if specified.
        This method extends the base implementation by checking if the
        configuration includes the `constrained_random_exposure_times` block.
        If present, it uses the provided `bin_edges` and `samples_per_bin` to
        generate a list of uniformly distributed random exposure times, and
        overwrites the `exposure_times` field with the generated values.
        Parameters
        ----------
        name : str
            Name of the calibration configuration to retrieve.
        Returns
        -------
        dict[str, Any]
            The full calibration configuration dictionary, with
            `exposure_times` updated if `constrained_random_exposure_times`
            was specified.
        """

        config = super().get_calibration_configuration(name)

        random_exptimes = config.get("constrained_random_exposure_times")
        if random_exptimes is not None:
            if random_exptimes["random_seed"] is None:
                t = time.localtime()
                date_int = int(time.strftime("%Y%m%d", t))
                config["constrained_random_exposure_times"]["random_seed"] = date_int
            exptimes, levels = self.generate_random_exposure_times(
                random_exptimes["samples_per_bin"],
                random_exptimes["bin_edges"],
                random_exptimes["bin_dac_values"],
                random_exptimes["random_seed"],
            )
            config["exposure_times"] = exptimes
            config["ptc_dac_values"] = levels

        return config

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
            Dictionary of config data

        Returns
        -------
        exposure_list : `list`[ATCalsysExposure|MTCalsysExposure]
            List of exposure information, includes wavelength
            and camera, fiberspectrograph and electrometer exposure times,
            and LED dac value.
        """
        exposures: list[MTCalsysExposure] = []

        exptimes = config_data["exposure_times"]
        if config_data.get("ptc_dac_values") is not None:
            levels = config_data["ptc_dac_values"]
        else:
            levels = [config_data["dac_value"]] * len(exptimes)

        for wavelength in wavelengths:

            for i, exptime in enumerate(exptimes):
                dac = levels[i]

                electrometer_exptime = (
                    await self._calculate_electrometer_exposure_times(
                        exptimes=[exptime],
                        electrometer_integration_time=config_data[
                            "electrometer_integration_time"
                        ],
                        use_electrometer=config_data["use_flatfield_electrometer"]
                        or config_data["use_cbp_electrometer"],
                    )
                )

                fiberspectrograph_exptime_red = (
                    await self._calculate_fiberspectrograph_exposure_times(
                        exptimes=[exptime],
                        use_fiberspectrograph=config_data["use_fiberspectrograph_red"],
                    )
                )

                fiberspectrograph_exptime_blue = (
                    await self._calculate_fiberspectrograph_exposure_times(
                        exptimes=[exptime],
                        use_fiberspectrograph=config_data["use_fiberspectrograph_blue"],
                    )
                )

                for n in range(config_data["n_flat"]):
                    exposures.append(
                        MTCalsysExposure(
                            wavelength=wavelength,
                            camera=exptime,
                            dacValue=dac,
                            electrometer=electrometer_exptime[0],
                            fiberspectrograph_red=fiberspectrograph_exptime_red[0],
                            fiberspectrograph_blue=fiberspectrograph_exptime_blue[0],
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
                base_exptime = 10  # sec
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
        delay_before: float = 1,
        delay_after: float = 1,
        calibration_type: CalibrationType = CalibrationType.WhiteLight,
        nburst: int = 5,
        laser_mode: int = 1,
        sequence_name: str | None = None,
        wavelength: int | None = None,
        wait_time: int = 10,
    ) -> dict:

        if self.mtcamera is not None:
            mtcamera_exposure_task = self.mtcamera.take_flats(
                mtcamera_exptime,
                nflats=1,
                filter=mtcamera_filter,
                **exposure_metadata,
            )
        else:
            self.log.debug("Taking Data without MTCamera")

        exposures_done: asyncio.Future = asyncio.Future()

        group_id = exposure_metadata.get("group_id", "")

        if group_id == "":
            self.log.warning(
                "No Group ID for Electrometer/Fiber Spectrograph exposures. Continuing."
            )

        electrometer_exposure_coroutine = self.take_electrometer_scan(
            exposure_time=electrometer_exposure_time,
            exposures_done=exposures_done,
            group_id=group_id,
            calibration_type=calibration_type,
            sequence_name=sequence_name,
        )

        if calibration_type == CalibrationType.CBP:
            if laser_mode == 4:
                laser_burst_coroutine = self.take_bursts(
                    nburst=nburst,
                    delay_before=delay_before,
                    delay_after=delay_after,
                    wait_time=wait_time,
                )
                try:
                    electrometer_exposure_task = asyncio.create_task(
                        electrometer_exposure_coroutine
                    )
                    laser_burst_task = asyncio.create_task(laser_burst_coroutine)
                    if self.mtcamera is not None:
                        mtcamera_exposure_id = await mtcamera_exposure_task
                    else:
                        mtcamera_exposure_id = [0]
                finally:
                    exposures_done.set_result(True)
                    (electrometer_exposure_result, laser_burst_result) = (
                        await asyncio.gather(
                            electrometer_exposure_task,
                            laser_burst_task,
                        )
                    )

                return {
                    mtcamera_exposure_id[0]: dict(
                        electrometer_exposure_result=electrometer_exposure_result,
                    )
                }
            else:
                try:
                    electrometer_exposure_task = asyncio.create_task(
                        electrometer_exposure_coroutine
                    )
                    if self.mtcamera is not None:
                        mtcamera_exposure_id = await mtcamera_exposure_task
                    else:
                        mtcamera_exposure_id = [0]
                finally:
                    exposures_done.set_result(True)
                    (electrometer_exposure_result,) = await asyncio.gather(
                        electrometer_exposure_task,
                    )

                return {
                    mtcamera_exposure_id[0]: dict(
                        electrometer_exposure_result=electrometer_exposure_result,
                    )
                }

        else:

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
                if self.mtcamera is not None:
                    mtcamera_exposure_id = await mtcamera_exposure_task
                else:
                    mtcamera_exposure_id = [0]
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
        sequence_name: str | None,
        group_id: str,
        exposures_done: asyncio.Future,
        calibration_type: CalibrationType = CalibrationType.WhiteLight,
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

        electrometer_exposures = list()

        if calibration_type == CalibrationType.CBP:
            electrometer = self.electrometer_cbp
        else:
            electrometer = self.electrometer_flatfield

        if exposure_time is not None:
            electrometer.evt_largeFileObjectAvailable.flush()

            try:
                await electrometer.cmd_startScanDt.set_start(
                    scanDuration=exposure_time,
                    groupId=group_id,
                    timeout=exposure_time + self.long_timeout,
                )
            except salobj.AckTimeoutError:
                self.log.exception("Timed out waiting for the command ack. Continuing.")

            # Make sure that a new lfo was created
            try:
                lfo = await electrometer.evt_largeFileObjectAvailable.next(
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
                await salobj.set_summary_state(electrometer, salobj.State.STANDBY)
                await salobj.set_summary_state(electrometer, salobj.State.ENABLED)
                if sequence_name is not None:
                    config_data = self.get_calibration_configuration(sequence_name)
                    if config_data["use_flatfield_electrometer"]:
                        electrometer_name = (
                            f"electrometer_{self.electrometer_projector_index}"
                        )
                    elif config_data["use_cbp_electrometer"]:
                        electrometer_name = (
                            f"electrometer_{self.electrometer_cbp_index}"
                        )
                    await self.setup_electrometers(
                        mode=str(config_data["electrometer_mode"]),
                        range=float(config_data["electrometer_range"]),
                        integration_time=float(
                            config_data["electrometer_integration_time"]
                        ),
                        electrometer_names=[electrometer_name],
                    )

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
        fiber_spectrum_exposures = []

        if exposure_time is not None:
            if fiberspectrograph_color == "blue":
                fiberspec = self.fiberspectrograph_blue
            elif fiberspectrograph_color == "red":
                fiberspec = self.fiberspectrograph_red
            fiberspec.evt_largeFileObjectAvailable.flush()

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
    def electrometer_flatfield(self) -> salobj.Remote:
        return getattr(self.rem, f"electrometer_{self.electrometer_projector_index}")

    @property
    def electrometer_cbp(self) -> salobj.Remote:
        return getattr(self.rem, f"electrometer_{self.electrometer_cbp_index}")

    @property
    def electrometer_cbpcal(self) -> salobj.Remote:
        return getattr(self.rem, f"electrometer_{self.electrometer_cbpcal_index}")

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

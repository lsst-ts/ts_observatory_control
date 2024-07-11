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

import numpy as np
import yaml
from lsst.ts import salobj, utils
from lsst.ts.xml.enums import TunableLaser

from ..base_calsys import BaseCalsys
from ..remote_group import Usages
from ..utils import CalibrationType
from . import ComCam


class MTCalsysUsages(Usages):
    """ATCalsys usages definition.

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

        self.electrometer_projector_index = 201
        self.fiberspectrograph_blue_index = 1
        self.fiberspectrograph_red_index = 2
        self.linearstage_led_select_index = 1
        self.linearstage_led_focus_index = 2
        self.linearstage_laser_focus_index = 3
        self.linearstage_select_index = 4

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
        self.ls_select_led_location = 9.96  # mm
        self.ls_select_laser_location = 79.96  # mm
        self.led_rest_position = 120.0  # mm

        self.led_projector_config_filename = "../data/mtledprojector.yaml"

        with open(self.led_projector_config_filename, "r") as f:
            self.led_projector_config = yaml.safe_load(f)

        self.laser_enclosure_temp = 20.0  # C

        self.exptime_dict: dict[str, float] = dict(
            camera=0.0,
            electrometer=0.0,
            fiberspectrograph=0.0,
        )

    def calculate_laser_focus_location(self, wavelength: float) -> float:
        """Calculates the location of the linear stage that provides the focus
        for the laser projector. This location is dependent on the
        wavelength of the laser.

        Parameters
        ----------
        wavelength : `float`
            wavelength of the laser projector in nm

        Returns
        ------
        location of the linear stage for the laser projector focus in mm

        """
        # TODO (DM-44772): implement the actual function
        return 10.0

    async def change_laser_wavelength(self, wavelength: float) -> None:
        """Change the TunableLaser wavelength setting

        Parameters
        ----------
        wavelength : `float`
            wavelength of the laser in nm
        """

        task_wavelength = self.rem.tunablelaser.cmd_changeWavelength.set_start(
            wavelength=wavelength, timeout=self.long_long_timeout
        )
        task_focus = self.linearstage_laser_focus.cmd_moveAbsolute.set_start(
            distance=self.calculate_laser_focus_location(wavelength)
        )

        await asyncio.gather(task_wavelength, task_focus)

    async def is_ready_for_flats(self) -> bool:
        """Add doctring"""
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

        self.exptime_dict = await self.calculate_optimized_exposure_times(sequence_name)

        if calibration_type == CalibrationType.WhiteLight:
            await self.linearstage_projector_select.cmd_moveAbsolute.set_start(
                distance=self.ls_select_led_location, timeout=self.long_timeout
            )
        else:
            await self.linearstage_led_select.cmd_moveAbsolute.set_start(
                distance=self.led_rest_position, timeout=self.long_timeout
            )
            await self.linearstage_projector_select.cmd_moveAbsolute.set_start(
                distance=self.ls_select_laser_location, timeout=self.long_timeout
            )
            await self.setup_laser(config_data["laser_mode"])
            await self.rem.tunablelaser.cmd_startPropagating.start(
                timeout=self.long_long_timeout
            )

    async def setup_laser(self, mode: str) -> None:
        """Perform all steps for preparing the laser for monchromatic flats.
        This includes confirming that the thermal system is
        turned on and set at the right temperature. It also checks
        the interlockState to confirm it's ready to propagate.

        Parameters
        ----------
        mode : `str`
            Mode of the TunableLaser
            Options: CONTINUOUS, BURST, TRIGGER

        """
        # check the thermal system is running
        # check set temp
        # check actual temp and determine if good enough
        # check the interlockState

        if mode == TunableLaser.Mode.CONTINUOUS:
            await self.rem.tunablelaser.cmd_setContinuousMode.start(
                timeout=self.long_timeout
            )
        elif mode in {TunableLaser.Mode.BURST, TunableLaser.Mode.TRIGGER}:
            await self.rem.tunablelaser.cmd_setBurstMode.start(
                timeout=self.long_timeout
            )
        else:
            raise RuntimeError(
                f"{mode} not an acceptable TunableLaser Mode [CONTINOUS, BURST, TRIGGER]"
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
        filter_name = config_data[
            "filter"
        ]  # not sure if this is an enumeration somewhere?
        led_info = self.led_projector_config.get(filter_name)

        task_setup_camera = (
            self.mtcamera.setup_instrument(
                filter=config_data["lsst_filter"],
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
            leds_ = led_info.get("led_name")
            task_select_led = self.linearstage_led_select.cmd_moveAbsolute.set_start(
                distance=led_info.get("led_location"), timeout=self.long_timeout
            )
            task_adjust_led_focus = (
                self.linearstage_led_focus.cmd_moveAbsolute.set_start(
                    distance=led_info.get("led_focus"), timeout=self.long_timeout
                )
            )
            task_turn_led_on = self.rem.ledprojector.cmd_switchOn.set_start(
                serialNumbers=leds_, timeout=self.long_timeout
            )

            await asyncio.gather(
                task_select_led,
                task_adjust_led_focus,
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

        for wavelength in calibration_wavelengths:
            self.log.debug(
                f"Performing {calibration_type.name} calibration with {wavelength=}."
            )
            await self.change_laser_wavelength(wavelength=wavelength)
            mtcamera_exposure_info: dict = dict()

            for exptime in config_data["exposure_times"]:
                self.log.debug("Taking data sequence.")
                exposure_info = await self._take_data(
                    mtcamera_exptime=float(exptime),
                    mtcamera_filter=str(config_data["atspec_filter"]),
                    mtcamera_grating=str(config_data["atspec_grating"]),
                    exposure_metadata=exposure_metadata,
                    use_red_fiberspec=config_data["use_red_fiberspectrograph"],
                    use_blue_fiberspec=config_data["use_blue_fiberspectrograph"],
                    fiber_spectrum_exposure_time=float(
                        self.exptime_dict["fiberspectrograph"]
                    ),
                    electrometer_exposure_time=float(self.exptime_dict["electrometer"]),
                )
                mtcamera_exposure_info.update(exposure_info)

                if calibration_type == CalibrationType.Mono:
                    self.log.debug(
                        "Taking data sequence without filter for monochromatic set."
                    )
                    exposure_info = await self._take_data(
                        mtcamera_exptime=float(exptime),
                        mtcamera_filter="empty_1",
                        mtcamera_grating=str(config_data["atspec_grating"]),
                        exposure_metadata=exposure_metadata,
                        use_red_fiberspec=config_data["use_red_fiberspectrograph"],
                        use_blue_fiberspec=config_data["use_blue_fiberspectrograph"],
                        fiber_spectrum_exposure_time=float(
                            self.exptime_dict["fiberspectrograph"]
                        ),
                        electrometer_exposure_time=float(
                            self.exptime_dict["electrometer"]
                        ),
                    )
                    mtcamera_exposure_info.update(exposure_info)

            step = dict(
                wavelength=wavelength,
                mtcamera_exposure_info=mtcamera_exposure_info,
            )

            calibration_summary["steps"].append(step)
        return calibration_summary

    async def calculate_optimized_exposure_times(
        self, sequence_name: str
    ) -> dict[str, float]:
        """Calculates the exposure times for the electrometer and
        fiber spectrograph given the type and wavelength of the exposure
        and the length of the camera exposure time

        Parameters
        ----------
        sequence_name : `str`

        Returns
        -------
        dictionary of exposure times for the camera, electrometer, and fiber
        spectrograph
        dict(
            camera=0.0,
            electrometer=0.0,
            fiberspectrograph=0.0,
        )

        TO-DO: DM-44361
        """
        raise NotImplementedError()

    async def _take_data(
        self,
        mtcamera_exptime: float,
        mtcamera_filter: str,
        mtcamera_grating: str,
        exposure_metadata: dict,
        use_red_fiberspec: bool,
        use_blue_fiberspec: bool,
        fiber_spectrum_exposure_time: float,
        electrometer_exposure_time: float,
    ) -> dict:

        assert self.mtcamera is not None

        mtcamera_exposure_task = self.mtcamera.take_flats(
            mtcamera_exptime,
            nflats=1,
            filter=mtcamera_filter,
            grating=mtcamera_grating,
            **exposure_metadata,
        )
        exposures_done: asyncio.Future = asyncio.Future()

        fiber_spectrum_exposure_coroutine = self.take_fiber_spectrum(
            use_red=use_red_fiberspec,
            use_blue=use_blue_fiberspec,
            exposure_time=fiber_spectrum_exposure_time,
            exposures_done=exposures_done,
        )
        electrometer_exposure_coroutine = self.take_electrometer_scan(
            exposure_time=electrometer_exposure_time,
            exposures_done=exposures_done,
        )
        try:
            fiber_spectrum_exposure_task = asyncio.create_task(
                fiber_spectrum_exposure_coroutine
            )
            electrometer_exposure_task = asyncio.create_task(
                electrometer_exposure_coroutine
            )

            mtcamera_exposure_id = await mtcamera_exposure_task
        finally:
            exposures_done.set_result(True)
            fiber_spectrum_exposure_result, electrometer_exposure_result = (
                await asyncio.gather(
                    fiber_spectrum_exposure_task, electrometer_exposure_task
                )
            )

        return {
            mtcamera_exposure_id[0]: dict(
                fiber_spectrum_exposure_result=fiber_spectrum_exposure_result,
                electrometer_exposure_result=electrometer_exposure_result,
            )
        }

    async def take_electrometer_scan(
        self,
        exposure_time: float,
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

        while not exposures_done.done():

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
                    "is in enabled state and continuing."
                )
                await salobj.set_summary_state(self.electrometer, salobj.State.ENABLED)
        return electrometer_exposures

    async def take_fiber_spectrum(
        self,
        use_blue: bool,
        use_red: bool,
        exposure_time: float,
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
        spectrographs = []
        if use_blue:
            spectrographs.append(self.fiberspectrograph_blue)
        if use_red:
            spectrographs.append(self.fiberspectrograph_red)

        for fiberspec in spectrographs:
            fiberspec.evt_largeFileObjectAvailable.flush()

        fiber_spectrum_exposures = []

        while not exposures_done.done():

            try:
                tasks = []
                for fiberspec in spectrographs:
                    task = await fiberspec.cmd_expose.set_start(
                        duration=exposure_time,
                        numExposures=1,
                        timeout=exposure_time + self.long_timeout,
                    )
                    tasks.append(task)

                await asyncio.gather(*tasks)

            except salobj.AckTimeoutError:
                self.log.exception("Timed out waiting for the command ack. Continuing.")

            for fiberspec in spectrographs:
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

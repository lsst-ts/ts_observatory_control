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

    * Setup: Enable ATWhitelight and perform warmup. Enable
             ATMonochromator, Electrometer, and FiberSpectrographs.
    * Configure: Adjust ATWhitelight and ATMonochromator for type of flat.
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
        self.ls_select_led_location = 0.0  # um
        self.ls_select_laser_location = 20.0  # um

        self.laser_enclosure_temp = 20.0  # C

        # ALl this needs to go in a config yaml file somewhere.
        self.led_per_filter = {
            "u": ["M385L3"],
            "g": ["M455L4", "M505L4"],
            "r": ["M565L3", "M660L4"],
            "i": ["M730L5", "M780LP1"],
            "z": ["M850L3", "M940L3"],
            "y": ["M970L4"],
        }
        self.ls_led_locations = {
            "u": 0.0,
            "g": 1.0,
            "r": 2.0,
            "i": 3.0,
            "z": 4.0,
            "y": 5.0,
        }
        self.ls_led_focus = {"u": 0.0, "g": 1.0, "r": 2.0, "i": 3.0, "z": 4.0, "y": 5.0}

        self.exptime_dict: dict[str, float] = dict(
            camera=0.0,
            electrometer=0.0,
            fiberspectrograph=0.0,
        )
        self.delay = 1

    def ls_laser_focus(self, wavelength: float) -> float:
        """Function for evaluating the distance of the focus linear stage"""
        return 10.0

    async def change_wavelength(self, wavelength: float) -> None:
        """Change the TunableLaser wavelength setting"""

        task_wavelength = self.rem.tunablelaser.cmd_changeWavelength.set_start(
            wavelength=wavelength, timeout=self.long_long_timeout
        )
        task_focus = self.linearstage_laser_focus.cmd_moveAbsolute.set_start(
            distance=self.ls_laser_focus(wavelength)
        )

        await asyncio.gather(task_wavelength, task_focus)

    async def is_ready_for_flats(self) -> bool:
        """Add doctring"""
        # TODO (DM-44310): Implement method to check that the
        # system is ready for flats.
        return True

    async def setup_calsys(self, sequence_name: str) -> None:
        """If monochromatic flats, check that laser can be enabled,
        check temperature, turn on laser to warm up.
        move linearstage_select to correct location for
        Mono or Whitelight flats
        """
        config_data = self.get_calibration_configuration(sequence_name)

        calibration_type = getattr(CalibrationType, str(config_data["calib_type"]))

        if calibration_type == CalibrationType.WhiteLight:
            await self.linearstage_projector_select.cmd_moveAbsolute.set_start(
                distance=self.ls_select_led_location
            )
        else:
            await self.linearstage_projector_select.cmd_moveAbsolute.set_start(
                distance=self.ls_select_laser_location
            )
            await self.laser_setup(config_data["laser_mode"])
            await self.rem.tunablelaser.cmd_startPropagating.set_start()

    async def laser_setup(self, mode: str) -> None:
        """Is the laser on? what is the temp like? thermal control on?"""
        # check the thermal system is running
        # check set temp
        # check actual temp and determine if good enough
        # check the interlockState

        if mode == TunableLaser.Mode.CONTINUOUS:
            await self.rem.tunablelaser.cmd_setContinuousMode.set_start()
        elif (mode == TunableLaser.Mode.BURST) | (mode == TunableLaser.Mode.TRIGGER):
            await self.rem.tunablelaser.cmd_setBurstMode.set_start()

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

        calibration_type = getattr(CalibrationType, str(config_data["calib_type"]))
        filter_name = config_data[
            "filter"
        ]  # not sure if this is an enumeration somewhere?

        task_setup_camera = (
            self.mtcamera.setup_instrument(
                filter=config_data["atspec_filter"],
                grating=config_data["atspec_grating"],
            )
            if self.mtcamera is not None and config_data["use_camera"]
            else utils.make_done_future()
        )
        if self.mtcamera is None and config_data["use_camera"]:
            raise RuntimeError(
                f"MTCamera is not defined but {config_name} requires it. "
                "Make sure you are instantiating ComCam and passing it to MTCalsys."
            )

        if calibration_type == CalibrationType.WhiteLight:
            leds_ = self.led_per_filter[filter_name]
            task_select_wavelength = (
                self.linearstage_led_select.cmd_moveAbsolute.set_start(
                    distance=self.ls_led_locations[filter_name]
                )
            )
            task_adjust_focus = self.linearstage_led_focus.cmd_moveAbsolute.set_start(
                distance=self.ls_led_focus[filter_name]
            )
            task_turn_on = self.rem.ledprojector.cmd_switchOn.set_start(
                serialNumbers=leds_
            )

            await asyncio.gather(
                task_select_wavelength,
                task_adjust_focus,
                task_turn_on,
                task_setup_camera,
            )

        elif calibration_type == CalibrationType.Mono:
            wavelengths = [400.0]  # function of filter_name
            task_select_wavelength = self.change_wavelength(wavelength=wavelengths[0])

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
            wavelength_width = float(
                config_data["wavelength_width"]
            )  # This doesn't make any sense
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
            await self.change_wavelength(wavelength=wavelength)
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
                        config_data["fiber_spectrum_exposure_time"]
                    ),
                    electrometer_exposure_time=float(
                        config_data["electrometer_exposure_time"]
                    ),
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
                            config_data["fiber_spectrum_exposure_time"]
                        ),
                        electrometer_exposure_time=float(
                            config_data["electrometer_exposure_time"]
                        ),
                    )
                    mtcamera_exposure_info.update(exposure_info)

            step = dict(
                wavelength=wavelength,
                mtcamera_exposure_info=mtcamera_exposure_info,
            )

            calibration_summary["steps"].append(step)
        return calibration_summary

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
        return getattr(self.rem, f"linearstage_{self.linearstage_led_focus_index}")

    @property
    def linearstage_laser_focus(self) -> salobj.Remote:
        return getattr(self.rem, f"linearstage_{self.linearstage_laser_focus_index}")

    @property
    def linearstage_led_select(self) -> salobj.Remote:
        return getattr(self.rem, f"linearstage_{self.linearstage_led_select_index}")

    @property
    def linearstage_projector_select(self) -> salobj.Remote:
        return getattr(self.rem, f"linearstage_{self.linearstage_select_index}")

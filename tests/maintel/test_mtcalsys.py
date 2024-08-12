# This file is part of ts_observatory_control
#
# Developed for the Vera Rubin Observatory Data Management System.
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

import asyncio
import logging
import types
import unittest.mock

import numpy as np
from lsst.ts.observatory.control.maintel.comcam import ComCam, ComCamUsages
from lsst.ts.observatory.control.maintel.mtcalsys import MTCalsys, MTCalsysUsages
from lsst.ts.observatory.control.mock import RemoteGroupAsyncMock
from lsst.ts.utils import index_generator


class TestMTCalsys(RemoteGroupAsyncMock):

    @property
    def remote_group(self) -> MTCalsys:
        """The remote_group property."""
        return self.mtcalsys

    async def setup_mocks(self) -> None:
        self.mtcalsys.rem.electrometer_103.configure_mock(
            **{
                "evt_largeFileObjectAvailable.next.side_effect": self.mock_electrometer_lfoa
            }
        )
        self.mtcalsys.rem.fiberspectrograph_1.configure_mock(
            **{
                "evt_largeFileObjectAvailable.next.side_effect": self.mock_fiberspectrograph_lfoa
            }
        )

    async def setup_types(self) -> None:
        pass

    @classmethod
    def setUpClass(cls) -> None:
        """This classmethod is only called once, when preparing the unit
        test.
        """

        cls.log = logging.getLogger(cls.__name__)

        # Pass in a string as domain to prevent MTCalsys from trying to create
        # a domain by itself. When using DryTest usage, the class won't create
        # any remote. When this method is called there is no event loop
        # running so all asyncio facilities will fail to create. This is later
        # rectified in the asyncSetUp.
        cls.mtcalsys = MTCalsys(
            domain="FakeDomain", log=cls.log, intended_usage=MTCalsysUsages.DryTest
        )

        [
            setattr(cls.mtcalsys.check, component, True)  # type: ignore
            for component in cls.mtcalsys.components_attr
        ]

        cls.image_index = index_generator()
        cls.electrometer_projector_index = index_generator()
        cls.fiberspectrograph_blue_index = index_generator()
        cls.fiberspectrograph_red_index = index_generator()
        cls.linearstage_led_select_index = index_generator()
        cls.linearstage_led_focus_index = index_generator()
        cls.linearstage_laser_focus_index = index_generator()
        cls.linearstage_select_index = index_generator()

    def test_load_calibration_config_file(self) -> None:
        self.mtcalsys.load_calibration_config_file()

        assert "whitelight_r" in self.mtcalsys.get_configuration_options()

    async def test_setup_electrometers(self) -> None:

        config_data = self.mtcalsys.get_calibration_configuration("whitelight_r")

        await self.mtcalsys.setup_electrometers(
            mode=str(config_data["electrometer_mode"]),
            range=float(config_data["electrometer_range"]),
            integration_time=float(config_data["electrometer_integration_time"]),
        )

        await self.mtcalsys.electrometer.cmd_performZeroCalib.start.assert_awaited_with(
            timeout=self.mtcalsys.long_timeout
        )
        await self.mtcalsys.electrometer.cmd_setDigitalFilter.set_start.assert_awaited_with(
            activateFilter=False,
            activateAvgFilter=False,
            activateMedFilter=False,
            timeout=self.mtcalsys.long_timeout,
        )

    async def test_change_laser_wavelength(self) -> None:

        await self.mtcalsys.change_laser_wavelength(wavelength=500.0)

    async def test_prepare_for_whitelight_flat(self) -> None:
        mock_comcam = ComCam(
            "FakeDomain", log=self.log, intended_usage=ComCamUsages.DryTest
        )

        self.mtcalsys.mtcamera = mock_comcam

        try:
            await self.mtcalsys.prepare_for_flat("whitelight_r")
        finally:
            self.mtcalsys.mtcamera = None

        config_data = self.mtcalsys.get_calibration_configuration("whitelight_r")

        await self.mtcalsys.linearstage_led_select.cmd_moveAbsolute.assert_awaited_with(
            distance=config_data.get("led_location"), timeout=self.mtcalsys.long_timeout
        )

        await self.mtcalsys.linearstage_led_focus.cmd_moveAbsolute.assert_awaited_with(
            distance=config_data.get("led_focus"), timeout=self.mtcalsys.long_timeout
        )
        await self.mtcalsys.rem.ledprojector.cmd_switchOn.assert_awaited_with(
            serialNumbers=config_data.get("led_name"),
            timeout=self.mtcalsys.long_timeout,
        )

        mock_comcam.self.mtcamera.setup_instrument.assert_awaited_with(
            filter=config_data["mtcamera_filter"],
        )

    async def mock_end_readout(
        self, flush: bool, timeout: float
    ) -> types.SimpleNamespace:
        image_index = next(self.image_index)
        self.log.debug(f"Calling mock end readout: {image_index=}.")
        await asyncio.sleep(0.5)
        return types.SimpleNamespace(imageName=f"A_B_20240523_{image_index:04d}")

    async def mock_electrometer_lfoa(
        self, flush: bool, timeout: float
    ) -> types.SimpleNamespace:
        image_index = next(self.electrometer_index)
        self.log.debug(f"Calling mock electrometer lfoa: {image_index=}.")
        await asyncio.sleep(0.25)
        return types.SimpleNamespace(
            url=f"https://electrometer_20240523_{image_index:04d}"
        )

    async def mock_fiberspectrograph_lfoa(
        self, flush: bool, timeout: float
    ) -> types.SimpleNamespace:
        image_index = next(self.fiber_spectrograph_index)
        self.log.debug(f"Calling mock fiberspectrograph lfoa: {image_index=}.")
        await asyncio.sleep(0.3)
        return types.SimpleNamespace(
            url=f"https://fiberspectrograph_20240523_{image_index:04d}"
        )

    async def test_run_calibration_sequence_white_light(self) -> None:

        mock_comcam = ComCam(
            "FakeDomain", log=self.log, intended_usage=ComCamUsages.DryTest
        )
        mock_comcam.rem.mtcamera = unittest.mock.AsyncMock()
        mock_comcam.rem.mtcamera.evt_endReadout.next.configure_mock(
            side_effect=self.mock_end_readout
        )
        self.mtcalsys.mtcamera = mock_comcam

        try:
            calibration_summary = await self.mtcalsys.run_calibration_sequence(
                "whitelight_r", exposure_metadata=dict()
            )
        finally:
            self.mtcalsys.mtcamera = None

        config_data = self.mtcalsys.get_calibration_configuration("whitelight_r")

        assert "sequence_name" in calibration_summary
        assert calibration_summary["sequence_name"] == "whitelight_r"
        assert "steps" in calibration_summary
        self.log.debug("number of steps:", len(calibration_summary["steps"]))
        assert len(calibration_summary["steps"]) == len(config_data["exposure_times"])
        for mtcamera_exposure_info in calibration_summary["steps"][0][
            "mtcamera_exposure_info"
        ].values():
            assert len(mtcamera_exposure_info["electrometer_exposure_result"]) >= 1
            assert len(mtcamera_exposure_info["fiber_spectrum_exposure_result"]) >= 1

    async def test_run_calibration_sequence_mono(self) -> None:

        mock_comcam = ComCam(
            "FakeDomain", log=self.log, intended_usage=ComCamUsages.DryTest
        )
        mock_comcam.rem.mtcamera = unittest.mock.AsyncMock()
        mock_comcam.rem.mtcamera.evt_endReadout.next.configure_mock(
            side_effect=self.mock_end_readout
        )
        self.mtcalsys.mtcamera = mock_comcam

        try:
            calibration_summary = await self.mtcalsys.run_calibration_sequence(
                "scan_r", exposure_metadata=dict()
            )
        finally:
            self.mtcalsys.mtcamera = None

        config_data = self.mtcalsys.get_calibration_configuration("scan_r")
        wavelength = float(config_data["wavelength"])
        wavelength_width = float(config_data["wavelength_width"])
        wavelength_resolution = float(config_data["wavelength_resolution"])
        wavelength_start = wavelength - wavelength_width / 2.0
        wavelength_end = wavelength + wavelength_width / 2.0

        calibration_wavelengths = np.arange(
            wavelength_start, wavelength_end, wavelength_resolution
        )
        expected_change_wavelegths_calls = [
            unittest.mock.call(
                wavelength=wavelength, timeout=self.mtcalsys.long_long_timeout
            )
            for wavelength in calibration_wavelengths
        ]

        assert "sequence_name" in calibration_summary
        assert calibration_summary["sequence_name"] == "scan_r"
        assert "steps" in calibration_summary
        assert len(calibration_summary["steps"]) == 51
        assert (
            len(calibration_summary["steps"][0]["mtcamera_exposure_info"])
            == len(config_data["exposure_times"]) * 2
        )
        for mtcamera_exposure_info in calibration_summary["steps"][0][
            "mtcamera_exposure_info"
        ].values():
            assert len(mtcamera_exposure_info["electrometer_exposure_result"]) >= 1
            assert len(mtcamera_exposure_info["fiber_spectrum_exposure_result"]) >= 1
        self.mtcalsys.change_laser_wavelength(
            wavelength=expected_change_wavelegths_calls
        )

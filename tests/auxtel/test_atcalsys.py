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
import pytest
from lsst.ts.observatory.control.auxtel.atcalsys import ATCalsys, ATCalsysUsages
from lsst.ts.observatory.control.auxtel.latiss import LATISS, LATISSUsages
from lsst.ts.observatory.control.mock import RemoteGroupAsyncMock
from lsst.ts.utils import index_generator
from lsst.ts.xml.enums.ATMonochromator import Grating


class TestATCalsys(RemoteGroupAsyncMock):

    @property
    def remote_group(self) -> ATCalsys:
        """The remote_group property."""
        return self.atcalsys

    async def setup_mocks(self) -> None:
        self.atcalsys.rem.electrometer_201.configure_mock(
            **{
                "evt_largeFileObjectAvailable.next.side_effect": self.mock_electrometer_lfoa
            }
        )
        self.atcalsys.rem.fiberspectrograph_3.configure_mock(
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

        # Pass in a string as domain to prevent ATCalsys from trying to create
        # a domain by itself. When using DryTest usage, the class won't create
        # any remote. When this method is called there is no event loop
        # running so all asyncio facilities will fail to create. This is later
        # rectified in the asyncSetUp.
        cls.atcalsys = ATCalsys(
            domain="FakeDomain", log=cls.log, intended_usage=ATCalsysUsages.DryTest
        )

        [
            setattr(cls.atcalsys.check, component, True)  # type: ignore
            for component in cls.atcalsys.components_attr
        ]

        cls.image_index = index_generator()
        cls.fiber_spectrograph_index = index_generator()
        cls.electrometer_index = index_generator()

    def test_load_calibration_config_file(self) -> None:
        self.atcalsys.load_calibration_config_file()

        assert "at_whitelight_r" in self.atcalsys.get_configuration_options()

    async def test_setup_electrometers(self) -> None:

        config_data = self.atcalsys.get_calibration_configuration("at_whitelight_r")

        await self.atcalsys.setup_electrometers(
            mode=str(config_data["electrometer_mode"]),
            range=float(config_data["electrometer_range"]),
            integration_time=float(config_data["electrometer_integration_time"]),
        )

        self.atcalsys.electrometer.cmd_performZeroCalib.start.assert_awaited_with(
            timeout=self.atcalsys.long_timeout
        )
        self.atcalsys.electrometer.cmd_setDigitalFilter.set_start.assert_awaited_with(
            activateFilter=False,
            activateAvgFilter=False,
            activateMedFilter=False,
            timeout=self.atcalsys.long_timeout,
        )

    async def test_change_wavelength(self) -> None:

        await self.atcalsys.change_wavelength(wavelength=500.0)

        self.atcalsys.rem.atmonochromator.cmd_changeWavelength.set_start.assert_awaited_with(
            wavelength=500.0, timeout=self.atcalsys.long_long_timeout
        )

    async def test_prepare_for_flat_no_latiss(self) -> None:

        with pytest.raises(
            RuntimeError,
            match="LATISS is not defined but at_whitelight_r requires it. "
            "Make sure you are instantiating LATISS and passing it to ATCalsys.",
        ):
            await self.atcalsys.prepare_for_flat("at_whitelight_r")

    async def test_prepare_for_flat(self) -> None:
        mock_latiss = LATISS(
            "FakeDomain", log=self.log, intended_usage=LATISSUsages.DryTest
        )
        mock_latiss.rem.atspectrograph = unittest.mock.AsyncMock()
        self.atcalsys.latiss = mock_latiss

        try:
            await self.atcalsys.prepare_for_flat("at_whitelight_r")
        finally:
            self.atcalsys.latiss = None

        config_data = self.atcalsys.get_calibration_configuration("at_whitelight_r")

        self.atcalsys.rem.atmonochromator.cmd_updateMonochromatorSetup.set_start.assert_awaited_with(
            wavelength=config_data["wavelength"],
            gratingType=getattr(Grating, config_data["monochromator_grating"]).value,
            fontExitSlitWidth=config_data["exit_slit"],
            fontEntranceSlitWidth=config_data["entrance_slit"],
            timeout=self.atcalsys.long_long_timeout,
        )
        mock_latiss.rem.atspectrograph.cmd_changeFilter.set_start.assert_awaited_with(
            filter=0,
            name=config_data["atspec_filter"],
            timeout=mock_latiss.long_timeout,
        )
        mock_latiss.rem.atspectrograph.cmd_changeDisperser.set_start.assert_awaited_with(
            disperser=0,
            name=config_data["atspec_grating"],
            timeout=mock_latiss.long_timeout,
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

        mock_latiss = LATISS(
            "FakeDomain", log=self.log, intended_usage=LATISSUsages.DryTest
        )
        mock_latiss.rem.atcamera = unittest.mock.AsyncMock()
        mock_latiss.rem.atspectrograph = unittest.mock.AsyncMock()
        mock_latiss.rem.atcamera.evt_endReadout.next.configure_mock(
            side_effect=self.mock_end_readout
        )
        self.atcalsys.latiss = mock_latiss

        try:
            calibration_summary = await self.atcalsys.run_calibration_sequence(
                "at_whitelight_r", exposure_metadata=dict()
            )
        finally:
            self.atcalsys.latiss = None

        config_data = self.atcalsys.get_calibration_configuration("at_whitelight_r")

        assert "sequence_name" in calibration_summary
        assert calibration_summary["sequence_name"] == "at_whitelight_r"
        assert "steps" in calibration_summary
        assert len(calibration_summary["steps"]) == 1
        assert len(calibration_summary["steps"][0]["latiss_exposure_info"]) == len(
            config_data["exposure_times"]
        )
        for latiss_exposure_info in calibration_summary["steps"][0][
            "latiss_exposure_info"
        ].values():
            assert len(latiss_exposure_info["electrometer_exposure_result"]) >= 1
            assert len(latiss_exposure_info["fiber_spectrum_exposure_result"]) >= 1

    async def test_run_calibration_sequence_mono(self) -> None:

        mock_latiss = LATISS(
            "FakeDomain", log=self.log, intended_usage=LATISSUsages.DryTest
        )
        mock_latiss.rem.atcamera = unittest.mock.AsyncMock()
        mock_latiss.rem.atcamera.evt_endReadout.next.configure_mock(
            side_effect=self.mock_end_readout
        )
        mock_latiss.rem.atspectrograph = unittest.mock.AsyncMock()
        self.atcalsys.latiss = mock_latiss

        try:
            calibration_summary = await self.atcalsys.run_calibration_sequence(
                "scan_r", exposure_metadata=dict()
            )
        finally:
            self.atcalsys.latiss = None

        config_data = self.atcalsys.get_calibration_configuration("scan_r")
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
                wavelength=wavelength, timeout=self.atcalsys.long_long_timeout
            )
            for wavelength in calibration_wavelengths
        ]

        assert "sequence_name" in calibration_summary
        assert calibration_summary["sequence_name"] == "scan_r"
        assert "steps" in calibration_summary
        assert len(calibration_summary["steps"]) == 30
        assert (
            len(calibration_summary["steps"][0]["latiss_exposure_info"])
            == len(config_data["exposure_times"]) * 2
        )
        for latiss_exposure_info in calibration_summary["steps"][0][
            "latiss_exposure_info"
        ].values():
            assert len(latiss_exposure_info["electrometer_exposure_result"]) >= 1
            assert len(latiss_exposure_info["fiber_spectrum_exposure_result"]) >= 1
        self.atcalsys.rem.atmonochromator.cmd_changeWavelength.set_start.assert_has_awaits(
            expected_change_wavelegths_calls
        )

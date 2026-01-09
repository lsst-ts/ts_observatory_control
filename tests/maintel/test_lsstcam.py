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
import json
import logging
import typing
from unittest.mock import AsyncMock, call, patch

import pytest
from lsst.ts.observatory.control.maintel.lsstcam import LSSTCam, LSSTCamUsages
from lsst.ts.observatory.control.mock.base_camera_async_mock import BaseCameraAsyncMock
from lsst.ts.observatory.control.utils.roi_spec import ROI, ROICommon, ROISpec


class TestLSSTCam(BaseCameraAsyncMock):
    @classmethod
    def setUpClass(cls) -> None:
        """This classmethod is only called once, when preparing the unit
        test.
        """

        cls.log = logging.getLogger(__name__)

        cls.lsstcam = LSSTCam(
            domain="FakeDomain",
            log=cls.log,
            intended_usage=LSSTCamUsages.DryTest,
        )

        cls.lsstcam._roi_spec_json = '{"roi": "default"}'

        return super().setUpClass()

    @property
    def remote_group(self) -> LSSTCam:
        return self.lsstcam

    async def setup_types(self) -> None:
        self.end_readout = self.get_sample(
            component="MTCamera",
            topic="logevent_endReadout",
        )

        self.start_integration = self.get_sample(
            component="MTCamera",
            topic="logevent_startIntegration",
        )

    async def test_setup_instrument(self) -> None:
        # OK when no filter requested
        await self.lsstcam.setup_instrument(filter=None)
        self.assert_setup_instrument(dict(filter=None))

        # Should raise when requesting a filter change without MTCS
        with self.assertRaises(RuntimeError):
            await self.lsstcam.setup_instrument(filter="band1")

        # invalid keyword still raises
        with self.assertRaises(RuntimeError):
            await self.lsstcam.setup_instrument(invalid_key_word=123)

    async def test_setup_instrument_with_mtcs(self) -> None:
        valid_entry: typing.Dict[str, typing.Union[int, float, str, None]] = dict(
            filter="band1"
        )

        mock_mtcs = AsyncMock()
        mock_mtcs.check.mtmount = True
        mock_mtcs.check.mtptg = True
        mock_mtcs.check.mtrotator = True

        self.lsstcam.mtcs = mock_mtcs

        await self.lsstcam.setup_instrument(**valid_entry)
        self.lsstcam.mtcs.assert_has_calls(
            [
                call.stop_tracking(),
                call.stop_rotator(),
                call.move_rotator(position=self.lsstcam.rotator_filter_change_position),
            ],
            any_order=False,
        )

        self.assert_setup_instrument(valid_entry)

    async def test_setup_instrument_with_mtcs_rotator_disabled(self) -> None:
        valid_entry: typing.Dict[str, typing.Union[int, float, str, None]] = dict(
            filter="band1"
        )

        mock_mtcs = AsyncMock()
        mock_mtcs.check.mtmount = True
        mock_mtcs.check.mtptg = True
        mock_mtcs.check.mtrotator = False
        self.lsstcam.mtcs = mock_mtcs

        await self.lsstcam.setup_instrument(**valid_entry)

        self.assert_setup_instrument(valid_entry)
        mock_mtcs.stop_tracking.assert_not_awaited()
        mock_mtcs.move_rotator.assert_not_awaited()

    async def test_setup_instrument_with_mtcs_mount_disabled(self) -> None:
        valid_entry: typing.Dict[str, typing.Union[int, float, str, None]] = dict(
            filter="band1"
        )

        mock_mtcs = AsyncMock()
        mock_mtcs.check.mtmount = False
        mock_mtcs.check.mtptg = True
        mock_mtcs.check.mtrotator = True
        self.lsstcam.mtcs = mock_mtcs

        await self.lsstcam.setup_instrument(**valid_entry)

        self.assert_setup_instrument(valid_entry)
        mock_mtcs.stop_tracking.assert_not_awaited()
        mock_mtcs.move_rotator.assert_awaited_once_with(
            position=self.lsstcam.rotator_filter_change_position
        )

    async def test_setup_instrument_change_to_same_filter(self) -> None:
        valid_entry: typing.Dict[str, typing.Union[int, float, str, None]] = dict(
            filter="band1"
        )

        mock_mtcs = AsyncMock()
        mock_mtcs.check.mtmount = True
        mock_mtcs.check.mtptg = True
        mock_mtcs.check.mtrotator = True
        self.lsstcam.mtcs = mock_mtcs

        with patch.object(self.lsstcam, "get_current_filter", return_value="band1"):
            await self.lsstcam.setup_instrument(**valid_entry)

        self.lsstcam.rem.mtcamera.cmd_setFilter.set_start.assert_not_awaited()
        mock_mtcs.stop_tracking.assert_not_awaited()
        mock_mtcs.move_rotator.assert_not_awaited()

    async def test_take_bias(self) -> None:
        await self.assert_take_bias(
            nbias=10,
        )

    async def test_take_bias_test_type(self) -> None:
        await self.assert_take_bias(nbias=10, test_type="LBIAS")

    async def test_take_bias_reason(self) -> None:
        await self.assert_take_bias(
            nbias=10,
            reason="DAYLIGHT CALIB",
        )

    async def test_take_bias_program(self) -> None:
        await self.assert_take_bias(
            nbias=10,
            program="CALIB",
        )

    async def test_take_bias_test_type_reason_program(self) -> None:
        await self.assert_take_bias(
            nbias=10,
            test_type="LBIAS",
            reason="DAYLIGHT CALIB",
            program="CALIB",
        )

    async def test_take_darks(self) -> None:
        ndarks = 4
        exptime = 1.0
        await self.assert_take_darks(ndarks=ndarks, exptime=exptime)

    async def test_take_darks_test_type(self) -> None:
        await self.lsstcam.take_darks(
            ndarks=1,
            exptime=1.0,
            test_type="LDARK",
        )

    async def test_take_darks_reason(self) -> None:
        await self.lsstcam.take_darks(
            ndarks=1,
            exptime=1.0,
            reason="DAYLIGHT CALIB",
        )

    async def test_take_darks_program(self) -> None:
        await self.lsstcam.take_darks(
            ndarks=1,
            exptime=1.0,
            program="CALIB",
        )

    async def test_take_darks_test_type_reason_program(self) -> None:
        await self.lsstcam.take_darks(
            ndarks=1,
            exptime=1.0,
            test_type="LDARK",
            reason="DAYLIGHT CALIB",
            program="CALIB",
        )

    async def test_take_flats(self) -> None:
        nflats = 4
        exptime = 1.0
        filter_name = "band1"

        await self.assert_take_flats(
            nflats=nflats,
            exptime=exptime,
            filter=filter_name,
        )

        self.assert_setup_instrument(
            entry=dict(filter=filter_name),
        )

    async def test_take_flats_test_type(self) -> None:
        await self.assert_take_flats(
            nflats=1,
            exptime=1.0,
            test_type="LFLAT",
        )

    async def test_take_flats_reason(self) -> None:
        await self.assert_take_flats(
            nflats=1,
            exptime=1.0,
            reason="DAYLIGHT CALIB",
        )

    async def test_take_flats_program(self) -> None:
        await self.assert_take_flats(
            nflats=1,
            exptime=1.0,
            program="CALIB",
        )

    async def test_take_flats_test_type_reason_program(self) -> None:
        await self.assert_take_flats(
            nflats=1,
            exptime=1.0,
            test_type="LFLAT",
            reason="DAYLIGHT CALIB",
            program="CALIB",
        )

    async def test_take_object(self) -> None:
        nobj = 4
        exptime = 1.0
        filter_name = "band1"

        await self.assert_take_object(
            n=nobj,
            exptime=exptime,
            filter=filter_name,
        )

        self.assert_setup_instrument(entry=dict(filter=filter_name))

    async def test_take_object_atcs_sync_fail(self) -> None:
        with self.get_fake_tcs() as fake_atcs:
            fake_atcs.fail = True

            # should raise the same exception
            with pytest.raises(RuntimeError):
                await self.lsstcam.take_object(
                    n=4,
                    exptime=10.0,
                )

    async def test_take_object_atcs_sync(self) -> None:
        with self.get_fake_tcs() as fake_atcs:
            fake_atcs.fail = False

            await self.assert_take_object(
                n=4,
                exptime=10.0,
            )

            assert fake_atcs.called == 1

    async def test_take_object_test_type(self) -> None:
        await self.assert_take_object(
            n=1,
            exptime=1.0,
            test_type="LOBJECT",
        )

    async def test_take_object_reason(self) -> None:
        await self.assert_take_object(
            n=1,
            exptime=1.0,
            reason="UNIT TEST",
        )

    async def test_take_object_program(self) -> None:
        await self.assert_take_object(
            n=1,
            exptime=1.0,
            program="UTEST",
        )

    async def test_take_object_test_type_reason_program(self) -> None:
        await self.assert_take_object(
            n=1,
            exptime=1.0,
            test_type="LOBJECT",
            reason="UNIT TEST",
            program="UTEST",
        )

    async def test_take_engtest(self) -> None:
        await self.assert_take_engtest(
            n=1,
            exptime=1.0,
        )

    async def test_take_engtest_test_type(self) -> None:
        await self.lsstcam.take_engtest(
            n=1,
            exptime=1.0,
            test_type="LENGTEST",
        )

    async def test_take_engtest_reason(self) -> None:
        await self.lsstcam.take_engtest(
            n=1,
            exptime=1.0,
            reason="UNIT TEST",
        )

    async def test_take_engtest_program(self) -> None:
        await self.lsstcam.take_engtest(
            n=1,
            exptime=1.0,
            program="UTEST",
        )

    async def test_take_engtest_test_type_reason_program(self) -> None:
        await self.lsstcam.take_engtest(
            n=1,
            exptime=1.0,
            test_type="LENGTEST",
            reason="UNIT TEST",
            program="UTEST",
        )

    async def test_instrument_parameters(self) -> None:
        valid_keywords = ["filter"]

        for key in valid_keywords:
            with self.subTest(test="valid_keywords", key=key):
                self.lsstcam.check_kwargs(**{key: "test"})

        invalid_keyword_sample = [
            "Filter",
            "Grating",
            "LinearStage",
            "frilter",
            "gating",
            "linearstate",
        ]

        for key in invalid_keyword_sample:
            with self.subTest(test="invalid_keywords", key=key):
                with pytest.raises(RuntimeError):
                    self.lsstcam.check_kwargs(**{key: "test"})

    async def test_take_focus(self) -> None:
        await self.assert_take_focus(
            n=1,
            exptime=1.0,
        )

    async def test_take_cwfs(self) -> None:
        await self.assert_take_cwfs(
            n=1,
            exptime=1.0,
        )

    async def test_take_acq(self) -> None:
        await self.assert_take_acq()

    async def test_take_stuttered(self) -> None:
        await self.assert_take_stuttered(
            n=1,
            exptime=0.1,
            n_shift=4,
            row_shift=100,
        )

    async def test_take_indome(self) -> None:
        await self.assert_take_indome(
            n=1,
            exptime=1.0,
        )

    async def test_take_indome_test_type(self) -> None:
        await self.assert_take_indome(
            n=1,
            exptime=1.0,
            test_type="LINDOME",
        )

    async def test_take_indome_reason(self) -> None:
        await self.assert_take_indome(
            n=1,
            exptime=1.0,
            reason="UNIT TEST",
        )

    async def test_take_indome_program(self) -> None:
        await self.assert_take_indome(
            n=1,
            exptime=1.0,
            program="UTEST",
        )

    async def test_take_indome_test_type_reason_program(self) -> None:
        await self.assert_take_indome(
            n=1,
            exptime=1.0,
            test_type="LINDOME",
            reason="UNIT TEST",
            program="UTEST",
        )

    async def test_take_cbp(self) -> None:
        await self.assert_take_cbp(
            n=1,
            exptime=1.0,
        )

    async def test_take_cbp_test_type(self) -> None:
        await self.assert_take_cbp(
            n=1,
            exptime=1.0,
            test_type="LCBP",
        )

    async def test_take_cbp_reason(self) -> None:
        await self.assert_take_cbp(
            n=1,
            exptime=1.0,
            reason="UNIT TEST",
        )

    async def test_take_cbp_program(self) -> None:
        await self.assert_take_cbp(
            n=1,
            exptime=1.0,
            program="UTEST",
        )

    async def test_take_cbp_test_type_reason_program(self) -> None:
        await self.assert_take_cbp(
            n=1,
            exptime=1.0,
            test_type="LCBP",
            reason="UNIT TEST",
            program="UTEST",
        )

    async def test_take_sflat(self) -> None:
        await self.assert_take_sflat(
            n=1,
            exptime=1.0,
        )

    async def test_take_sflat_test_type(self) -> None:
        await self.assert_take_sflat(
            n=1,
            exptime=1.0,
            test_type="LSFLAT",
        )

    async def test_take_sflat_reason(self) -> None:
        await self.assert_take_sflat(
            n=1,
            exptime=1.0,
            reason="UNIT TEST",
        )

    async def test_take_sflat_program(self) -> None:
        await self.assert_take_sflat(
            n=1,
            exptime=1.0,
            program="UTEST",
        )

    async def test_take_sflat_test_type_reason_program(self) -> None:
        await self.assert_take_sflat(
            n=1,
            exptime=1.0,
            test_type="LSFLAT",
            reason="UNIT TEST",
            program="UTEST",
        )

    async def test_take_dflat(self) -> None:
        await self.assert_take_dflat(
            n=1,
            exptime=1.0,
        )

    async def test_take_dflat_test_type(self) -> None:
        await self.assert_take_dflat(
            n=1,
            exptime=1.0,
            test_type="LDFLAT",
        )

    async def test_take_dflat_reason(self) -> None:
        await self.assert_take_dflat(
            n=1,
            exptime=1.0,
            reason="UNIT TEST",
        )

    async def test_take_dflat_program(self) -> None:
        await self.assert_take_dflat(
            n=1,
            exptime=1.0,
            program="UTEST",
        )

    async def test_take_dflat_test_type_reason_program(self) -> None:
        await self.assert_take_dflat(
            n=1,
            exptime=1.0,
            test_type="LDFLAT",
            reason="UNIT TEST",
            program="UTEST",
        )

    async def test_init_guider(self) -> None:
        roi = ROI(
            segment=3,
            start_row=260,
            start_col=162,
        )

        roi_common = ROICommon(
            rows=100,
            cols=100,
            integration_time_millis=200,
        )

        roi_spec = ROISpec(
            common=roi_common,
            roi=dict(
                R40_SG0=roi,
                R01_SG0=roi,
                R02_SG0=roi,
                R03_SG0=roi,
            ),
        )

        # initialize guiders
        await self.lsstcam.init_guider(roi_spec=roi_spec)

        roi_spec_dict = roi_spec.model_dump()
        roi = roi_spec_dict.pop("roi")
        roi_spec_dict.update(roi)
        expected_roi_spec_json = json.dumps(roi_spec_dict, separators=(",", ":"))

        assert self.lsstcam._roi_spec_json == expected_roi_spec_json

    async def test_set_init_guider(self) -> None:
        roi = ROI(
            segment=3,
            start_row=260,
            start_col=162,
        )

        roi_common = ROICommon(
            rows=100,
            cols=100,
            integration_time_millis=200,
        )

        roi_spec = ROISpec(
            common=roi_common,
            roi=dict(
                R40_SG0=roi,
                R01_SG0=roi,
                R02_SG0=roi,
                R03_SG0=roi,
            ),
        )

        # initialize guiders
        await self.lsstcam.init_guider(roi_spec=roi_spec)

        await self.lsstcam.set_init_guider()
        await self.lsstcam.take_object(n=2, exptime=30)
        roi_spec_dict = roi_spec.model_dump()
        roi = roi_spec_dict.pop("roi")
        roi_spec_dict.update(roi)
        expected_roi_spec_json = json.dumps(roi_spec_dict, separators=(",", ":"))
        expected_calls = [
            call(roiSpec=expected_roi_spec_json, timeout=self.lsstcam.long_timeout),
        ]
        self.lsstcam.rem.mtcamera.cmd_initGuiders.set_start.assert_has_awaits(
            expected_calls
        )
        assert self.lsstcam.rem.mtcamera.cmd_initGuiders.set_start.call_count == 2

    def assert_setup_instrument(
        self, entry: typing.Dict[str, typing.Union[int, float, str, None]]
    ) -> None:
        """Assert setup instrument.

        Parameters
        ----------
        entry : typing.Dict[str, str]
            Parameters used to setup instrument.
        """
        selected_filter = entry.get("filter", None)

        if selected_filter is None:
            self.lsstcam.rem.mtcamera.cmd_setFilter.set_start.assert_not_awaited()
        else:
            self.lsstcam.rem.mtcamera.cmd_setFilter.set_start.assert_awaited_with(
                name=selected_filter, timeout=self.lsstcam.filter_change_timeout
            )

        self.lsstcam.rem.mtcamera.cmd_setFilter.set_start.reset_mock()

    async def test_take_spot(self) -> None:
        await self.lsstcam.take_spot(
            n=1,
            exptime=1.0,
        )

    async def test_take_spot_test_type(self) -> None:
        await self.lsstcam.take_spot(
            n=1,
            exptime=1.0,
            test_type="LSPOT",
        )

    async def test_take_spot_reason(self) -> None:
        await self.lsstcam.take_spot(
            n=1,
            exptime=1.0,
            reason="UNIT TEST",
        )

    async def test_take_spot_program(self) -> None:
        await self.lsstcam.take_spot(
            n=1,
            exptime=1.0,
            program="UTEST",
        )

    async def test_take_spot_test_type_reason_program(self) -> None:
        await self.lsstcam.take_spot(
            n=1,
            exptime=1.0,
            test_type="LSPOT",
            reason="UNIT TEST",
            program="UTEST",
        )

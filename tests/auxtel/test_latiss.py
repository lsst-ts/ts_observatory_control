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

import logging
import typing

import pytest
from lsst.ts.observatory.control.auxtel.latiss import LATISS, LATISSUsages
from lsst.ts.observatory.control.mock.base_camera_async_mock import BaseCameraAsyncMock


class TestLATISS(BaseCameraAsyncMock):
    @classmethod
    def setUpClass(cls) -> None:
        """This classmethod is only called once, when preparing the unit
        test.
        """

        cls.log = logging.getLogger(__name__)

        cls.latiss = LATISS(
            domain="FakeDomain",
            log=cls.log,
            intended_usage=LATISSUsages.DryTest,
        )

        return super().setUpClass()

    @property
    def remote_group(self) -> LATISS:
        return self.latiss

    async def setup_types(self) -> None:
        self.end_readout = self.get_sample(
            component="ATCamera",
            topic="logevent_endReadout",
        )

    async def test_setup_instrument(self) -> None:
        valid_entries: typing.List[
            typing.Dict[str, typing.Union[int, float, str, None]]
        ] = [
            dict(
                filter=None,
                grating=None,
                linear_stage=None,
            ),
            dict(filter=1),
            dict(grating=1),
            dict(linear_stage=101.12),
            dict(filter="band1"),
            dict(grating="grating1"),
            dict(filter="band2", grating="grating2", linear_stage=50.0),
        ]

        for entry in valid_entries:
            await self.latiss.setup_instrument(**entry)

            self.assert_setup_instrument(entry)

        with self.assertRaises(RuntimeError):
            await self.latiss.setup_instrument(invalid_key_word=123)

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
        await self.latiss.take_darks(
            ndarks=1,
            exptime=1.0,
            test_type="LDARK",
        )

    async def test_take_darks_reason(self) -> None:
        await self.latiss.take_darks(
            ndarks=1,
            exptime=1.0,
            reason="DAYLIGHT CALIB",
        )

    async def test_take_darks_program(self) -> None:
        await self.latiss.take_darks(
            ndarks=1,
            exptime=1.0,
            program="CALIB",
        )

    async def test_take_darks_test_type_reason_program(self) -> None:
        await self.latiss.take_darks(
            ndarks=1,
            exptime=1.0,
            test_type="LDARK",
            reason="DAYLIGHT CALIB",
            program="CALIB",
        )

    async def test_take_flats(self) -> None:
        nflats = 4
        exptime = 1.0
        filter_id = 1
        grating_id = 1
        linear_stage = 100.0

        await self.assert_take_flats(
            nflats=nflats,
            exptime=exptime,
            filter=filter_id,
            grating=grating_id,
            linear_stage=linear_stage,
        )

        self.assert_setup_instrument(
            entry=dict(filter=filter_id, grating=grating_id, linear_stage=linear_stage),
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
        filter_id = 1
        grating_id = 1
        linear_stage = 100.0

        await self.assert_take_object(
            n=nobj,
            exptime=exptime,
            filter=filter_id,
            grating=grating_id,
            linear_stage=linear_stage,
        )

        self.assert_setup_instrument(
            entry=dict(filter=filter_id, grating=grating_id, linear_stage=linear_stage),
        )

    async def test_take_object_atcs_sync_fail(self) -> None:
        with self.get_fake_tcs() as fake_atcs:
            fake_atcs.fail = True

            # should raise the same exception
            with pytest.raises(RuntimeError):
                await self.latiss.take_object(
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
        await self.latiss.take_engtest(
            n=1,
            exptime=1.0,
            test_type="LENGTEST",
        )

    async def test_take_engtest_reason(self) -> None:
        await self.latiss.take_engtest(
            n=1,
            exptime=1.0,
            reason="UNIT TEST",
        )

    async def test_take_engtest_program(self) -> None:
        await self.latiss.take_engtest(
            n=1,
            exptime=1.0,
            program="UTEST",
        )

    async def test_take_engtest_test_type_reason_program(self) -> None:
        await self.latiss.take_engtest(
            n=1,
            exptime=1.0,
            test_type="LENGTEST",
            reason="UNIT TEST",
            program="UTEST",
        )

    async def test_instrument_parameters(self) -> None:
        valid_keywords = ["filter", "grating", "linear_stage"]

        for key in valid_keywords:
            with self.subTest(test="valid_keywords", key=key):
                self.latiss.check_kwargs(**{key: "test"})

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
                    self.latiss.check_kwargs(**{key: "test"})

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
        if isinstance(selected_filter, int):
            self.latiss.rem.atspectrograph.cmd_changeFilter.set_start.assert_awaited_with(
                filter=selected_filter, name="", timeout=self.latiss.long_timeout
            )
        elif isinstance(selected_filter, str):
            self.latiss.rem.atspectrograph.cmd_changeFilter.set_start.assert_awaited_with(
                filter=0, name=selected_filter, timeout=self.latiss.long_timeout
            )
        else:
            self.latiss.rem.atspectrograph.cmd_changeFilter.set_start.assert_not_awaited()

        selected_grating = entry.get("grating", None)
        if isinstance(selected_grating, int):
            self.latiss.rem.atspectrograph.cmd_changeDisperser.set_start.assert_awaited_with(
                disperser=selected_grating, name="", timeout=self.latiss.long_timeout
            )
        elif isinstance(selected_grating, str):
            self.latiss.rem.atspectrograph.cmd_changeDisperser.set_start.assert_awaited_with(
                disperser=0, name=selected_grating, timeout=self.latiss.long_timeout
            )
        else:
            self.latiss.rem.atspectrograph.cmd_changeDisperser.set_start.assert_not_awaited()

        selected_linear_stage = entry.get("linear_stage", None)
        if selected_linear_stage is None:
            self.latiss.rem.atspectrograph.cmd_moveLinearStage.set_start.assert_not_awaited()
        else:
            self.latiss.rem.atspectrograph.cmd_moveLinearStage.set_start.assert_awaited_with(
                distanceFromHome=selected_linear_stage, timeout=self.latiss.long_timeout
            )

        self.latiss.rem.atspectrograph.cmd_changeFilter.set_start.reset_mock()
        self.latiss.rem.atspectrograph.cmd_changeDisperser.set_start.reset_mock()
        self.latiss.rem.atspectrograph.cmd_moveLinearStage.set_start.reset_mock()

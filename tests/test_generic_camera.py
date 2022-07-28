# This file is part of ts_observatory_control
#
# Developed for the Vera Rubin Observatory Telescope and Site Subsystem.
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
# along with this program. If not, see <https://www.gnu.org/licenses/>.

import pytest
import logging

from lsst.ts import utils

from lsst.ts.observatory.control import Usages
from lsst.ts.observatory.control.generic_camera import GenericCamera
from lsst.ts.observatory.control.mock.base_camera_async_mock import BaseCameraAsyncMock

HB_TIMEOUT = 5  # Heartbeat timeout (sec)
MAKE_TIMEOUT = 60  # Timeout for make_script (sec)

index_gen = utils.index_generator()


class TestGenericCamera(BaseCameraAsyncMock):
    log: logging.Logger
    generic_camera: GenericCamera

    @classmethod
    def setUpClass(cls) -> None:
        """This classmethod is only called once, when preparing the unit
        test.
        """

        cls.log = logging.getLogger(__name__)

        cls.generic_camera = GenericCamera(
            index=1,
            domain="FakeDomain",
            log=cls.log,
            intended_usage=Usages.DryTest,
        )
        return super().setUpClass()

    @property
    def remote_group(self) -> GenericCamera:
        return self.generic_camera

    async def setup_types(self) -> None:

        self.end_readout = self.get_sample(
            component="GenericCamera:1",
            topic="logevent_endReadout",
        )

    async def test_start_live_view(self) -> None:

        await self.generic_camera.start_live_view(exptime=1.0)

        self.generic_camera.rem.genericcamera_1.cmd_startLiveView.set_start.assert_awaited_with(
            expTime=1.0,
            timeout=self.generic_camera.fast_timeout,
        )

    async def test_stop_live_view(self) -> None:

        await self.generic_camera.stop_live_view()

        self.generic_camera.rem.genericcamera_1.cmd_stopLiveView.start.assert_awaited_with(
            timeout=self.generic_camera.fast_timeout,
        )

    async def test_take_stuttered(self) -> None:

        with self.assertRaises(AssertionError):
            await self.generic_camera.take_stuttered(
                exptime=5,
                n_shift=10,
                row_shift=50,
            )

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

        await self.generic_camera.take_darks(
            ndarks=1,
            exptime=1.0,
            test_type="LDARK",
        )

    async def test_take_darks_reason(self) -> None:
        await self.generic_camera.take_darks(
            ndarks=1,
            exptime=1.0,
            reason="DAYLIGHT CALIB",
        )

    async def test_take_darks_program(self) -> None:
        await self.generic_camera.take_darks(
            ndarks=1,
            exptime=1.0,
            program="CALIB",
        )

    async def test_take_darks_test_type_reason_program(self) -> None:
        await self.generic_camera.take_darks(
            ndarks=1,
            exptime=1.0,
            test_type="LDARK",
            reason="DAYLIGHT CALIB",
            program="CALIB",
        )

    async def test_take_flats(self) -> None:

        nflats = 4
        exptime = 1.0

        await self.assert_take_flats(
            nflats=nflats,
            exptime=exptime,
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

        await self.assert_take_object(
            n=nobj,
            exptime=exptime,
        )

    async def test_take_object_tcs_sync_fail(self) -> None:

        with self.get_fake_tcs() as fake_tcs:
            fake_tcs.fail = True

            # should raise the same exception
            with pytest.raises(RuntimeError):
                await self.generic_camera.take_object(
                    n=4,
                    exptime=10.0,
                )

    async def test_take_object_tcs_sync(self) -> None:

        with self.get_fake_tcs() as fake_tcs:
            fake_tcs.fail = False

            await self.assert_take_object(
                n=4,
                exptime=10.0,
            )

            assert fake_tcs.called == 1

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
        await self.generic_camera.take_engtest(
            n=1,
            exptime=1.0,
            test_type="LENGTEST",
        )

    async def test_take_engtest_reason(self) -> None:
        await self.generic_camera.take_engtest(
            n=1,
            exptime=1.0,
            reason="UNIT TEST",
        )

    async def test_take_engtest_program(self) -> None:
        await self.generic_camera.take_engtest(
            n=1,
            exptime=1.0,
            program="UTEST",
        )

    async def test_take_engtest_test_type_reason_program(self) -> None:
        await self.generic_camera.take_engtest(
            n=1,
            exptime=1.0,
            test_type="LENGTEST",
            reason="UNIT TEST",
            program="UTEST",
        )

    async def test_instrument_parameters(self) -> None:

        # Generic camera does not support any keword argument.
        invalid_keyword_sample = [
            "filter",
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
                    self.generic_camera.check_kwargs(**{key: "test"})

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

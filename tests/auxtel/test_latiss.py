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
import unittest

import pytest

from lsst.ts.utils import make_done_future
from lsst.ts.observatory.control.mock import LATISSMock
from lsst.ts.observatory.control.auxtel.latiss import LATISS, LATISSUsages
from lsst.ts.observatory.control.utils import RemoteGroupTestCase


class FakeATCS:
    """This class is used to test the the synchronization between the ATCS and
    LATISS.
    """

    def __init__(self):
        self._future = make_done_future()
        self._future_task = None
        self.fail = False
        self.called = 0

    def ready_to_take_data(self):
        if self._future.done():
            self.called += 1
            self._future = asyncio.Future()
            if self.fail:
                self._future_task = asyncio.create_task(self.wait_and_fail_future())
            else:
                self._future_task = asyncio.create_task(self.wait_and_set_future())

        return self._future

    async def wait_and_set_future(self):
        await asyncio.sleep(5.0)
        if not self._future.done():
            self._future.set_result(True)

    async def wait_and_fail_future(self):
        await asyncio.sleep(5.0)
        if not self._future.done():
            self._future.set_exception(RuntimeError("Failed."))


class TestLATISS(RemoteGroupTestCase, unittest.IsolatedAsyncioTestCase):
    async def basic_make_group(self, usage=None):
        self.atcs = FakeATCS()
        self.latiss_remote = LATISS(
            intended_usage=usage, tcs_ready_to_take_data=self.atcs.ready_to_take_data
        )
        self.latiss_mock = LATISSMock()
        return self.latiss_remote, self.latiss_mock

    async def test_take_bias(self):

        async with self.make_group(usage=LATISSUsages.TakeImage):

            nbias = 4
            await self.latiss_remote.take_bias(nbias=nbias)

            end_readout = self.latiss_remote.camera.evt_endReadout.get()

            assert end_readout.additionalKeys == "imageType:groupId:testType"

            assert self.latiss_mock.nimages == nbias
            assert len(self.latiss_mock.exptime_list) == nbias
            for i in range(nbias):
                assert self.latiss_mock.exptime_list[i] == 0.0
            assert self.latiss_mock.latiss_linear_stage is None
            assert self.latiss_mock.latiss_grating is None
            assert self.latiss_mock.latiss_filter is None

    async def test_take_bias_additional_keywords(self):

        async with self.make_group(usage=LATISSUsages.TakeImage):

            group_id = self.latiss_remote.next_group_id()

            await self.latiss_remote.take_bias(
                nbias=1,
                group_id=group_id,
            )

            end_readout = self.latiss_remote.camera.evt_endReadout.get()

            assert end_readout.additionalKeys == "imageType:groupId:testType"
            assert end_readout.additionalValues == f"BIAS:{group_id}:BIAS"

            await self.latiss_remote.take_bias(
                nbias=1,
                group_id=group_id,
                test_type="LBIAS",
            )

            end_readout = self.latiss_remote.camera.evt_endReadout.get()

            assert end_readout.additionalKeys == "imageType:groupId:testType"
            assert end_readout.additionalValues == f"BIAS:{group_id}:LBIAS"

            await self.latiss_remote.take_bias(
                nbias=1,
                group_id=group_id,
                reason="DAYLIGHT CALIB",
            )

            end_readout = self.latiss_remote.camera.evt_endReadout.get()

            assert end_readout.additionalKeys == "imageType:groupId:testType:reason"
            assert (
                end_readout.additionalValues == f"BIAS:{group_id}:BIAS:DAYLIGHT CALIB"
            )

            await self.latiss_remote.take_bias(
                nbias=1,
                group_id=group_id,
                program="CALIB",
            )

            end_readout = self.latiss_remote.camera.evt_endReadout.get()

            assert end_readout.additionalKeys == "imageType:groupId:testType:program"
            assert end_readout.additionalValues == f"BIAS:{group_id}:BIAS:CALIB"

            await self.latiss_remote.take_bias(
                nbias=1,
                group_id=group_id,
                test_type="LBIAS",
                reason="DAYLIGHT CALIB",
                program="CALIB",
            )

            end_readout = self.latiss_remote.camera.evt_endReadout.get()

            assert (
                end_readout.additionalKeys
                == "imageType:groupId:testType:reason:program"
            )
            assert (
                end_readout.additionalValues
                == f"BIAS:{group_id}:LBIAS:DAYLIGHT CALIB:CALIB"
            )

    async def test_take_darks(self):
        async with self.make_group(usage=LATISSUsages.TakeImage):
            ndarks = 4
            exptime = 1.0
            await self.latiss_remote.take_darks(ndarks=ndarks, exptime=exptime)

            end_readout = self.latiss_remote.camera.evt_endReadout.get()

            assert end_readout.additionalKeys == "imageType:groupId:testType"
            assert self.latiss_mock.nimages == ndarks
            assert len(self.latiss_mock.exptime_list) == ndarks
            for i in range(ndarks):
                assert self.latiss_mock.exptime_list[i] == exptime
            assert self.latiss_mock.latiss_linear_stage is None
            assert self.latiss_mock.latiss_grating is None
            assert self.latiss_mock.latiss_filter is None

    async def test_take_darks_additional_keywords(self):

        async with self.make_group(usage=LATISSUsages.TakeImage):

            group_id = self.latiss_remote.next_group_id()

            await self.latiss_remote.take_darks(
                ndarks=1,
                exptime=1.0,
                group_id=group_id,
            )

            end_readout = self.latiss_remote.camera.evt_endReadout.get()

            assert end_readout.additionalKeys == "imageType:groupId:testType"
            assert end_readout.additionalValues == f"DARK:{group_id}:DARK"

            await self.latiss_remote.take_darks(
                ndarks=1,
                exptime=1.0,
                group_id=group_id,
                test_type="LDARK",
            )

            end_readout = self.latiss_remote.camera.evt_endReadout.get()

            assert end_readout.additionalKeys == "imageType:groupId:testType"
            assert end_readout.additionalValues == f"DARK:{group_id}:LDARK"

            await self.latiss_remote.take_darks(
                ndarks=1,
                exptime=1.0,
                group_id=group_id,
                reason="DAYLIGHT CALIB",
            )

            end_readout = self.latiss_remote.camera.evt_endReadout.get()

            assert end_readout.additionalKeys == "imageType:groupId:testType:reason"
            assert (
                end_readout.additionalValues == f"DARK:{group_id}:DARK:DAYLIGHT CALIB"
            )

            await self.latiss_remote.take_darks(
                ndarks=1,
                exptime=1.0,
                group_id=group_id,
                program="CALIB",
            )

            end_readout = self.latiss_remote.camera.evt_endReadout.get()

            assert end_readout.additionalKeys == "imageType:groupId:testType:program"
            assert end_readout.additionalValues == f"DARK:{group_id}:DARK:CALIB"

            await self.latiss_remote.take_darks(
                ndarks=1,
                exptime=1.0,
                group_id=group_id,
                test_type="LDARK",
                reason="DAYLIGHT CALIB",
                program="CALIB",
            )

            end_readout = self.latiss_remote.camera.evt_endReadout.get()

            assert (
                end_readout.additionalKeys
                == "imageType:groupId:testType:reason:program"
            )
            assert (
                end_readout.additionalValues
                == f"DARK:{group_id}:LDARK:DAYLIGHT CALIB:CALIB"
            )

    async def test_take_flats(self):
        async with self.make_group(usage=LATISSUsages.TakeImage + LATISSUsages.Setup):
            nflats = 4
            exptime = 1.0
            filter_id = 1
            filter_name = f"filter{filter_id}"
            grating_id = 1
            grating_name = f"grating{grating_id}"
            linear_stage = 100.0

            await self.latiss_remote.take_flats(
                nflats=nflats,
                exptime=exptime,
                filter=filter_id,
                grating=grating_id,
                linear_stage=linear_stage,
            )

            end_readout = self.latiss_remote.camera.evt_endReadout.get()

            assert end_readout.additionalKeys == "imageType:groupId:testType"

            (
                current_filter,
                current_grating,
                current_stage_pos,
            ) = await self.latiss_remote.get_setup()

            assert self.latiss_mock.nimages == nflats
            assert len(self.latiss_mock.exptime_list) == nflats
            for i in range(nflats):
                assert self.latiss_mock.exptime_list[i] == exptime
            assert self.latiss_mock.latiss_filter == filter_id
            assert self.latiss_mock.latiss_grating == grating_id
            assert self.latiss_mock.latiss_linear_stage == linear_stage

            assert current_filter == filter_name
            assert current_grating == grating_name
            assert current_stage_pos == linear_stage

    async def test_take_flats_additional_keywords(self):

        async with self.make_group(usage=LATISSUsages.TakeImage):

            group_id = self.latiss_remote.next_group_id()

            await self.latiss_remote.take_flats(
                nflats=1,
                exptime=1.0,
                group_id=group_id,
            )

            end_readout = self.latiss_remote.camera.evt_endReadout.get()

            assert end_readout.additionalKeys == "imageType:groupId:testType"
            assert end_readout.additionalValues == f"FLAT:{group_id}:FLAT"

            await self.latiss_remote.take_flats(
                nflats=1,
                exptime=1.0,
                group_id=group_id,
                test_type="LFLAT",
            )

            end_readout = self.latiss_remote.camera.evt_endReadout.get()

            assert end_readout.additionalKeys == "imageType:groupId:testType"
            assert end_readout.additionalValues == f"FLAT:{group_id}:LFLAT"

            await self.latiss_remote.take_flats(
                nflats=1,
                exptime=1.0,
                group_id=group_id,
                reason="DAYLIGHT CALIB",
            )

            end_readout = self.latiss_remote.camera.evt_endReadout.get()

            assert end_readout.additionalKeys == "imageType:groupId:testType:reason"
            assert (
                end_readout.additionalValues == f"FLAT:{group_id}:FLAT:DAYLIGHT CALIB"
            )

            await self.latiss_remote.take_flats(
                nflats=1,
                exptime=1.0,
                group_id=group_id,
                program="CALIB",
            )

            end_readout = self.latiss_remote.camera.evt_endReadout.get()

            assert end_readout.additionalKeys == "imageType:groupId:testType:program"
            assert end_readout.additionalValues == f"FLAT:{group_id}:FLAT:CALIB"

            await self.latiss_remote.take_flats(
                nflats=1,
                exptime=1.0,
                group_id=group_id,
                test_type="LFLAT",
                reason="DAYLIGHT CALIB",
                program="CALIB",
            )

            end_readout = self.latiss_remote.camera.evt_endReadout.get()

            assert (
                end_readout.additionalKeys
                == "imageType:groupId:testType:reason:program"
            )
            assert (
                end_readout.additionalValues
                == f"FLAT:{group_id}:LFLAT:DAYLIGHT CALIB:CALIB"
            )

    async def test_take_object(self):
        async with self.make_group(usage=LATISSUsages.TakeImage + LATISSUsages.Setup):

            nobj = 4
            exptime = 1.0
            filter_id = 1
            filter_name = f"filter{filter_id}"
            grating_id = 1
            grating_name = f"grating{grating_id}"
            linear_stage = 100.0

            await self.latiss_remote.take_object(
                n=nobj,
                exptime=exptime,
                filter=filter_id,
                grating=grating_id,
                linear_stage=linear_stage,
            )

            end_readout = self.latiss_remote.camera.evt_endReadout.get()

            assert end_readout.additionalKeys == "imageType:groupId:testType"

            (
                current_filter,
                current_grating,
                current_stage_pos,
            ) = await self.latiss_remote.get_setup()

            assert self.latiss_mock.nimages == nobj
            assert len(self.latiss_mock.exptime_list) == nobj
            for i in range(nobj):
                assert self.latiss_mock.exptime_list[i] == exptime
            assert self.latiss_mock.latiss_filter == filter_id
            assert self.latiss_mock.latiss_grating == grating_id
            assert self.latiss_mock.latiss_linear_stage == linear_stage

            assert current_filter == filter_name
            assert current_grating == grating_name
            assert current_stage_pos == linear_stage

            # Test case where synchronization fails
            self.atcs.fail = True

            # should raise the same exception
            with pytest.raises(RuntimeError):
                await self.latiss_remote.take_object(
                    n=nobj,
                    exptime=exptime,
                )

            # Test case where synchronization is not setup
            self.latiss_remote.ready_to_take_data = None

            nobj_2 = 2
            exptime = 0.5
            filter_id = 2
            filter_name = f"filter{filter_id}"
            grating_id = 2
            grating_name = f"grating{grating_id}"
            linear_stage = 50.0

            await self.latiss_remote.take_object(
                n=nobj_2,
                exptime=exptime,
                filter=filter_id,
                grating=grating_id,
                linear_stage=linear_stage,
            )

            (
                current_filter,
                current_grating,
                current_stage_pos,
            ) = await self.latiss_remote.get_setup()

            assert self.latiss_mock.nimages == nobj + nobj_2
            assert len(self.latiss_mock.exptime_list) == nobj + nobj_2
            for i in range(nobj, nobj + nobj_2):
                assert self.latiss_mock.exptime_list[i] == exptime
            assert self.latiss_mock.latiss_filter == filter_id
            assert self.latiss_mock.latiss_grating == grating_id
            assert self.latiss_mock.latiss_linear_stage == linear_stage

            assert current_filter == filter_name
            assert current_grating == grating_name
            assert current_stage_pos == linear_stage

            # Check ATCS synchronization. This is called only once per
            # take_object when synchronization is configured.
            assert self.atcs.called == 2

    async def test_take_object_additional_keywords(self):

        async with self.make_group(usage=LATISSUsages.TakeImage):

            group_id = self.latiss_remote.next_group_id()

            await self.latiss_remote.take_object(
                n=1,
                exptime=1.0,
                group_id=group_id,
            )

            end_readout = self.latiss_remote.camera.evt_endReadout.get()

            assert end_readout.additionalKeys == "imageType:groupId:testType"
            assert end_readout.additionalValues == f"OBJECT:{group_id}:OBJECT"

            await self.latiss_remote.take_object(
                n=1,
                exptime=1.0,
                group_id=group_id,
                test_type="LOBJECT",
            )

            end_readout = self.latiss_remote.camera.evt_endReadout.get()

            assert end_readout.additionalKeys == "imageType:groupId:testType"
            assert end_readout.additionalValues == f"OBJECT:{group_id}:LOBJECT"

            await self.latiss_remote.take_object(
                n=1,
                exptime=1.0,
                group_id=group_id,
                reason="UNIT TEST",
            )

            end_readout = self.latiss_remote.camera.evt_endReadout.get()

            assert end_readout.additionalKeys == "imageType:groupId:testType:reason"
            assert end_readout.additionalValues == f"OBJECT:{group_id}:OBJECT:UNIT TEST"

            await self.latiss_remote.take_object(
                n=1,
                exptime=1.0,
                group_id=group_id,
                program="UTEST",
            )

            end_readout = self.latiss_remote.camera.evt_endReadout.get()

            assert end_readout.additionalKeys == "imageType:groupId:testType:program"
            assert end_readout.additionalValues == f"OBJECT:{group_id}:OBJECT:UTEST"

            await self.latiss_remote.take_object(
                n=1,
                exptime=1.0,
                group_id=group_id,
                test_type="LOBJECT",
                reason="UNIT TEST",
                program="UTEST",
            )

            end_readout = self.latiss_remote.camera.evt_endReadout.get()

            assert (
                end_readout.additionalKeys
                == "imageType:groupId:testType:reason:program"
            )
            assert (
                end_readout.additionalValues
                == f"OBJECT:{group_id}:LOBJECT:UNIT TEST:UTEST"
            )

    async def test_take_engtest_additional_keywords(self):

        async with self.make_group(usage=LATISSUsages.TakeImage):

            group_id = self.latiss_remote.next_group_id()

            await self.latiss_remote.take_engtest(
                n=1,
                exptime=1.0,
                group_id=group_id,
            )

            end_readout = self.latiss_remote.camera.evt_endReadout.get()

            assert end_readout.additionalKeys == "imageType:groupId:testType"
            assert end_readout.additionalValues == f"ENGTEST:{group_id}:ENGTEST"

            await self.latiss_remote.take_engtest(
                n=1,
                exptime=1.0,
                group_id=group_id,
                test_type="LENGTEST",
            )

            end_readout = self.latiss_remote.camera.evt_endReadout.get()

            assert end_readout.additionalKeys == "imageType:groupId:testType"
            assert end_readout.additionalValues == f"ENGTEST:{group_id}:LENGTEST"

            await self.latiss_remote.take_engtest(
                n=1,
                exptime=1.0,
                group_id=group_id,
                reason="UNIT TEST",
            )

            end_readout = self.latiss_remote.camera.evt_endReadout.get()

            assert end_readout.additionalKeys == "imageType:groupId:testType:reason"
            assert (
                end_readout.additionalValues == f"ENGTEST:{group_id}:ENGTEST:UNIT TEST"
            )

            await self.latiss_remote.take_engtest(
                n=1,
                exptime=1.0,
                group_id=group_id,
                program="UTEST",
            )

            end_readout = self.latiss_remote.camera.evt_endReadout.get()

            assert end_readout.additionalKeys == "imageType:groupId:testType:program"
            assert end_readout.additionalValues == f"ENGTEST:{group_id}:ENGTEST:UTEST"

            await self.latiss_remote.take_engtest(
                n=1,
                exptime=1.0,
                group_id=group_id,
                test_type="LENGTEST",
                reason="UNIT TEST",
                program="UTEST",
            )

            end_readout = self.latiss_remote.camera.evt_endReadout.get()

            assert (
                end_readout.additionalKeys
                == "imageType:groupId:testType:reason:program"
            )
            assert (
                end_readout.additionalValues
                == f"ENGTEST:{group_id}:LENGTEST:UNIT TEST:UTEST"
            )

    async def test_instrument_parameters(self):
        async with self.make_group(usage=LATISSUsages.TakeImage):
            valid_keywords = ["filter", "grating", "linear_stage"]

            for key in valid_keywords:
                with self.subTest(test="valid_keywords", key=key):
                    self.latiss_remote.check_kwargs(**{key: "test"})

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
                        self.latiss_remote.check_kwargs(**{key: "test"})

    async def test_take_focus(self):
        async with self.make_group(usage=LATISSUsages.TakeImage):
            group_id = self.latiss_remote.next_group_id()

            await self.latiss_remote.take_focus(
                n=1,
                exptime=1.0,
                group_id=group_id,
            )

            self.assert_last_end_readout(
                additional_keys="imageType:groupId:testType",
                additional_values=f"FOCUS:{group_id}:FOCUS",
            )

    async def test_take_cwfs(self):
        async with self.make_group(usage=LATISSUsages.TakeImage):
            group_id = self.latiss_remote.next_group_id()

            await self.latiss_remote.take_cwfs(
                n=1,
                exptime=1.0,
                group_id=group_id,
            )

            self.assert_last_end_readout(
                additional_keys="imageType:groupId:testType",
                additional_values=f"CWFS:{group_id}:CWFS",
            )

    async def test_take_acq(self):
        async with self.make_group(usage=LATISSUsages.TakeImage):
            group_id = self.latiss_remote.next_group_id()

            await self.latiss_remote.take_acq(
                n=1,
                exptime=1.0,
                group_id=group_id,
            )

            self.assert_last_end_readout(
                additional_keys="imageType:groupId:testType",
                additional_values=f"ACQ:{group_id}:ACQ",
            )

    async def test_take_stuttered(self):
        async with self.make_group(usage=LATISSUsages.TakeImage):
            group_id = self.latiss_remote.next_group_id()

            await self.latiss_remote.take_stuttered(
                n=1,
                exptime=1.0,
                n_shift=20,
                row_shift=100,
                group_id=group_id,
            )

            self.assert_last_end_readout(
                additional_keys="imageType:groupId:testType",
                additional_values=f"STUTTERED:{group_id}:STUTTERED",
            )

    def assert_last_end_readout(self, additional_keys, additional_values):

        end_readout = self.latiss_remote.camera.evt_endReadout.get()

        assert end_readout.additionalKeys == additional_keys
        assert end_readout.additionalValues == additional_values

# This file is part of ts_observatory_control
#
# Developed for the Vera Rubin Observatory Telescope and Site System.
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
import unittest

from lsst.ts.observatory.control.maintel.comcam import ComCam, ComCamUsages
from lsst.ts.observatory.control.mock import ComCamMock
from lsst.ts.observatory.control.utils import RemoteGroupTestCase


class TestComCam(RemoteGroupTestCase, unittest.IsolatedAsyncioTestCase):
    async def basic_make_group(self, usage=None):
        self.comcam = ComCam(intended_usage=usage)
        self.comcam_mock = ComCamMock()
        return (self.comcam, self.comcam_mock)

    async def test_take_bias(self):
        async with self.make_group(usage=ComCamUsages.TakeImage):
            nbias = 3
            await self.comcam.take_bias(nbias=nbias)
            assert self.comcam_mock.nimages == nbias
            assert len(self.comcam_mock.exptime_list) == nbias
            for i in range(nbias):
                assert self.comcam_mock.exptime_list[i] == 0.0
            assert self.comcam_mock.camera_filter is None

    async def test_take_bias_additional_keywords(self):

        async with self.make_group(usage=ComCamUsages.TakeImage):

            group_id = self.comcam.next_group_id()

            await self.comcam.take_bias(
                nbias=1,
                group_id=group_id,
            )

            end_readout = self.comcam.camera.evt_endReadout.get()

            assert end_readout.additionalKeys == "imageType:groupId:testType"
            assert end_readout.additionalValues == f"BIAS:{group_id}:BIAS"

            await self.comcam.take_bias(
                nbias=1,
                group_id=group_id,
                test_type="LBIAS",
            )

            end_readout = self.comcam.camera.evt_endReadout.get()

            assert end_readout.additionalKeys == "imageType:groupId:testType"
            assert end_readout.additionalValues == f"BIAS:{group_id}:LBIAS"

            await self.comcam.take_bias(
                nbias=1,
                group_id=group_id,
                reason="DAYLIGHT CALIB",
            )

            end_readout = self.comcam.camera.evt_endReadout.get()

            assert end_readout.additionalKeys == "imageType:groupId:testType:reason"
            assert (
                end_readout.additionalValues == f"BIAS:{group_id}:BIAS:DAYLIGHT CALIB"
            )

            await self.comcam.take_bias(
                nbias=1,
                group_id=group_id,
                program="CALIB",
            )

            end_readout = self.comcam.camera.evt_endReadout.get()

            assert end_readout.additionalKeys == "imageType:groupId:testType:program"
            assert end_readout.additionalValues == f"BIAS:{group_id}:BIAS:CALIB"

            await self.comcam.take_bias(
                nbias=1,
                group_id=group_id,
                test_type="LBIAS",
                reason="DAYLIGHT CALIB",
                program="CALIB",
            )

            end_readout = self.comcam.camera.evt_endReadout.get()

            assert (
                end_readout.additionalKeys
                == "imageType:groupId:testType:reason:program"
            )
            assert (
                end_readout.additionalValues
                == f"BIAS:{group_id}:LBIAS:DAYLIGHT CALIB:CALIB"
            )

    async def test_take_darks(self):
        async with self.make_group(usage=ComCamUsages.TakeImage):
            ndarks = 3
            exptime = 1.0
            await self.comcam.take_darks(ndarks=ndarks, exptime=exptime)
            assert self.comcam_mock.nimages == ndarks
            assert len(self.comcam_mock.exptime_list) == ndarks
            for i in range(ndarks):
                assert self.comcam_mock.exptime_list[i] == exptime
            assert self.comcam_mock.camera_filter is None

    async def test_take_darks_additional_keywords(self):

        async with self.make_group(usage=ComCamUsages.TakeImage):

            group_id = self.comcam.next_group_id()

            await self.comcam.take_darks(
                ndarks=1,
                exptime=1.0,
                group_id=group_id,
            )

            end_readout = self.comcam.camera.evt_endReadout.get()

            assert end_readout.additionalKeys == "imageType:groupId:testType"
            assert end_readout.additionalValues == f"DARK:{group_id}:DARK"

            await self.comcam.take_darks(
                ndarks=1,
                exptime=1.0,
                group_id=group_id,
                test_type="LDARK",
            )

            end_readout = self.comcam.camera.evt_endReadout.get()

            assert end_readout.additionalKeys == "imageType:groupId:testType"
            assert end_readout.additionalValues == f"DARK:{group_id}:LDARK"

            await self.comcam.take_darks(
                ndarks=1,
                exptime=1.0,
                group_id=group_id,
                reason="DAYLIGHT CALIB",
            )

            end_readout = self.comcam.camera.evt_endReadout.get()

            assert end_readout.additionalKeys == "imageType:groupId:testType:reason"
            assert (
                end_readout.additionalValues == f"DARK:{group_id}:DARK:DAYLIGHT CALIB"
            )

            await self.comcam.take_darks(
                ndarks=1,
                exptime=1.0,
                group_id=group_id,
                program="CALIB",
            )

            end_readout = self.comcam.camera.evt_endReadout.get()

            assert end_readout.additionalKeys == "imageType:groupId:testType:program"
            assert end_readout.additionalValues == f"DARK:{group_id}:DARK:CALIB"

            await self.comcam.take_darks(
                ndarks=1,
                exptime=1.0,
                group_id=group_id,
                test_type="LDARK",
                reason="DAYLIGHT CALIB",
                program="CALIB",
            )

            end_readout = self.comcam.camera.evt_endReadout.get()

            assert (
                end_readout.additionalKeys
                == "imageType:groupId:testType:reason:program"
            )
            assert (
                end_readout.additionalValues
                == f"DARK:{group_id}:LDARK:DAYLIGHT CALIB:CALIB"
            )

    async def test_take_flats(self):
        async with self.make_group(usage=ComCamUsages.TakeImage):
            nflats = 3
            exptime = 1.0

            await self.comcam.take_flats(
                nflats=nflats,
                exptime=exptime,
            )
            assert self.comcam_mock.nimages == nflats
            assert len(self.comcam_mock.exptime_list) == nflats
            for i in range(nflats):
                assert self.comcam_mock.exptime_list[i] == exptime
            assert self.comcam_mock.camera_filter is None

    async def test_take_flats_additional_keywords(self):

        async with self.make_group(usage=ComCamUsages.TakeImage):

            group_id = self.comcam.next_group_id()

            await self.comcam.take_flats(
                nflats=1,
                exptime=1.0,
                group_id=group_id,
            )

            end_readout = self.comcam.camera.evt_endReadout.get()

            assert end_readout.additionalKeys == "imageType:groupId:testType"
            assert end_readout.additionalValues == f"FLAT:{group_id}:FLAT"

            await self.comcam.take_flats(
                nflats=1,
                exptime=1.0,
                group_id=group_id,
                test_type="LFLAT",
            )

            end_readout = self.comcam.camera.evt_endReadout.get()

            assert end_readout.additionalKeys == "imageType:groupId:testType"
            assert end_readout.additionalValues == f"FLAT:{group_id}:LFLAT"

            await self.comcam.take_flats(
                nflats=1,
                exptime=1.0,
                group_id=group_id,
                reason="DAYLIGHT CALIB",
            )

            end_readout = self.comcam.camera.evt_endReadout.get()

            assert end_readout.additionalKeys == "imageType:groupId:testType:reason"
            assert (
                end_readout.additionalValues == f"FLAT:{group_id}:FLAT:DAYLIGHT CALIB"
            )

            await self.comcam.take_flats(
                nflats=1,
                exptime=1.0,
                group_id=group_id,
                program="CALIB",
            )

            end_readout = self.comcam.camera.evt_endReadout.get()

            assert end_readout.additionalKeys == "imageType:groupId:testType:program"
            assert end_readout.additionalValues == f"FLAT:{group_id}:FLAT:CALIB"

            await self.comcam.take_flats(
                nflats=1,
                exptime=1.0,
                group_id=group_id,
                test_type="LFLAT",
                reason="DAYLIGHT CALIB",
                program="CALIB",
            )

            end_readout = self.comcam.camera.evt_endReadout.get()

            assert (
                end_readout.additionalKeys
                == "imageType:groupId:testType:reason:program"
            )
            assert (
                end_readout.additionalValues
                == f"FLAT:{group_id}:LFLAT:DAYLIGHT CALIB:CALIB"
            )

    async def test_take_flats_with_filter(self):
        async with self.make_group(usage=ComCamUsages.TakeImage):
            nflats = 3
            exptime = 1.0
            camera_filter = "r_07"

            await self.comcam.take_flats(
                nflats=nflats, exptime=exptime, filter=camera_filter
            )
            assert self.comcam_mock.nimages == nflats
            assert len(self.comcam_mock.exptime_list) == nflats
            for i in range(nflats):
                assert self.comcam_mock.exptime_list[i] == exptime
            assert self.comcam_mock.camera_filter == camera_filter

    async def test_take_object_additional_keywords(self):

        async with self.make_group(usage=ComCamUsages.TakeImage):

            group_id = self.comcam.next_group_id()

            await self.comcam.take_object(
                n=1,
                exptime=1.0,
                group_id=group_id,
            )

            end_readout = self.comcam.camera.evt_endReadout.get()

            assert end_readout.additionalKeys == "imageType:groupId:testType"
            assert end_readout.additionalValues == f"OBJECT:{group_id}:OBJECT"

            await self.comcam.take_object(
                n=1,
                exptime=1.0,
                group_id=group_id,
                test_type="LOBJECT",
            )

            end_readout = self.comcam.camera.evt_endReadout.get()

            assert end_readout.additionalKeys == "imageType:groupId:testType"
            assert end_readout.additionalValues == f"OBJECT:{group_id}:LOBJECT"

            await self.comcam.take_object(
                n=1,
                exptime=1.0,
                group_id=group_id,
                reason="UNIT TEST",
            )

            end_readout = self.comcam.camera.evt_endReadout.get()

            assert end_readout.additionalKeys == "imageType:groupId:testType:reason"
            assert end_readout.additionalValues == f"OBJECT:{group_id}:OBJECT:UNIT TEST"

            await self.comcam.take_object(
                n=1,
                exptime=1.0,
                group_id=group_id,
                program="UTEST",
            )

            end_readout = self.comcam.camera.evt_endReadout.get()

            assert end_readout.additionalKeys == "imageType:groupId:testType:program"
            assert end_readout.additionalValues == f"OBJECT:{group_id}:OBJECT:UTEST"

            await self.comcam.take_object(
                n=1,
                exptime=1.0,
                group_id=group_id,
                test_type="LOBJECT",
                reason="UNIT TEST",
                program="UTEST",
            )

            end_readout = self.comcam.camera.evt_endReadout.get()

            assert (
                end_readout.additionalKeys
                == "imageType:groupId:testType:reason:program"
            )
            assert (
                end_readout.additionalValues
                == f"OBJECT:{group_id}:LOBJECT:UNIT TEST:UTEST"
            )

    async def test_take_engtest_additional_keywords(self):

        async with self.make_group(usage=ComCamUsages.TakeImage):

            group_id = self.comcam.next_group_id()

            await self.comcam.take_engtest(
                n=1,
                exptime=1.0,
                group_id=group_id,
            )

            end_readout = self.comcam.camera.evt_endReadout.get()

            assert end_readout.additionalKeys == "imageType:groupId:testType"
            assert end_readout.additionalValues == f"ENGTEST:{group_id}:ENGTEST"

            await self.comcam.take_engtest(
                n=1,
                exptime=1.0,
                group_id=group_id,
                test_type="LENGTEST",
            )

            end_readout = self.comcam.camera.evt_endReadout.get()

            assert end_readout.additionalKeys == "imageType:groupId:testType"
            assert end_readout.additionalValues == f"ENGTEST:{group_id}:LENGTEST"

            await self.comcam.take_engtest(
                n=1,
                exptime=1.0,
                group_id=group_id,
                reason="UNIT TEST",
            )

            end_readout = self.comcam.camera.evt_endReadout.get()

            assert end_readout.additionalKeys == "imageType:groupId:testType:reason"
            assert (
                end_readout.additionalValues == f"ENGTEST:{group_id}:ENGTEST:UNIT TEST"
            )

            await self.comcam.take_engtest(
                n=1,
                exptime=1.0,
                group_id=group_id,
                program="UTEST",
            )

            end_readout = self.comcam.camera.evt_endReadout.get()

            assert end_readout.additionalKeys == "imageType:groupId:testType:program"
            assert end_readout.additionalValues == f"ENGTEST:{group_id}:ENGTEST:UTEST"

            await self.comcam.take_engtest(
                n=1,
                exptime=1.0,
                group_id=group_id,
                test_type="LENGTEST",
                reason="UNIT TEST",
                program="UTEST",
            )

            end_readout = self.comcam.camera.evt_endReadout.get()

            assert (
                end_readout.additionalKeys
                == "imageType:groupId:testType:reason:program"
            )
            assert (
                end_readout.additionalValues
                == f"ENGTEST:{group_id}:LENGTEST:UNIT TEST:UTEST"
            )

    async def test_take_spot_additional_keywords(self):

        async with self.make_group(usage=ComCamUsages.TakeImage):

            group_id = self.comcam.next_group_id()

            await self.comcam.take_spot(
                n=1,
                exptime=1.0,
                group_id=group_id,
            )

            end_readout = self.comcam.camera.evt_endReadout.get()

            assert end_readout.additionalKeys == "imageType:groupId:testType"
            assert end_readout.additionalValues == f"SPOT:{group_id}:SPOT"

            await self.comcam.take_spot(
                n=1,
                exptime=1.0,
                group_id=group_id,
                test_type="LSPOT",
            )

            end_readout = self.comcam.camera.evt_endReadout.get()

            assert end_readout.additionalKeys == "imageType:groupId:testType"
            assert end_readout.additionalValues == f"SPOT:{group_id}:LSPOT"

            await self.comcam.take_spot(
                n=1,
                exptime=1.0,
                group_id=group_id,
                reason="UNIT TEST",
            )

            end_readout = self.comcam.camera.evt_endReadout.get()

            assert end_readout.additionalKeys == "imageType:groupId:testType:reason"
            assert end_readout.additionalValues == f"SPOT:{group_id}:SPOT:UNIT TEST"

            await self.comcam.take_spot(
                n=1,
                exptime=1.0,
                group_id=group_id,
                program="UTEST",
            )

            end_readout = self.comcam.camera.evt_endReadout.get()

            assert end_readout.additionalKeys == "imageType:groupId:testType:program"
            assert end_readout.additionalValues == f"SPOT:{group_id}:SPOT:UTEST"

            await self.comcam.take_spot(
                n=1,
                exptime=1.0,
                group_id=group_id,
                test_type="LSPOT",
                reason="UNIT TEST",
                program="UTEST",
            )

            end_readout = self.comcam.camera.evt_endReadout.get()

            assert (
                end_readout.additionalKeys
                == "imageType:groupId:testType:reason:program"
            )
            assert (
                end_readout.additionalValues == f"SPOT:{group_id}:LSPOT:UNIT TEST:UTEST"
            )

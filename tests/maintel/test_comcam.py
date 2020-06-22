# This file is part of ts_observatory_control
#
# Developed for the LSST Telescope and Site System.
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
# import logging
import random
import unittest

import asynctest
import pytest

# from lsst.ts import salobj
from lsst.ts.observatory.control.maintel import ComCam
from lsst.ts.observatory.control.mock import ComCamMock
from lsst.ts.observatory.control.utils import RemoteGroupTestCase

random.seed(42)  # for set_random_lsst_dds_domain

# logging.basicConfig(level=logging.DEBUG)


class TestComCam(RemoteGroupTestCase, asynctest.TestCase):
    async def basic_make_group(self, usage=None):
        self.comcam = ComCam(intended_usage=usage)
        self.comcam_mock = ComCamMock()
        return (self.comcam, self.comcam_mock)

    async def test_take_bias(self):
        async with self.make_group():
            nbias = 10
            await self.comcam.take_bias(nbias=nbias)
            self.assertEqual(self.comcam_mock.nimages, nbias)
            self.assertEqual(len(self.comcam_mock.exptime_list), nbias)
            for i in range(nbias):
                self.assertEqual(self.comcam_mock.exptime_list[i], 0.0)
            self.assertIsNone(self.comcam_mock.camera_filter)

    async def test_take_darks(self):
        async with self.make_group():
            ndarks = 10
            exptime = 5.0
            await self.comcam.take_darks(ndarks=ndarks, exptime=exptime)
            self.assertEqual(self.comcam_mock.nimages, ndarks)
            self.assertEqual(len(self.comcam_mock.exptime_list), ndarks)
            for i in range(ndarks):
                self.assertEqual(self.comcam_mock.exptime_list[i], exptime)
            self.assertIsNone(self.comcam_mock.camera_filter)

    async def test_take_flats(self):
        async with self.make_group():
            nflats = 10
            exptime = 5.0

            await self.comcam.take_flats(
                nflats=nflats, exptime=exptime,
            )
            self.assertEqual(self.comcam_mock.nimages, nflats)
            self.assertEqual(len(self.comcam_mock.exptime_list), nflats)
            for i in range(nflats):
                self.assertEqual(self.comcam_mock.exptime_list[i], exptime)
            self.assertIsNone(self.comcam_mock.camera_filter)

    async def test_take_flats_with_filter(self):
        async with self.make_group():
            nflats = 10
            exptime = 5.0
            camera_filter = "r"

            with pytest.raises(NotImplementedError):
                await self.comcam.take_flats(
                    nflats=nflats, exptime=exptime, filter=camera_filter
                )
            self.assertEqual(self.comcam_mock.nimages, 0)
            self.assertEqual(len(self.comcam_mock.exptime_list), 0)
            self.assertIsNone(self.comcam_mock.camera_filter)


if __name__ == "__main__":
    unittest.main()

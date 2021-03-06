# This file is part of ts_observatory_control
#
# Developed for the LSST Data Management System.
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

import asynctest

from lsst.ts.observatory.control.mock import LATISSMock
from lsst.ts.observatory.control.auxtel.latiss import LATISS, LATISSUsages
from lsst.ts.observatory.control.utils import RemoteGroupTestCase


class TestLATISS(RemoteGroupTestCase, asynctest.TestCase):
    async def basic_make_group(self, usage=None):
        self.latiss_remote = LATISS(intended_usage=usage)
        self.latiss_mock = LATISSMock()
        return self.latiss_remote, self.latiss_mock

    async def test_take_bias(self):

        async with self.make_group(usage=LATISSUsages.TakeImage):

            nbias = 4
            await self.latiss_remote.take_bias(nbias=nbias)
            self.assertEqual(self.latiss_mock.nimages, nbias)
            self.assertEqual(len(self.latiss_mock.exptime_list), nbias)
            for i in range(nbias):
                self.assertEqual(self.latiss_mock.exptime_list[i], 0.0)
            self.assertIsNone(self.latiss_mock.latiss_linear_stage)
            self.assertIsNone(self.latiss_mock.latiss_grating)
            self.assertIsNone(self.latiss_mock.latiss_filter)

    async def test_take_darks(self):
        async with self.make_group(usage=LATISSUsages.TakeImage):
            ndarks = 4
            exptime = 1.0
            await self.latiss_remote.take_darks(ndarks=ndarks, exptime=exptime)
            self.assertEqual(self.latiss_mock.nimages, ndarks)
            self.assertEqual(len(self.latiss_mock.exptime_list), ndarks)
            for i in range(ndarks):
                self.assertEqual(self.latiss_mock.exptime_list[i], exptime)
            self.assertIsNone(self.latiss_mock.latiss_linear_stage)
            self.assertIsNone(self.latiss_mock.latiss_grating)
            self.assertIsNone(self.latiss_mock.latiss_filter)

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

            (
                current_filter,
                current_grating,
                current_stage_pos,
            ) = await self.latiss_remote.get_setup()

            self.assertEqual(self.latiss_mock.nimages, nflats)
            self.assertEqual(len(self.latiss_mock.exptime_list), nflats)
            for i in range(nflats):
                self.assertEqual(self.latiss_mock.exptime_list[i], exptime)
            self.assertEqual(self.latiss_mock.latiss_filter, filter_id)
            self.assertEqual(self.latiss_mock.latiss_grating, grating_id)
            self.assertEqual(self.latiss_mock.latiss_linear_stage, linear_stage)

            self.assertEqual(current_filter, filter_name)
            self.assertEqual(current_grating, grating_name)
            self.assertEqual(current_stage_pos, linear_stage)

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
                    with self.assertRaises(RuntimeError):
                        self.latiss_remote.check_kwargs(**{key: "test"})


if __name__ == "__main__":
    unittest.main()

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

import astropy.units as u
from astropy.coordinates import ICRS, EarthLocation, Angle

from lsst.ts import salobj
from lsst.ts.observatory.control import utils


class TestUtils(unittest.TestCase):
    def test_calculate_parallactic_angle(self):
        # TODO: Implement test (DM-21336)
        radec_icrs = ICRS(Angle(0.0, unit=u.hourangle), Angle(-80.0, unit=u.deg))

        location = EarthLocation.from_geodetic(
            lon=-70.747698 * u.deg, lat=-30.244728 * u.deg, height=2663.0 * u.m
        )

        current_time = salobj.astropy_time_from_tai_unix(salobj.current_tai())

        current_time.location = location

        par_angle = utils.calculate_parallactic_angle(
            location,
            current_time.sidereal_time("mean"),
            radec_icrs,
        )

        self.assertIsNotNone(par_angle)

    def test_handle_exception_in_dict_items_nothing_to_handle(self):

        object_with_nothing_to_handle = dict(item1=1, item2=2, item3=3)

        # In this case the call below will not do anything, so there is no
        # assertion to make afterwards.
        utils.handle_exception_in_dict_items(object_with_nothing_to_handle)

    def test_handle_exception_in_dict_items_with_one_exception(self):

        object_with_one_exception_to_handle = dict(
            item1=1, item2=2, item3=TypeError("Raising some exception for testing.")
        )

        with self.assertRaises(RuntimeError):
            utils.handle_exception_in_dict_items(object_with_one_exception_to_handle)

        with self.assertRaises(RuntimeError):
            utils.handle_exception_in_dict_items(
                object_with_one_exception_to_handle,
                "Proving some additional message for the exception.",
            )

    def test_handle_exception_in_dict_items_with_two_exceptions(self):

        object_with_two_exceptions_to_handle = dict(
            item1=1,
            item2=asyncio.TimeoutError("Raising some exception for testing."),
            item3=TypeError("Raising some exception for testing."),
        )

        with self.assertRaises(RuntimeError):
            utils.handle_exception_in_dict_items(object_with_two_exceptions_to_handle)

        with self.assertRaises(RuntimeError):
            utils.handle_exception_in_dict_items(
                object_with_two_exceptions_to_handle,
                "Proving some additional message for the exception.",
            )


if __name__ == "__main__":
    unittest.main()

# This file is part of ts_standardscripts
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

import itertools
import unittest

from lsst.ts.observatory.control import utils


class TestUtils(unittest.TestCase):
    def test_subtract_angles(self):
        for angle1, nwraps, diff in itertools.product(
            (-90, -0.0001, 0, 0.0001, 90, 179.9999, 180, 180.0001),
            (0, -1, 1, -5, 5),
            (-0.00001, 0, 0.00001, -90, 90, -179.9999, 179.9999),
        ):
            with self.subTest(angle1=angle1, nwraps=nwraps, diff=diff):
                angle2 = angle1 - diff
                wrapped_angle1 = nwraps * 360 + angle1
                wrapped_angle2 = nwraps * 360 + angle2
                meas_diff1 = utils.subtract_angles(wrapped_angle1, angle2)
                self.assertAlmostEqual(meas_diff1, diff)
                meas_diff2 = utils.subtract_angles(angle1, wrapped_angle2)
                self.assertAlmostEqual(meas_diff2, diff)


if __name__ == "__main__":
    unittest.main()

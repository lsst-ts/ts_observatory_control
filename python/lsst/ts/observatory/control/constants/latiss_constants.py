# This file is part of ts_observatory_control.
#
# Developed for the Vera Rubin Observatory Telescope and Site Systems.
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

"""Useful constants for running auxTel"""
from lsst.geom import PointD

# pixel_scale was measured astrometrically in tickets/DM-24592
pixel_scale = 0.09569  # arcsec/pixel

boresight = PointD(2036.5, 2000.5)  # boreSight on detector (pixels)
sweet_spots = {  # the sweet spots for the gratings (pixels)
    "ronchi90lpmm": PointD(1780, 1800),
    "ronchi170lpmm": PointD(1750, 300),  # estimate added in DM-28818
    "holo4_003": PointD(1750, 300),  # estimate added in DM-28818
    "empty_1": PointD(1780, 1800),
}

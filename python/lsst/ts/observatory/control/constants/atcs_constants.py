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

# Derived astrometrically in latiss_constants.py, then
# converted to mm/arcsecond for usage here.

plate_scale = 0.1045  # mm/arcsecond at the telescope focal plane

# Matrix to map hexapod xy-offset to alt/az offset in the focal plane
# units are arcsec/mm. X-axis is Elevation
# Measured with data from AT run SUMMIT-5027.
hexapod_offset_scale = [
    [52.459, 0.0, 0.0],
    [0.0, 50.468, 0.0],
    [0.0, 0.0, 0.0],
]

# Matrix to map hexapod uv-offset to alt/az offset in the focal plane
# units are arcsec/degrees.
# Measured with data from AT run SUMMIT-7280
hexapod_uv_offset_scale = [
    [1312.95, 0.0, 0.0],
    [0.0, -1331.81, 0.0],
    [0.0, 0.0, 0.0],
]

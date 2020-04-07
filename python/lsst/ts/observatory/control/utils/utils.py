# This file is part of ts_observatory_control
#
# Developed for the LSST Telescope and Site.
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

__all__ = ["subtract_angles"]


def subtract_angles(angle1, angle2):
    """Compute the difference between two angles, wrapped to [-180, 180].

    Parameters
    ----------
    angle1 : `float`
        Angle 1 (deg)
    angle2 : `float`
        Angle 2 (deg)

    Returns
    -------
    subtract_angles : `float`
        angle1 - angle2 wrapped to [-180, 180] degrees
    """
    return ((angle1 - angle2) + 180) % 360.0 - 180

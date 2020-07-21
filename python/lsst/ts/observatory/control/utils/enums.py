# This file is part of ts_observatory_control.
#
# Developed for the LSST Telescope and Site Systems.
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

__all__ = ["RotType"]

import enum


class RotType(enum.IntEnum):
    """Defines the different types of rotator strategies.

    Sky: Sky position angle strategy. The rotator is positioned with respect
         to the North axis so rot_angle=0. means y-axis is aligned with North.
         Angle grows clock-wise.

    Parallactic: This strategy is required for taking optimum spectra with
                 LATISS. If set to zero, the rotator is positioned so that the
                 y-axis (dispersion axis) is aligned with the parallactic
                 angle.

    Physical_Sky: This strategy allows users to select the **initial** position
                  of the rotator in terms of the physical rotator angle (in the
                  reference frame of the telescope). Note that the telescope
                  will resume tracking the sky rotation.
    """

    Sky = 0
    Parallactic = 1
    Physical_Sky = 2

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

__all__ = [
    "RotType",
    "InstrumentFocus",
    "ClosedLoopMode",
    "DOFName",
    "CalibrationType",
    "LaserOpticalConfiguration",
]

import enum


class RotType(enum.IntEnum):
    """Available types of rotation, i.e. the meaning of the rot_angle argument
    in slew operations.

    Sky: Rotate with the sky. The rotator is positioned with respect to the
         North axis so rot_angle=0. means y-axis is aligned with North. Angle
         grows clock-wise.

    SkyAuto: Same as sky position angle but it will verify that the requested
             angle is achievable and wrap it to a valid range.

    ParallacticSky: This strategy is required for taking optimum spectra with
                    LATISS. If set to zero, the rotator is positioned so that
                    the y-axis (dispersion axis) is aligned with the
                    parallactic angle. *IMPORTANT*: The position is set at the
                    start of the slew operation and the rotator will then track
                    the sky.

    PhysicalSky:  This strategy allows users to select the **initial** position
                  of the rotator in terms of the physical rotator angle (in the
                  reference frame of the telescope). Note that the telescope
                  will resume tracking the sky rotation.

    Physical: Select a fixed position for the rotator in the reference frame of
              the telescope. Rotator will not track in this mode.

    """

    Sky = 0
    SkyAuto = 1
    Parallactic = 2
    PhysicalSky = 3
    Physical = 4


class InstrumentFocus(enum.IntEnum):
    """Defines the different types of instrument focus location.

    Prime: Instrument in the prime focus.

    Nasmyth: Instrument in a nasmyth focus.

    """

    Prime = 1
    Nasmyth = 2


class ClosedLoopMode(enum.IntEnum):
    """Defines the different mode to run closed loop.

    CWFS: Using only the corner wavefront sensors with focal
    plane in focus.

    FAM: Full Array Mode.

    """

    CWFS = 0
    FAM = 1


class DOFName(enum.IntEnum):
    """Defines the different Degrees of Freedom used in AOS."""

    M2_dz = 0
    M2_dx = 1
    M2_dy = 2
    M2_rx = 3
    M2_ry = 4
    Cam_dz = 5
    Cam_dx = 6
    Cam_dy = 7
    Cam_rx = 8
    Cam_ry = 9
    M1M3_B1 = 10
    M1M3_B2 = 11
    M1M3_B3 = 12
    M1M3_B4 = 13
    M1M3_B5 = 14
    M1M3_B6 = 15
    M1M3_B7 = 16
    M1M3_B8 = 17
    M1M3_B9 = 18
    M1M3_B10 = 19
    M1M3_B11 = 20
    M1M3_B12 = 21
    M1M3_B13 = 22
    M1M3_B14 = 23
    M1M3_B15 = 24
    M1M3_B16 = 25
    M1M3_B17 = 26
    M1M3_B18 = 27
    M1M3_B19 = 28
    M1M3_B20 = 29
    M2_B1 = 30
    M2_B2 = 31
    M2_B3 = 32
    M2_B4 = 33
    M2_B5 = 34
    M2_B6 = 35
    M2_B7 = 36
    M2_B8 = 37
    M2_B9 = 38
    M2_B10 = 39
    M2_B11 = 40
    M2_B12 = 41
    M2_B13 = 42
    M2_B14 = 43
    M2_B15 = 44
    M2_B16 = 45
    M2_B17 = 46
    M2_B18 = 47
    M2_B19 = 48
    M2_B20 = 49


class CalibrationType(enum.IntEnum):
    """Defines the different types of flat field calibrations

    Whitelight: Broad spectrum light.

    Mono: Monochromatic.

    """

    WhiteLight = 1
    Mono = 2
    CBP = 3
    CBPCalibration = 4


# TODO: (DM-46168) Revert workaround for TunableLaser XML changes
class LaserOpticalConfiguration(enum.StrEnum):
    """Configuration of the optical output

    Attributes
    ----------

    SCU: `str`
        Pass the beam straight-through the SCU.
    F1_SCU: `str`
        Direct the beam through the F1 after passing through the SCU.
    F2_SCU: `str`
        Direct the beam through the F2 after passing through the SCU.
    NO_SCU: `str`
        Pass the beam straight-through.
    F1_NO_SCU: `str`
        Pass the beam to F1 output.
    F2_NO_SCU: `str`
        Pass the beam to F2 output.

    """

    SCU = "SCU"
    F1_SCU = "F1 SCU"
    F2_SCU = "F2 SCU"
    NO_SCU = "No SCU"
    F1_NO_SCU = "F1 No SCU"
    F2_NO_SCU = "F2 No SCU"

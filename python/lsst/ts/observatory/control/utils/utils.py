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

__all__ = ["parallactic_angle", "handle_rottype"]

import numpy as np

import astropy.units as u
from astropy.coordinates import Angle

from .enums import RotType


def handle_rottype(rot_sky=0.0, rot_par=None, rot_phys_sky=None):
    """Handle different kinds of rotation strategies.

    From the given input the method will return an angle to be used
    (converted to `astropy.coordinates.Angle`) and a rotator positioning
    strategy; sky, parallactic or physical (see `RotType` for an
    explanation).

    Parameters
    ----------
    rot_sky : `float`, `str` or `astropy.coordinates.Angle`
        Has the same behavior of `rottype=RotType.Sky`.
    rot_par :  `float`, `str` or `astropy.coordinates.Angle`
        Has the same behavior of `rottype=RotType.Parallactic`.
    rot_phys_sky : `float`, `str` or `astropy.coordinates.Angle`
        Has the same behavior of `rottype=RotType.Physical_Sky`.

    Returns
    -------
    rotang: `astropy.coordinates.Angle`
        Selected rotation angle.
    rottype: `RotSky`
        Selected rotation type.

    Raises
    ------
    RuntimeError: If both `rot_par` and `rot_tel` are specified.

    """
    if rot_par is not None and rot_phys_sky is not None:
        raise RuntimeError(
            f"Cannot specify both `rot_par` and `rot_tel`. Got: rot_par={rot_par}, "
            f"rot_tel={rot_phys_sky}."
        )
    elif rot_par is not None:
        return Angle(rot_par, unit=u.deg), RotType.Parallactic
    elif rot_phys_sky is not None:
        return Angle(rot_phys_sky, unit=u.deg), RotType.Physical_Sky
    else:
        return Angle(rot_sky, unit=u.deg), RotType.Sky


def parallactic_angle(location, lst, target):
    """
    Calculate the parallactic angle.

    Parameters
    ----------
    location: ``
        Observatory location.

    lst: ``
        Local sidereal time.

    target: ``
        The observing target coordinates.

    Returns
    -------
    `~astropy.coordinates.Angle`
        Parallactic angle.

    Notes
    -----
    The parallactic angle is the angle between the great circle that
    intersects a celestial object and the zenith, and the object's hour
    circle [1]_.

    .. [1] https://en.wikipedia.org/wiki/Parallactic_angle

    """

    # Eqn (14.1) of Meeus' Astronomical Algorithms
    H = (lst - target.ra).radian
    q = (
        np.arctan2(
            np.sin(H),
            (
                np.tan(location.lat.radian) * np.cos(target.dec.radian)
                - np.sin(target.dec.radian) * np.cos(H)
            ),
        )
        * u.rad
    )

    return Angle(q)

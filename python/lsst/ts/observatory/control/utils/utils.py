# This file is part of ts_observatory_control
#
# Developed for the Vera Rubin Observatory Telescope and Site.
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
    "calculate_parallactic_angle",
    "handle_exception_in_dict_items",
    "get_catalogs_path",
    "cast_int_or_str",
]

import pathlib
import typing

import astropy.units as u
import numpy as np
from astropy.coordinates import ICRS, Angle, EarthLocation

from .. import catalogs


def calculate_parallactic_angle(
    location: EarthLocation, lst: Angle, target: ICRS
) -> Angle:
    """
    Calculate the parallactic angle.

    Parameters
    ----------
    location: `astropy.coordinates.EarthLocation`
        Observatory location.

    lst: `astropy.coordinates.Angle`
        Local sidereal time.

    target: `astropy.coordinates.ICRS`
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


def handle_exception_in_dict_items(
    input_dict: typing.Dict[str, typing.Any],
    message: str = "Exceptions in the following items",
) -> None:
    """Handle execeptions in dictionary items."""

    exception_keys = [
        key for key in input_dict if isinstance(input_dict[key], Exception)
    ]

    if len(exception_keys) > 0:
        raise RuntimeError(f"{message}: {exception_keys}")


def get_catalogs_path() -> pathlib.Path:
    """Return the path to the internal catalog directory.

    Returns
    -------
    catalogs_path : `pathlib.Path`
        Path to catalogs directory.
    """
    return pathlib.Path(catalogs.__file__).resolve().parent


def cast_int_or_str(value: typing.Any) -> typing.Union[int, str]:
    """Return an int or a string.

    Parameters
    ----------
    value : `int` or `str`
        A value to be cast as integer or string.

    Returns
    -------
    `int` or `str`
        Recasted value.
    """
    return int(value) if isinstance(value, int) else str(value)

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

import typing
from dataclasses import dataclass


@dataclass
class CameraExposure:
    """Store the parameters that define an exposure."""

    exp_time: float
    shutter: bool
    image_type: str
    group_id: str
    n: int
    n_snaps: int
    n_shift: typing.Union[int, None]
    row_shift: typing.Union[int, None]
    checkpoint: None | typing.Optional[typing.Callable[[str], typing.Awaitable]]
    test_type: typing.Union[str, None]
    reason: typing.Union[str, None]
    program: typing.Union[str, None]
    sensors: typing.Union[str, None]
    note: typing.Union[str, None]

    def get_key_value_map(self) -> str:
        """Parse inputs into a valid key-value string for the cameras.

        Returns
        -------
        key_value_map : `str`
            Key value map for camera exposure.
        """

        key_value_map = (
            f"imageType: {self.image_type}, groupId: {self.group_id}, "
            f"testType: {self.image_type if self.test_type is None else self.test_type}, "
            f"stutterRows: {self.get_row_shift()}, "
            f"stutterNShifts: {self.get_n_shift()}, "
            f"stutterDelay: {self.get_stutter_delay()}"
        )

        if self.reason is not None:
            key_value_map += f", reason: {self.reason}"

        if self.program is not None:
            key_value_map += f", program: {self.program}"

        return key_value_map

    def is_stutter(self) -> bool:
        """Check if image is stutter.

        Returns
        -------
        `bool`
            True if image type is STUTTERED.
        """
        return self.image_type == "STUTTERED"

    def get_n_shift(self) -> int:
        """Return valid n_shift.

        Returns
        -------
        `int`
            n_shift if image type is STUTTERED, else 0.
        """
        if self.is_stutter():
            assert self.n_shift is not None
            return self.n_shift
        else:
            return 0

    def get_row_shift(self) -> int:
        """Return valid row_shift.

        Returns
        -------
        `int`
            row_shift if image type is STUTTERED, else 0.
        """
        if self.is_stutter():
            assert self.row_shift is not None
            return self.row_shift
        else:
            return 0

    def get_stutter_delay(self) -> float:
        """Return the stutter image delay.

        Returns
        -------
        `float`
            The stutter image delay if image type is STUTTERED, else 0
        """
        return self.exp_time if self.is_stutter() else 0.0

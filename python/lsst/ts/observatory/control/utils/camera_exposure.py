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
    n_shift: int
    row_shift: int
    test_type: str
    reason: str
    program: str
    sensors: str
    note: str

    def get_key_value_map(self) -> str:
        """Parse inputs into a valid key-value string for the cameras."""

        key_value_map = (
            f"imageType: {self.image_type}, groupId: {self.group_id}, "
            f"testType: {self.image_type if self.test_type is None else self.test_type}"
        )

        if self.reason is not None:
            key_value_map += f", reason: {self.reason}"

        if self.program is not None:
            key_value_map += f", program: {self.program}"

        return key_value_map

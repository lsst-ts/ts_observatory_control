# This file is part of ts_observatory_control.
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
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

__all__ = [
    "ROICommon",
    "ROI",
    "ROISpec",
    "get_default_guider_rois",
]

from typing import Any, Generator

from pydantic import BaseModel, Field, validator


class ROICommon(BaseModel):
    rows: int = Field(default=50)
    cols: int = Field(default=50)
    integrationTimeMillis: int = Field(alias="integration_time_millis", default=100)

    @validator("rows")
    def check_rows(cls, v: int) -> int:
        if not (10 <= v <= 400):
            raise ValueError(f"Rows must be between 10 and 400, got {v!r}.")
        return v

    @validator("cols")
    def check_cols(cls, v: int) -> int:
        if not (10 <= v <= 400):
            raise ValueError(f"Columns must be between 10 and 400, got {v!r}.")
        return v

    @validator("integrationTimeMillis")
    def check_integrationTimeMillis(cls, v: int) -> int:
        if not (5 <= v <= 200):
            raise ValueError(
                f"Integration time in milliseconds must be between 5 and 200, got {v!r}."
            )
        return v


class ROI(BaseModel):
    segment: int
    startRow: int = Field(alias="start_row")
    startCol: int = Field(alias="start_col")


def get_default_guider_rois() -> dict[str, ROI]:
    """Get the default ROI for each guider.

    These ROIs are used when no guide star is available from the guide
    star catalog. They are positioned to catch a volunteer star, which in
    dense fields is often bright enough to guide on.

    Returns
    -------
    `dict` [`str`, `ROI`]
        Default ROI for each guider, keyed by the name used in the ROI
        specification, e.g. "R00SG0".
    """
    return {
        "R00SG0": ROI(segment=7, start_row=800, start_col=56),
        "R00SG1": ROI(segment=0, start_row=800, start_col=56),
        "R04SG0": ROI(segment=7, start_row=800, start_col=56),
        "R04SG1": ROI(segment=0, start_row=800, start_col=56),
        "R40SG0": ROI(segment=7, start_row=800, start_col=56),
        "R40SG1": ROI(segment=0, start_row=800, start_col=56),
        "R44SG0": ROI(segment=7, start_row=800, start_col=56),
        "R44SG1": ROI(segment=0, start_row=800, start_col=56),
    }


class ROISpec(BaseModel):
    common: ROICommon
    roi: dict[str, ROI] = Field(flatten=True)

    def _iter(
        self, to_dict: bool = False, *args: Any, **kwargs: Any
    ) -> Generator[tuple[str, Any], None, None]:
        for dict_key, v in super()._iter(to_dict, *args, **kwargs):
            if to_dict and self.__fields__[dict_key].field_info.extra.get(
                "flatten", False
            ):
                assert isinstance(v, dict)
                yield from v.items()
            else:
                yield dict_key, v

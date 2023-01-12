# This file is part of ts_observatory_control
#
# Developed for the Vera Rubin Observatory Data Management System.
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
# You should have received a copy of the GNU General Public License.
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import astropy.coordinates
import astropy.units
import pytest
from lsst.ts.observatory.control.utils.extras import (
    DM_STACK_AVAILABLE,
    find_target_radec,
)


@pytest.mark.skipif(not DM_STACK_AVAILABLE, reason="DM stack not available.")
def test_find_target_radec() -> None:

    radec_find = astropy.coordinates.ICRS(
        ra=astropy.coordinates.Angle(281.81158107, unit=astropy.units.deg),
        dec=astropy.coordinates.Angle(-25.88640971, unit=astropy.units.deg),
    )

    radec = find_target_radec(
        radec=radec_find,
        radius=astropy.coordinates.Angle(0.5, units=astropy.units.deg),
        mag_limit=(6.0, 8.0),
    )

    assert radec.ra == pytest.approx(
        astropy.coordinates.Angle(4.975997291756341, units=astropy.units.rad)
    )
    assert radec.dec == pytest.approx(
        astropy.coordinates.Angle(-0.43531985697592745, units=astropy.units.rad)
    )

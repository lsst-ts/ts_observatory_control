# This file is part of ts_observatory_control
#
# Developed for the Vera Rubin Observatory Telescope and Site Subsystem.
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
# along with this program. If not, see <https://www.gnu.org/licenses/>.

import unittest

from lsst.ts.idl.enums.ScriptQueue import SalIndex

from lsst.ts.observatory.control import Usages
from lsst.ts.observatory.control.auxtel import ATQueue

HB_TIMEOUT = 5  # Heartbeat timeout (sec)
MAKE_TIMEOUT = 60  # Timeout for make_script (sec)


class TestATQueue(unittest.IsolatedAsyncioTestCase):
    async def test_constructor(self) -> None:

        atqueue = ATQueue(domain="FakeDomain", intended_usage=Usages.DryTest)

        assert f"ScriptQueue:{SalIndex.AUX_TEL}" in atqueue.components

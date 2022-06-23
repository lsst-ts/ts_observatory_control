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
# along with this program. If not, see <https://www.gnu.org/licenses/>.

__all__ = ["ATQueue"]

import typing
import logging

from lsst.ts import salobj
from lsst.ts.idl.enums.ScriptQueue import SalIndex

from ..script_queue import ScriptQueue


class ATQueue(ScriptQueue):
    """High level class to operate the Auxiliary Telescope ScriptQueue.

    Parameters
    ----------
    domain : `salobj.Domain`
        Domain for remotes. If `None`, creates a domain.
    log : `logging.Logger`
        Optional logging class to be used for logging operations. If `None`,
        creates a new logger.
    intended_usage : `int`
        Optional bitmask that maps to a list of intended operations. This is
        used to limit the resources allocated by the class by gathering some
        knowledge about the usage intention. By default allocates all
        resources.
    """

    def __init__(
        self,
        domain: typing.Optional[typing.Union[salobj.Domain, str]] = None,
        log: typing.Optional[logging.Logger] = None,
        intended_usage: typing.Optional[int] = None,
    ) -> None:
        super().__init__(SalIndex.AUX_TEL, domain, log, intended_usage)

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

import asyncio
import logging
import types
import typing

from lsst.ts.observatory.control.auxtel.atbuilding import ATBuilding, ATBuildingUsages
from lsst.ts.observatory.control.mock.remote_group_async_mock import (
    RemoteGroupAsyncMock,
)
from lsst.ts.xml.enums.ATBuilding import VentGateState

# Time for mock vent gate state transitions (seconds).
GATE_TRANSITION_TIME = 0.1


class ATBuildingAsyncMock(RemoteGroupAsyncMock):
    """RemoteGroupAsyncMock subclass for ATBuilding unit tests.

    Provides side-effect methods that simulate ATBuilding CSC behaviour so
    that unit tests can exercise the high-level ``ATBuilding`` methods without
    a running DDS environment.
    """

    @property
    def remote_group(self) -> ATBuilding:
        return self.atbuilding

    @classmethod
    def setUpClass(cls) -> None:
        """Create the ATBuilding instance once per test class."""

        cls.log = logging.getLogger("TestATBuilding")

        # Pass a string as domain so ATBuilding does not try to create a real
        # salobj Domain (no event loop is running at this point).
        cls.atbuilding = ATBuilding(
            domain="FakeDomain",
            log=cls.log,
            intended_usage=ATBuildingUsages.DryTest,
        )

        for component in cls.atbuilding.components_attr:
            setattr(cls.atbuilding.check, component, True)

    async def setup_types(self) -> None:
        """Initialise the simulated ATBuilding hardware state."""

        # Vent gate state: all gates closed initially.
        self._atbuilding_evt_vent_gate_state = types.SimpleNamespace(
            state=[int(VentGateState.CLOSED)] * 4
        )

    async def setup_mocks(self) -> None:
        """Wire side effects into the ATBuilding remote mock."""
        await self.setup_atbuilding()

    async def setup_atbuilding(self) -> None:
        """Augment the atbuilding remote mock with realistic side effects."""

        self.atbuilding.rem.atbuilding.configure_mock(
            **{
                "evt_ventGateState.aget.side_effect": self.atbuilding_evt_vent_gate_state,
                "evt_ventGateState.next.side_effect": self.atbuilding_evt_vent_gate_state,
                "cmd_openVentGate.set_start.side_effect": self.atbuilding_cmd_open_vent_gate,
                "cmd_closeVentGate.set_start.side_effect": self.atbuilding_cmd_close_vent_gate,
            }
        )

    async def atbuilding_evt_vent_gate_state(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> types.SimpleNamespace:
        await asyncio.sleep(GATE_TRANSITION_TIME)
        return self._atbuilding_evt_vent_gate_state

    async def atbuilding_cmd_open_vent_gate(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> None:
        gate_mask = kwargs["gate"]
        asyncio.create_task(self._open_vent_gates(gate_mask))

    async def atbuilding_cmd_close_vent_gate(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> None:
        gate_mask = kwargs["gate"]
        asyncio.create_task(self._close_vent_gates(gate_mask))

    async def _open_vent_gates(self, gate_array: typing.List[int]) -> None:
        """Open the gates listed in ``gate_array``. -1 entries are ignored."""
        await asyncio.sleep(GATE_TRANSITION_TIME)
        for gate_index in gate_array:
            if gate_index >= 0:
                self._atbuilding_evt_vent_gate_state.state[gate_index] = int(
                    VentGateState.OPENED
                )

    async def _close_vent_gates(self, gate_array: typing.List[int]) -> None:
        """Close the gates listed in ``gate_array``. -1 entries are ignored."""
        await asyncio.sleep(GATE_TRANSITION_TIME)
        for gate_index in gate_array:
            if gate_index >= 0:
                self._atbuilding_evt_vent_gate_state.state[gate_index] = int(
                    VentGateState.CLOSED
                )

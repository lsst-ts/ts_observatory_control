# This file is part of ts_observatory_control
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

import pytest
from lsst.ts.observatory.control.mock import ATBuildingAsyncMock
from lsst.ts.xml.enums.ATBuilding import VentGateState


class TestATBuilding(ATBuildingAsyncMock):
    async def test_open_vent_gates_single(self) -> None:
        """Opening gate 2 should leave the other gates closed."""
        gates = [2]
        await self.atbuilding.open_vent_gates(gates)

        state = self._atbuilding_evt_vent_gate_state.state
        assert VentGateState(state[2]) == VentGateState.OPENED
        for i in [0, 1, 3]:
            assert VentGateState(state[i]) == VentGateState.CLOSED

        # Verify the correct SAL command was called with the right gate array.
        self.atbuilding.rem.atbuilding.cmd_openVentGate.set_start.assert_awaited_once()
        call_kwargs = (
            self.atbuilding.rem.atbuilding.cmd_openVentGate.set_start.call_args.kwargs
        )
        assert call_kwargs["gate"] == [2, -1, -1, -1]

    async def test_open_vent_gates_multiple(self) -> None:
        """Opening gates 0 and 3 should leave gates 1 and 2 unchanged."""
        # Start from a known state: all closed.
        self._atbuilding_evt_vent_gate_state.state = [int(VentGateState.CLOSED)] * 4

        gates = [0, 3]
        await self.atbuilding.open_vent_gates(gates)

        state = self._atbuilding_evt_vent_gate_state.state
        assert VentGateState(state[0]) == VentGateState.OPENED
        assert VentGateState(state[3]) == VentGateState.OPENED
        assert VentGateState(state[1]) == VentGateState.CLOSED
        assert VentGateState(state[2]) == VentGateState.CLOSED

    async def test_open_all_vent_gates(self) -> None:
        """open_all_vent_gates should open all four gates."""
        self._atbuilding_evt_vent_gate_state.state = [int(VentGateState.CLOSED)] * 4

        await self.atbuilding.open_all_vent_gates()

        for i in range(4):
            assert (
                VentGateState(self._atbuilding_evt_vent_gate_state.state[i])
                == VentGateState.OPENED
            )

    async def test_close_vent_gates_single(self) -> None:
        """Closing gate 1 should leave other gates in their current state."""
        # Start with all gates open.
        self._atbuilding_evt_vent_gate_state.state = [int(VentGateState.OPENED)] * 4

        await self.atbuilding.close_vent_gates([1])

        state = self._atbuilding_evt_vent_gate_state.state
        assert VentGateState(state[1]) == VentGateState.CLOSED
        for i in [0, 2, 3]:
            assert VentGateState(state[i]) == VentGateState.OPENED

        call_kwargs = (
            self.atbuilding.rem.atbuilding.cmd_closeVentGate.set_start.call_args.kwargs
        )
        assert call_kwargs["gate"] == [1, -1, -1, -1]

    async def test_close_all_vent_gates(self) -> None:
        """close_all_vent_gates should close all four gates."""
        self._atbuilding_evt_vent_gate_state.state = [int(VentGateState.OPENED)] * 4

        await self.atbuilding.close_all_vent_gates()

        for i in range(4):
            assert (
                VentGateState(self._atbuilding_evt_vent_gate_state.state[i])
                == VentGateState.CLOSED
            )

    async def test_open_vent_gates_invalid_index(self) -> None:
        """Gate indices outside [0, 3] should raise ValueError."""
        with pytest.raises(ValueError):
            await self.atbuilding.open_vent_gates([4])

        with pytest.raises(ValueError):
            await self.atbuilding.open_vent_gates([-1])

    async def test_close_vent_gates_invalid_index(self) -> None:
        """Gate indices outside [0, 3] should raise ValueError."""
        with pytest.raises(ValueError):
            await self.atbuilding.close_vent_gates([5])

    async def test_assert_vent_gate_state_pass(self) -> None:
        """assert_vent_gate_state should pass when gates are in expected
        state."""
        self._atbuilding_evt_vent_gate_state.state = [int(VentGateState.CLOSED)] * 4

        # Should not raise.
        await self.atbuilding.assert_vent_gate_state([0, 1, 2, 3], VentGateState.CLOSED)

    async def test_assert_vent_gate_state_fail(self) -> None:
        """assert_vent_gate_state should raise AssertionError on mismatch."""
        self._atbuilding_evt_vent_gate_state.state = [int(VentGateState.CLOSED)] * 4
        # Manually open gate 1.
        self._atbuilding_evt_vent_gate_state.state[1] = int(VentGateState.OPENED)

        with pytest.raises(AssertionError):
            await self.atbuilding.assert_vent_gate_state(
                [0, 1, 2, 3], VentGateState.CLOSED
            )

    def test_gate_array_single_gate(self) -> None:
        """_gate_array for a single gate should set slot 0 and pad with -1."""
        assert self.atbuilding._gate_array([2]) == [2, -1, -1, -1]

    def test_gate_array_multiple_gates(self) -> None:
        """_gate_array for multiple gates should fill slots in order."""
        assert self.atbuilding._gate_array([0, 3]) == [0, 3, -1, -1]

    def test_gate_array_all_gates(self) -> None:
        """_gate_array for all four gates should have no -1 padding."""
        assert self.atbuilding._gate_array([0, 1, 2, 3]) == [0, 1, 2, 3]

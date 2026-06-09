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

__all__ = ["ATBuilding", "ATBuildingUsages"]

import asyncio
import logging
import typing

from lsst.ts import salobj
from lsst.ts.xml.enums.ATBuilding import VentGateState

from ..remote_group import RemoteGroup, Usages, UsagesResources

# Number of vent gates on ATBuilding (0-3, counter-clockwise from door).
N_VENT_GATES = 4


class ATBuildingUsages(Usages):
    """ATBuilding usages definition.

    Notes
    -----

    Additional usages definition:

    * Setup: Enable ATBuilding setup operations (vent gates, extraction fan).
    * DryTest: Disables CSCs and unit tests.
    """

    Setup = 1 << 3
    DryTest = 1 << 4

    def __iter__(self) -> typing.Iterator[int]:
        return iter(
            [
                self.All,
                self.Setup,
                self.DryTest,
            ]
        )


class ATBuilding(RemoteGroup):
    """LSST Auxiliary Telescope Building.

    ATBuilding encapsulates core functionality from the ATBuilding CSC,
    providing high-level methods for controlling the vent gates and extraction
    fan.

    Parameters
    ----------
    domain : `lsst.ts.salobj.Domain`
        Domain for remotes. If `None` create a domain.
    log : `logging.Logger`
        Optional logging class to be used for logging operations. If `None`,
        creates a new logger. Useful to use in salobj.BaseScript and allow
        logging in the class use the script logging.
    intended_usage : `int`
        Optional integer that maps to a list of intended operations. This is
        used to limit the resources allocated by the class by gathering some
        knowledge about the usage intention. By default allocates all
        resources.

    Attributes
    ----------
    rem.atbuilding : `salobj.Remote`
    """

    def __init__(
        self,
        domain: typing.Optional[salobj.Domain] = None,
        log: typing.Optional[logging.Logger] = None,
        intended_usage: typing.Optional[int] = None,
    ) -> None:

        super().__init__(
            components=[
                "ATBuilding",
            ],
            domain=domain,
            log=log,
            intended_usage=intended_usage,
        )

    @property
    def valid_use_cases(self) -> ATBuildingUsages:
        """Returns valid usages.

        When subclassing, overwrite this method to return the proper enum.

        Returns
        -------
        usages : `ATBuildingUsages`
        """
        return ATBuildingUsages()

    @property
    def usages(self) -> typing.Dict[int, UsagesResources]:
        if self._usages is None:
            usages = super().usages

            usages[self.valid_use_cases.Setup] = UsagesResources(
                components_attr=["atbuilding"],
                readonly=False,
                generics=["summaryState"],
                atbuilding=[
                    "openVentGate",
                    "closeVentGate",
                    "setExtractionFanDriveFreq",
                    "ventGateState",
                ],
            )

            usages[self.valid_use_cases.DryTest] = UsagesResources(
                components_attr=(), readonly=True
            )

            self._usages = usages

        return self._usages

    async def open_vent_gates(
        self,
        gates: typing.List[int],
    ) -> None:
        """Open the specified vent gates and wait for them to report open.

        Parameters
        ----------
        gates : `list` of `int`
            Indices of the gates to open (0-3, counter-clockwise from door).

        Raises
        ------
        ValueError
            If any gate index is outside the range [0, N_VENT_GATES).
        RuntimeError
            If a gate does not reach `VentGateState.OPENED` after the command.
        """
        self._validate_gate_indices(gates)

        gate_array = self._gate_array(gates)

        self.log.info(f"Opening vent gates {gates}.")

        self.rem.atbuilding.evt_ventGateState.flush()

        await self.rem.atbuilding.cmd_openVentGate.set_start(
            gate=gate_array,
            timeout=self.long_timeout,
        )

        await self._wait_for_vent_gate_state(gates, VentGateState.OPENED)

    async def close_vent_gates(
        self,
        gates: typing.List[int],
    ) -> None:
        """Close the specified vent gates and wait for them to report closed.

        Parameters
        ----------
        gates : `list` of `int`
            Indices of the gates to close (0-3, counter-clockwise from door).

        Raises
        ------
        ValueError
            If any gate index is outside the range [0, N_VENT_GATES).
        RuntimeError
            If a gate does not reach `VentGateState.CLOSED` after the command.
        """
        self._validate_gate_indices(gates)

        gate_array = self._gate_array(gates)

        self.log.info(f"Closing vent gates {gates}.")

        self.rem.atbuilding.evt_ventGateState.flush()

        await self.rem.atbuilding.cmd_closeVentGate.set_start(
            gate=gate_array,
            timeout=self.long_timeout,
        )

        await self._wait_for_vent_gate_state(gates, VentGateState.CLOSED)

    async def open_all_vent_gates(self) -> None:
        """Open all four vent gates and wait for them to report open.

        Raises
        ------
        RuntimeError
            If any gate does not reach `VentGateState.OPENED`.
        """
        await self.open_vent_gates(list(range(N_VENT_GATES)))

    async def close_all_vent_gates(self) -> None:
        """Close all four vent gates and wait for them to report closed.

        Raises
        ------
        RuntimeError
            If any gate does not reach `VentGateState.CLOSED`.
        """
        await self.close_vent_gates(list(range(N_VENT_GATES)))

    @staticmethod
    def _validate_gate_indices(gates: typing.List[int]) -> None:
        """Raise ValueError if any gate index is out of range."""
        for gate in gates:
            if gate not in range(N_VENT_GATES):
                raise ValueError(
                    f"Gate index {gate} is out of range. "
                    f"Valid indices are 0 to {N_VENT_GATES - 1}."
                )

    @staticmethod
    def _gate_array(gates: typing.List[int]) -> typing.List[int]:
        """Convert a list of gate indices into the SAL command gate array.

        The ``openVentGate`` and ``closeVentGate`` commands accept an
        ``int[4]`` array where each element is a gate index (0-3) to act on,
        or ``-1`` to leave that slot unused.  For example, opening gate 2
        is represented as ``[2, -1, -1, -1]``.

        Parameters
        ----------
        gates : `list` of `int`
            Gate indices to include (0 to N_VENT_GATES-1).

        Returns
        -------
        array : `list` of `int`
            Length-``N_VENT_GATES`` array with gate indices followed by -1
            padding.
        """
        array = [-1] * N_VENT_GATES
        for slot, gate in enumerate(gates):
            array[slot] = gate
        return array

    async def _wait_for_vent_gate_state(
        self,
        gates: typing.List[int],
        expected_state: VentGateState,
        timeout: typing.Optional[float] = None,
    ) -> None:
        """Wait until all specified vent gates reach ``expected_state``.

        Parameters
        ----------
        gates : `list` of `int`
            Gate indices to monitor.
        expected_state : `VentGateState`
            State to wait for.
        timeout : `float`, optional
            Seconds to wait. Defaults to ``self.long_timeout``.

        Raises
        ------
        RuntimeError
            If the gates do not reach the expected state within ``timeout``.
        asyncio.TimeoutError
            If waiting for the event times out.
        """
        if timeout is None:
            timeout = self.long_timeout

        pending = set(gates)

        try:
            while pending:
                vent_gate_state = await asyncio.wait_for(
                    self.rem.atbuilding.evt_ventGateState.next(flush=False),
                    timeout=timeout,
                )
                for gate in list(pending):
                    if VentGateState(vent_gate_state.state[gate]) == expected_state:
                        pending.discard(gate)
                        self.log.debug(
                            f"Gate {gate} reached state {expected_state.name!r}."
                        )
        except asyncio.TimeoutError:
            raise RuntimeError(
                f"Timed out waiting for vent gates {sorted(pending)} "
                f"to reach state {expected_state.name!r}."
            )

        self.log.info(f"Vent gates {gates} are now in state {expected_state.name!r}.")

    async def start_extraction_fan(
        self,
        target_frequency: float,
    ) -> None:
        """Start the extraction fan at a specified drive frequency.

        Parameters
        ----------
        target_frequency : `float`
            Target drive frequency in Hz.  Must be positive.

        Raises
        ------
        ValueError
            If `target_frequency` is not positive.
        """
        if target_frequency <= 0:
            raise ValueError(
                f"target_frequency must be positive, got {target_frequency}."
            )

        self.log.info(f"Starting extraction fan at {target_frequency} Hz.")

        await self.rem.atbuilding.cmd_setExtractionFanDriveFreq.set_start(
            targetFrequency=target_frequency,
            timeout=self.long_timeout,
        )

    async def stop_extraction_fan(self) -> None:
        """Stop the extraction fan."""
        self.log.info("Stopping extraction fan.")

        await self.rem.atbuilding.cmd_setExtractionFanDriveFreq.set_start(
            targetFrequency=0,
            timeout=self.long_timeout,
        )

    async def assert_vent_gate_state(
        self,
        gates: typing.List[int],
        expected_state: VentGateState,
    ) -> None:
        """Assert that the specified vent gates are in the expected state.

        Parameters
        ----------
        gates : `list` of `int`
            Gate indices to check (0-3).
        expected_state : `VentGateState`
            Expected state for all specified gates.

        Raises
        ------
        AssertionError
            If any gate is not in `expected_state`.
        """
        self._validate_gate_indices(gates)

        vent_gate_state = await self.rem.atbuilding.evt_ventGateState.aget(
            timeout=self.fast_timeout
        )

        for gate in gates:
            actual = VentGateState(vent_gate_state.state[gate])
            assert actual == expected_state, (
                f"Gate {gate} is in state {actual.name!r}, "
                f"expected {expected_state.name!r}."
            )

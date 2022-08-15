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

import types
import typing
import asyncio
import logging

import numpy as np

from lsst.ts import utils
from lsst.ts import idl

from lsst.ts.observatory.control.maintel.mtcs import MTCS, MTCSUsages
from lsst.ts.observatory.control.mock import RemoteGroupAsyncMock


class MTCSAsyncMock(RemoteGroupAsyncMock):
    """Implement MTCS support for RemoteGroupAsyncMock unit test helper class
    to.

    This class is intended to be used for developing unit tests for MTCS
    class.
    """

    @property
    def remote_group(self) -> MTCS:
        return self.mtcs

    @classmethod
    def setUpClass(cls) -> None:
        """This classmethod is only called once, when preparing the unit
        test.
        """

        cls.log = logging.getLogger("TestMTCS")

        # Pass in a string as domain to prevent MTCS from trying to create a
        # domain by itself. When using DryTest usage, the class won't create
        # any remote. When this method is called there is no event loop
        # running so all asyncio facilities will fail to create. This is later
        # rectified in the asyncSetUp.
        cls.mtcs = MTCS(
            domain="FakeDomain", log=cls.log, intended_usage=MTCSUsages.DryTest
        )

        [
            setattr(cls.mtcs.check, component, True)  # type: ignore
            for component in cls.mtcs.components_attr
        ]

        # Decrease telescope settle time to speed up unit test
        cls.mtcs.tel_settle_time = 0.25

        # setup some execution times
        cls.execute_raise_lower_m1m3_time = 4.0  # seconds
        cls.heartbeat_time = 1.0  # seconds
        cls.short_process_time = 0.1  # seconds
        cls.normal_process_time = 0.25  # seconds

        cls.track_id_gen = utils.index_generator(1)

    async def setup_types(self) -> None:
        self.mtcs._create_asyncio_events()

        # MTMount data
        self._mtmount_evt_target = types.SimpleNamespace(
            trackId=next(self.track_id_gen),
            azimuth=0.0,
            elevation=80.0,
        )

        self._mtmount_evt_cameraCableWrapFollowing = types.SimpleNamespace(enabled=1)

        self._mtmount_tel_azimuth = types.SimpleNamespace(actualPosition=0.0)
        self._mtmount_tel_elevation = types.SimpleNamespace(actualPosition=80.0)

        self._mtmount_evt_elevation_in_position = types.SimpleNamespace(
            inPosition=True,
        )
        self._mtmount_evt_azimuth_in_position = types.SimpleNamespace(
            inPosition=True,
        )

        # MTRotator data
        self._mtrotator_tel_rotation = types.SimpleNamespace(
            demandPosition=0.0,
            actualPosition=0.0,
        )
        self._mtrotator_evt_in_position = types.SimpleNamespace(inPosition=True)

        # MTDome data
        self._mtdome_tel_azimuth = types.SimpleNamespace(
            positionActual=0.0,
            positionCommanded=0.0,
        )

        self._mtdome_tel_light_wind_screen = types.SimpleNamespace(
            positionActual=0.0,
            positionCommanded=0.0,
        )

        # MTM1M3 data
        self._mtm1m3_evt_detailed_state = types.SimpleNamespace(
            detailedState=idl.enums.MTM1M3.DetailedState.PARKED
        )
        self._mtm1m3_evt_applied_balance_forces = types.SimpleNamespace(
            forceMagnitude=0.0
        )

        self._mtm1m3_raise_task = utils.make_done_future()
        self._mtm1m3_lower_task = utils.make_done_future()
        self._hardpoint_corrections_task = utils.make_done_future()

        # MTM2 data
        self._mtm2_evt_force_balance_system_status = types.SimpleNamespace(status=False)

        # Camera hexapod data
        self._mthexapod_1_evt_compensation_mode = types.SimpleNamespace(enabled=False)
        self._mthexapod_1_evt_uncompensated_position = types.SimpleNamespace(
            x=0.0, y=0.0, z=0.0, u=0.0, v=0.0, w=0.0
        )
        self._mthexapod_1_evt_in_position = types.SimpleNamespace(inPosition=True)
        self._mthexapod_1_move_task = utils.make_done_future()

        # M2 hexapod data
        self._mthexapod_2_evt_compensation_mode = types.SimpleNamespace(enabled=False)
        self._mthexapod_2_evt_uncompensated_position = types.SimpleNamespace(
            x=0.0, y=0.0, z=0.0, u=0.0, v=0.0, w=0.0
        )
        self._mthexapod_2_evt_in_position = types.SimpleNamespace(inPosition=True)
        self._mthexapod_2_move_task = utils.make_done_future()

    async def setup_mocks(self) -> None:
        await self.setup_mtmount()
        await self.setup_mtrotator()
        await self.setup_mtdome()
        await self.setup_mtm1m3()
        await self.setup_mtm2()
        await self.setup_mthexapod_1()
        await self.setup_mthexapod_2()

    async def setup_mtmount(self) -> None:
        """Augment MTMount."""
        mtmount_mocks = {
            "evt_target.next.side_effect": self.mtmount_evt_target_next,
            "tel_azimuth.next.side_effect": self.mtmount_tel_azimuth_next,
            "tel_azimuth.DataType.return_value": self.get_sample("MTMount", "azimuth"),
            "tel_elevation.next.side_effect": self.mtmount_tel_elevation_next,
            "tel_elevation.aget.side_effect": self.mtmount_tel_elevation_next,
            "evt_elevationInPosition.next.side_effect": self.mtmount_evt_elevation_in_position_next,
            "evt_azimuthInPosition.next.side_effect": self.mtmount_evt_azimuth_in_position_next,
            "evt_cameraCableWrapFollowing.aget.side_effect": self.mtmount_evt_cameraCableWrapFollowing,
            "cmd_enableCameraCableWrapFollowing.start.side_effect": self.mtmount_cmd_enable_ccw_following,
            "cmd_disableCameraCableWrapFollowing.start.side_effect": self.mtmount_cmd_disable_ccw_following,
        }

        self.mtcs.rem.mtmount.configure_mock(**mtmount_mocks)

    async def setup_mtrotator(self) -> None:
        """Augment MTRotator."""
        mtrotator_mocks = {
            "tel_rotation.next.side_effect": self.mtrotator_tel_rotation_next,
            "tel_rotation.aget.side_effect": self.mtrotator_tel_rotation_next,
            "evt_inPosition.next.side_effect": self.mtrotator_evt_in_position_next,
            "evt_inPosition.aget.side_effect": self.mtrotator_evt_in_position_next,
            "cmd_move.set_start.side_effect": self.mtrotator_cmd_move,
        }
        self.mtcs.rem.mtrotator.configure_mock(**mtrotator_mocks)

    async def setup_mtdome(self) -> None:
        """Augment MTDome."""
        mtdome_mocks = {
            "tel_azimuth.next.side_effect": self.mtdome_tel_azimuth_next,
            "tel_lightWindScreen.next.side_effect": self.mtdome_tel_light_wind_screen_next,
        }

        self.mtcs.rem.mtdome.configure_mock(**mtdome_mocks)

    async def setup_mtm1m3(self) -> None:
        """Augment MTM1M3."""

        m1m3_mocks = {
            "evt_detailedState.next.side_effect": self.mtm1m3_evt_detailed_state,
            "evt_detailedState.aget.side_effect": self.mtm1m3_evt_detailed_state,
            "cmd_raiseM1M3.set_start.side_effect": self.mtm1m3_cmd_raise_m1m3,
            "cmd_lowerM1M3.set_start.side_effect": self.mtm1m3_cmd_lower_m1m3,
            "cmd_enableHardpointCorrections.start.side_effect": self.mtm1m3_cmd_enable_hardpoint_corrections,
            "cmd_abortRaiseM1M3.start.side_effect": self.mtm1m3_cmd_abort_raise_m1m3,
        }

        # Compatibility with xml>12
        if (
            "logevent_appliedBalanceForces"
            in self.components_metadata["MTM1M3"].topic_info
        ):
            m1m3_mocks[
                "evt_appliedBalanceForces.next.side_effect"
            ] = self.mtm1m3_evt_applied_balance_forces
            m1m3_mocks[
                "evt_appliedBalanceForces.aget.side_effect"
            ] = self.mtm1m3_evt_applied_balance_forces
        else:
            m1m3_mocks[
                "tel_appliedBalanceForces.next.side_effect"
            ] = self.mtm1m3_evt_applied_balance_forces
            m1m3_mocks[
                "tel_appliedBalanceForces.aget.side_effect"
            ] = self.mtm1m3_evt_applied_balance_forces

        self.mtcs.rem.mtm1m3.configure_mock(**m1m3_mocks)

    async def setup_mtm2(self) -> None:
        """Augment M2."""

        m2_mocks = {
            "evt_forceBalanceSystemStatus.aget.side_effect": self.mtm2_evt_force_balance_system_status,
            "evt_forceBalanceSystemStatus.next.side_effect": self.mtm2_evt_force_balance_system_status,
            "cmd_switchForceBalanceSystem.set_start.side_effect": self.mtm2_cmd_switch_force_balance_system,
        }

        self.mtcs.rem.mtm2.configure_mock(**m2_mocks)

    async def setup_mthexapod_1(self) -> None:
        """Augment Camera Hexapod."""

        hexapod_1_mocks = {
            "evt_compensationMode.aget.side_effect": self.mthexapod_1_evt_compensation_mode,
            "evt_compensationMode.next.side_effect": self.mthexapod_1_evt_compensation_mode,
            "evt_uncompensatedPosition.aget.side_effect": self.mthexapod_1_evt_uncompensated_position,
            "evt_uncompensatedPosition.next.side_effect": self.mthexapod_1_evt_uncompensated_position,
            "evt_inPosition.aget.side_effect": self.mthexapod_1_evt_in_position,
            "evt_inPosition.next.side_effect": self.mthexapod_1_evt_in_position,
            "cmd_setCompensationMode.set_start.side_effect": self.mthexapod_1_cmd_set_compensation_mode,
            "cmd_move.set_start.side_effect": self.mthexapod_1_cmd_move,
        }

        self.mtcs.rem.mthexapod_1.configure_mock(**hexapod_1_mocks)

    async def setup_mthexapod_2(self) -> None:
        """Augment M2 Hexapod."""

        hexapod_2_mocks = {
            "evt_compensationMode.aget.side_effect": self.mthexapod_2_evt_compensation_mode,
            "evt_compensationMode.next.side_effect": self.mthexapod_2_evt_compensation_mode,
            "evt_uncompensatedPosition.aget.side_effect": self.mthexapod_2_evt_uncompensated_position,
            "evt_uncompensatedPosition.next.side_effect": self.mthexapod_2_evt_uncompensated_position,
            "evt_inPosition.aget.side_effect": self.mthexapod_2_evt_in_position,
            "evt_inPosition.next.side_effect": self.mthexapod_2_evt_in_position,
            "cmd_setCompensationMode.set_start.side_effect": self.mthexapod_2_cmd_set_compensation_mode,
            "cmd_move.set_start.side_effect": self.mthexapod_2_cmd_move,
        }

        self.mtcs.rem.mthexapod_2.configure_mock(**hexapod_2_mocks)

    async def mtmount_evt_target_next(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> types.SimpleNamespace:
        return self._mtmount_evt_target

    async def mtmount_tel_azimuth_next(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> types.SimpleNamespace:
        return self._mtmount_tel_azimuth

    async def mtmount_tel_elevation_next(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> types.SimpleNamespace:
        return self._mtmount_tel_elevation

    async def mtmount_evt_elevation_in_position_next(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> types.SimpleNamespace:
        return self._mtmount_evt_elevation_in_position

    async def mtmount_evt_azimuth_in_position_next(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> types.SimpleNamespace:
        return self._mtmount_evt_azimuth_in_position

    async def mtmount_evt_cameraCableWrapFollowing(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> types.SimpleNamespace:
        return self._mtmount_evt_cameraCableWrapFollowing

    async def mtmount_cmd_enable_ccw_following(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> None:
        self._mtmount_evt_cameraCableWrapFollowing.enabled = 1

    async def mtmount_cmd_disable_ccw_following(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> None:
        self._mtmount_evt_cameraCableWrapFollowing.enabled = 0

    async def mtrotator_cmd_move(self, *args: typing.Any, **kwargs: typing.Any) -> None:

        asyncio.create_task(self._mtrotator_move(position=kwargs.get("position", 0.0)))

    async def _mtrotator_move(self, position: float) -> None:

        self._mtrotator_evt_in_position.inPosition = False

        position_vector = (
            np.arange(self._mtrotator_tel_rotation.actualPosition, position, 0.5)
            if self._mtrotator_tel_rotation.actualPosition < position
            else np.arange(position, self._mtrotator_tel_rotation.actualPosition, 0.5)
        )

        for actual_position in position_vector:
            await asyncio.sleep(0.1)
            self._mtrotator_tel_rotation.actualPosition = actual_position

        self._mtrotator_tel_rotation.actualPosition = position
        self._mtrotator_evt_in_position.inPosition = True

    async def mtrotator_tel_rotation_next(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> types.SimpleNamespace:
        await asyncio.sleep(self.heartbeat_time)
        return self._mtrotator_tel_rotation

    async def mtrotator_evt_in_position_next(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> types.SimpleNamespace:
        await asyncio.sleep(self.heartbeat_time)
        return self._mtrotator_evt_in_position

    async def mtdome_tel_azimuth_next(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> types.SimpleNamespace:
        return self._mtdome_tel_azimuth

    async def mtdome_tel_light_wind_screen_next(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> types.SimpleNamespace:
        return self._mtdome_tel_light_wind_screen

    async def mtm1m3_evt_detailed_state(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> types.SimpleNamespace:
        await asyncio.sleep(self.heartbeat_time)
        return self._mtm1m3_evt_detailed_state

    async def mtm1m3_evt_applied_balance_forces(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> types.SimpleNamespace:
        await asyncio.sleep(self.normal_process_time)
        return self._mtm1m3_evt_applied_balance_forces

    async def mtm1m3_cmd_raise_m1m3(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> None:
        raise_m1m3 = kwargs.get("raiseM1M3", True)

        if (
            raise_m1m3
            and self._mtm1m3_evt_detailed_state.detailedState
            == idl.enums.MTM1M3.DetailedState.PARKED
        ):
            self._mtm1m3_raise_task = asyncio.create_task(self.execute_raise_m1m3())
        else:
            raise RuntimeError(
                f"MTM1M3 current detailed state is {self._mtm1m3_evt_detailed_state.detailedState!r}."
            )

    async def mtm1m3_cmd_abort_raise_m1m3(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> None:

        if self._mtm1m3_evt_detailed_state.detailedState in {
            idl.enums.MTM1M3.DetailedState.RAISINGENGINEERING,
            idl.enums.MTM1M3.DetailedState.RAISING,
        }:
            self._mtm1m3_abort_raise_task = asyncio.create_task(
                self.execute_abort_raise_m1m3()
            )
        else:
            raise RuntimeError("M1M3 Not raising. Cannot abort.")

    async def execute_raise_m1m3(self) -> None:
        self.log.debug("Start raising M1M3...")
        self._mtm1m3_evt_detailed_state.detailedState = (
            idl.enums.MTM1M3.DetailedState.RAISING
        )
        await asyncio.sleep(self.execute_raise_lower_m1m3_time)
        self.log.debug("Done raising M1M3...")
        self._mtm1m3_evt_detailed_state.detailedState = (
            idl.enums.MTM1M3.DetailedState.ACTIVE
        )

    async def mtm1m3_cmd_lower_m1m3(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> None:
        lower_m1m3 = kwargs.get("lowerM1M3", True)

        if (
            lower_m1m3
            and self._mtm1m3_evt_detailed_state.detailedState
            == idl.enums.MTM1M3.DetailedState.ACTIVE
        ):
            self._mtm1m3_lower_task = asyncio.create_task(self.execute_lower_m1m3())
        else:
            raise RuntimeError(
                f"MTM1M3 current detailed state is {self._mtm1m3_evt_detailed_state.detailedState!r}."
            )

    async def execute_lower_m1m3(self) -> None:
        self.log.debug("Start lowering M1M3...")
        self._mtm1m3_evt_detailed_state.detailedState = (
            idl.enums.MTM1M3.DetailedState.LOWERING
        )
        await asyncio.sleep(self.execute_raise_lower_m1m3_time)
        self.log.debug("Done lowering M1M3...")
        self._mtm1m3_evt_detailed_state.detailedState = (
            idl.enums.MTM1M3.DetailedState.PARKED
        )

    async def execute_abort_raise_m1m3(self) -> None:

        if not self._mtm1m3_raise_task.done():
            self.log.debug("Cancel m1m3 raise task...")
            self._mtm1m3_raise_task.cancel()

        self.log.debug("Set m1m3 detailed state to lowering...")
        self._mtm1m3_evt_detailed_state.detailedState = (
            idl.enums.MTM1M3.DetailedState.LOWERING
        )
        await asyncio.sleep(self.execute_raise_lower_m1m3_time)
        self.log.debug("M1M3 raise task done, set detailed state to parked...")
        self._mtm1m3_evt_detailed_state.detailedState = (
            idl.enums.MTM1M3.DetailedState.PARKED
        )

    async def mtm1m3_cmd_enable_hardpoint_corrections(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> None:
        await asyncio.sleep(self.short_process_time)
        if self._mtm1m3_evt_applied_balance_forces.forceMagnitude == 0.0:
            self._hardpoint_corrections_task = asyncio.create_task(
                self._execute_enable_hardpoint_corrections()
            )

    async def _execute_enable_hardpoint_corrections(self) -> float:

        for force_magnitude in range(0, 2200, 200):
            self._mtm1m3_evt_applied_balance_forces.forceMagnitude = force_magnitude
            await asyncio.sleep(self.normal_process_time)

        return self._mtm1m3_evt_applied_balance_forces.forceMagnitude

    async def mtm2_evt_force_balance_system_status(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> types.SimpleNamespace:
        await asyncio.sleep(self.heartbeat_time)
        return self._mtm2_evt_force_balance_system_status

    async def mtm2_cmd_switch_force_balance_system(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> None:
        status = kwargs.get("status", False)

        if status == self._mtm2_evt_force_balance_system_status.status:
            raise RuntimeError(f"Force balance status already {status}.")
        else:
            self.log.debug(
                "Switching force balance status "
                f"{self._mtm2_evt_force_balance_system_status.status} -> {status}"
            )
            await asyncio.sleep(self.heartbeat_time)
            self._mtm2_evt_force_balance_system_status.status = status

    async def mthexapod_1_evt_compensation_mode(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> types.SimpleNamespace:
        await asyncio.sleep(self.heartbeat_time)
        return self._mthexapod_1_evt_compensation_mode

    async def mthexapod_1_cmd_set_compensation_mode(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> None:
        await asyncio.sleep(self.heartbeat_time)
        self._mthexapod_1_evt_compensation_mode.enabled = kwargs.get("enable", 0) == 1

    async def mthexapod_2_evt_compensation_mode(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> types.SimpleNamespace:
        await asyncio.sleep(self.heartbeat_time)
        return self._mthexapod_2_evt_compensation_mode

    async def mthexapod_1_evt_uncompensated_position(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> types.SimpleNamespace:
        await asyncio.sleep(self.heartbeat_time)
        return self._mthexapod_1_evt_uncompensated_position

    async def mthexapod_1_evt_in_position(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> types.SimpleNamespace:
        await asyncio.sleep(self.heartbeat_time)
        return self._mthexapod_1_evt_in_position

    async def mthexapod_2_evt_uncompensated_position(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> types.SimpleNamespace:
        await asyncio.sleep(self.heartbeat_time)
        return self._mthexapod_2_evt_uncompensated_position

    async def mthexapod_2_evt_in_position(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> types.SimpleNamespace:
        await asyncio.sleep(self.heartbeat_time)
        return self._mthexapod_2_evt_in_position

    async def mthexapod_2_cmd_set_compensation_mode(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> None:
        if self._mthexapod_2_evt_compensation_mode.enabled:
            raise RuntimeError("Hexapod 2 compensation mode already enabled.")
        else:
            await asyncio.sleep(self.heartbeat_time)
            self._mthexapod_2_evt_compensation_mode.enabled = True

    async def mthexapod_1_cmd_move(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> None:
        self.log.debug("Move camera hexapod...")
        await asyncio.sleep(self.heartbeat_time / 2)
        self._mthexapod_1_move_task = asyncio.create_task(
            self.execute_hexapod_move(hexapod=1, **kwargs)
        )
        await asyncio.sleep(self.short_process_time)

    async def mthexapod_2_cmd_move(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> None:
        await asyncio.sleep(self.heartbeat_time / 2.0)
        self._mthexapod_2_move_task = asyncio.create_task(
            self.execute_hexapod_move(hexapod=2, **kwargs)
        )
        await asyncio.sleep(self.short_process_time)

    async def execute_hexapod_move(self, hexapod: int, **kwargs: typing.Any) -> None:

        self.log.debug(f"Execute hexapod {hexapod} movement.")
        getattr(self, f"_mthexapod_{hexapod}_evt_in_position").inPosition = False
        hexapod_positions_steps = np.array(
            [
                np.linspace(
                    getattr(self._mthexapod_1_evt_uncompensated_position, axis),
                    kwargs.get(axis, 0.0),
                    10,
                )
                for axis in "xyzuvw"
            ]
        ).T

        for x, y, z, u, v, w in hexapod_positions_steps:
            self.log.debug(f"Hexapod {hexapod} movement: {x} {y} {z} {u} {v} {w}")
            getattr(self, f"_mthexapod_{hexapod}_evt_uncompensated_position").x = x
            getattr(self, f"_mthexapod_{hexapod}_evt_uncompensated_position").y = y
            getattr(self, f"_mthexapod_{hexapod}_evt_uncompensated_position").z = z
            getattr(self, f"_mthexapod_{hexapod}_evt_uncompensated_position").u = u
            getattr(self, f"_mthexapod_{hexapod}_evt_uncompensated_position").v = v
            getattr(self, f"_mthexapod_{hexapod}_evt_uncompensated_position").w = w
            await asyncio.sleep(self.short_process_time * 2.0)

        getattr(self, f"_mthexapod_{hexapod}_evt_in_position").inPosition = True

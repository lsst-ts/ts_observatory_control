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

import asyncio
import logging
import types
import typing

import numpy as np
from lsst.ts import utils, xml
from lsst.ts.observatory.control.maintel.mtcs import MTCS, MTCSUsages
from lsst.ts.observatory.control.mock import RemoteGroupAsyncMock
from lsst.ts.xml.enums import MTM1M3, MTDome


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
        self._mtmount_evt_elevation_motion_state = types.SimpleNamespace(
            state=xml.enums.MTMount.AxisMotionState.STOPPED
        )
        self._mtmount_evt_azimuth_in_position = types.SimpleNamespace(
            inPosition=True,
        )
        self._mtmount_evt_azimuth_motion_state = types.SimpleNamespace(
            state=xml.enums.MTMount.AxisMotionState.STOPPED
        )

        self._mtmount_evt_mirror_covers_motion_state = types.SimpleNamespace(
            state=xml.enums.MTMount.DeployableMotionState.DEPLOYED
        )
        self._mtmount_evt_mirror_covers_system_state = types.SimpleNamespace(
            state=xml.enums.MTMount.PowerState.ON
        )
        self._mtmount_evt_mirror_covers_lock_motion_state = types.SimpleNamespace(
            state=xml.enums.MTMount.DeployableMotionState.RETRACTED
        )
        self._mtmount_mirror_cover_final_closed_state = (
            xml.enums.MTMount.DeployableMotionState.DEPLOYED
        )
        self._mtmount_mirror_cover_final_opened_state = (
            xml.enums.MTMount.DeployableMotionState.RETRACTED
        )

        # MTRotator data
        self._mtrotator_tel_rotation = types.SimpleNamespace(
            demandPosition=0.0,
            actualPosition=0.0,
        )
        self._mtrotator_evt_in_position = types.SimpleNamespace(inPosition=True)
        self._mtrotator_evt_controller_state = types.SimpleNamespace(
            enabledSubstate=xml.enums.MTRotator.EnabledSubstate.STATIONARY
        )
        self._mtrotator_evt_configuration = types.SimpleNamespace(
            positionErrorThreshold=0.1
        )

        # MTDome data
        self._mtdome_tel_azimuth = types.SimpleNamespace(
            positionActual=0.0,
            positionCommanded=0.0,
        )

        self._mtdome_tel_light_wind_screen = types.SimpleNamespace(
            positionActual=0.0,
            positionCommanded=0.0,
        )

        # MTDome Motion PARKED state. State is set by the mocked park cmd.
        self._mtdome_evt_az_motion = types.SimpleNamespace(
            state=MTDome.MotionState.UNDETERMINED, inPosition=False
        )

        self._mtdome_evt_shutter_motion = types.SimpleNamespace(
            state=MTDome.MotionState.UNDETERMINED, inPosition=False
        )

        # MTM1M3 data
        self._mtm1m3_evt_detailed_state = types.SimpleNamespace(
            detailedState=xml.enums.MTM1M3.DetailedState.PARKED
        )
        self._mtm1m3_evt_applied_balance_forces = types.SimpleNamespace(
            forceMagnitude=0.0
        )
        self._mtm1m3_evt_hp_test_status = types.SimpleNamespace(
            testState=[xml.enums.MTM1M3.HardpointTest.NOTTESTED] * 6
        )
        self._mtm1m3_evt_force_actuator_bump_test_status = types.SimpleNamespace(
            actuatorId=0,
            primaryTest=[xml.enums.MTM1M3.BumpTest.NOTTESTED]
            * len(self.mtcs.get_m1m3_actuator_ids()),
            secondaryTest=[xml.enums.MTM1M3.BumpTest.NOTTESTED]
            * len(self.mtcs.get_m1m3_actuator_secondary_ids()),
            primaryTestTimestamps=[0.0] * len(self.mtcs.get_m1m3_actuator_ids()),
            secondaryTestTimestamps=[0.0]
            * len(self.mtcs.get_m1m3_actuator_secondary_ids()),
        )
        self._mtm1m3_evt_force_actuator_state = types.SimpleNamespace(
            slewFlag=False,
            balanceForcesApplied=False,
        )
        self.desired_hp_test_final_status = xml.enums.MTM1M3.HardpointTest.PASSED
        self.desired_bump_test_final_status = xml.enums.MTM1M3.BumpTest.PASSED

        self.m1m3_actuator_offset = 101

        self._mtm1m3_raise_task = utils.make_done_future()
        self._mtm1m3_lower_task = utils.make_done_future()
        self._hardpoint_corrections_task = utils.make_done_future()

        # MTM2 data
        self._mtm2_evt_force_balance_system_status = types.SimpleNamespace(status=False)
        self._mtm2_evt_hardpointList = types.SimpleNamespace(
            actuators=list([6, 16, 26, 74, 76, 78])
        )

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

        self._evt_slew_controller_settings = types.SimpleNamespace(
            useAccelerationForces=False,
            useBalanceForces=False,
            triggerBoosterValves=False,
            useVelocityForces=False,
        )

    async def setup_mocks(self) -> None:
        await self.setup_mtmount()
        await self.setup_mtrotator()
        await self.setup_mtdome()
        await self.setup_mtm1m3()
        await self.setup_mtm2()
        await self.setup_mthexapod_1()
        await self.setup_mthexapod_2()
        await self.setup_mtaos()

    async def setup_mtmount(self) -> None:
        """Augment MTMount."""
        mtmount_mocks = {
            "evt_target.next.side_effect": self.mtmount_evt_target_next,
            "evt_target.aget.side_effect": self.mtmount_evt_target_next,
            "tel_azimuth.next.side_effect": self.mtmount_tel_azimuth_next,
            "tel_azimuth.aget.side_effect": self.mtmount_tel_azimuth_next,
            "tel_azimuth.DataType.return_value": self.get_sample(
                "MTMount", "tel_azimuth"
            ),
            "tel_elevation.next.side_effect": self.mtmount_tel_elevation_next,
            "tel_elevation.aget.side_effect": self.mtmount_tel_elevation_next,
            "evt_elevationInPosition.next.side_effect": self.mtmount_evt_elevation_in_position_next,
            "evt_azimuthInPosition.next.side_effect": self.mtmount_evt_azimuth_in_position_next,
            "evt_elevationMotionState.next.side_effect": self.mtmount_evt_elevation_motion_state_next,
            "evt_azimuthMotionState.next.side_effect": self.mtmount_evt_azimuth_motion_state_next,
            "evt_elevationMotionState.aget.side_effect": self.mtmount_evt_elevation_motion_state_aget,
            "evt_azimuthMotionState.aget.side_effect": self.mtmount_evt_azimuth_motion_state_aget,
            "evt_cameraCableWrapFollowing.aget.side_effect": self.mtmount_evt_cameraCableWrapFollowing,
            "cmd_enableCameraCableWrapFollowing.start.side_effect": self.mtmount_cmd_enable_ccw_following,
            "cmd_disableCameraCableWrapFollowing.start.side_effect": self.mtmount_cmd_disable_ccw_following,
            "evt_mirrorCoversMotionState.aget.side_effect": self.mtmount_evt_mirror_covers_motion_state,
            "evt_mirrorCoversMotionState.next.side_effect": self.mtmount_evt_mirror_covers_motion_state,
            "evt_mirrorCoversSystemState.aget.side_effect": self.mtmount_evt_mirror_covers_system_state,
            "evt_mirrorCoverLocksMotionState.aget.side_effect": (
                self.mtmount_evt_mirror_covers_locks_motion_state
            ),
            "evt_mirrorCoverLocksMotionState.next.side_effect": (
                self.mtmount_evt_mirror_covers_locks_motion_state
            ),
            "cmd_closeMirrorCovers.start.side_effect": self.mtmount_cmd_close_mirror_covers,
            "cmd_openMirrorCovers.set_start.side_effect": self.mtmount_cmd_open_mirror_covers,
        }

        self.mtcs.rem.mtmount.configure_mock(**mtmount_mocks)

    async def setup_mtrotator(self) -> None:
        """Augment MTRotator."""
        mtrotator_mocks = {
            "tel_rotation.next.side_effect": self.mtrotator_tel_rotation_next,
            "tel_rotation.aget.side_effect": self.mtrotator_tel_rotation_next,
            "evt_inPosition.next.side_effect": self.mtrotator_evt_in_position_next,
            "evt_inPosition.aget.side_effect": self.mtrotator_evt_in_position_next,
            "evt_configuration.aget.side_effect": self.mtrotator_evt_configuration_aget,
            "cmd_move.set_start.side_effect": self.mtrotator_cmd_move,
            "cmd_stop.start.side_effect": self.mtrotator_cmd_stop,
            "evt_controllerState.next.side_effect": self.mtrotator_evt_controller_state_next,
            "evt_controllerState.aget.side_effect": self.mtrotator_evt_controller_state_next,
        }
        self.mtcs.rem.mtrotator.configure_mock(**mtrotator_mocks)

    async def setup_mtdome(self) -> None:
        """Augment MTDome."""
        mtdome_mocks = {
            "tel_azimuth.next.side_effect": self.mtdome_tel_azimuth_next,
            "tel_azimuth.aget.side_effect": self.mtdome_tel_azimuth_next,
            "tel_lightWindScreen.next.side_effect": self.mtdome_tel_light_wind_screen_next,
            "cmd_park.start.side_effect": self.mtdome_cmd_park,
            "cmd_moveAz.set_start.side_effect": self.mtdome_cmd_move_az,
            "evt_azMotion.aget.side_effect": self.mtdome_evt_az_motion_next,
            "evt_azMotion.next.side_effect": self.mtdome_evt_az_motion_next,
            "cmd_stop.set_start.side_effect": self.mtdome_cmd_stop,
            "cmd_setZeroAz.start.side_effect": self.mtdome_cmd_set_zero_az,
            "evt_shutterMotion.aget.side_effect": self.mtdome_evt_shutter_motion_next,
            "cmd_openShutter.start.side_effect": self.mtdome_cmd_open_shutter,
            "cmd_closeShutter.start.side_effect": self.mtdome_cmd_close_shutter,
        }

        self.mtcs.rem.mtdome.configure_mock(**mtdome_mocks)

    async def setup_mtm1m3(self) -> None:
        """Augment MTM1M3."""

        self.mtm1m3_cmd_enter_engineering_timeout = False

        m1m3_mocks = {
            "evt_detailedState.next.side_effect": self.mtm1m3_evt_detailed_state,
            "evt_detailedState.aget.side_effect": self.mtm1m3_evt_detailed_state,
            "evt_hardpointTestStatus.next.side_effect": self.mtm1m3_evt_hp_test_status,
            "evt_hardpointTestStatus.aget.side_effect": self.mtm1m3_evt_hp_test_status,
            "evt_forceActuatorBumpTestStatus.next.side_effect": self.mtm1m3_evt_bump_test_status,
            "evt_forceActuatorBumpTestStatus.aget.side_effect": self.mtm1m3_evt_bump_test_status,
            "cmd_raiseM1M3.set_start.side_effect": self.mtm1m3_cmd_raise_m1m3,
            "cmd_lowerM1M3.set_start.side_effect": self.mtm1m3_cmd_lower_m1m3,
            "cmd_enableHardpointCorrections.start.side_effect": self.mtm1m3_cmd_enable_hardpoint_corrections,
            "cmd_disableHardpointCorrections.start.side_effect": self.mtm1m3_cmd_disable_hp_corrections,
            "cmd_abortRaiseM1M3.start.side_effect": self.mtm1m3_cmd_abort_raise_m1m3,
            "cmd_enterEngineering.start.side_effect": self.mtm1m3_cmd_enter_engineering,
            "cmd_exitEngineering.start.side_effect": self.mtm1m3_cmd_exit_engineering,
            "cmd_testHardpoint.set_start.side_effect": self.mtm1m3_cmd_test_hardpoint,
            "cmd_forceActuatorBumpTest.set_start.side_effect": self.mtm1m3_cmd_force_actuator_bump_test,
            "evt_slewControllerSettings.aget.side_effect": self.mtm1m3_evt_slew_controller_flags,
            "cmd_setSlewControllerSettings.set_start.side_effect": self.mtm1m3_cmd_set_slew_controller_flags,
        }

        # Compatibility with xml>12
        if "evt_appliedBalanceForces" in self.components_metadata["MTM1M3"].topics:
            m1m3_mocks["evt_appliedBalanceForces.next.side_effect"] = (
                self.mtm1m3_evt_applied_balance_forces
            )
            m1m3_mocks["evt_appliedBalanceForces.aget.side_effect"] = (
                self.mtm1m3_evt_applied_balance_forces
            )
        else:
            m1m3_mocks["tel_appliedBalanceForces.next.side_effect"] = (
                self.mtm1m3_evt_applied_balance_forces
            )
            m1m3_mocks["tel_appliedBalanceForces.aget.side_effect"] = (
                self.mtm1m3_evt_applied_balance_forces
            )

        # Compatibility with xml>16
        if "evt_forceControllerState" in self.components_metadata["MTM1M3"].topics:
            m1m3_mocks["evt_forceControllerState.aget.side_effect"] = (
                self.mtm1m3_evt_force_actuator_state
            )
            m1m3_mocks["evt_forceControllerState.next.side_effect"] = (
                self.mtm1m3_evt_force_actuator_state
            )

        if "evt_boosterValveStatus" in self.components_metadata["MTM1M3"].topics:
            m1m3_mocks["evt_boosterValveStatus.aget.side_effect"] = (
                self.mtm1m3_evt_force_actuator_state
            )
            m1m3_mocks["evt_boosterValveStatus.next.side_effect"] = (
                self.mtm1m3_evt_force_actuator_state
            )

        if "cmd_setAirSlewFlag" in self.components_metadata["MTM1M3"].topics:
            m1m3_mocks["cmd_setAirSlewFlag.set_start.side_effect"] = (
                self.mtm1m3_cmd_set_air_slew_flag
            )

        if "cmd_setSlewFlag" in self.components_metadata["MTM1M3"].topics:
            m1m3_mocks["cmd_setSlewFlag.set_start.side_effect"] = (
                self.mtm1m3_cmd_set_slew_flag
            )

        if "cmd_clearSlewFlag" in self.components_metadata["MTM1M3"].topics:
            m1m3_mocks["cmd_clearSlewFlag.set_start.side_effect"] = (
                self.mtm1m3_cmd_clear_slew_flag
            )

        if "cmd_boosterValveOpen" in self.components_metadata["MTM1M3"].topics:
            m1m3_mocks["cmd_boosterValveOpen.start.side_effect"] = (
                self.mtm1m3_cmd_booster_valve_open
            )
            m1m3_mocks["cmd_boosterValveClose.start.side_effect"] = (
                self.mtm1m3_cmd_booster_valve_close
            )

        self.mtcs.rem.mtm1m3.configure_mock(**m1m3_mocks)

    async def setup_mtm2(self) -> None:
        """Augment M2."""

        m2_mocks = {
            "evt_forceBalanceSystemStatus.aget.side_effect": self.mtm2_evt_force_balance_system_status,
            "evt_forceBalanceSystemStatus.next.side_effect": self.mtm2_evt_force_balance_system_status,
            "cmd_switchForceBalanceSystem.set_start.side_effect": self.mtm2_cmd_switch_force_balance_system,
            "cmd_actuatorBumpTest.set_start.side_effect": self.mtm2_cmd_actuator_bump_test,
            "evt_hardpointList.aget.side_effect": self.mtm2_evt_hardpointList,
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
            "cmd_offset.set_start.side_effect": self.mthexapod_1_cmd_offset,
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
            "cmd_offset.set_start.side_effect": self.mthexapod_2_cmd_offset,
        }

        self.mtcs.rem.mthexapod_2.configure_mock(**hexapod_2_mocks)

    async def setup_mtaos(self) -> None:

        offset_dof_field_info = self.get_sample("MTAOS", "cmd_offsetDOF")
        mtaos_mocks = {
            "cmd_offsetDOF.DataType.return_value": types.SimpleNamespace(
                value=np.zeros(offset_dof_field_info.value.count)
            ),
            "cmd_offsetDOF.start.side_effect": self.mtaos_cmd_offset_dof,
        }

        self.mtcs.rem.mtaos.configure_mock(**mtaos_mocks)

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
        await asyncio.sleep(self.heartbeat_time)
        return self._mtmount_tel_elevation

    async def mtmount_evt_elevation_in_position_next(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> types.SimpleNamespace:
        return self._mtmount_evt_elevation_in_position

    async def mtmount_evt_elevation_motion_state_next(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> types.SimpleNamespace:
        await asyncio.sleep(0.5)
        return self._mtmount_evt_elevation_motion_state

    async def mtmount_evt_elevation_motion_state_aget(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> types.SimpleNamespace:
        return self._mtmount_evt_elevation_motion_state

    async def mtmount_evt_azimuth_in_position_next(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> types.SimpleNamespace:
        return self._mtmount_evt_azimuth_in_position

    async def mtmount_evt_azimuth_motion_state_next(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> types.SimpleNamespace:
        await asyncio.sleep(0.5)
        return self._mtmount_evt_azimuth_motion_state

    async def mtmount_evt_azimuth_motion_state_aget(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> types.SimpleNamespace:
        return self._mtmount_evt_azimuth_motion_state

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

    async def mtmount_evt_mirror_covers_motion_state(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> types.SimpleNamespace:
        await asyncio.sleep(self.heartbeat_time)
        return self._mtmount_evt_mirror_covers_motion_state

    async def mtmount_evt_mirror_covers_locks_motion_state(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> types.SimpleNamespace:
        await asyncio.sleep(self.heartbeat_time)
        return self._mtmount_evt_mirror_covers_lock_motion_state

    async def mtmount_evt_mirror_covers_system_state(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> types.SimpleNamespace:
        await asyncio.sleep(self.heartbeat_time)
        return self._mtmount_evt_mirror_covers_system_state

    async def mtmount_cmd_close_mirror_covers(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> None:
        asyncio.create_task(self._mtmount_cmd_close_mirror_covers())

    async def _mtmount_cmd_close_mirror_covers(self) -> None:
        self._mtmount_evt_mirror_covers_lock_motion_state.state = (
            xml.enums.MTMount.DeployableMotionState.RETRACTING
        )
        await asyncio.sleep(self.heartbeat_time)
        self._mtmount_evt_mirror_covers_lock_motion_state.state = (
            xml.enums.MTMount.DeployableMotionState.RETRACTED
        )
        await asyncio.sleep(self.heartbeat_time)
        self._mtmount_evt_mirror_covers_motion_state.state = (
            self._mtmount_mirror_cover_final_closed_state
        )
        await asyncio.sleep(self.heartbeat_time)
        self._mtmount_evt_mirror_covers_motion_state.state = (
            xml.enums.MTMount.DeployableMotionState.DEPLOYED
        )

    async def mtmount_cmd_open_mirror_covers(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> None:
        asyncio.create_task(self._mtmount_cmd_open_mirror_covers())

    async def _mtmount_cmd_open_mirror_covers(self) -> None:
        self._mtmount_evt_mirror_covers_motion_state.state = (
            xml.enums.MTMount.DeployableMotionState.RETRACTING
        )
        await asyncio.sleep(self.heartbeat_time)
        self._mtmount_evt_mirror_covers_motion_state.state = (
            self._mtmount_mirror_cover_final_opened_state
        )
        self._mtmount_evt_mirror_covers_lock_motion_state.state = (
            xml.enums.MTMount.DeployableMotionState.DEPLOYING
        )
        await asyncio.sleep(self.heartbeat_time)
        self._mtmount_evt_mirror_covers_lock_motion_state.state = (
            xml.enums.MTMount.DeployableMotionState.DEPLOYED
        )
        await asyncio.sleep(self.heartbeat_time)

    async def _mtrotator_move(self, position: float) -> None:
        self._mtrotator_evt_in_position.inPosition = False
        self._mtrotator_evt_controller_state.enabledSubstate = (
            xml.enums.MTRotator.EnabledSubstate.MOVING_POINT_TO_POINT
        )

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
        self._mtrotator_evt_controller_state.enabledSubstate = (
            xml.enums.MTRotator.EnabledSubstate.STATIONARY
        )

    async def mtrotator_cmd_stop(self, *args: typing.Any, **kwargs: typing.Any) -> None:
        asyncio.create_task(self._mtrotator_stop())

    async def _mtrotator_stop(self) -> None:
        self._mtrotator_evt_controller_state.enabledSubstate = (
            xml.enums.MTRotator.EnabledSubstate.CONSTANT_VELOCITY
        )
        await asyncio.sleep(1.0)
        self._mtrotator_evt_controller_state.enabledSubstate = (
            xml.enums.MTRotator.EnabledSubstate.STATIONARY
        )

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

    async def mtrotator_evt_configuration_aget(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> types.SimpleNamespace:
        return self._mtrotator_evt_configuration

    async def mtrotator_evt_controller_state_next(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> types.SimpleNamespace:
        await asyncio.sleep(self.heartbeat_time)
        return self._mtrotator_evt_controller_state

    async def mtdome_tel_azimuth_next(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> types.SimpleNamespace:
        return self._mtdome_tel_azimuth

    async def mtdome_tel_light_wind_screen_next(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> types.SimpleNamespace:
        return self._mtdome_tel_light_wind_screen

    async def mtdome_cmd_park(self, timeout: float) -> None:
        asyncio.create_task(self._mtdome_park())

    async def _mtdome_park(self) -> None:
        # Mock implementation of cmd_park
        await asyncio.sleep(self.heartbeat_time)
        self.log.info("Dome park command executed")
        self._mtdome_evt_az_motion = types.SimpleNamespace(
            state=MTDome.MotionState.PARKED, inPosition=True
        )

        self._mtdome_tel_azimuth = types.SimpleNamespace(
            positionActual=360.0 - 32.0,  # as per current logic in MTDome
            # do_park: 360.0 - DOME_AZIMUTH_OFFSET
            positionCommanded=0.0,
        )

    async def mtdome_cmd_move_az(self, *args: typing.Any, **kwargs: typing.Any) -> None:
        asyncio.create_task(self._mtdome_move_az())

    async def _mtdome_move_az(self, *args: typing.Any, **kwargs: typing.Any) -> None:
        # Mock implementation of dome park , unpark and slew_dome_to
        self.log.info("Dome moveAz command executed")
        await asyncio.sleep(self.heartbeat_time * 2)
        # This wait time and Dome MotionSate MOVING is to mock the
        # test_unpark_dome
        self._mtdome_evt_az_motion = types.SimpleNamespace(
            state=MTDome.MotionState.MOVING, inPosition=False
        )

        # The following delay is timed so that the MOVING state above
        # remains long enough for the test_unpark_dome to pick it
        # up and complete successfully. Same wise the test_slew_dome_to
        # expects at some point an ENABLED and inPosition.
        await asyncio.sleep(self.heartbeat_time * 3)
        self.log.info("Slew dome to azimuth command executed")
        self._mtdome_evt_az_motion = types.SimpleNamespace(
            state=MTDome.MotionState.ENABLED, inPosition=True
        )

    async def mtdome_evt_az_motion_next(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> types.SimpleNamespace:
        await asyncio.sleep(self.heartbeat_time * 3)
        return self._mtdome_evt_az_motion

    async def mtdome_cmd_stop(self, *args: typing.Any, **kwargs: typing.Any) -> None:
        asyncio.create_task(self._mtdome_stop())

    async def _mtdome_stop(self) -> None:
        self.log.info("Stopping dome.")
        self._mtdome_evt_az_motion.state = xml.enums.MTDome.MotionState.STOPPING_BRAKING
        await asyncio.sleep(self.heartbeat_time * 10)
        self._mtdome_evt_az_motion.state = xml.enums.MTDome.MotionState.STOPPED_BRAKED
        self.log.info("Dome stopped.")

    async def mtdome_cmd_set_zero_az(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> None:
        self._mtdome_tel_azimuth = types.SimpleNamespace(
            positionActual=0.0,
            positionCommanded=0.0,
        )

    async def mtdome_evt_shutter_motion_next(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> types.SimpleNamespace:
        await asyncio.sleep(self.heartbeat_time)
        return self._mtdome_evt_shutter_motion

    async def mtdome_cmd_open_shutter(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> None:
        asyncio.create_task(self._mtdome_open_shutter())

    async def _mtdome_open_shutter(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> None:
        self.log.debug("Dome openShutter command executed")
        self._mtdome_evt_shutter_motion = types.SimpleNamespace(
            state=MTDome.MotionState.OPENING, inPosition=False
        )
        await asyncio.sleep(self.heartbeat_time)
        self._mtdome_evt_shutter_motion = types.SimpleNamespace(
            state=MTDome.MotionState.OPEN, inPosition=True
        )

    async def mtdome_cmd_close_shutter(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> None:
        asyncio.create_task(self._mtdome_close_shutter())

    async def _mtdome_close_shutter(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> None:
        self.log.debug("Dome closeShutter command executed")
        self._mtdome_evt_shutter_motion = types.SimpleNamespace(
            state=MTDome.MotionState.CLOSING, inPosition=False
        )
        await asyncio.sleep(self.heartbeat_time)
        self._mtdome_evt_shutter_motion = types.SimpleNamespace(
            state=MTDome.MotionState.CLOSED, inPosition=True
        )

    async def mtm1m3_evt_detailed_state(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> types.SimpleNamespace:
        await asyncio.sleep(self.heartbeat_time / 4.0)
        return self._mtm1m3_evt_detailed_state

    async def mtm1m3_evt_hp_test_status(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> types.SimpleNamespace:
        await asyncio.sleep(self.heartbeat_time / 4.0)
        return self._mtm1m3_evt_hp_test_status

    async def mtm1m3_evt_bump_test_status(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> types.SimpleNamespace:
        await asyncio.sleep(self.heartbeat_time / 4.0)
        return self._mtm1m3_evt_force_actuator_bump_test_status

    async def mtm1m3_evt_applied_balance_forces(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> types.SimpleNamespace:
        await asyncio.sleep(self.normal_process_time)
        return self._mtm1m3_evt_applied_balance_forces

    async def mtm1m3_evt_force_actuator_state(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> types.SimpleNamespace:
        await asyncio.sleep(self.heartbeat_time / 4.0)
        return self._mtm1m3_evt_force_actuator_state

    async def mtm1m3_cmd_set_air_slew_flag(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> None:
        asyncio.create_task(
            self._mtm1m3_cmd_set_air_slew_flag(slew_flag=kwargs["slewFlag"])
        )

    async def mtm1m3_cmd_set_slew_flag(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> None:
        asyncio.create_task(self._mtm1m3_cmd_set_air_slew_flag(slew_flag=True))

    async def mtm1m3_cmd_clear_slew_flag(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> None:
        asyncio.create_task(self._mtm1m3_cmd_set_air_slew_flag(slew_flag=False))

    async def mtm1m3_cmd_booster_valve_open(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> None:
        asyncio.create_task(self._mtm1m3_cmd_set_air_slew_flag(slew_flag=True))

    async def mtm1m3_cmd_booster_valve_close(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> None:
        asyncio.create_task(self._mtm1m3_cmd_set_air_slew_flag(slew_flag=False))

    async def _mtm1m3_cmd_set_air_slew_flag(self, slew_flag: bool) -> None:
        await asyncio.sleep(self.heartbeat_time / 2.0)
        self._mtm1m3_evt_force_actuator_state.slewFlag = slew_flag

    async def mtm1m3_cmd_raise_m1m3(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> None:
        raise_m1m3 = kwargs.get("raiseM1M3", True)

        if (
            raise_m1m3
            and self._mtm1m3_evt_detailed_state.detailedState
            == xml.enums.MTM1M3.DetailedState.PARKED
        ):
            self._mtm1m3_raise_task = asyncio.create_task(self.execute_raise_m1m3())
        else:
            raise RuntimeError(
                f"MTM1M3 current detailed state is {self._mtm1m3_evt_detailed_state.detailedState!r}."
            )

    async def mtm1m3_cmd_enter_engineering(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> None:
        # This is a very simple mock of the enter engineering command. I
        # imagine the actual command only works from certain detailed states
        # but I don't think it is worth trying to do anything more elaborate
        # since it could change considerably from what the m1m3 actually does.
        asyncio.create_task(
            self._set_m1m3_detailed_state(
                xml.enums.MTM1M3.DetailedState.PARKEDENGINEERING
            )
        )

        # TODO (DM-39458): Remove this workaround.
        # While running this command at the summit/production environment we
        # have have experienced higher than average command timeouts. For the
        # time being I implemented a workaround in
        # MTCS.enter_m1m3_engineering_mode to ignore command timeouts. Once we
        # figure out what is causing this issues (or we finish moving from DDS
        # to Kafka and these issues, hopefully disappears) this work around
        # should be removed.
        if self.mtm1m3_cmd_enter_engineering_timeout:
            raise asyncio.TimeoutError("Mock command timeout.")

    async def mtm1m3_cmd_exit_engineering(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> None:
        # This is a very simple mock of the exit engineering command. It will
        # simply put m1m3 in PARKED state, regardless of which engineering
        # state it was before.
        asyncio.create_task(
            self._set_m1m3_detailed_state(xml.enums.MTM1M3.DetailedState.PARKED)
        )

    async def mtm1m3_cmd_test_hardpoint(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> None:
        asyncio.create_task(
            self._mtm1m3_cmd_test_hardpoint(hp=kwargs["hardpointActuator"] - 1)
        )

    async def mtm1m3_cmd_force_actuator_bump_test(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> None:
        actuator_id = kwargs["actuatorId"]
        self._mtm1m3_evt_force_actuator_bump_test_status.actuatorId = actuator_id
        if (
            kwargs["testSecondary"]
            and actuator_id not in self.mtcs.get_m1m3_actuator_secondary_ids()
        ):
            raise RuntimeError(f"Actuator {actuator_id} does not have secondary axis.")
        asyncio.create_task(
            self._mtm1m3_cmd_force_actuator_bump_test(
                actuator_id=actuator_id,
                test_primary=kwargs["testPrimary"],
                test_secondary=kwargs["testSecondary"],
            )
        )

    async def mtm1m3_cmd_abort_raise_m1m3(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> None:
        if self._mtm1m3_evt_detailed_state.detailedState in {
            xml.enums.MTM1M3.DetailedState.RAISINGENGINEERING,
            xml.enums.MTM1M3.DetailedState.RAISING,
        }:
            self._mtm1m3_abort_raise_task = asyncio.create_task(
                self.execute_abort_raise_m1m3()
            )
        else:
            raise RuntimeError("M1M3 Not raising. Cannot abort.")

    async def execute_raise_m1m3(self) -> None:
        self.log.debug("Start raising M1M3...")
        self._mtm1m3_evt_detailed_state.detailedState = (
            xml.enums.MTM1M3.DetailedState.RAISING
        )
        await asyncio.sleep(self.execute_raise_lower_m1m3_time)
        self.log.debug("Done raising M1M3...")
        self._mtm1m3_evt_detailed_state.detailedState = (
            xml.enums.MTM1M3.DetailedState.ACTIVE
        )

    async def mtm1m3_cmd_lower_m1m3(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> None:
        lower_m1m3 = kwargs.get("lowerM1M3", True)

        if (
            lower_m1m3
            and self._mtm1m3_evt_detailed_state.detailedState
            == xml.enums.MTM1M3.DetailedState.ACTIVE
        ):
            self._mtm1m3_lower_task = asyncio.create_task(self.execute_lower_m1m3())
        else:
            raise RuntimeError(
                f"MTM1M3 current detailed state is {self._mtm1m3_evt_detailed_state.detailedState!r}."
            )

    async def execute_lower_m1m3(self) -> None:
        self.log.debug("Start lowering M1M3...")
        self._mtm1m3_evt_detailed_state.detailedState = (
            xml.enums.MTM1M3.DetailedState.LOWERING
        )
        await asyncio.sleep(self.execute_raise_lower_m1m3_time)
        self.log.debug("Done lowering M1M3...")
        self._mtm1m3_evt_detailed_state.detailedState = (
            xml.enums.MTM1M3.DetailedState.PARKED
        )

    async def execute_abort_raise_m1m3(self) -> None:
        if not self._mtm1m3_raise_task.done():
            self.log.debug("Cancel m1m3 raise task...")
            self._mtm1m3_raise_task.cancel()

        self.log.debug("Set m1m3 detailed state to lowering...")
        self._mtm1m3_evt_detailed_state.detailedState = (
            xml.enums.MTM1M3.DetailedState.LOWERING
        )
        await asyncio.sleep(self.execute_raise_lower_m1m3_time)
        self.log.debug("M1M3 raise task done, set detailed state to parked...")
        self._mtm1m3_evt_detailed_state.detailedState = (
            xml.enums.MTM1M3.DetailedState.PARKED
        )

    async def mtm1m3_cmd_enable_hardpoint_corrections(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> None:
        await asyncio.sleep(self.short_process_time)

        if not self._mtm1m3_evt_force_actuator_state.balanceForcesApplied:
            self._hardpoint_corrections_task = asyncio.create_task(
                self._execute_enable_hardpoint_corrections()
            )

    async def mtm1m3_cmd_disable_hp_corrections(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> None:
        await asyncio.sleep(self.short_process_time)

        if self._mtm1m3_evt_force_actuator_state.balanceForcesApplied:
            self._hardpoint_corrections_task = asyncio.create_task(
                self._execute_disable_hardpoint_corrections()
            )

    async def _set_m1m3_detailed_state(
        self, detailed_state: xml.enums.MTM1M3.DetailedState
    ) -> None:
        self.log.debug(
            f"M1M3 detailed state: {self._mtm1m3_evt_detailed_state.detailedState!r} -> {detailed_state!r}"
        )
        await asyncio.sleep(self.heartbeat_time / 2.0)
        self._mtm1m3_evt_detailed_state.detailedState = detailed_state

    async def _mtm1m3_cmd_test_hardpoint(self, hp: int) -> None:
        hp_test_status = [
            xml.enums.MTM1M3.HardpointTest.TESTINGPOSITIVE,
            xml.enums.MTM1M3.HardpointTest.TESTINGNEGATIVE,
            self.desired_hp_test_final_status,
        ]

        for test_status in hp_test_status:
            self._mtm1m3_evt_hp_test_status.testState[hp] = test_status
            self.log.debug(f"{self._mtm1m3_evt_hp_test_status!r}")
            await asyncio.sleep(self.heartbeat_time / 2.0)

    async def _mtm1m3_cmd_force_actuator_bump_test(
        self, actuator_id: int, test_primary: bool, test_secondary: bool
    ) -> None:
        bump_test_states = [
            xml.enums.MTM1M3.BumpTest.TESTINGPOSITIVE,
            xml.enums.MTM1M3.BumpTest.TESTINGPOSITIVEWAIT,
            xml.enums.MTM1M3.BumpTest.TESTINGNEGATIVE,
            xml.enums.MTM1M3.BumpTest.TESTINGNEGATIVEWAIT,
        ]

        if test_primary:
            actuator_index = self.mtcs.get_m1m3_actuator_index(actuator_id=actuator_id)

            for state in bump_test_states:
                self._mtm1m3_evt_force_actuator_bump_test_status.primaryTest[
                    actuator_index
                ] = state
                self._mtm1m3_evt_force_actuator_bump_test_status.primaryTestTimestamps[
                    actuator_index
                ] = utils.current_tai()
                await asyncio.sleep(self.heartbeat_time / 2.0)

            if not test_secondary:
                self._mtm1m3_evt_force_actuator_bump_test_status.actuatorId = -1
            self._mtm1m3_evt_force_actuator_bump_test_status.primaryTest[
                actuator_index
            ] = self.desired_bump_test_final_status
            self._mtm1m3_evt_force_actuator_bump_test_status.primaryTestTimestamps[
                actuator_index
            ] = utils.current_tai()

        if test_secondary:
            actuator_sindex = self.mtcs.get_m1m3_actuator_secondary_index(
                actuator_id=actuator_id
            )
            for state in bump_test_states:
                self._mtm1m3_evt_force_actuator_bump_test_status.secondaryTest[
                    actuator_sindex
                ] = state
                self._mtm1m3_evt_force_actuator_bump_test_status.secondaryTestTimestamps[
                    actuator_sindex
                ] = utils.current_tai()
                await asyncio.sleep(self.heartbeat_time / 2.0)

            self._mtm1m3_evt_force_actuator_bump_test_status.actuatorId = -1
            self._mtm1m3_evt_force_actuator_bump_test_status.secondaryTest[
                actuator_sindex
            ] = self.desired_bump_test_final_status
            self._mtm1m3_evt_force_actuator_bump_test_status.secondaryTestTimestamps[
                actuator_sindex
            ] = utils.current_tai()

    async def mtm1m3_cmd_set_slew_controller_flags(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> None:
        # Extract parameters from kwargs
        slew_setting_value = kwargs.get("slewSettings")
        enable_slew_management = kwargs.get("enableSlewManagement")

        if slew_setting_value is None or enable_slew_management is None:
            raise ValueError(
                "slewSettings and enableSlewManagement parameters are required."
            )

        # Convert the integer to the corresponding enumeration member name
        setting_enum = MTM1M3.SetSlewControllerSettings(slew_setting_value)

        # Mapping enum names to the expected attributes
        setting_attr = self.mtcs.map_slew_setting_to_attribute(setting_enum)

        if setting_attr is None:
            raise RuntimeError(f"Invalid slew setting value: {slew_setting_value}")

        # Update the internal state to reflect the change
        if hasattr(self._evt_slew_controller_settings, setting_attr):
            setattr(
                self._evt_slew_controller_settings, setting_attr, enable_slew_management
            )
        else:
            raise RuntimeError(
                f"Unexpected error. Setting attribute '{setting_attr}' not found."
            )

    async def mtm1m3_evt_slew_controller_flags(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> types.SimpleNamespace:
        await asyncio.sleep(self.heartbeat_time / 4.0)
        return self._evt_slew_controller_settings

    async def _execute_enable_hardpoint_corrections(self) -> float:
        for force_magnitude in range(0, 2200, 200):
            self._mtm1m3_evt_applied_balance_forces.forceMagnitude = force_magnitude
            await asyncio.sleep(self.normal_process_time)
        self._mtm1m3_evt_force_actuator_state.balanceForcesApplied = True
        return self._mtm1m3_evt_applied_balance_forces.forceMagnitude

    async def _execute_disable_hardpoint_corrections(self) -> float:
        for force_magnitude in range(2000, -200, -200):
            self._mtm1m3_evt_applied_balance_forces.forceMagnitude = force_magnitude
            await asyncio.sleep(self.normal_process_time)
        self._mtm1m3_evt_force_actuator_state.balanceForcesApplied = False
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

    async def mtm2_cmd_actuator_bump_test(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> None:
        for key in ["actuator", "period", "force"]:
            if key not in kwargs:
                raise Exception(f"{key} not given in call")

    async def mtm2_evt_hardpointList(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> types.SimpleNamespace:
        await asyncio.sleep(self.heartbeat_time)
        return self._mtm2_evt_hardpointList

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

    async def mthexapod_1_cmd_offset(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> None:
        self.log.debug("Move camera hexapod...")
        await asyncio.sleep(self.heartbeat_time / 2)

        self._mthexapod_1_move_task = asyncio.create_task(
            self.execute_hexapod_offset(hexapod=1, **kwargs)
        )
        await asyncio.sleep(self.short_process_time)

    async def mtaos_cmd_offset_dof(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> None:
        self.log.info(f"{kwargs=}")
        await self.mtcs.rem.mthexapod_1.cmd_move.set_start(
            x=kwargs["data"].value[6],
            y=kwargs["data"].value[7],
            z=kwargs["data"].value[5],
            u=kwargs["data"].value[8],
            v=kwargs["data"].value[9],
            w=0,
            sync=True,
            timeout=kwargs["timeout"],
        )
        await self.mtcs.rem.mthexapod_2.cmd_move.set_start(
            x=kwargs["data"].value[1],
            y=kwargs["data"].value[2],
            z=kwargs["data"].value[0],
            u=kwargs["data"].value[3],
            v=kwargs["data"].value[4],
            w=0,
            sync=True,
            timeout=kwargs["timeout"],
        )

    async def mthexapod_2_cmd_offset(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> None:
        await asyncio.sleep(self.heartbeat_time / 2.0)
        self._mthexapod_2_move_task = asyncio.create_task(
            self.execute_hexapod_offset(hexapod=2, **kwargs)
        )
        await asyncio.sleep(self.short_process_time)

    async def execute_hexapod_move(self, hexapod: int, **kwargs: typing.Any) -> None:
        self.log.debug(f"Execute hexapod {hexapod} movement.")

        getattr(self, f"_mthexapod_{hexapod}_evt_in_position").inPosition = False
        hexapod_positions_steps = np.array(
            [
                np.linspace(
                    getattr(
                        getattr(
                            self, f"_mthexapod_{hexapod}_evt_uncompensated_position"
                        ),
                        axis,
                    ),
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

    async def execute_hexapod_offset(self, hexapod: int, **kwargs: typing.Any) -> None:
        self.log.debug(f"Execute hexapod {hexapod} offset.")
        getattr(self, f"_mthexapod_{hexapod}_evt_in_position").inPosition = False
        desired_position = dict(
            [
                (
                    axis,
                    getattr(
                        getattr(
                            self, f"_mthexapod_{hexapod}_evt_uncompensated_position"
                        ),
                        axis,
                    )
                    + kwargs.get(axis, 0.0),
                )
                for axis in "xyzuvw"
            ]
        )

        self.log.debug(f"Execute hexapod {hexapod} move: {desired_position}")
        await self.execute_hexapod_move(hexapod=hexapod, **desired_position)

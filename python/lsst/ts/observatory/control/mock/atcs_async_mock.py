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
import unittest.mock

import numpy as np
from lsst.ts import salobj, utils
from lsst.ts.idl.enums import ATMCS, ATDome, ATPneumatics, ATPtg
from lsst.ts.observatory.control.auxtel.atcs import ATCS, ATCSUsages
from lsst.ts.observatory.control.mock import RemoteGroupAsyncMock


class ATCSAsyncMock(RemoteGroupAsyncMock):
    """Implement ATCS support for RemoteGroupAsyncMock unit test helper class
    to.

    This class is intended to be used for developing unit tests for ATCS
    class.
    """

    @property
    def remote_group(self) -> ATCS:
        return self.atcs

    @classmethod
    def setUpClass(cls) -> None:
        """This classmethod is only called once, when preparing the unit
        test.
        """

        cls.log = logging.getLogger("TestATCS")

        # Pass in a string as domain to prevent ATCS from trying to create a
        # domain by itself. When using DryTest usage, the class won't create
        # any remote. When this method is called there is no event loop
        # running so all asyncio facilities will fail to create. This is later
        # rectified in the asyncSetUp.
        cls.atcs = ATCS(
            domain="FakeDomain", log=cls.log, intended_usage=ATCSUsages.DryTest
        )

        [
            setattr(cls.atcs.check, component, True)  # type: ignore
            for component in cls.atcs.components_attr
        ]

        # Decrease telescope settle time to speed up unit test
        cls.atcs.tel_settle_time = 0.25

        cls.track_id_gen = utils.index_generator(1)

    async def setup_types(self) -> None:
        self.atcs._create_asyncio_events()

        # Setup required ATAOS data
        self._ataos_evt_correction_enabled = types.SimpleNamespace(
            m1=False,
            hexapod=False,
            m2=False,
            focus=False,
            atspectrograph=False,
            moveWhileExposing=False,
        )

        # Setup required ATPtg data
        self._atptg_evt_focus_name_selected = types.SimpleNamespace(
            focus=ATPtg.Foci.NASMYTH2
        )

        # Setup required ATMCS data
        self._telescope_position = types.SimpleNamespace(
            elevationCalculatedAngle=np.zeros(100) + 80.0,
            azimuthCalculatedAngle=np.zeros(100),
        )

        self._atmcs_tel_mount_nasmyth_encoders = types.SimpleNamespace(
            nasmyth1CalculatedAngle=np.zeros(100), nasmyth2CalculatedAngle=np.zeros(100)
        )

        self._telescope_target_position = types.SimpleNamespace(
            trackId=next(self.track_id_gen),
            elevation=80.0,
            azimuth=0.0,
            nasmyth1RotatorAngle=0.0,
            nasmyth2RotatorAngle=0.0,
        )

        self._atmcs_all_axes_in_position = types.SimpleNamespace(inPosition=True)

        self._atmcs_evt_at_mount_state = types.SimpleNamespace(
            state=int(ATMCS.AtMountState.TRACKINGDISABLED)
        )

        # Setup required ATDome data
        self.dome_slit_positioning_time = 0.5
        self._atdome_position = types.SimpleNamespace(azimuthPosition=0.0)
        self._atdome_in_position = types.SimpleNamespace(inPosition=False)

        self._atdome_azimth_commanded_state = types.SimpleNamespace(azimuth=0.0)

        self._atdome_evt_azimuth_state = types.SimpleNamespace(
            homing=False,
            _taken=False,
            homed=False,
        )

        self._atdome_evt_scb_link = types.SimpleNamespace(active=True)

        self._atdome_evt_main_door_state = types.SimpleNamespace(
            state=ATDome.ShutterDoorState.CLOSED
        )

        # Setup rquired ATDomeTrajectory data
        self._atdometrajectory_dome_following = types.SimpleNamespace(enabled=False)

        # Setup required ATPneumatics data
        self._atpneumatics_evt_m1_cover_state = types.SimpleNamespace(
            state=ATPneumatics.MirrorCoverState.CLOSED
        )

        self._atpneumatics_evt_m1_vents_position = types.SimpleNamespace(
            position=ATPneumatics.VentsPosition.CLOSED
        )

        self._atpneumatics_evt_instrument_state = types.SimpleNamespace(
            state=ATPneumatics.AirValveState.CLOSED
        )

        self._atpneumatics_evt_main_valve_state = types.SimpleNamespace(
            state=ATPneumatics.AirValveState.CLOSED
        )

    async def setup_mocks(self) -> None:
        await self.setup_ataos()
        await self.setup_atptg()
        await self.setup_atmcs()
        await self.setup_atdome()
        await self.setup_atdometrajectory()
        await self.setup_atpneumatics()

    async def setup_ataos(self) -> None:
        """Augment ataos mock."""

        self.atcs.rem.ataos.configure_mock(
            **{
                "evt_correctionEnabled.aget.side_effect": self.ataos_evt_correction_enabled
            }
        )

    async def setup_atptg(self) -> None:
        """Augment atptg mock."""
        self.atcs.rem.atptg.configure_mock(
            **{
                "evt_focusNameSelected.aget.side_effect": self.atptg_evt_focus_name_selected,
                "cmd_stopTracking.start.side_effect": self.atmcs_stop_tracking,
                "cmd_raDecTarget.DataType.return_value": self.get_sample(
                    "ATPtg", "command_raDecTarget"
                ),
            }
        )

    async def setup_atmcs(self) -> None:
        """Augment atmcs mock."""
        self.atcs.rem.atmcs.configure_mock(
            **{
                "tel_mount_Nasmyth_Encoders.aget.side_effect": self.atmcs_tel_mount_nasmyth_encoders,
                "tel_mount_Nasmyth_Encoders.next.side_effect": self.atmcs_tel_mount_nasmyth_encoders,
                "evt_allAxesInPosition.next.side_effect": self.atmcs_all_axes_in_position,
                "evt_allAxesInPosition.aget.side_effect": self.atmcs_all_axes_in_position,
                "evt_atMountState.aget.side_effect": self.atmcs_evt_at_mount_state,
            }
        )

        self.atcs._tel_position = self._telescope_position
        self.atcs._tel_target = self._telescope_target_position

        self.atcs.next_telescope_position = unittest.mock.AsyncMock(
            side_effect=self.next_telescope_position
        )

        self.atcs.next_telescope_target = unittest.mock.AsyncMock(
            side_effect=self.next_telescope_target
        )

    async def setup_atdome(self) -> None:
        """Augment atdome mock."""
        self.atcs.rem.atdome.configure_mock(
            **{
                "tel_position.next.side_effect": self.atdome_tel_position,
                "tel_position.aget.side_effect": self.atdome_tel_position,
                "evt_azimuthInPosition.aget.side_effect": self.atdome_evt_in_position,
                "evt_azimuthInPosition.next.side_effect": self.atdome_evt_in_position,
                "evt_azimuthCommandedState.aget.side_effect": self.atdome_evt_azimuth_commanded_state,
                "evt_azimuthCommandedState.next.side_effect": self.atdome_evt_azimuth_commanded_state,
                "evt_azimuthState.next.side_effect": self.atdome_evt_azimuth_state,
                "evt_azimuthState.aget.side_effect": self.atdome_evt_azimuth_state,
                "evt_scbLink.aget.side_effect": self.atdome_evt_scb_link,
                "evt_mainDoorState.aget.side_effect": self.atdome_evt_main_door_state,
                "evt_mainDoorState.next.side_effect": self.atdome_evt_main_door_state,
                "cmd_homeAzimuth.start.side_effect": self.atdome_cmd_home_azimuth,
                "cmd_moveShutterMainDoor.set_start.side_effect": self.atdome_cmd_move_shutter_main_door,
                "cmd_moveAzimuth.set_start.side_effect": self.atdome_cmd_move_azimuth,
                "cmd_closeShutter.set_start.side_effect": self.atdome_cmd_close_shutter,
                "cmd_stopMotion.start.side_effect": self.atdome_cmd_stop_motion,
            }
        )

        self.atcs.rem.atdome.evt_azimuthState.attach_mock(
            unittest.mock.Mock(side_effect=self.atdome_evt_azimuth_state_flush),
            "flush",
        )

    async def setup_atdometrajectory(self) -> None:
        """Augment atdometrajectory mock."""
        self.atcs.rem.atdometrajectory.configure_mock(
            **{
                "evt_followingMode.aget.side_effect": self.atdometrajectory_following_mode,
                "cmd_setFollowingMode.set_start.side_effect": self.atdometrajectory_cmd_set_following_mode,
            }
        )

    async def setup_atpneumatics(self) -> None:
        """Augment atpneumatics mock."""
        self.atcs.rem.atpneumatics.configure_mock(
            **{
                "evt_m1CoverState.aget.side_effect": self.atpneumatics_evt_m1_cover_state,
                "evt_m1CoverState.next.side_effect": self.atpneumatics_evt_m1_cover_state,
                "evt_m1VentsPosition.aget.side_effect": self.atpneumatics_evt_m1_vents_position,
                "evt_m1VentsPosition.next.side_effect": self.atpneumatics_evt_m1_vents_position,
                "evt_instrumentState.aget.side_effect": self.atpneumatics_evt_instrument_state,
                "evt_instrumentState.next.side_effect": self.atpneumatics_evt_instrument_state,
                "evt_mainValveState.aget.side_effect": self.atpneumatics_evt_main_valve_state,
                "evt_mainValveState.next.side_effect": self.atpneumatics_evt_main_valve_state,
                "cmd_openInstrumentAirValve.start.side_effect": self.atpneumatics_open_air_valve,
                "cmd_openMasterAirSupply.start.side_effect": self.atpneumatics_open_main_valve,
                "cmd_closeM1Cover.start.side_effect": self.atpneumatics_close_m1_cover,
                "cmd_openM1Cover.start.side_effect": self.atpneumatics_open_m1_cover,
                "cmd_openM1CellVents.start.side_effect": self.atpneumatics_open_m1_cell_vents,
                "cmd_closeM1CellVents.start.side_effect": self.atpneumatics_close_m1_cell_vents,
            }
        )

    async def ataos_evt_correction_enabled(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> types.SimpleNamespace:
        return self._ataos_evt_correction_enabled

    async def atptg_evt_focus_name_selected(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> types.SimpleNamespace:
        return self._atptg_evt_focus_name_selected

    async def atmcs_tel_mount_nasmyth_encoders(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> types.SimpleNamespace:
        return self._atmcs_tel_mount_nasmyth_encoders

    async def next_telescope_position(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> types.SimpleNamespace:
        return self._telescope_position

    async def next_telescope_target(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> types.SimpleNamespace:
        return self._telescope_target_position

    async def atdome_tel_position(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> types.SimpleNamespace:
        return self._atdome_position

    async def atdome_evt_in_position(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> types.SimpleNamespace:
        await asyncio.sleep(1.0)
        return self._atdome_in_position

    async def atdome_evt_azimuth_commanded_state(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> types.SimpleNamespace:
        return self._atdome_azimth_commanded_state

    async def atdome_evt_azimuth_state(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> types.SimpleNamespace:
        if self._atdome_evt_azimuth_state._taken:
            raise asyncio.TimeoutError("Timeout waiting for azimuthState")
        else:
            await asyncio.sleep(0.1)
            return self._atdome_evt_azimuth_state

    def atdome_evt_azimuth_state_flush(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> None:
        self._atdome_evt_azimuth_state._taken = True

    async def atdome_evt_scb_link(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> types.SimpleNamespace:
        return self._atdome_evt_scb_link

    async def atdome_evt_main_door_state(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> types.SimpleNamespace:
        await asyncio.sleep(0.2)
        return self._atdome_evt_main_door_state

    async def atdome_cmd_home_azimuth(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> None:
        if self._atdome_position.azimuthPosition == 0.0:
            return
        else:
            self._atdome_evt_azimuth_state._taken = False
            self._atdome_evt_azimuth_state.homing = True
            asyncio.create_task(self._atdome_cmd_home_azimuth())

    async def atdome_cmd_move_shutter_main_door(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> None:
        asyncio.create_task(
            self._atdome_cmd_move_shutter_main_door(open=kwargs["open"])
        )

    async def atdome_cmd_move_azimuth(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> None:
        self._atdome_in_position.inPosition = False
        target_position = kwargs["azimuth"]

        asyncio.create_task(self._atdome_move_azimuth(target_position))

    async def _atdome_move_azimuth(self, target_position: float) -> None:
        dome_positions = np.arange(
            self._atdome_position.azimuthPosition, target_position, 1.0
        )
        for position in dome_positions:
            self._atdome_position.azimuthPosition = position
            await asyncio.sleep(0.5)
        self._atdome_position.azimuthPosition = target_position
        self._atdome_in_position.inPosition = True

    async def atdome_cmd_close_shutter(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> None:
        asyncio.create_task(self._atdome_cmd_move_shutter_main_door(open=False))

    async def atdome_cmd_stop_motion(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> None:
        if self._atdome_evt_main_door_state.state in {
            ATDome.ShutterDoorState.CLOSING,
            ATDome.ShutterDoorState.OPENING,
        }:
            self._atdome_evt_main_door_state.state = (
                ATDome.ShutterDoorState.PARTIALLYOPENED
            )

    async def atdometrajectory_following_mode(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> types.SimpleNamespace:
        self.log.debug(
            "Retrieving atdometrajectory dome following mode: "
            f"{self._atdometrajectory_dome_following}"
        )
        return self._atdometrajectory_dome_following

    async def atdometrajectory_cmd_set_following_mode(
        self, enable: bool, *args: typing.Any, **kwargs: typing.Any
    ) -> None:
        self.log.debug(
            "Updating atdometrajectory following: "
            f"{self._atdometrajectory_dome_following.enabled} -> {enable}"
        )
        self._atdometrajectory_dome_following.enabled = enable

    async def _atdome_cmd_home_azimuth(self) -> None:
        await asyncio.sleep(0.2)
        self._atdome_evt_azimuth_state.homing = False
        self._atdome_evt_azimuth_state.homed = True

    async def _atdome_cmd_move_shutter_main_door(self, open: bool) -> None:
        if (
            open
            and self._atdome_evt_main_door_state.state != ATDome.ShutterDoorState.OPENED
        ):
            self._atdome_evt_main_door_state.state = ATDome.ShutterDoorState.OPENING
            await asyncio.sleep(self.dome_slit_positioning_time)
            self._atdome_evt_main_door_state.state = ATDome.ShutterDoorState.OPENED
        elif (
            not open
            and self._atdome_evt_main_door_state.state != ATDome.ShutterDoorState.CLOSED
        ):
            self._atdome_evt_main_door_state.state = ATDome.ShutterDoorState.CLOSING
            await asyncio.sleep(self.dome_slit_positioning_time)
            self._atdome_evt_main_door_state.state = ATDome.ShutterDoorState.CLOSED

    async def atmcs_all_axes_in_position(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> types.SimpleNamespace:
        await asyncio.sleep(0.1)
        return self._atmcs_all_axes_in_position

    async def atmcs_evt_at_mount_state(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> types.SimpleNamespace:
        return self._atmcs_evt_at_mount_state

    async def start_tracking(
        self,
        data: salobj.type_hints.BaseMsgType,
        *args: typing.Any,
        **kwargs: typing.Any,
    ) -> None:
        self._atmcs_all_axes_in_position.inPosition = True

        self._atmcs_evt_at_mount_state.state = int(ATMCS.AtMountState.TRACKINGENABLED)

    async def atmcs_stop_tracking(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> None:
        self._atmcs_all_axes_in_position.inPosition = False
        self._atmcs_evt_at_mount_state.state = int(ATMCS.AtMountState.TRACKINGDISABLED)

    async def atpneumatics_evt_m1_cover_state(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> types.SimpleNamespace:
        await asyncio.sleep(0.1)
        return self._atpneumatics_evt_m1_cover_state

    async def atpneumatics_evt_m1_vents_position(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> types.SimpleNamespace:
        await asyncio.sleep(0.1)
        return self._atpneumatics_evt_m1_vents_position

    async def atpneumatics_evt_instrument_state(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> types.SimpleNamespace:
        await asyncio.sleep(0.1)
        return self._atpneumatics_evt_instrument_state

    async def atpneumatics_evt_main_valve_state(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> types.SimpleNamespace:
        await asyncio.sleep(0.1)
        return self._atpneumatics_evt_main_valve_state

    async def atpneumatics_close_m1_cover(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> None:
        asyncio.create_task(self._atpneumatics_close_m1_cover())

    async def atpneumatics_open_m1_cover(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> None:
        if (
            self._atpneumatics_evt_main_valve_state.state
            != ATPneumatics.AirValveState.OPENED
        ):
            raise RuntimeError("Valves not opened.")
        asyncio.create_task(self._atpneumatics_open_m1_cover())

    async def atpneumatics_open_m1_cell_vents(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> None:
        if (
            self._atpneumatics_evt_main_valve_state.state
            != ATPneumatics.AirValveState.OPENED
            or self._atpneumatics_evt_instrument_state.state
            != ATPneumatics.AirValveState.OPENED
        ):
            raise RuntimeError("Valves not opened.")
        asyncio.create_task(self._atpneumatics_open_m1_cell_vents())

    async def atpneumatics_close_m1_cell_vents(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> None:
        asyncio.create_task(self._atpneumatics_close_m1_cell_vents())

    async def atpneumatics_open_air_valve(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> None:
        asyncio.create_task(self._atpneumatics_open_air_valve())

    async def atpneumatics_open_main_valve(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> None:
        asyncio.create_task(self._atpneumatics_open_main_valve())

    async def _atpneumatics_close_m1_cover(self) -> None:
        if (
            self._atpneumatics_evt_m1_cover_state.state
            == ATPneumatics.MirrorCoverState.CLOSED
        ):
            return
        else:
            self._atpneumatics_evt_m1_cover_state.state = (
                ATPneumatics.MirrorCoverState.INMOTION
            )
            await asyncio.sleep(0.5)
            self._atpneumatics_evt_m1_cover_state.state = (
                ATPneumatics.MirrorCoverState.CLOSED
            )

    async def _atpneumatics_open_m1_cover(self) -> None:
        if (
            self._atpneumatics_evt_m1_cover_state.state
            == ATPneumatics.MirrorCoverState.OPENED
        ):
            return
        else:
            self._atpneumatics_evt_m1_cover_state.state = (
                ATPneumatics.MirrorCoverState.INMOTION
            )
            await asyncio.sleep(0.5)
            self._atpneumatics_evt_m1_cover_state.state = (
                ATPneumatics.MirrorCoverState.OPENED
            )

    async def _atpneumatics_close_m1_cell_vents(self) -> None:
        if (
            self._atpneumatics_evt_m1_vents_position.position
            == ATPneumatics.VentsPosition.CLOSED
        ):
            return
        else:
            self._atpneumatics_evt_m1_vents_position.position = (
                ATPneumatics.VentsPosition.PARTIALLYOPENED
            )
            await asyncio.sleep(0.5)
            self._atpneumatics_evt_m1_vents_position.position = (
                ATPneumatics.VentsPosition.CLOSED
            )

    async def _atpneumatics_open_m1_cell_vents(self) -> None:
        if (
            self._atpneumatics_evt_m1_vents_position.position
            == ATPneumatics.VentsPosition.OPENED
        ):
            return
        else:
            self._atpneumatics_evt_m1_vents_position.position = (
                ATPneumatics.VentsPosition.PARTIALLYOPENED
            )
            await asyncio.sleep(0.5)
            self._atpneumatics_evt_m1_vents_position.position = (
                ATPneumatics.VentsPosition.OPENED
            )

    async def _atpneumatics_open_air_valve(self) -> None:
        if (
            self._atpneumatics_evt_instrument_state.state
            == ATPneumatics.AirValveState.OPENED
        ):
            return
        else:
            await asyncio.sleep(0.5)

            self._atpneumatics_evt_instrument_state.state = (
                ATPneumatics.AirValveState.OPENED
            )

    async def _atpneumatics_open_main_valve(self) -> None:
        if (
            self._atpneumatics_evt_main_valve_state.state
            == ATPneumatics.AirValveState.OPENED
        ):
            return
        else:
            await asyncio.sleep(0.5)

            self._atpneumatics_evt_main_valve_state.state = (
                ATPneumatics.AirValveState.OPENED
            )

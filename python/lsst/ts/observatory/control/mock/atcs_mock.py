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

__all__ = ["ATCSMock"]

import asyncio
import typing
from itertools import cycle

import astropy.units as u
import numpy as np
from astropy.coordinates import EarthLocation
from astropy.time import Time
from lsst.ts import salobj
from lsst.ts.xml.enums import ATMCS, ATDome, ATPneumatics, ATPtg

from .base_group_mock import BaseGroupMock

LONG_TIMEOUT = 30  # seconds
HEARTBEAT_INTERVAL = 1  # seconds
CLOSE_SLEEP = 5  # seconds


class ATCSMock(BaseGroupMock):
    """Mock the behavior of the combined components that make out ATTCS.

    This is useful for unit testing.

    """

    def __init__(self) -> None:
        super().__init__(
            components=[
                "ATMCS",
                "ATPtg",
                "ATAOS",
                "ATPneumatics",
                "ATHexapod",
                "ATDome",
                "ATDomeTrajectory",
            ]
        )

        self.location = EarthLocation.from_geodetic(
            lon=-70.747698 * u.deg, lat=-30.244728 * u.deg, height=2663.0 * u.m
        )

        self.atdome.cmd_start.callback = self.atdome_start_callback

        self.atdome.cmd_moveShutterMainDoor.callback = self.move_shutter_callback
        self.atdome.cmd_closeShutter.callback = self.close_shutter_callback
        self.atdome.cmd_moveShutterDropoutDoor.callback = (
            self.move_shutter_dropout_door_callback
        )
        self.atdome.cmd_homeAzimuth.callback = self.dome_home_callback

        self.atpneumatics.cmd_openM1Cover.callback = self.open_m1_cover_callback
        self.atpneumatics.cmd_closeM1Cover.callback = self.close_m1_cover_callback
        self.atpneumatics.cmd_openM1CellVents.callback = (
            self.open_m1_cell_vents_callback
        )
        self.atpneumatics.cmd_closeM1CellVents.callback = (
            self.close_m1_cell_vents_callback
        )

        self.atpneumatics.evt_m1VentsPosition.set(
            position=ATPneumatics.VentsPosition.CLOSED
        )

        self.ataos.cmd_enableCorrection.callback = self.ataos_enable_corrections
        self.ataos.cmd_disableCorrection.callback = self.ataos_disable_corrections

        self.dome_shutter_pos = 0.0
        self.dropout_door_pos = 0.0

        self.slew_time = 5.0

        self.tel_alt = 80.0
        self.tel_az = 0.0
        self.dom_az = 0.0
        self.is_dome_homming = False

        self.track = False

        self.atmcs_telemetry_task: typing.Union[asyncio.Task, None] = None
        self.atdome_telemetry_task: typing.Union[asyncio.Task, None] = None
        self.atptg_telemetry_task: typing.Union[asyncio.Task, None] = None
        self.ataos_telemetry_task: typing.Union[asyncio.Task, None] = None

        self.run_telemetry_loop = True

        self.atptg.cmd_raDecTarget.callback = self.slew_callback
        self.atptg.cmd_azElTarget.callback = self.slew_callback
        self.atptg.cmd_planetTarget.callback = self.slew_callback
        self.atptg.cmd_stopTracking.callback = self.stop_tracking_callback
        self.atptg.cmd_poriginOffset.callback = self.generic_callback

        self.atdome.cmd_moveAzimuth.callback = self.move_dome

        self.atdometrajectory.cmd_setFollowingMode.callback = self.generic_callback

        self.ataos_corrections = {
            "m1",
            "m2",
            "hexapod",
            "focus",
            "atspectrograph",
            "moveWhileExposing",
        }

    @property
    def atmcs(self) -> salobj.Remote:
        return self.controllers.atmcs

    @property
    def atptg(self) -> salobj.Remote:
        return self.controllers.atptg

    @property
    def ataos(self) -> salobj.Remote:
        return self.controllers.ataos

    @property
    def atpneumatics(self) -> salobj.Remote:
        return self.controllers.atpneumatics

    @property
    def athexapod(self) -> salobj.Remote:
        return self.controllers.athexapod

    @property
    def atdome(self) -> salobj.Remote:
        return self.controllers.atdome

    @property
    def atdometrajectory(self) -> salobj.Remote:
        return self.controllers.atdometrajectory

    @property
    def m1_cover_state(self) -> ATPneumatics.MirrorCoverState:
        return ATPneumatics.MirrorCoverState(
            self.atpneumatics.evt_m1CoverState.data.state
        )

    async def set_m1_cover_state(self, value: int) -> None:
        await self.atpneumatics.evt_m1CoverState.set_write(state=value)

    async def start_task_publish(self) -> None:
        if self.start_task.done():
            raise RuntimeError("Start task already completed.")

        await super().start_task_publish()

        await self.set_m1_cover_state(ATPneumatics.MirrorCoverState.CLOSED)

        await self.atmcs.evt_atMountState.set_write(
            state=ATMCS.AtMountState.TRACKINGDISABLED
        )
        await self.atdome.evt_scbLink.set_write(active=True, force_output=True)
        await self.atdome.evt_azimuthCommandedState.write()
        await self.atptg.evt_focusNameSelected.set_write(focus=ATPtg.Foci.NASMYTH2)

        self.atmcs_telemetry_task = asyncio.create_task(self.atmcs_telemetry())
        self.atdome_telemetry_task = asyncio.create_task(self.atdome_telemetry())
        self.atptg_telemetry_task = asyncio.create_task(self.atptg_telemetry())
        self.ataos_telemetry_task = asyncio.create_task(self.ataos_telemetry())

    async def atmcs_telemetry(self) -> None:
        while self.run_telemetry_loop:
            await self.atmcs.tel_mount_AzEl_Encoders.set_write(
                elevationCalculatedAngle=np.zeros(100) + self.tel_alt,
                azimuthCalculatedAngle=np.zeros(100) + self.tel_az,
            )

            await self.atmcs.tel_mount_Nasmyth_Encoders.write()

            await self.atpneumatics.evt_m1VentsPosition.write()  # only output when it changes

            if self.track:
                await self.atmcs.evt_target.set_write(
                    elevation=self.tel_alt, azimuth=self.tel_az, force_output=True
                )

            await asyncio.sleep(1.0)

    async def atdome_telemetry(self) -> None:
        while self.run_telemetry_loop:
            await self.atdome.tel_position.set_write(azimuthPosition=self.dom_az)
            await self.atdome.evt_azimuthState.set_write(homing=self.is_dome_homming)
            await asyncio.sleep(1.0)

    async def atptg_telemetry(self) -> None:
        while self.run_telemetry_loop:
            now = Time.now()
            await self.atptg.tel_timeAndDate.set_write(
                timestamp=now.unix_tai,
                utc=now.utc.mjd,
                lst=now.sidereal_time("mean", self.location.lon).value,
            )
            await asyncio.sleep(1.0)

    async def ataos_telemetry(self) -> None:
        await self.ataos.evt_correctionEnabled.set_write()

        correction_times = cycle((1, 1, 2, 4, 10))
        while self.run_telemetry_loop:
            if self.ataos.evt_summaryState.data.summaryState == salobj.State.ENABLED:
                for correction in self.ataos_corrections:
                    if getattr(
                        self.ataos.evt_correctionEnabled.data, correction
                    ) and hasattr(self.ataos, f"evt_{correction}CorrectionStarted"):
                        await getattr(
                            self.ataos, f"evt_{correction}CorrectionStarted"
                        ).set_write(force_output=True)
                await asyncio.sleep(0.5)
                for correction in self.ataos_corrections:
                    if getattr(
                        self.ataos.evt_correctionEnabled.data, correction
                    ) and hasattr(self.ataos, f"evt_{correction}CorrectionCompleted"):
                        await getattr(
                            self.ataos, f"evt_{correction}CorrectionCompleted"
                        ).set_write(force_output=True)
            await asyncio.sleep(next(correction_times))

    async def atmcs_wait_and_fault(self, wait_time: float) -> None:
        await self.atmcs.evt_summaryState.set_write(
            summaryState=salobj.State.ENABLED, force_output=True
        )
        await asyncio.sleep(wait_time)
        await self.atmcs.evt_summaryState.set_write(
            summaryState=salobj.State.FAULT, force_output=True
        )

    async def atptg_wait_and_fault(self, wait_time: float) -> None:
        await self.atptg.evt_summaryState.set_write(
            summaryState=salobj.State.ENABLED, force_output=True
        )
        await asyncio.sleep(wait_time)
        await self.atptg.evt_summaryState.set_write(
            summaryState=salobj.State.FAULT, force_output=True
        )

    async def open_m1_cover_callback(self, data: salobj.type_hints.BaseMsgType) -> None:
        if self.m1_cover_state != ATPneumatics.MirrorCoverState.CLOSED:
            raise RuntimeError(
                f"M1 cover not closed. Current state is {self.m1_cover_state!r}"
            )

        self.task_list.append(asyncio.create_task(self.open_m1_cover()))

    async def close_m1_cover_callback(
        self, data: salobj.type_hints.BaseMsgType
    ) -> None:
        if self.m1_cover_state != ATPneumatics.MirrorCoverState.OPENED:
            raise RuntimeError(
                f"M1 cover not opened. Current state is {self.m1_cover_state!r}"
            )

        self.task_list.append(asyncio.create_task(self.close_m1_cover()))

    async def open_m1_cell_vents_callback(
        self, data: salobj.type_hints.BaseMsgType
    ) -> None:
        if (
            self.atpneumatics.evt_m1VentsPosition.data.position
            != ATPneumatics.VentsPosition.CLOSED
        ):
            vent_pos = ATPneumatics.VentsPosition(
                self.atpneumatics.evt_m1VentsPosition.data.position
            )
            raise RuntimeError(
                f"Cannot open vent. Current vent position is " f"{vent_pos!r}"
            )
        else:
            self.task_list.append(asyncio.create_task(self.open_m1_cell_vents()))

    async def close_m1_cell_vents_callback(
        self, data: salobj.type_hints.BaseMsgType
    ) -> None:
        if (
            self.atpneumatics.evt_m1VentsPosition.data.position
            != ATPneumatics.VentsPosition.OPENED
        ):
            vent_pos = ATPneumatics.VentsPosition(
                self.atpneumatics.evt_m1VentsPosition.data.position
            )
            raise RuntimeError(
                f"Cannot close vent. Current vent position is " f"{vent_pos!r}"
            )
        else:
            self.task_list.append(asyncio.create_task(self.close_m1_cell_vents()))

    async def dome_home_callback(self, data: salobj.type_hints.BaseMsgType) -> None:
        await asyncio.sleep(0.5)
        self.task_list.append(asyncio.create_task(self.home_dome()))

    async def open_m1_cover(self) -> None:
        await asyncio.sleep(0.5)
        await self.set_m1_cover_state(ATPneumatics.MirrorCoverState.INMOTION)
        await asyncio.sleep(5.0)
        await self.set_m1_cover_state(ATPneumatics.MirrorCoverState.OPENED)

    async def close_m1_cover(self) -> None:
        await asyncio.sleep(0.5)
        await self.set_m1_cover_state(ATPneumatics.MirrorCoverState.INMOTION)
        await asyncio.sleep(5.0)
        await self.set_m1_cover_state(ATPneumatics.MirrorCoverState.CLOSED)

    async def open_m1_cell_vents(self) -> None:
        self.atpneumatics.evt_m1VentsPosition.set(
            position=ATPneumatics.VentsPosition.PARTIALLYOPENED
        )
        await asyncio.sleep(2.0)
        self.atpneumatics.evt_m1VentsPosition.set(
            position=ATPneumatics.VentsPosition.OPENED
        )

    async def close_m1_cell_vents(self) -> None:
        self.atpneumatics.evt_m1VentsPosition.set(
            position=ATPneumatics.VentsPosition.PARTIALLYOPENED
        )
        await asyncio.sleep(2.0)
        self.atpneumatics.evt_m1VentsPosition.set(
            position=ATPneumatics.VentsPosition.CLOSED
        )

    async def home_dome(self) -> None:
        print("Homing dome")
        await asyncio.sleep(0.5)
        self.is_dome_homming = True
        await self.atdome.evt_azimuthCommandedState.set_write(
            azimuth=0.0, commandedState=ATDome.AzimuthCommandedState.HOME
        )

        await asyncio.sleep(5.0)
        print("Dome homed")
        self.dom_az = 0.0
        await self.atdome.evt_azimuthCommandedState.set_write(
            azimuth=0.0, commandedState=ATDome.AzimuthCommandedState.STOP
        )
        self.is_dome_homming = False

    async def slew_callback(self, data: salobj.type_hints.BaseMsgType) -> None:
        """Fake slew waits 5 seconds, then reports all axes
        in position. Does not simulate the actual slew.
        """
        await self.atmcs.evt_allAxesInPosition.set_write(
            inPosition=False, force_output=True
        )
        await self.atdome.evt_azimuthInPosition.set_write(
            inPosition=False, force_output=True
        )

        await self.atdome.evt_azimuthCommandedState.write()
        self.track = True
        self.task_list.append(asyncio.create_task(self.wait_and_send_inposition()))

    async def move_dome(self, data: salobj.type_hints.BaseMsgType) -> None:
        print(f"Move dome {self.dom_az} -> {data.azimuth}")
        await self.atdome.evt_azimuthInPosition.set_write(
            inPosition=False, force_output=True
        )

        await self.atdome.evt_azimuthCommandedState.set_write(
            azimuth=data.azimuth,
            commandedState=ATDome.AzimuthCommandedState.GOTOPOSITION,
            force_output=True,
        )

        await asyncio.sleep(self.slew_time)
        self.dom_az = data.azimuth

        await self.atdome.evt_azimuthCommandedState.set_write(
            azimuth=data.azimuth,
            commandedState=ATDome.AzimuthCommandedState.STOP,
            force_output=True,
        )
        await self.atdome.evt_azimuthInPosition.set_write(
            inPosition=True, force_output=True
        )

    async def stop_tracking_callback(self, data: salobj.type_hints.BaseMsgType) -> None:
        print("Stop tracking start")
        await self.atmcs.evt_atMountState.set_write(state=ATMCS.AtMountState.STOPPING)
        await asyncio.sleep(0.5)
        self.track = False
        await self.atmcs.evt_atMountState.set_write(
            state=ATMCS.AtMountState.TRACKINGDISABLED
        )
        await asyncio.sleep(0.5)
        await self.atmcs.evt_allAxesInPosition.set_write(
            inPosition=False, force_output=True
        )

        print("Stop tracking end")

    async def wait_and_send_inposition(self) -> None:
        await asyncio.sleep(self.slew_time)
        await self.atmcs.evt_allAxesInPosition.set_write(
            inPosition=True, force_output=True
        )
        await asyncio.sleep(0.5)
        await self.atdome.evt_azimuthInPosition.set_write(
            inPosition=True, force_output=True
        )

        await self.atmcs.evt_atMountState.set_write(
            state=ATMCS.AtMountState.TRACKINGENABLED
        )

    async def move_shutter_dropout_door_callback(
        self, data: salobj.type_hints.BaseMsgType
    ) -> None:
        if data.open and self.dropout_door_pos == 0.0:
            await self.open_dropout_door()
        elif not data.open and self.dropout_door_pos == 1.0:
            await self.close_dropout_door()
        else:
            raise RuntimeError(
                f"Cannot execute operation: {data.open} with dome "
                f"at {self.dropout_door_pos}."
            )

    async def open_dropout_door(self) -> None:
        if (
            self.atdome.evt_dropoutDoorState.data.state
            != ATDome.ShutterDoorState.CLOSED
        ):
            raise RuntimeError(
                f"Dropout door state is {self.atdome.evt_dropoutDoorState.data.state}. "
                f"It should be {ATDome.ShutterDoorState.CLOSED!r}."
            )

        await self.atdome.evt_shutterInPosition.set_write(
            inPosition=False, force_output=True
        )
        await self.atdome.evt_dropoutDoorState.set_write(
            state=ATDome.ShutterDoorState.OPENING
        )
        for self.dropout_door_pos in np.linspace(0.0, 1.0, 10):
            await self.atdome.tel_position.set_write(
                dropoutDoorOpeningPercentage=self.dropout_door_pos
            )
            await asyncio.sleep(self.slew_time / 10.0)
        await self.atdome.evt_shutterInPosition.set_write(
            inPosition=True, force_output=True
        )
        await self.atdome.evt_dropoutDoorState.set_write(
            state=ATDome.ShutterDoorState.OPENED
        )

    async def close_dropout_door(self) -> None:
        if (
            self.atdome.evt_dropoutDoorState.data.state
            != ATDome.ShutterDoorState.OPENED
        ):
            raise RuntimeError(
                f"Dropout door state is {self.atdome.evt_dropoutDoorState.data.state}. "
                f"It should be {ATDome.ShutterDoorState.OPENED!r}."
            )

        await self.atdome.evt_shutterInPosition.set_write(
            inPosition=False, force_output=True
        )
        await self.atdome.evt_dropoutDoorState.set_write(
            state=ATDome.ShutterDoorState.CLOSING
        )
        for self.dropout_door_pos in np.linspace(1.0, 0.0, 10):
            await self.atdome.tel_position.set_write(
                dropoutDoorOpeningPercentage=self.dropout_door_pos
            )
            await asyncio.sleep(self.slew_time / 10.0)
        await self.atdome.evt_shutterInPosition.set_write(
            inPosition=True, force_output=True
        )
        await self.atdome.evt_dropoutDoorState.set_write(
            state=ATDome.ShutterDoorState.CLOSED
        )

    async def move_shutter_callback(self, data: salobj.type_hints.BaseMsgType) -> None:
        if data.open and self.dome_shutter_pos == 0.0:
            await self.open_shutter()
        elif not data.open and self.dome_shutter_pos == 1.0:
            await self.close_shutter()
        else:
            raise RuntimeError(
                f"Cannot execute operation: {data.open} with dome "
                f"at {self.dome_shutter_pos}"
            )

    async def close_shutter_callback(self, data: salobj.type_hints.BaseMsgType) -> None:
        if self.dome_shutter_pos == 1.0:
            await self.close_shutter()
        else:
            raise RuntimeError(
                f"Cannot close dome with dome " f"at {self.dome_shutter_pos}"
            )

    async def open_shutter(self) -> None:
        if self.atdome.evt_mainDoorState.data.state != ATDome.ShutterDoorState.CLOSED:
            raise RuntimeError(
                f"Main door state is {self.atdome.evt_mainDoorState.data.state}. "
                f"should be {ATDome.ShutterDoorState.CLOSED!r}."
            )

        await self.atdome.evt_shutterInPosition.set_write(
            inPosition=False, force_output=True
        )
        await self.atdome.evt_mainDoorState.set_write(
            state=ATDome.ShutterDoorState.OPENING
        )
        for self.dome_shutter_pos in np.linspace(0.0, 1.0, 10):
            await self.atdome.tel_position.set_write(
                mainDoorOpeningPercentage=self.dome_shutter_pos
            )
            await asyncio.sleep(self.slew_time / 10.0)
        await self.atdome.evt_shutterInPosition.set_write(
            inPosition=True, force_output=True
        )
        await self.atdome.evt_mainDoorState.set_write(
            state=ATDome.ShutterDoorState.OPENED
        )

    async def close_shutter(self) -> None:
        if self.atdome.evt_mainDoorState.data.state != ATDome.ShutterDoorState.OPENED:
            raise RuntimeError(
                f"Main door state is {self.atdome.evt_mainDoorState.data.state}. "
                f"should be {ATDome.ShutterDoorState.OPENED!r}."
            )

        await self.atdome.evt_shutterInPosition.set_write(
            inPosition=False, force_output=True
        )
        await self.atdome.evt_mainDoorState.set_write(
            state=ATDome.ShutterDoorState.CLOSING
        )
        for self.dome_shutter_pos in np.linspace(1.0, 0.0, 10):
            await self.atdome.tel_position.set_write(
                mainDoorOpeningPercentage=self.dome_shutter_pos
            )
            await asyncio.sleep(self.slew_time / 10.0)
        await self.atdome.evt_shutterInPosition.set_write(
            inPosition=True, force_output=True
        )
        await self.atdome.evt_mainDoorState.set_write(
            state=ATDome.ShutterDoorState.CLOSED
        )

    async def atdome_start_callback(self, data: salobj.type_hints.BaseMsgType) -> None:
        """ATDome start commands do more than the generic callback."""

        ss = self.atdome.evt_summaryState

        if ss.data.summaryState != salobj.State.STANDBY:
            raise RuntimeError(
                f"atdome current state is {salobj.State(ss.data.summaryState)!r}. "
                f"Expected {salobj.State.STANDBY!r}"
            )

        print(
            f"[atdome] {ss.data.summaryState!r} -> {salobj.State.DISABLED!r} "
            f"[{data.configurationOverride}]"
        )

        await ss.set_write(summaryState=salobj.State.DISABLED)

        self.override["atdome"] = data.configurationOverride

        await self.atdome.evt_mainDoorState.set_write(
            state=ATDome.ShutterDoorState.CLOSED
        )
        self.atdome.tel_position.set(azimuthPosition=0.0)
        await self.atdome.evt_azimuthInPosition.set_write(
            inPosition=True, force_output=True
        )

        await asyncio.sleep(HEARTBEAT_INTERVAL)

    async def ataos_enable_corrections(
        self, data: salobj.type_hints.BaseMsgType
    ) -> None:
        """"""
        enable_corrections = dict()

        for correction in self.ataos_corrections:
            if getattr(data, correction):
                enable_corrections[correction] = True
        await self.ataos.evt_correctionEnabled.set_write(**enable_corrections)

    async def ataos_disable_corrections(
        self, data: salobj.type_hints.BaseMsgType
    ) -> None:
        """"""
        disable_corrections = dict()

        for correction in self.ataos_corrections:
            if getattr(data, correction):
                disable_corrections[correction] = False
        await self.ataos.evt_correctionEnabled.set_write(**disable_corrections)

    async def close(self) -> None:
        # await all tasks created during runtime

        try:
            self.run_telemetry_loop = False

            await asyncio.sleep(CLOSE_SLEEP)

            for task in (
                self.atmcs_telemetry_task,
                self.atdome_telemetry_task,
                self.atptg_telemetry_task,
                self.ataos_telemetry_task,
            ):
                assert task is not None
                if not task.done():
                    print("Task not done. Cancelling it.")
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
                    except Exception as e:
                        print(f"Unexpected exception cancelling pending task: {e}")

        except Exception:
            pass

        await super().close()

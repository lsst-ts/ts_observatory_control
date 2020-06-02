# This file is part of ts_observatory_control.
#
# Developed for the LSST Telescope and Site Systems.
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

import numpy as np

from .base_group_mock import BaseGroupMock

import astropy.units as u
from astropy.time import Time
from astropy.coordinates import EarthLocation, Angle

from lsst.ts import salobj
from lsst.ts.idl.enums import ATDome, ATPneumatics, ATMCS

LONG_TIMEOUT = 30  # seconds
HEARTBEAT_INTERVAL = 1  # seconds
CLOSE_SLEEP = 5  # seconds


class ATCSMock(BaseGroupMock):
    """ Mock the behavior of the combined components that make out ATTCS.

    This is useful for unit testing.

    """

    def __init__(self):

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

        self.ataos.cmd_enableCorrection.callback = self.generic_callback
        self.ataos.cmd_disableCorrection.callback = self.generic_callback

        self.dome_shutter_pos = 0.0

        self.slew_time = 5.0

        self.tel_alt = 80.0
        self.tel_az = 0.0
        self.dom_az = 0.0
        self.is_dome_homming = False

        self.m1_cover_state = ATPneumatics.MirrorCoverState.CLOSED

        self.track = False

        self.atmcs_telemetry_task = None
        self.atdome_telemetry_task = None
        self.atptg_telemetry_task = None
        self.run_telemetry_loop = True

        self.atptg.cmd_raDecTarget.callback = self.slew_callback
        self.atptg.cmd_azElTarget.callback = self.slew_callback
        self.atptg.cmd_planetTarget.callback = self.slew_callback
        self.atptg.cmd_stopTracking.callback = self.stop_tracking_callback

        self.atdome.cmd_moveAzimuth.callback = self.move_dome

    @property
    def atmcs(self):
        return self.controllers.atmcs

    @property
    def atptg(self):
        return self.controllers.atptg

    @property
    def ataos(self):
        return self.controllers.ataos

    @property
    def atpneumatics(self):
        return self.controllers.atpneumatics

    @property
    def athexapod(self):
        return self.controllers.athexapod

    @property
    def atdome(self):
        return self.controllers.atdome

    @property
    def atdometrajectory(self):
        return self.controllers.atdometrajectory

    @property
    def m1_cover_state(self):
        return ATPneumatics.MirrorCoverState(
            self.atpneumatics.evt_m1CoverState.data.state
        )

    @m1_cover_state.setter
    def m1_cover_state(self, value):
        self.atpneumatics.evt_m1CoverState.set_put(state=value)

    async def start_task_publish(self):

        if self.start_task.done():
            raise RuntimeError("Start task already completed.")

        await super().start_task_publish()

        self.atmcs.evt_atMountState.set_put(state=ATMCS.AtMountState.TRACKINGDISABLED)
        self.atdome.evt_scbLink.set_put(active=True, force_output=True)
        self.atdome.evt_azimuthCommandedState.put()

        self.atmcs_telemetry_task = asyncio.create_task(self.atmcs_telemetry())
        self.atdome_telemetry_task = asyncio.create_task(self.atdome_telemetry())
        self.atptg_telemetry_task = asyncio.create_task(self.atptg_telemetry())

    async def atmcs_telemetry(self):
        while self.run_telemetry_loop:

            self.atmcs.tel_mount_AzEl_Encoders.set_put(
                elevationCalculatedAngle=np.zeros(100) + self.tel_alt,
                azimuthCalculatedAngle=np.zeros(100) + self.tel_az,
            )

            self.atmcs.tel_mount_Nasmyth_Encoders.put()

            self.atpneumatics.evt_m1VentsPosition.put()  # only output when it changes

            if self.track:
                self.atmcs.evt_target.set_put(
                    elevation=self.tel_alt, azimuth=self.tel_az, force_output=True
                )

            await asyncio.sleep(1.0)

    async def atdome_telemetry(self):
        while self.run_telemetry_loop:
            self.atdome.tel_position.set_put(azimuthPosition=self.dom_az)
            self.atdome.evt_azimuthState.set_put(homing=self.is_dome_homming)
            await asyncio.sleep(1.0)

    async def atptg_telemetry(self):
        while self.run_telemetry_loop:
            now = Time.now()
            self.atptg.tel_timeAndDate.set_put(
                timestamp=now.tai.mjd,
                utc=now.utc.value.hour
                + now.utc.value.minute / 60.0
                + (now.utc.value.second + now.utc.value.microsecond / 1e3)
                / 60.0
                / 60.0,
                lst=Angle(now.sidereal_time("mean", self.location.lon)).to_string(
                    sep=":"
                ),
            )
            await asyncio.sleep(1.0)

    async def atmcs_wait_and_fault(self, wait_time):
        self.atmcs.evt_summaryState.set_put(
            summaryState=salobj.State.ENABLED, force_output=True
        )
        await asyncio.sleep(wait_time)
        self.atmcs.evt_summaryState.set_put(
            summaryState=salobj.State.FAULT, force_output=True
        )

    async def atptg_wait_and_fault(self, wait_time):
        self.atptg.evt_summaryState.set_put(
            summaryState=salobj.State.ENABLED, force_output=True
        )
        await asyncio.sleep(wait_time)
        self.atptg.evt_summaryState.set_put(
            summaryState=salobj.State.FAULT, force_output=True
        )

    async def open_m1_cover_callback(self, data):

        if self.m1_cover_state != ATPneumatics.MirrorCoverState.CLOSED:
            raise RuntimeError(
                f"M1 cover not closed. Current state is {self.m1_cover_state!r}"
            )

        self.task_list.append(asyncio.create_task(self.open_m1_cover()))

    async def close_m1_cover_callback(self, data):
        if self.m1_cover_state != ATPneumatics.MirrorCoverState.OPENED:
            raise RuntimeError(
                f"M1 cover not opened. Current state is {self.m1_cover_state!r}"
            )

        self.task_list.append(asyncio.create_task(self.close_m1_cover()))

    async def open_m1_cell_vents_callback(self, data):
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

    async def close_m1_cell_vents_callback(self, data):
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

    async def dome_home_callback(self, data):
        await asyncio.sleep(0.5)
        self.task_list.append(asyncio.create_task(self.home_dome()))

    async def open_m1_cover(self):
        await asyncio.sleep(0.5)
        self.m1_cover_state = ATPneumatics.MirrorCoverState.INMOTION
        await asyncio.sleep(5.0)
        self.m1_cover_state = ATPneumatics.MirrorCoverState.OPENED

    async def close_m1_cover(self):
        await asyncio.sleep(0.5)
        self.m1_cover_state = ATPneumatics.MirrorCoverState.INMOTION
        await asyncio.sleep(5.0)
        self.m1_cover_state = ATPneumatics.MirrorCoverState.CLOSED

    async def open_m1_cell_vents(self):
        self.atpneumatics.evt_m1VentsPosition.set(
            position=ATPneumatics.VentsPosition.PARTIALLYOPENED
        )
        await asyncio.sleep(2.0)
        self.atpneumatics.evt_m1VentsPosition.set(
            position=ATPneumatics.VentsPosition.OPENED
        )

    async def close_m1_cell_vents(self):
        self.atpneumatics.evt_m1VentsPosition.set(
            position=ATPneumatics.VentsPosition.PARTIALLYOPENED
        )
        await asyncio.sleep(2.0)
        self.atpneumatics.evt_m1VentsPosition.set(
            position=ATPneumatics.VentsPosition.CLOSED
        )

    async def home_dome(self):
        print("Homing dome")
        await asyncio.sleep(0.5)
        self.is_dome_homming = True
        self.atdome.evt_azimuthCommandedState.set_put(
            azimuth=0.0, commandedState=ATDome.AzimuthCommandedState.HOME
        )

        await asyncio.sleep(5.0)
        print("Dome homed")
        self.dom_az = 0.0
        self.atdome.evt_azimuthCommandedState.set_put(
            azimuth=0.0, commandedState=ATDome.AzimuthCommandedState.STOP
        )
        self.is_dome_homming = False

    async def slew_callback(self, data):
        """Fake slew waits 5 seconds, then reports all axes
           in position. Does not simulate the actual slew.
        """
        self.atmcs.evt_allAxesInPosition.set_put(inPosition=False, force_output=True)
        self.atdome.evt_azimuthInPosition.set_put(inPosition=False, force_output=True)

        self.atdome.evt_azimuthCommandedState.put()
        self.track = True
        self.task_list.append(asyncio.create_task(self.wait_and_send_inposition()))

    async def move_dome(self, data):

        print(f"Move dome {self.dom_az} -> {data.azimuth}")
        self.atdome.evt_azimuthInPosition.set_put(inPosition=False, force_output=True)

        self.atdome.evt_azimuthCommandedState.set_put(
            azimuth=data.azimuth,
            commandedState=ATDome.AzimuthCommandedState.GOTOPOSITION,
            force_output=True,
        )

        await asyncio.sleep(self.slew_time)
        self.dom_az = data.azimuth

        self.atdome.evt_azimuthCommandedState.set_put(
            azimuth=data.azimuth,
            commandedState=ATDome.AzimuthCommandedState.STOP,
            force_output=True,
        )
        self.atdome.evt_azimuthInPosition.set_put(inPosition=True, force_output=True)

    async def stop_tracking_callback(self, data):
        print("Stop tracking start")
        self.atmcs.evt_atMountState.set_put(state=ATMCS.AtMountState.STOPPING)
        await asyncio.sleep(0.5)
        self.track = False
        self.atmcs.evt_atMountState.set_put(state=ATMCS.AtMountState.TRACKINGDISABLED)
        await asyncio.sleep(0.5)
        self.atmcs.evt_allAxesInPosition.set_put(inPosition=False, force_output=True)

        print("Stop tracking end")

    async def wait_and_send_inposition(self):

        await asyncio.sleep(self.slew_time)
        self.atmcs.evt_allAxesInPosition.set_put(inPosition=True, force_output=True)
        await asyncio.sleep(0.5)
        self.atdome.evt_azimuthInPosition.set_put(inPosition=True, force_output=True)

        self.atmcs.evt_atMountState.set_put(state=ATMCS.AtMountState.TRACKINGENABLED)

    async def move_shutter_callback(self, data):
        if data.open and self.dome_shutter_pos == 0.0:
            await self.open_shutter()
        elif not data.open and self.dome_shutter_pos == 1.0:
            await self.close_shutter()
        else:
            raise RuntimeError(
                f"Cannot execute operation: {data.open} with dome "
                f"at {self.dome_shutter_pos}"
            )

    async def close_shutter_callback(self, data):
        if self.dome_shutter_pos == 1.0:
            await self.close_shutter()
        else:
            raise RuntimeError(
                f"Cannot close dome with dome " f"at {self.dome_shutter_pos}"
            )

    async def open_shutter(self):
        if self.atdome.evt_mainDoorState.data.state != ATDome.ShutterDoorState.CLOSED:
            raise RuntimeError(
                f"Main door state is {self.atdome.evt_mainDoorState.data.state}. "
                f"should be {ATDome.ShutterDoorState.CLOSED!r}."
            )

        self.atdome.evt_shutterInPosition.set_put(inPosition=False, force_output=True)
        self.atdome.evt_mainDoorState.set_put(state=ATDome.ShutterDoorState.OPENING)
        for self.dome_shutter_pos in np.linspace(0.0, 1.0, 10):
            self.atdome.tel_position.set_put(
                mainDoorOpeningPercentage=self.dome_shutter_pos
            )
            await asyncio.sleep(self.slew_time / 10.0)
        self.atdome.evt_shutterInPosition.set_put(inPosition=True, force_output=True)
        self.atdome.evt_mainDoorState.set_put(state=ATDome.ShutterDoorState.OPENED)

    async def close_shutter(self):
        if self.atdome.evt_mainDoorState.data.state != ATDome.ShutterDoorState.OPENED:
            raise RuntimeError(
                f"Main door state is {self.atdome.evt_mainDoorState.data.state}. "
                f"should be {ATDome.ShutterDoorState.OPENED!r}."
            )

        self.atdome.evt_shutterInPosition.set_put(inPosition=False, force_output=True)
        self.atdome.evt_mainDoorState.set_put(state=ATDome.ShutterDoorState.CLOSING)
        for self.dome_shutter_pos in np.linspace(1.0, 0.0, 10):
            self.atdome.tel_position.set_put(
                mainDoorOpeningPercentage=self.dome_shutter_pos
            )
            await asyncio.sleep(self.slew_time / 10.0)
        self.atdome.evt_shutterInPosition.set_put(inPosition=True, force_output=True)
        self.atdome.evt_mainDoorState.set_put(state=ATDome.ShutterDoorState.CLOSED)

    async def atdome_start_callback(self, data):
        """ATDome start commands do more than the generic callback."""

        ss = self.atdome.evt_summaryState

        if ss.data.summaryState != salobj.State.STANDBY:
            raise RuntimeError(
                f"atdome current state is {salobj.State(ss.data.summaryState)!r}. "
                f"Expected {salobj.State.STANDBY!r}"
            )

        print(
            f"[atdome] {ss.data.summaryState!r} -> {salobj.State.DISABLED!r} "
            f"[{data.settingsToApply}]"
        )

        ss.set_put(summaryState=salobj.State.DISABLED)

        self.settings_to_apply["atdome"] = data.settingsToApply

        self.atdome.evt_mainDoorState.set_put(state=ATDome.ShutterDoorState.CLOSED)
        self.atdome.tel_position.set(azimuthPosition=0.0)
        self.atdome.evt_azimuthInPosition.set_put(inPosition=True, force_output=True)

        await asyncio.sleep(HEARTBEAT_INTERVAL)

    async def close(self):

        # await all tasks created during runtime

        try:
            await asyncio.wait_for(
                asyncio.gather(*self.task_list), timeout=LONG_TIMEOUT
            )

            self.run_telemetry_loop = False

            await asyncio.gather(self.atmcs_telemetry_task, self.atdome_telemetry_task)

        except Exception:
            pass

        await super().close()

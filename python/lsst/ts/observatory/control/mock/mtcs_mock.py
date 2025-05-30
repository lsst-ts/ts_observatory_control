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

__all__ = ["MTCSMock"]

import asyncio
import math
import typing

import astropy.units as u
import numpy as np
from astropy.coordinates import ICRS, AltAz, Angle, EarthLocation
from astropy.time import Time
from lsst.ts import salobj
from lsst.ts.utils import angle_diff, current_tai
from lsst.ts.xml.enums import MTMount, MTPtg

from .base_group_mock import BaseGroupMock
from .m1m3_topic_samples import get_m1m3_topic_samples_data

LONG_TIMEOUT = 30  # seconds
HEARTBEAT_INTERVAL = 1  # seconds
CLOSE_SLEEP = 5  # seconds
ROT_IN_POSITION_DELTA = 1e-1 * u.deg
STEP_FACTOR = 0.9


class MTCSMock(BaseGroupMock):
    """Mock the behavior of the combined components that make out MTCS.

    This is useful for unit testing.

    """

    def __init__(self) -> None:
        super().__init__(
            components=[
                "MTMount",
                "MTPtg",
                "MTAOS",
                "MTM1M3",
                "MTM2",
                "MTHexapod:1",
                "MTHexapod:2",
                "MTRotator",
                "MTDome",
                "MTDomeTrajectory",
            ],
        )

        self.location = EarthLocation.from_geodetic(
            lon=-70.747698 * u.deg, lat=-30.244728 * u.deg, height=2663.0 * u.m
        )

        self.m1m3_accelerometer_error = 1e-3
        self.m1m3_breakaway_lvdt = 5.0
        self.m1m3_displacement_lvdt = 0.0
        self.m1m3_breakaway_pressure = 110.0
        self.m1m3_pressure_sensor_1 = 1.0
        self.m1m3_pressure_sensor_2 = 1.0
        self.m1m3_pressure_sensor_3 = 1.0

        self.m1m3_force_actuator_state: typing.Dict[str, typing.Any] = dict()

        self.tracking = False
        self.acting = False

        # store radec offsets
        self.radec_offsets: typing.List[salobj.type_hints.BaseMsgType] = []
        # store azel offsets
        self.azel_offsets: typing.List[salobj.type_hints.BaseMsgType] = []
        # store poring offsets
        self.poring_offsets: typing.List[salobj.type_hints.BaseMsgType] = []

        self.controllers.mtptg.cmd_stopTracking.callback = (
            self.mtptg_stop_tracking_callback
        )
        self.controllers.mtptg.cmd_azElTarget.callback = self.azel_target_callback
        self.controllers.mtptg.cmd_raDecTarget.callback = self.radec_target_callback
        self.controllers.mtptg.cmd_offsetRADec.callback = self.offset_radec_callback
        self.controllers.mtptg.cmd_offsetAzEl.callback = self.offset_azel_callback
        self.controllers.mtptg.cmd_offsetClear.callback = self.offset_clear_callback
        self.controllers.mtptg.cmd_poriginOffset.callback = self.offset_porigin_callback
        self.controllers.mtptg.cmd_poriginClear.callback = (
            self.poring_offset_clear_callback
        )

        # Implement xml 7.1 and 8 compatibility
        if hasattr(self.controllers.mtmount.tel_azimuth.DataType(), "angleSet"):
            # xml 7.1
            self.mtmount_demand_position_name = "angleSet"
            self.mtmount_actual_position_name = "angleActual"
        else:
            # xml 8
            self.mtmount_demand_position_name = "demandPosition"
            self.mtmount_actual_position_name = "actualPosition"

        self.controllers.mtmount.tel_azimuth.set(
            **{self.mtmount_demand_position_name: 0.0}
        )
        self.controllers.mtmount.tel_elevation.set(
            **{self.mtmount_demand_position_name: 80.0}
        )

    async def offset_radec_callback(self, data: salobj.type_hints.BaseMsgType) -> None:
        self.radec_offsets.append(data)

    async def offset_azel_callback(self, data: salobj.type_hints.BaseMsgType) -> None:
        self.azel_offsets.append(data)

    async def offset_clear_callback(self, data: salobj.type_hints.BaseMsgType) -> None:
        self.azel_offsets = []
        self.radec_offsets = []

    async def offset_porigin_callback(
        self, data: salobj.type_hints.BaseMsgType
    ) -> None:
        self.poring_offsets.append(data)

    async def poring_offset_clear_callback(
        self, data: salobj.type_hints.BaseMsgType
    ) -> None:
        self.poring_offsets = []

    async def mtptg_stop_tracking_callback(
        self, data: salobj.type_hints.BaseMsgType
    ) -> None:
        self.tracking = False
        self.acting = False
        await self.controllers.mtmount.evt_axesInPosition.set_write(
            elevation=False, azimuth=False
        )
        await self.controllers.mtrotator.evt_inPosition.set_write(inPosition=False)

        await asyncio.sleep(HEARTBEAT_INTERVAL)

    async def azel_target_callback(self, data: salobj.type_hints.BaseMsgType) -> None:
        if (
            self.controllers.mtptg.evt_summaryState.data.summaryState
            != salobj.State.ENABLED
        ):
            raise RuntimeError("MTPtg not in enable state.")

        self.tracking = False

        await asyncio.sleep(HEARTBEAT_INTERVAL)

        self.controllers.mtmount.evt_target.set(
            elevation=data.elDegs,
            azimuth=data.azDegs,
            trackId=data.trackId,
        )

        self.acting = True

        self.controllers.mtmount.tel_azimuth.set(
            **{self.mtmount_demand_position_name: data.azDegs}
        )

        self.controllers.mtmount.tel_elevation.set(
            **{self.mtmount_demand_position_name: data.elDegs}
        )

        self.controllers.mtrotator.tel_rotation.set(demandPosition=data.rotPA)

    async def radec_target_callback(self, data: salobj.type_hints.BaseMsgType) -> None:
        if (
            self.controllers.mtptg.evt_summaryState.data.summaryState
            != salobj.State.ENABLED
        ):
            raise RuntimeError("MTPtg not in enable state.")

        self.controllers.mtptg.evt_currentTarget.set(
            ra=Angle(data.ra, unit=u.hourangle).to(u.radian).value,
            declination=Angle(data.declination, unit=u.deg).to(u.radian).value,
            rotPA=Angle(data.declination, unit=u.deg).value,
            targetType=MTPtg.TargetTypes.RADEC,
            targetName=data.targetName,
        )

        self.controllers.mtmount.evt_target.set(trackId=data.trackId)

        self.tracking = True
        self.acting = True

    async def start_task_publish(self) -> None:
        await super().start_task_publish()

        self.task_list.append(asyncio.create_task(self.mount_telemetry()))
        self.task_list.append(asyncio.create_task(self.rotator_telemetry()))
        self.task_list.append(asyncio.create_task(self.mtptg_telemetry()))
        self.task_list.append(asyncio.create_task(self.dome_telemetry()))
        self.task_list.append(asyncio.create_task(self.m1m3_telemetry()))

    async def mount_telemetry(self) -> None:
        await self.controllers.mtmount.evt_elevationMotionState.set_write(
            state=MTMount.AxisMotionState.STOPPED
        )
        await self.controllers.mtmount.evt_azimuthMotionState.set_write(
            state=MTMount.AxisMotionState.STOPPED
        )
        await self.controllers.mtmount.evt_cameraCableWrapMotionState.set_write(
            state=MTMount.AxisMotionState.STOPPED
        )
        await self.controllers.mtmount.evt_cameraCableWrapFollowing.set_write(
            enabled=True
        )
        await self.controllers.mtmount.evt_connected.set_write(
            command=True, replies=True
        )

        while self.run_telemetry_loop:
            if (
                self.controllers.mtmount.evt_summaryState.data.summaryState
                == salobj.State.ENABLED
            ):
                # Safely initilize data
                if not self.controllers.mtmount.tel_azimuth.has_data:
                    self.controllers.mtmount.tel_azimuth.set(
                        **{
                            self.mtmount_demand_position_name: 0.0,
                            self.mtmount_actual_position_name: 0.0,
                        }
                    )

                if not self.controllers.mtmount.tel_elevation.has_data:
                    self.controllers.mtmount.tel_elevation.set(
                        **{
                            self.mtmount_demand_position_name: 0.0,
                            self.mtmount_actual_position_name: 0.0,
                        }
                    )

                if not self.controllers.mtmount.tel_elevationDrives.has_data:
                    self.controllers.mtmount.tel_elevationDrives.set()

                if not self.controllers.mtmount.tel_azimuthDrives.has_data:
                    self.controllers.mtmount.tel_azimuthDrives.set()

                if not self.controllers.mtmount.evt_target.has_data:
                    self.controllers.mtmount.evt_target.set()

                az_induced_error = np.random.normal(0.0, 1e-7)
                el_induced_error = np.random.normal(0.0, 1e-7)

                az_set = getattr(
                    self.controllers.mtmount.tel_azimuth.data,
                    self.mtmount_demand_position_name,
                )
                el_set = getattr(
                    self.controllers.mtmount.tel_elevation.data,
                    self.mtmount_demand_position_name,
                )

                az_actual = getattr(
                    self.controllers.mtmount.tel_azimuth.data,
                    self.mtmount_actual_position_name,
                )
                el_actual = getattr(
                    self.controllers.mtmount.tel_elevation.data,
                    self.mtmount_actual_position_name,
                )

                az_dif = angle_diff(az_set, az_actual)
                el_dif = angle_diff(el_set, el_actual)
                in_position_elevation = np.abs(el_dif) < 1e-1 * u.deg
                in_position_azimuth = np.abs(az_dif) < 1e-1 * u.deg

                if self.acting:
                    await self.controllers.mtmount.evt_elevationMotionState.set_write(
                        state=MTMount.AxisMotionState.TRACKING
                    )
                    await self.controllers.mtmount.evt_azimuthMotionState.set_write(
                        state=MTMount.AxisMotionState.TRACKING
                    )
                    await self.controllers.mtmount.evt_cameraCableWrapMotionState.set_write(
                        state=MTMount.AxisMotionState.TRACKING
                    )
                    await self.controllers.mtmount.evt_elevationInPosition.set_write(
                        inPosition=in_position_elevation
                    )
                    await self.controllers.mtmount.evt_azimuthInPosition.set_write(
                        inPosition=in_position_azimuth
                    )
                    await self.controllers.mtmount.evt_cameraCableWrapInPosition.set_write(
                        inPosition=True
                    )
                elif (
                    self.controllers.mtmount.evt_elevationMotionState.data.state
                    == MTMount.AxisMotionState.TRACKING
                ):
                    await self.controllers.mtmount.evt_elevationMotionState.set_write(
                        state=MTMount.AxisMotionState.STOPPING
                    )
                    await self.controllers.mtmount.evt_azimuthMotionState.set_write(
                        state=MTMount.AxisMotionState.STOPPING
                    )
                    await self.controllers.mtmount.evt_cameraCableWrapMotionState.set_write(
                        state=MTMount.AxisMotionState.STOPPING
                    )
                else:
                    await self.controllers.mtmount.evt_elevationMotionState.set_write(
                        state=MTMount.AxisMotionState.STOPPED
                    )
                    await self.controllers.mtmount.evt_azimuthMotionState.set_write(
                        state=MTMount.AxisMotionState.STOPPED
                    )
                    await self.controllers.mtmount.evt_cameraCableWrapMotionState.set_write(
                        state=MTMount.AxisMotionState.STOPPED
                    )
                # The following computation of angleActual is to emulate a
                # trajectory. At every loop it adds three factors:
                #   1 - the currect position
                #   2 - a random error factor
                #   3 - difference between the current and target positions
                #       multiplied by a STEP_FACTOR, where
                #       0 < STEP_FACTOR <= 1.0
                # If STEP_FACTOR == 1 it means the target position will be
                # achieved in one loop. By reducing STEP_FACTOR we can emulate
                # a slew that takes a certain number of iterations to be
                # completed.
                await self.controllers.mtmount.tel_azimuth.set_write(
                    **{
                        self.mtmount_actual_position_name: az_actual
                        + az_induced_error
                        + az_dif.deg * STEP_FACTOR
                    }
                )
                await self.controllers.mtmount.tel_elevation.set_write(
                    **{
                        self.mtmount_actual_position_name: el_actual
                        + el_induced_error
                        + el_dif.deg * STEP_FACTOR
                    }
                )

                await self.controllers.mtmount.tel_azimuthDrives.set_write(
                    current=np.random.normal(
                        loc=0.5,
                        scale=0.01,
                        size=len(
                            self.controllers.mtmount.tel_azimuthDrives.data.current
                        ),
                    ),
                    timestamp=current_tai(),
                )

                await self.controllers.mtmount.tel_elevationDrives.set_write(
                    current=np.random.normal(
                        loc=0.5,
                        scale=0.01,
                        size=len(
                            self.controllers.mtmount.tel_elevationDrives.data.current
                        ),
                    ),
                    timestamp=current_tai(),
                )

                await self.controllers.mtmount.tel_cameraCableWrap.set_write(
                    actualPosition=self.controllers.mtrotator.tel_rotation.data.actualPosition,
                    timestamp=current_tai(),
                )
                await self.controllers.mtmount.evt_cameraCableWrapTarget.set_write(
                    position=self.controllers.mtrotator.tel_rotation.data.actualPosition,
                    taiTime=current_tai(),
                    force_output=True,
                )

                await self.controllers.mtmount.evt_target.write()

            await asyncio.sleep(HEARTBEAT_INTERVAL)

    async def rotator_telemetry(self) -> None:
        await self.controllers.mtrotator.tel_electrical.set_write()
        await self.controllers.mtrotator.evt_connected.set_write(connected=True)
        await self.controllers.mtrotator.evt_configuration.set_write(
            positionAngleUpperLimit=90.0,
            velocityLimit=3.0,
            accelerationLimit=1.0,
            positionErrorThreshold=0.0,
            positionAngleLowerLimit=-90.0,
            followingErrorThreshold=0.1,
            trackingSuccessPositionThreshold=0.01,
            trackingLostTimeout=5.0,
        )
        await self.controllers.mtrotator.evt_controllerState.set_write(
            controllerState=0,
            offlineSubstate=1,
            enabledSubstate=0,
            applicationStatus=1024,
        )

        await self.controllers.mtrotator.evt_interlock.set_write(engaged=False)

        while self.run_telemetry_loop:
            if (
                self.controllers.mtrotator.evt_summaryState.data.summaryState
                == salobj.State.ENABLED
            ):
                # Safely initilize topic data.
                if not self.controllers.mtrotator.tel_rotation.has_data:
                    self.controllers.mtrotator.tel_rotation.set(
                        demandPosition=0.0, actualPosition=0.0
                    )

                error = np.random.normal(0.0, 1e-7)
                demand = self.controllers.mtrotator.tel_rotation.data.demandPosition
                position = self.controllers.mtrotator.tel_rotation.data.actualPosition
                dif = angle_diff(demand, position)

                await self.controllers.mtrotator.tel_rotation.set_write(
                    actualPosition=position + error + dif.deg / 1.1
                )

                await self.controllers.mtrotator.tel_motors.set_write(
                    calibrated=np.zeros(2)
                    + self.controllers.mtrotator.tel_rotation.data.actualPosition,
                    raw=27.4e6
                    * (
                        np.zeros(2)
                        + self.controllers.mtrotator.tel_rotation.data.actualPosition
                    ),
                )

                await self.controllers.mtrotator.tel_ccwFollowingError.set_write(
                    timestamp=current_tai()
                )

                if self.acting:
                    await self.controllers.mtrotator.evt_target.set_write(
                        position=position,
                        velocity=0.0,
                        tai=current_tai(),
                    )
                    await self.controllers.mtrotator.evt_tracking.set_write(
                        tracking=True
                    )
                    await self.controllers.mtrotator.evt_inPosition.set_write(
                        inPosition=np.abs(dif) < ROT_IN_POSITION_DELTA
                    )
                else:
                    await self.controllers.mtrotator.evt_tracking.set_write(
                        tracking=False
                    )

            await asyncio.sleep(HEARTBEAT_INTERVAL)

    async def dome_telemetry(self) -> None:
        while self.run_telemetry_loop:
            if (
                self.controllers.mtdome.evt_summaryState.data.summaryState
                == salobj.State.ENABLED
            ):
                dome_az_set = self.controllers.mtdome.tel_azimuth.data.positionCommanded
                dome_el_set = (
                    self.controllers.mtdome.tel_lightWindScreen.data.positionCommanded
                )

                dome_az_pos = self.controllers.mtdome.tel_azimuth.data.positionActual
                dome_el_pos = (
                    self.controllers.mtdome.tel_lightWindScreen.data.positionActual
                )

                error_az = np.random.normal(0.0, 1e-7)
                error_el = np.random.normal(0.0, 1e-7)

                diff_az = angle_diff(dome_az_set, dome_az_pos)
                diff_el = angle_diff(dome_el_set, dome_el_pos)

                # This next bit is to simulate the MTDomeTrajectory behavior.
                if (
                    self.controllers.mtdometrajectory.evt_summaryState.data.summaryState
                    == salobj.State.ENABLED
                ):
                    dome_az_set = getattr(
                        self.controllers.mtmount.tel_azimuth.data,
                        self.mtmount_demand_position_name,
                    )
                    dome_el_set = getattr(
                        self.controllers.mtmount.tel_elevation.data,
                        self.mtmount_demand_position_name,
                    )

                self.controllers.mtdome.tel_azimuth.set(
                    positionCommanded=dome_az_set,
                    positionActual=dome_az_pos + error_az + diff_az.deg / 1.1,
                )
                self.controllers.mtdome.tel_lightWindScreen.set(
                    positionCommanded=dome_el_set,
                    positionActual=dome_el_pos + error_el + diff_el.deg / 1.1,
                )

                await self.controllers.mtdome.tel_azimuth.write()

                await self.controllers.mtdome.tel_lightWindScreen.write()

            await asyncio.sleep(HEARTBEAT_INTERVAL)

    async def mtptg_telemetry(self) -> None:
        while self.run_telemetry_loop:
            if (
                self.controllers.mtptg.evt_summaryState.data.summaryState
                == salobj.State.ENABLED
            ):
                now = Time.now()
                await self.controllers.mtptg.tel_timeAndDate.set_write(
                    timestamp=now.unix_tai,
                    utc=now.utc.mjd,
                    lst=now.sidereal_time("mean", self.location.lon).value,
                )

                if self.tracking:
                    radec_icrs = ICRS(
                        Angle(
                            self.controllers.mtptg.evt_currentTarget.data.ra,
                            unit=u.radian,
                        ),
                        Angle(
                            self.controllers.mtptg.evt_currentTarget.data.declination,
                            unit=u.radian,
                        ),
                    )

                    coord_frame_altaz = AltAz(location=self.location, obstime=now)

                    alt_az = radec_icrs.transform_to(coord_frame_altaz)

                    await self.controllers.mtptg.evt_currentTarget.set_write(
                        timestamp=now.tai.mjd,
                        azDegs=alt_az.az.deg,
                        elDegs=alt_az.alt.deg,
                    )

                    self.controllers.mtmount.tel_azimuth.set(
                        **{self.mtmount_demand_position_name: alt_az.az.deg}
                    )

                    self.controllers.mtmount.tel_elevation.set(
                        **{self.mtmount_demand_position_name: alt_az.alt.deg}
                    )

                    self.controllers.mtrotator.tel_rotation.set(
                        demandPosition=self.controllers.mtptg.evt_currentTarget.data.rotPA
                    )

                    self.controllers.mtmount.evt_target.set(
                        elevation=alt_az.alt.deg,
                        azimuth=alt_az.az.deg,
                    )

            await asyncio.sleep(HEARTBEAT_INTERVAL)

    async def m1m3_telemetry(self) -> None:
        await self.publish_m1m3_topic_samples()

        while self.run_telemetry_loop:
            if (
                self.controllers.mtm1m3.evt_summaryState.data.summaryState
                == salobj.State.ENABLED
            ):
                raw_accelerometer_data = (
                    self.controllers.mtm1m3.tel_accelerometerData.DataType()
                )

                nominal_raw_accelerometer = np.sin(
                    np.radians(
                        getattr(
                            self.controllers.mtmount.tel_elevation.data,
                            self.mtmount_demand_position_name,
                        )
                    )
                )

                raw_accelerometer_arr = np.random.normal(
                    loc=nominal_raw_accelerometer,
                    scale=self.m1m3_accelerometer_error,
                    size=len(raw_accelerometer_data.rawAccelerometer),
                )

                await self.controllers.mtm1m3.tel_accelerometerData.set_write(
                    timestamp=current_tai(),
                    rawAccelerometer=raw_accelerometer_arr,
                    accelerometer=raw_accelerometer_arr,
                )

                force_actuator_data = (
                    self.controllers.mtm1m3.tel_forceActuatorData.DataType()
                )

                fx = np.random.rand()
                fy = np.random.rand()
                fz = np.random.rand()

                await self.controllers.mtm1m3.tel_forceActuatorData.set_write(
                    timestamp=current_tai(),
                    primaryCylinderForce=np.random.rand(
                        len(force_actuator_data.primaryCylinderForce)
                    ),
                    secondaryCylinderForce=np.random.rand(
                        len(force_actuator_data.secondaryCylinderForce)
                    ),
                    xForce=np.random.rand(len(force_actuator_data.xForce)),
                    yForce=np.random.rand(len(force_actuator_data.yForce)),
                    zForce=np.random.rand(len(force_actuator_data.zForce)),
                    fx=fx,
                    fy=fy,
                    fz=fz,
                    mx=np.random.rand(),
                    my=np.random.rand(),
                    mz=np.random.rand(),
                    forceMagnitude=math.hypot(fx, fy, fz),
                )

                hardpoint_actuator_data = (
                    self.controllers.mtm1m3.tel_hardpointActuatorData.DataType()
                )

                await self.controllers.mtm1m3.tel_hardpointActuatorData.set_write(
                    timestamp=current_tai(),
                    measuredForce=np.random.normal(
                        size=len(hardpoint_actuator_data.measuredForce)
                    ),
                    encoder=np.array(
                        [32438, 37387, 43686, 44733, 34862, 40855], dtype=int
                    ),
                    displacement=np.random.normal(
                        size=len(hardpoint_actuator_data.displacement)
                    ),
                    fx=np.random.normal(),
                    fy=np.random.normal(),
                    fz=np.random.normal(),
                    mx=np.random.normal(),
                    my=np.random.normal(),
                    mz=np.random.normal(),
                    forceMagnitude=np.random.normal(),
                    xPosition=np.random.normal(),
                    yPosition=np.random.normal(),
                    zPosition=np.random.normal(),
                    xRotation=np.random.normal(),
                    yRotation=np.random.normal(),
                    zRotation=np.random.normal(),
                )

                hardpoint_monitor_data = (
                    self.controllers.mtm1m3.tel_hardpointMonitorData.DataType()
                )

                await self.controllers.mtm1m3.tel_hardpointMonitorData.set_write(
                    timestamp=current_tai(),
                    breakawayLVDT=np.random.normal(
                        loc=self.m1m3_breakaway_lvdt,
                        scale=self.m1m3_breakaway_lvdt / 10.0,
                        size=len(hardpoint_monitor_data.breakawayLVDT),
                    ),
                    displacementLVDT=np.random.normal(
                        loc=self.m1m3_displacement_lvdt,
                        scale=self.m1m3_displacement_lvdt / 10.0,
                        size=len(hardpoint_monitor_data.displacementLVDT),
                    ),
                    breakawayPressure=np.random.normal(
                        loc=self.m1m3_breakaway_pressure,
                        scale=self.m1m3_breakaway_pressure / 10.0,
                        size=len(hardpoint_monitor_data.breakawayPressure),
                    ),
                    pressureSensor1=np.random.normal(
                        loc=self.m1m3_pressure_sensor_1,
                        scale=self.m1m3_pressure_sensor_1 / 10.0,
                        size=len(hardpoint_monitor_data.pressureSensor1),
                    ),
                    pressureSensor2=np.random.normal(
                        loc=self.m1m3_pressure_sensor_2,
                        scale=self.m1m3_pressure_sensor_2 / 10.0,
                        size=len(hardpoint_monitor_data.pressureSensor2),
                    ),
                    pressureSensor3=np.random.normal(
                        loc=self.m1m3_pressure_sensor_3,
                        scale=self.m1m3_pressure_sensor_3 / 10.0,
                        size=len(hardpoint_monitor_data.pressureSensor3),
                    ),
                )

                self.controllers.mtm1m3.evt_forceActuatorState.data.ilcState = (
                    np.ones_like(
                        self.controllers.mtm1m3.evt_forceActuatorState.data.ilcState,
                        dtype=int,
                    )
                )

                if "ilcState" in self.m1m3_force_actuator_state and np.all(
                    self.m1m3_force_actuator_state["ilcState"] == 0
                ):
                    self.m1m3_force_actuator_state["timestamp"] = current_tai()
                    self.m1m3_force_actuator_state["ilcState"] = np.ones_like(
                        self.controllers.mtm1m3.evt_forceActuatorState.data.ilcState,
                        dtype=int,
                    )

            else:
                self.m1m3_force_actuator_state["timestamp"] = current_tai()
                self.m1m3_force_actuator_state["ilcState"] = np.zeros_like(
                    self.controllers.mtm1m3.evt_forceActuatorState.data.ilcState,
                    dtype=int,
                )
            # This will only publish if there is a change in the topic.
            await self.controllers.mtm1m3.evt_forceActuatorState.set_write(
                **self.m1m3_force_actuator_state
            )

            await asyncio.sleep(HEARTBEAT_INTERVAL)

    async def publish_m1m3_topic_samples(self) -> None:
        """Publish m1m3 topic samples."""

        self.log.debug("Publishing m1m3 topic samples.")

        # Load data without blocking the event loop.

        loop = asyncio.get_running_loop()

        m1m3_topic_samples = await loop.run_in_executor(
            None, get_m1m3_topic_samples_data
        )

        for topic_sample in m1m3_topic_samples:
            if "timestamp" in m1m3_topic_samples[topic_sample]:
                m1m3_topic_samples[topic_sample]["timestamp"] = current_tai()

            # Cleanup sample data in case of schema evolution
            cleanup_topic_attr = []

            for topic_attr in m1m3_topic_samples[topic_sample]:
                if not hasattr(
                    getattr(self.controllers.mtm1m3, f"evt_{topic_sample}").data,
                    topic_attr,
                ):
                    self.log.debug(
                        f"M1M3 topic {topic_sample} does not have attribute {topic_attr}."
                    )
                    cleanup_topic_attr.append(topic_attr)

            if len(cleanup_topic_attr) > 0:
                self.log.warning(
                    f"The following topic attributes are not available in {topic_sample}: "
                    f"{cleanup_topic_attr}. Need to update topic samples."
                )
            for topic_attr in cleanup_topic_attr:
                self.log.debug(
                    f"Removing topic {topic_attr} from {topic_sample} sample."
                )
                m1m3_topic_samples[topic_sample].pop(topic_attr)

            try:
                await getattr(self.controllers.mtm1m3, f"evt_{topic_sample}").set_write(
                    **m1m3_topic_samples[topic_sample]
                )
            except Exception:
                self.log.exception(f"Error publishing topic {topic_sample}")

        self.log.debug("Finished publishing m1m3 topic samples.")

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

from .base_group_mock import BaseGroupMock
from .m1m3_topic_samples import get_m1m3_topic_samples_data

from lsst.ts import salobj

import astropy.units as u
import numpy as np

from astropy.time import Time
from astropy.coordinates import AltAz, ICRS, EarthLocation, Angle

from lsst.ts.idl.enums import MTPtg, MTMount
from lsst.ts.utils import angle_diff, current_tai

LONG_TIMEOUT = 30  # seconds
HEARTBEAT_INTERVAL = 1  # seconds
CLOSE_SLEEP = 5  # seconds
ROT_IN_POSITION_DELTA = 1e-1 * u.deg
STEP_FACTOR = 0.9


class MTCSMock(BaseGroupMock):
    """Mock the behavior of the combined components that make out MTCS.

    This is useful for unit testing.

    """

    def __init__(self):

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

        self.m1m3_force_actuator_state = dict()

        self.tracking = False
        self.acting = False

        # store radec offsets
        self.radec_offsets = []
        # store azel offsets
        self.azel_offsets = []
        # store poring offsets
        self.poring_offsets = []

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

    async def offset_radec_callback(self, data):
        self.radec_offsets.append(data)

    async def offset_azel_callback(self, data):
        self.azel_offsets.append(data)

    async def offset_clear_callback(self, data):

        self.azel_offsets = []
        self.radec_offsets = []

    async def offset_porigin_callback(self, data):
        self.poring_offsets.append(data)

    async def poring_offset_clear_callback(self, data):
        self.poring_offsets = []

    async def mtptg_stop_tracking_callback(self, data):

        self.tracking = False
        self.acting = False
        self.controllers.mtmount.evt_axesInPosition.set_put(
            elevation=False, azimuth=False
        )
        self.controllers.mtrotator.evt_inPosition.set_put(inPosition=False)

        await asyncio.sleep(HEARTBEAT_INTERVAL)

    async def azel_target_callback(self, data):

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

    async def radec_target_callback(self, data):

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

    async def start_task_publish(self):

        await super().start_task_publish()

        self.task_list.append(asyncio.create_task(self.mount_telemetry()))
        self.task_list.append(asyncio.create_task(self.rotator_telemetry()))
        self.task_list.append(asyncio.create_task(self.mtptg_telemetry()))
        self.task_list.append(asyncio.create_task(self.dome_telemetry()))
        self.task_list.append(asyncio.create_task(self.m1m3_telemetry()))

    async def mount_telemetry(self):

        self.controllers.mtmount.evt_axesState.set_put(
            elevation=MTMount.AxisState.IDLE, azimuth=MTMount.AxisState.IDLE
        )
        self.controllers.mtmount.evt_cameraCableWrapState.set_put(
            state=MTMount.AxisState.IDLE
        )
        self.controllers.mtmount.evt_cameraCableWrapFollowing.set_put(enabled=True)
        self.controllers.mtmount.evt_connected.set_put(command=True, replies=True)

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
                    self.controllers.mtmount.evt_axesState.set_put(
                        elevation=MTMount.AxisState.TRACKING,
                        azimuth=MTMount.AxisState.TRACKING,
                    )
                    self.controllers.mtmount.evt_cameraCableWrapState.set_put(
                        state=MTMount.AxisState.TRACKING,
                    )

                    self.controllers.mtmount.evt_axesInPosition.set_put(
                        elevation=in_position_elevation, azimuth=in_position_azimuth
                    )
                elif (
                    self.controllers.mtmount.evt_axesState.data.elevation
                    == MTMount.AxisState.TRACKING
                ):
                    self.controllers.mtmount.evt_axesState.set_put(
                        elevation=MTMount.AxisState.STOPPING,
                        azimuth=MTMount.AxisState.STOPPING,
                    )
                    self.controllers.mtmount.evt_cameraCableWrapState.set_put(
                        state=MTMount.AxisState.STOPPING,
                    )
                else:
                    self.controllers.mtmount.evt_axesState.set_put(
                        elevation=MTMount.AxisState.ENABLED,
                        azimuth=MTMount.AxisState.ENABLED,
                    )
                    self.controllers.mtmount.evt_cameraCableWrapState.set_put(
                        state=MTMount.AxisState.ENABLED,
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
                self.controllers.mtmount.tel_azimuth.set_put(
                    **{
                        self.mtmount_actual_position_name: az_actual
                        + az_induced_error
                        + az_dif.deg * STEP_FACTOR
                    }
                )
                self.controllers.mtmount.tel_elevation.set_put(
                    **{
                        self.mtmount_actual_position_name: el_actual
                        + el_induced_error
                        + el_dif.deg * STEP_FACTOR
                    }
                )

                self.controllers.mtmount.tel_azimuthDrives.set_put(
                    current=np.random.normal(
                        loc=0.5,
                        scale=0.01,
                        size=len(
                            self.controllers.mtmount.tel_azimuthDrives.data.current
                        ),
                    ),
                    timestamp=current_tai(),
                )

                self.controllers.mtmount.tel_elevationDrives.set_put(
                    current=np.random.normal(
                        loc=0.5,
                        scale=0.01,
                        size=len(
                            self.controllers.mtmount.tel_elevationDrives.data.current
                        ),
                    ),
                    timestamp=current_tai(),
                )

                self.controllers.mtmount.tel_cameraCableWrap.set_put(
                    actualPosition=self.controllers.mtrotator.tel_rotation.data.actualPosition,
                    timestamp=current_tai(),
                )
                self.controllers.mtmount.evt_cameraCableWrapTarget.set_put(
                    position=self.controllers.mtrotator.tel_rotation.data.actualPosition,
                    taiTime=current_tai(),
                    force_output=True,
                )

                self.controllers.mtmount.evt_target.put()

            await asyncio.sleep(HEARTBEAT_INTERVAL)

    async def rotator_telemetry(self):

        self.controllers.mtrotator.tel_electrical.set_put()
        self.controllers.mtrotator.evt_connected.set_put(command=True, telemetry=True)
        self.controllers.mtrotator.evt_configuration.set_put(
            positionAngleUpperLimit=90.0,
            velocityLimit=3.0,
            accelerationLimit=1.0,
            positionErrorThreshold=0.0,
            positionAngleLowerLimit=-90.0,
            followingErrorThreshold=0.1,
            trackingSuccessPositionThreshold=0.01,
            trackingLostTimeout=5.0,
        )
        self.controllers.mtrotator.evt_controllerState.set_put(
            controllerState=0,
            offlineSubstate=1,
            enabledSubstate=0,
            applicationStatus=1024,
        )

        self.controllers.mtrotator.evt_interlock.set_put(detail="Disengaged")

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

                self.controllers.mtrotator.tel_rotation.set_put(
                    actualPosition=position + error + dif.deg / 1.1
                )

                self.controllers.mtrotator.tel_motors.set_put(
                    calibrated=np.zeros(2)
                    + self.controllers.mtrotator.tel_rotation.data.actualPosition,
                    raw=27.4e6
                    * (
                        np.zeros(2)
                        + self.controllers.mtrotator.tel_rotation.data.actualPosition
                    ),
                )

                self.controllers.mtrotator.tel_ccwFollowingError.set_put(
                    timestamp=current_tai()
                )

                if self.acting:
                    self.controllers.mtrotator.evt_target.set_put(
                        position=position,
                        velocity=0.0,
                        tai=current_tai(),
                    )
                    self.controllers.mtrotator.evt_tracking.set_put(tracking=True)
                    self.controllers.mtrotator.evt_inPosition.set_put(
                        inPosition=np.abs(dif) < ROT_IN_POSITION_DELTA
                    )
                else:
                    self.controllers.mtrotator.evt_tracking.set_put(tracking=False)

            await asyncio.sleep(HEARTBEAT_INTERVAL)

    async def dome_telemetry(self):

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

                self.controllers.mtdome.tel_azimuth.put()

                self.controllers.mtdome.tel_lightWindScreen.put()

            await asyncio.sleep(HEARTBEAT_INTERVAL)

    async def mtptg_telemetry(self):

        while self.run_telemetry_loop:
            if (
                self.controllers.mtptg.evt_summaryState.data.summaryState
                == salobj.State.ENABLED
            ):
                now = Time.now()
                time_and_date = self.controllers.mtptg.tel_timeAndDate.DataType()
                time_and_date.timestamp = now.tai.mjd
                time_and_date.utc = (
                    now.utc.value.hour
                    + now.utc.value.minute / 60.0
                    + (now.utc.value.second + now.utc.value.microsecond / 1e3)
                    / 60.0
                    / 60.0
                )
                if type(time_and_date.lst) is str:
                    time_and_date.lst = Angle(
                        now.sidereal_time("mean", self.location.lon)
                    ).to_string(sep=":")
                else:
                    time_and_date.lst = now.sidereal_time(
                        "mean", self.location.lon
                    ).value

                self.controllers.mtptg.tel_timeAndDate.put(time_and_date)

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

                    self.controllers.mtptg.evt_currentTarget.set_put(
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

    async def m1m3_telemetry(self):

        await self.publish_m1m3_topic_samples()

        while self.run_telemetry_loop:
            if (
                self.controllers.mtm1m3.evt_summaryState.data.summaryState
                == salobj.State.ENABLED
            ):

                accelerometer_data = (
                    self.controllers.mtm1m3.tel_accelerometerData.DataType()
                )

                accelerometer_data.timestamp = current_tai()

                raw_accelerometer = np.sin(
                    np.radians(
                        getattr(
                            self.controllers.mtmount.tel_elevation.data,
                            self.mtmount_demand_position_name,
                        )
                    )
                )

                accelerometer_data.rawAccelerometer = np.random.normal(
                    loc=raw_accelerometer,
                    scale=self.m1m3_accelerometer_error,
                    size=len(accelerometer_data.rawAccelerometer),
                )

                accelerometer_data.accelerometer = accelerometer_data.rawAccelerometer

                self.controllers.mtm1m3.tel_accelerometerData.put(accelerometer_data)

                force_actuator_data = (
                    self.controllers.mtm1m3.tel_forceActuatorData.DataType()
                )

                force_actuator_data.timestamp = current_tai()

                force_actuator_data.primaryCylinderForce = np.random.rand(
                    len(force_actuator_data.primaryCylinderForce)
                )
                force_actuator_data.secondaryCylinderForce = np.random.rand(
                    len(force_actuator_data.secondaryCylinderForce)
                )
                force_actuator_data.xForce = np.random.rand(
                    len(force_actuator_data.xForce)
                )
                force_actuator_data.yForce = np.random.rand(
                    len(force_actuator_data.yForce)
                )
                force_actuator_data.zForce = np.random.rand(
                    len(force_actuator_data.zForce)
                )
                force_actuator_data.fx = np.random.rand()
                force_actuator_data.fy = np.random.rand()
                force_actuator_data.fz = np.random.rand()
                force_actuator_data.mx = np.random.rand()
                force_actuator_data.my = np.random.rand()
                force_actuator_data.mz = np.random.rand()

                force_actuator_data.forceMagnitude = np.sqrt(
                    force_actuator_data.fx ** 2
                    + force_actuator_data.fy ** 2
                    + force_actuator_data.fz ** 2
                )

                self.controllers.mtm1m3.tel_forceActuatorData.put(force_actuator_data)

                hardpoint_actuator_data = (
                    self.controllers.mtm1m3.tel_hardpointActuatorData.DataType()
                )

                hardpoint_actuator_data.timestamp = current_tai()
                hardpoint_actuator_data.measuredForce = np.random.normal(
                    size=len(hardpoint_actuator_data.measuredForce)
                )
                hardpoint_actuator_data.encoder = np.array(
                    [32438, 37387, 43686, 44733, 34862, 40855], dtype=int
                )
                hardpoint_actuator_data.displacement = np.random.normal(
                    size=len(hardpoint_actuator_data.displacement)
                )
                hardpoint_actuator_data.fx = np.random.normal()
                hardpoint_actuator_data.fy = np.random.normal()
                hardpoint_actuator_data.fz = np.random.normal()
                hardpoint_actuator_data.mx = np.random.normal()
                hardpoint_actuator_data.my = np.random.normal()
                hardpoint_actuator_data.mz = np.random.normal()
                hardpoint_actuator_data.forceMagnitude = np.random.normal()
                hardpoint_actuator_data.xPosition = np.random.normal()
                hardpoint_actuator_data.yPosition = np.random.normal()
                hardpoint_actuator_data.zPosition = np.random.normal()
                hardpoint_actuator_data.xRotation = np.random.normal()
                hardpoint_actuator_data.yRotation = np.random.normal()
                hardpoint_actuator_data.zRotation = np.random.normal()

                self.controllers.mtm1m3.tel_hardpointActuatorData.put(
                    hardpoint_actuator_data
                )

                hardpoint_monitor_data = (
                    self.controllers.mtm1m3.tel_hardpointMonitorData.DataType()
                )

                hardpoint_monitor_data.timestamp = current_tai()
                hardpoint_monitor_data.breakawayLVDT = np.random.normal(
                    loc=self.m1m3_breakaway_lvdt,
                    scale=self.m1m3_breakaway_lvdt / 10.0,
                    size=len(hardpoint_monitor_data.breakawayLVDT),
                )
                hardpoint_monitor_data.displacementLVDT = np.random.normal(
                    loc=self.m1m3_displacement_lvdt,
                    scale=self.m1m3_displacement_lvdt / 10.0,
                    size=len(hardpoint_monitor_data.displacementLVDT),
                )
                hardpoint_monitor_data.breakawayPressure = np.random.normal(
                    loc=self.m1m3_breakaway_pressure,
                    scale=self.m1m3_breakaway_pressure / 10.0,
                    size=len(hardpoint_monitor_data.breakawayPressure),
                )
                hardpoint_monitor_data.pressureSensor1 = np.random.normal(
                    loc=self.m1m3_pressure_sensor_1,
                    scale=self.m1m3_pressure_sensor_1 / 10.0,
                    size=len(hardpoint_monitor_data.pressureSensor1),
                )
                hardpoint_monitor_data.pressureSensor2 = np.random.normal(
                    loc=self.m1m3_pressure_sensor_2,
                    scale=self.m1m3_pressure_sensor_2 / 10.0,
                    size=len(hardpoint_monitor_data.pressureSensor2),
                )
                hardpoint_monitor_data.pressureSensor3 = np.random.normal(
                    loc=self.m1m3_pressure_sensor_3,
                    scale=self.m1m3_pressure_sensor_3 / 10.0,
                    size=len(hardpoint_monitor_data.pressureSensor3),
                )

                self.controllers.mtm1m3.tel_hardpointMonitorData.put(
                    hardpoint_monitor_data
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
            self.controllers.mtm1m3.evt_forceActuatorState.set_put(
                **self.m1m3_force_actuator_state
            )

            await asyncio.sleep(HEARTBEAT_INTERVAL)

    async def publish_m1m3_topic_samples(self):
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
                getattr(self.controllers.mtm1m3, f"evt_{topic_sample}").set_put(
                    **m1m3_topic_samples[topic_sample]
                )
            except Exception:
                self.log.exception(f"Error publishing topic {topic_sample}")

        self.log.debug("Finished publishing m1m3 topic samples.")

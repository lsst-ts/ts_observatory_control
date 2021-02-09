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

__all__ = ["MTCSMock"]

import asyncio

from .base_group_mock import BaseGroupMock

from lsst.ts import salobj

import astropy.units as u
import numpy as np

from astropy.time import Time
from astropy.coordinates import AltAz, ICRS, EarthLocation, Angle

from lsst.ts.idl.enums import MTPtg

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

        self.tracking = False
        self.acting = False

        self.controllers.mtptg.cmd_stopTracking.callback = (
            self.mtptg_stop_tracking_callback
        )
        self.controllers.mtptg.cmd_azElTarget.callback = self.azel_target_callback
        self.controllers.mtptg.cmd_raDecTarget.callback = self.radec_target_callback

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
            elevation=data.elDegs, azimuth=data.azDegs, trackId=data.trackId,
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

    async def mount_telemetry(self):

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

                az_dif = salobj.angle_diff(az_set, az_actual)
                el_dif = salobj.angle_diff(el_set, el_actual)
                in_position_elevation = np.abs(el_dif) < 1e-1 * u.deg
                in_position_azimuth = np.abs(az_dif) < 1e-1 * u.deg

                if self.acting:
                    self.controllers.mtmount.evt_axesInPosition.set_put(
                        elevation=in_position_elevation, azimuth=in_position_azimuth
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

                self.controllers.mtmount.evt_target.put()

            await asyncio.sleep(HEARTBEAT_INTERVAL)

    async def rotator_telemetry(self):

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
                dif = salobj.angle_diff(demand, position)

                self.controllers.mtrotator.tel_rotation.set_put(
                    actualPosition=position + error + dif.deg / 1.1
                )

                if self.acting:
                    self.controllers.mtrotator.evt_inPosition.set_put(
                        inPosition=np.abs(dif) < ROT_IN_POSITION_DELTA
                    )

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

                diff_az = salobj.angle_diff(dome_az_set, dome_az_pos)
                diff_el = salobj.angle_diff(dome_el_set, dome_el_pos)

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
                        elevation=alt_az.alt.deg, azimuth=alt_az.az.deg,
                    )

            await asyncio.sleep(HEARTBEAT_INTERVAL)

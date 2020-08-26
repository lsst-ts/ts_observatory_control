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


class MTCSMock(BaseGroupMock):
    """Mock the behavior of the combined components that make out MTCS.

    This is useful for unit testing.

    """

    def __init__(self):

        super().__init__(
            components=[
                "NewMTMount",
                "MTMount",
                "MTPtg",
                "MTAOS",
                "MTM1M3",
                "MTM2",
                "Hexapod:1",
                "Hexapod:2",
                "Rotator",
                "Dome",
                "MTDomeTrajectory",
            ],
            output_only=["MTMount"],
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

        self.controllers.mtmount.tel_Azimuth.set(Azimuth_Angle_Set=0.0)
        self.controllers.mtmount.tel_Elevation.set(Elevation_Angle_Set=80.0)

    async def mtptg_stop_tracking_callback(self, data):

        self.tracking = False
        self.acting = False
        self.controllers.newmtmount.evt_axesInPosition.set_put(
            elevation=False, azimuth=False
        )
        self.controllers.rotator.evt_inPosition.set_put(inPosition=False)

        await asyncio.sleep(HEARTBEAT_INTERVAL)

    async def azel_target_callback(self, data):

        if (
            self.controllers.mtptg.evt_summaryState.data.summaryState
            != salobj.State.ENABLED
        ):
            raise RuntimeError("MTPtg not in enable state.")

        self.tracking = False

        await asyncio.sleep(HEARTBEAT_INTERVAL)

        self.controllers.newmtmount.evt_target.set(
            elevation=data.elDegs, azimuth=data.azDegs, trackId=data.trackId,
        )

        self.acting = True

        self.controllers.mtmount.tel_Azimuth.set(Azimuth_Angle_Set=data.azDegs)

        self.controllers.mtmount.tel_Elevation.set(Elevation_Angle_Set=data.elDegs)

        self.controllers.rotator.tel_Application.set(Demand=data.rotPA)

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

        self.controllers.newmtmount.evt_target.set(trackId=data.trackId)

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
                self.controllers.newmtmount.evt_summaryState.data.summaryState
                == salobj.State.ENABLED
            ):

                az_induced_error = np.random.normal(0.0, 1e-7)
                el_induced_error = np.random.normal(0.0, 1e-7)

                az_set = self.controllers.mtmount.tel_Azimuth.data.Azimuth_Angle_Set
                el_set = self.controllers.mtmount.tel_Elevation.data.Elevation_Angle_Set

                az_actual = (
                    self.controllers.mtmount.tel_Azimuth.data.Azimuth_Angle_Actual
                )
                el_actual = (
                    self.controllers.mtmount.tel_Elevation.data.Elevation_Angle_Actual
                )

                az_dif = salobj.angle_diff(az_set, az_actual)
                el_dif = salobj.angle_diff(el_set, el_actual)
                in_position_elevation = np.abs(el_dif) < 1e-1 * u.deg
                in_position_azimuth = np.abs(az_dif) < 1e-1 * u.deg

                if self.acting:
                    self.controllers.newmtmount.evt_axesInPosition.set_put(
                        elevation=in_position_elevation, azimuth=in_position_azimuth
                    )

                self.controllers.mtmount.tel_Azimuth.set_put(
                    Azimuth_Angle_Actual=az_actual + az_induced_error + az_dif.deg / 1.1
                )
                self.controllers.mtmount.tel_Elevation.set_put(
                    Elevation_Angle_Actual=el_actual
                    + el_induced_error
                    + el_dif.deg / 1.1
                )

                self.controllers.newmtmount.evt_target.put()

            await asyncio.sleep(HEARTBEAT_INTERVAL)

    async def rotator_telemetry(self):

        while self.run_telemetry_loop:
            if (
                self.controllers.rotator.evt_summaryState.data.summaryState
                == salobj.State.ENABLED
            ):

                error = np.random.normal(0.0, 1e-7)
                demand = self.controllers.rotator.tel_Application.data.Demand
                position = self.controllers.rotator.tel_Application.data.Position
                dif = salobj.angle_diff(demand, position)

                in_position = np.abs(dif) < 1e-1 * u.deg

                if self.acting:
                    self.controllers.rotator.evt_inPosition.set_put(
                        inPosition=in_position
                    )

                self.controllers.rotator.tel_Application.set_put(
                    Position=position + error + dif.deg / 1.1,
                    Error=error + dif.deg / 1.1,
                )

            await asyncio.sleep(HEARTBEAT_INTERVAL)

    async def dome_telemetry(self):

        while self.run_telemetry_loop:
            if (
                self.controllers.dome.evt_summaryState.data.summaryState
                == salobj.State.ENABLED
            ):

                dome_az_set = self.controllers.dome.tel_azimuth.data.positionCommanded
                dome_el_set = (
                    self.controllers.dome.tel_lightWindScreen.data.positionCommanded
                )

                dome_az_pos = self.controllers.dome.tel_azimuth.data.positionActual
                dome_el_pos = (
                    self.controllers.dome.tel_lightWindScreen.data.positionActual
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
                    dome_az_set = (
                        self.controllers.mtmount.tel_Azimuth.data.Azimuth_Angle_Set
                    )
                    dome_el_set = (
                        self.controllers.mtmount.tel_Elevation.data.Elevation_Angle_Set
                    )

                self.controllers.dome.tel_azimuth.set(
                    positionCommanded=dome_az_set,
                    positionActual=dome_az_pos + error_az + diff_az.deg / 1.1,
                )
                self.controllers.dome.tel_lightWindScreen.set(
                    positionCommanded=dome_el_set,
                    positionActual=dome_el_pos + error_el + diff_el.deg / 1.1,
                )

                self.controllers.dome.tel_azimuth.put()

                self.controllers.dome.tel_lightWindScreen.put()

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

                    self.controllers.mtmount.tel_Azimuth.set(
                        Azimuth_Angle_Set=alt_az.az.deg
                    )

                    self.controllers.mtmount.tel_Elevation.set(
                        Elevation_Angle_Set=alt_az.alt.deg
                    )

                    self.controllers.rotator.tel_Application.set(
                        Demand=self.controllers.mtptg.evt_currentTarget.data.rotPA
                    )

                    self.controllers.newmtmount.evt_target.set(
                        elevation=alt_az.alt.deg, azimuth=alt_az.az.deg,
                    )

            await asyncio.sleep(HEARTBEAT_INTERVAL)

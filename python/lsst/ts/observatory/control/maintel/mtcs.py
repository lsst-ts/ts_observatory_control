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

__all__ = ["MTCS"]

import types
import asyncio

import numpy as np
import astropy.units as u
from astropy.coordinates import Angle

from lsst.ts import salobj
from lsst.ts.idl.enums import MTPtg
from ..remote_group import Usages
from ..base_tcs import BaseTCS


class MTCSUsages(Usages):
    """MTCS usages definition.

    Notes
    -----

    Additional usages definition:

    * Slew: Enable all slew operations.
    * StartUp: Enable startup operations.
    * Shutdown: Enable shutdown operations.
    * PrepareForFlatfield: Enable preparation for flat-field.
    """

    Slew = 1 << 3
    StartUp = 1 << 4
    Shutdown = 1 << 5
    PrepareForFlatfield = 1 << 6

    def __iter__(self):

        return iter(
            [
                self.All,
                self.StateTransition,
                self.MonitorState,
                self.MonitorHeartBeat,
                self.Slew,
                self.StartUp,
                self.Shutdown,
                self.PrepareForFlatfield,
            ]
        )


class MTCS(BaseTCS):
    """High level library for the Main Telescope Control System

    This is the high level interface for interacting with the CSCs that
    control the Main Telescope. Essentially this will allow the user to
    slew and track the telescope.

    This is a placeholder for the Main Telescope Class.

    Parameters
    ----------
    domain: `salobj.Domain`
        Domain to use of the Remotes. If `None`, create a new domain.

    """

    def __init__(self, domain=None, log=None, intended_usage=None):

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
            domain=domain,
            log=log,
            intended_usage=intended_usage,
        )

        # For now MTMount is only used for telemetry/event from the low level
        # mount control system. This will make sure MTMount is excluded from
        # commanding activities.
        self.check.mtmount = False

        self.open_dome_shutter_time = 1200.0

        self.tel_park_el = 80.0
        self.tel_park_az = 0.0
        self.tel_flat_el = 39.0
        self.tel_flat_az = 205.7
        self.tel_settle_time = 3.0

        self.dome_park_az = 285.0
        self.dome_park_el = 80.0
        self.dome_flat_az = 20.0
        self.dome_flat_el = self.dome_park_el
        self.dome_slew_tolerance = Angle(1.5 * u.deg)

        self._dome_az_in_position = asyncio.Event()
        self._dome_az_in_position.clear()

        self._dome_el_in_position = asyncio.Event()
        self._dome_el_in_position.clear()

    async def _slew_to(
        self, slew_cmd, slew_timeout, stop_before_slew=True, wait_settle=True
    ):
        """Encapsulate "slew" activities.

        Parameters
        ----------
        slew_cmd : `coro`
            One of the slew commands from the mtptg remote. Command need to be
            setup before calling this method.
        slew_timeout : `float`
            Expected slewtime (seconds).
        stop_before_slew : `bool`
            Before starting a slew, send a stop target event?
        wait_settle : `bool`
            Once the telescope report in position, add an additional wait
            before returning? The time is controlled by the internal variable
            `self.tel_settle_time`.
        """
        if stop_before_slew:
            try:
                await self.stop_tracking()
            except Exception:
                pass

        track_id = next(self.track_id_gen)

        try:
            current_target = await self.rem.newmtmount.evt_target.next(
                flush=True, timeout=self.fast_timeout
            )
            if track_id <= current_target.trackId:
                self.track_id_gen = salobj.index_generator(current_target.trackId + 1)
                track_id = next(self.track_id_gen)

        except asyncio.TimeoutError:
            pass

        slew_cmd.data.trackId = track_id

        self.log.debug("Sending slew command.")

        ack = await slew_cmd.start(timeout=slew_timeout)
        self._dome_az_in_position.clear()

        self.log.debug("Scheduling check coroutines")

        self.scheduled_coro.append(
            asyncio.create_task(
                self.wait_for_inposition(timeout=slew_timeout, wait_settle=wait_settle)
            )
        )
        self.scheduled_coro.append(asyncio.create_task(self.monitor_position(ack)))

        for comp in self.components:
            if getattr(self.check, comp):
                getattr(self.rem, comp).evt_summaryState.flush()
                self.scheduled_coro.append(
                    asyncio.create_task(self.check_component_state(comp))
                )

        await self.process_as_completed(self.scheduled_coro)

    async def wait_for_inposition(self, timeout, cmd_ack=None, wait_settle=True):
        """Wait for both the ATMCS and ATDome to be in position.

        Parameters
        ----------
        timeout: `float`
            How long should it wait before timing out.

        Returns
        -------
        status: `str`
            String with final status.
        """
        status = list()

        if self.check.newmtmount:
            # Note that this event comes from MTMount not NewMTMount,
            # but it is actually started by MTMount. For now MTMount should
            # always be unchecked and we will use NewMTMount to manage that.
            status.append(
                asyncio.create_task(
                    self.wait_for_mtmount_inposition(timeout, cmd_ack, wait_settle)
                )
            )

        if self.check.dome:
            status.append(
                asyncio.create_task(self.wait_for_dome_inposition(timeout, cmd_ack))
            )

        if self.check.rotator:
            status.append(
                asyncio.create_task(self.wait_for_rotator_inposition(timeout, cmd_ack))
            )

        ret_val = ""
        for s in await asyncio.gather(*status):
            ret_val += f"{s!r}"

        return ret_val

    async def monitor_position(self, ack):
        """Monitor MTCS axis position.

        Monitor/log a selected set of axis from the main
        telescope. This is useful during slew activities to
        make sure everything is going as expected.
        """
        self.log.debug("Monitor position started.")

        if self.check.newmtmount:
            self.log.debug("Waiting for Target event from newmtmount.")
            try:
                target = await self.rem.newmtmount.evt_target.next(
                    flush=True, timeout=self.long_timeout
                )
                self.log.debug(f"Got {target}")
            except asyncio.TimeoutError:
                raise RuntimeError(
                    "Not receiving target events from the NewMTMount. "
                    "Check component for errors."
                )

        while True:

            status = ""

            if self.check.newmtmount:
                tel_az = await self.rem.mtmount.tel_Azimuth.next(
                    flush=True, timeout=self.fast_timeout
                )
                tel_el = await self.rem.mtmount.tel_Elevation.next(
                    flush=True, timeout=self.fast_timeout
                )
                status += (
                    f"[Tel]: Az = {tel_az.Azimuth_Angle_Actual:+08.3f}; "
                    f"El = {tel_el.Elevation_Angle_Actual:+08.3f} "
                )

            if self.check.rotator:
                rotator = await self.rem.rotator.tel_Application.next(
                    flush=True, timeout=self.fast_timeout
                )
                status += f"[Rot]: {rotator.Position:+08.3f} "

            if self.check.dome:
                dome_az = await self.rem.dome.tel_domeADB_status.next(
                    flush=True, timeout=self.fast_timeout
                )
                dome_el = await self.rem.dome.tel_domeAPS_status.next(
                    flush=True, timeout=self.fast_timeout
                )
                dome_az_diff = salobj.angle_diff(
                    dome_az.positionActual, dome_az.positionCmd
                )
                dome_el_diff = salobj.angle_diff(
                    dome_el.positionActual, dome_el.positionCmd
                )
                if np.abs(dome_az_diff) < self.dome_slew_tolerance:
                    self._dome_az_in_position.set()

                if np.abs(dome_el_diff) < self.dome_slew_tolerance:
                    self._dome_el_in_position.set()

                status += (
                    f"[Dome] Az = {dome_az.positionActual:+08.3f}; "
                    f"El = {dome_el.positionActual:+08.3f} "
                )

            if len(status) > 0:
                self.log.debug(status)

            await asyncio.sleep(self.fast_timeout)

    async def wait_for_mtmount_inposition(
        self, timeout, cmd_ack=None, wait_settle=True
    ):
        """Wait for the MTMount `inPosition` event.

        Parameters
        ----------
        timeout: `float`
            How to to wait for mount to be in position (in seconds).
        cmd_ack: `CmdAck` or `None`
            Slew command acknowledgment. This can be used by the method to
            ignore rogue in position events. This is an experimental feature.
        wait_settle: `bool`
            After receiving the in position command add an addional settle
            wait? (default: True)
        """

        self.log.debug("Wait for mtmount in position event.")

        while True:

            in_position = await self.rem.mtmount.evt_mountInPosition.next(
                flush=False, timeout=timeout
            )

            # make sure timestamp of event is after command was acknowledged.
            if (
                cmd_ack is not None
                and in_position.private_sndStamp < cmd_ack.private_sndStamp
            ):
                self.log.debug("Received old event. Ignoring.")
            else:
                self.log.info(f"Got {in_position.inposition}")
                if in_position.inposition:
                    if wait_settle:
                        self.log.info("Waiting for telescope to settle.")
                        await asyncio.sleep(self.tel_settle_time)
                    self.log.info("Telescope in position.")
                    return "Telescope in position."
                else:
                    self.log.debug("Telescope not in position")

    async def wait_for_dome_inposition(self, timeout, cmd_ack=None, wait_settle=True):
        """Wait for the Dome to be in position.

        Parameters
        ----------
        timeout: `float`
            How to to wait for mount to be in position (in seconds).
        cmd_ack: `CmdAck` or `None`
            Slew command acknowledgment. This can be used by the method to
            ignore rogue in position events. This is an experimental feature.
        wait_settle: `bool`
            After receiving the in position command add an addional settle
            wait? (default: True)
        """
        self.log.debug("Wait for dome in position event.")

        self._dome_az_in_position.clear()
        self._dome_el_in_position.clear()

        tasks = [
            asyncio.create_task(self.dome_az_in_position()),
            asyncio.create_task(self.dome_el_in_position()),
        ]
        ret_val = ""
        for completed in asyncio.as_completed(tasks):
            val = await completed
            self.log.debug(val)
            ret_val += f"{val} "

        return ret_val

    async def wait_for_rotator_inposition(
        self, timeout, cmd_ack=None, wait_settle=True
    ):
        """Wait for the Rotator `inPosition` event.

        Parameters
        ----------
        timeout: `float`
            How to to wait for mount to be in position (in seconds).
        cmd_ack: `CmdAck` or `None`
            Slew command acknowledgment. This can be used by the method to
            ignore rogue in position events. This is an experimental feature.
        wait_settle: `bool`
            After receiving the in position command add an addional settle
            wait? (default: True)
        """
        self.log.debug("Wait for rotator in position event.")

        while True:

            in_position = await self.rem.rotator.evt_inPosition.next(
                flush=False, timeout=timeout
            )

            # make sure timestamp of event is after command was acknowledged.
            if (
                cmd_ack is not None
                and in_position.private_sndStamp < cmd_ack.private_sndStamp
            ):
                self.log.debug("Received old event. Ignoring.")
            else:
                self.log.info(f"Got {in_position.inPosition}")
                if in_position.inPosition:
                    self.log.info("Rotator in position.")
                    return "Rotator in position."
                else:
                    self.log.debug("Rotator not in position")

    async def dome_az_in_position(self):
        """Wait for `_dome_az_in_position` event to be set and return a string
        indicating the dome azimuth is in position.
        """
        await self._dome_az_in_position.wait()
        return "Dome azimuth in position."

    async def dome_el_in_position(self):
        """Wait for `_dome_el_in_position` event to be set and return a string
        indicating the dome elevation is in position.
        """
        await self._dome_el_in_position.wait()
        return "Dome elevation in position."

    def set_azel_slew_checks(self, wait_dome):
        """Handle azEl slew to wait or not for the dome.
        """
        check = types.SimpleNamespace(
            dome=self.check.dome, mtdometrajectory=self.check.mtdometrajectory,
        )
        self.check.dome = wait_dome
        self.check.mtdometrajectory = wait_dome
        return check

    def unset_azel_slew_checks(self, checks):
        """Handle azEl slew to wait or not for the dome.
        """
        self.check.dome = checks.dome
        self.check.mtdometrajectory = checks.mtdometrajectory

    def check_tracking(self, track_duration=None):
        # TODO: Finish implementation of this method (DM-24488).
        pass

    def close_dome(self):
        # TODO: Implement (DM-21336).
        pass

    def close_m1_cover(self):
        # TODO: Implement (DM-21336).
        pass

    def home_dome(self):
        # TODO: Implement (DM-21336).
        pass

    def open_dome_shutter(self):
        # TODO: Implement (DM-21336).
        pass

    def open_m1_cover(self):
        # TODO: Implement (DM-21336).
        pass

    def prepare_for_flatfield(self):
        # TODO: Implement (DM-21336).
        pass

    def prepare_for_onsky(self, settings=None):
        # TODO: Implement (DM-21336).
        pass

    def shutdown(self):
        # TODO: Implement (DM-21336).
        pass

    def stop_all(self):
        # TODO: Implement (DM-21336).
        pass

    @property
    def ptg_name(self):
        """Return name of the pointing component.
        """
        return "mtptg"

    @property
    def CoordFrame(self):
        """Return CoordFrame enumeration.
        """
        return MTPtg.CoordFrame

    @property
    def RotFrame(self):
        """Return RotFrame enumeration.
        """
        return MTPtg.RotFrame

    @property
    def RotMode(self):
        """Return RotMode enumeration.
        """
        return MTPtg.RotMode

    @property
    def valid_use_cases(self):
        """Returns valid usages.

        Returns
        -------
        usages: enum

        """
        return MTCSUsages()

    @property
    def usages(self):

        usages = super().usages

        usages[self.valid_use_cases.All] = types.SimpleNamespace(
            components=self._components,
            readonly=False,
            include=[
                "start",
                "enable",
                "disable",
                "standby",
                "exitControl",
                "enterControl",
                "azElTarget",
                "raDecTarget",
                "planetTarget",
                "stopTracking",
                "offsetAzEl",
                "offsetRADec",
                "summaryState",
                "settingVersions",
                "heartbeat",
                "pointAddData",
                "pointNewFile",
                "pointAddData",
                "timeAndDate",
            ],
        )

        usages[self.valid_use_cases.Slew] = types.SimpleNamespace(
            components=self._components,
            readonly=False,
            include=[
                "azElTarget",
                "raDecTarget",
                "planetTarget",
                "stopTracking",
                "offsetAzEl",
                "offsetRADec",
                "pointAddData",
                "pointNewFile",
                "pointAddData",
                "summaryState",
                "settingVersions",
                "heartbeat",
                "timeAndDate",
                "target",
                "Application",
                "Azimuth",
                "Elevation",
                "mountInPosition",
                "inPosition",
                "domeADB_status",
                "domeAPS_status",
            ],
        )

        usages[self.valid_use_cases.StartUp] = types.SimpleNamespace(
            components=self._components,
            readonly=False,
            include=[
                "start",
                "enable",
                "disable",
                "standby",
                "exitControl",
                "enterControl",
                "azElTarget",
                "stopTracking",
                "summaryState",
                "settingVersions",
                "heartbeat",
            ],
        )

        usages[self.valid_use_cases.Shutdown] = types.SimpleNamespace(
            components=self._components,
            readonly=False,
            include=[
                "start",
                "enable",
                "disable",
                "standby",
                "exitControl",
                "enterControl",
                "azElTarget",
                "stopTracking",
                "summaryState",
                "settingVersions",
                "heartbeat",
            ],
        )

        usages[self.valid_use_cases.PrepareForFlatfield] = types.SimpleNamespace(
            components=self._components,
            readonly=False,
            include=[
                "start",
                "enable",
                "disable",
                "standby",
                "exitControl",
                "enterControl",
                "summaryState",
                "settingVersions",
                "heartbeat",
            ],
        )

        return usages

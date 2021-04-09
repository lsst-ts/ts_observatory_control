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

__all__ = ["MTCS"]

import copy
import types
import asyncio

import numpy as np
import astropy.units as u
from astropy.coordinates import Angle

from lsst.ts import salobj
from lsst.ts.idl.enums import MTPtg
from ..remote_group import Usages, UsagesResources
from ..base_tcs import BaseTCS
from ..constants import mtcs_constants


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
            domain=domain,
            log=log,
            intended_usage=intended_usage,
        )

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
            current_target = await self.rem.mtmount.evt_target.next(
                flush=True, timeout=self.fast_timeout
            )
            if track_id <= current_target.trackId:
                self.track_id_gen = salobj.index_generator(current_target.trackId + 1)
                track_id = next(self.track_id_gen)

        except asyncio.TimeoutError:
            pass

        slew_cmd.data.trackId = track_id

        self.log.debug("Sending slew command.")

        if stop_before_slew:
            self.rem.mtmount.evt_axesInPosition.flush()
            self.rem.mtrotator.evt_inPosition.flush()

        await slew_cmd.start(timeout=slew_timeout)
        self._dome_az_in_position.clear()

        self.log.debug("Scheduling check coroutines")

        self.scheduled_coro.append(
            asyncio.create_task(
                self.wait_for_inposition(timeout=slew_timeout, wait_settle=wait_settle)
            )
        )
        self.scheduled_coro.append(asyncio.create_task(self.monitor_position()))

        for comp in self.components_attr:
            if getattr(self.check, comp):
                getattr(self.rem, comp).evt_summaryState.flush()
                self.scheduled_coro.append(
                    asyncio.create_task(self.check_component_state(comp))
                )

        await self.process_as_completed(self.scheduled_coro)

    async def wait_for_inposition(
        self, timeout, cmd_ack=None, wait_settle=True, check=None
    ):
        """Wait for Mount, Dome and Rotator to be in position.

        Parameters
        ----------
        timeout: `float`
            How long should it wait before timing out.
        cmd_ack: `CmdAck` or `None`
            CmdAck from the command that started the slew process. This is an
            experimental feature to discard events that where sent before the
            slew starts.
        wait_settle: `bool`
            After slew complets, add an addional settle wait before returning.
        check : `types.SimpleNamespace` or `None`
            Override `self.check` for defining which resources are used.

        Returns
        -------
        status: `str`
            String with final status.
        """
        # Creates a copy of check so it can be freely modified to control what
        # needs to be verified at each stage of the process.
        _check = copy.copy(self.check) if check is None else copy.copy(check)

        status = list()

        if _check.mtmount:
            # Note that this event comes from MTMount not NewMTMount,
            # but it is actually started by MTMount. For now MTMount should
            # always be unchecked and we will use NewMTMount to manage that.
            status.append(
                asyncio.create_task(
                    self.wait_for_mtmount_inposition(timeout, cmd_ack, wait_settle)
                )
            )

        if _check.mtdome:
            status.append(
                asyncio.create_task(self.wait_for_dome_inposition(timeout, cmd_ack))
            )

        if _check.mtrotator:
            status.append(
                asyncio.create_task(self.wait_for_rotator_inposition(timeout, cmd_ack))
            )

        ret_val = ""
        for s in await asyncio.gather(*status):
            ret_val += f"{s!r}"

        return ret_val

    async def monitor_position(self, check=None):
        """Monitor MTCS axis position.

        Monitor/log a selected set of axis from the main telescope. This is
        useful during slew activities to make sure everything is going as
        expected.

        Parameters
        ----------
        check : `types.SimpleNamespace` or `None`
            Override `self.check` for defining which resources are used.

        """
        # Creates a copy of check so it can be freely modified to control what
        # needs to be verified at each stage of the process.
        _check = copy.copy(self.check) if check is None else copy.copy(check)

        self.log.debug("Monitor position started.")

        # xml 7.1/8.0 backward compatibility
        mtmount_actual_position_name = "actualPosition"

        if _check.mtmount:
            self.log.debug("Waiting for Target event from mtmount.")
            try:
                target = await self.rem.mtmount.evt_target.next(
                    flush=True, timeout=self.long_timeout
                )
                self.log.debug(f"Mount target: {target}")
            except asyncio.TimeoutError:
                raise RuntimeError(
                    "Not receiving target events from the NewMTMount. "
                    "Check component for errors."
                )
            if not hasattr(
                self.rem.mtmount.tel_azimuth.DataType(), mtmount_actual_position_name
            ):
                self.log.debug("Running in xml 7.1 compatibility mode.")
                mtmount_actual_position_name = "angleActual"

        while True:

            status = ""

            if _check.mtmount:
                target, tel_az, tel_el = await asyncio.gather(
                    self.rem.mtmount.evt_target.next(
                        flush=True, timeout=self.long_timeout
                    ),
                    self.rem.mtmount.tel_azimuth.next(
                        flush=True, timeout=self.fast_timeout
                    ),
                    self.rem.mtmount.tel_elevation.next(
                        flush=True, timeout=self.fast_timeout
                    ),
                )
                tel_az_actual_position = getattr(tel_az, mtmount_actual_position_name)
                tel_el_actual_position = getattr(tel_el, mtmount_actual_position_name)
                distance_az = salobj.angle_diff(target.azimuth, tel_az_actual_position)
                distance_el = salobj.angle_diff(
                    target.elevation, tel_el_actual_position
                )
                status += (
                    f"[Tel]: Az = {tel_az_actual_position:+08.3f}[{distance_az.deg:+6.1f}]; "
                    f"El = {tel_el_actual_position:+08.3f}[{distance_el.deg:+6.1f}] "
                )

            if _check.mtrotator:
                rotation_data = await self.rem.mtrotator.tel_rotation.next(
                    flush=True, timeout=self.fast_timeout
                )
                distance_rot = salobj.angle_diff(
                    rotation_data.demandPosition, rotation_data.actualPosition
                )
                status += f"[Rot]: {rotation_data.demandPosition:+08.3f}[{distance_rot.deg:+6.1f}] "

            if _check.mtdome:
                dome_az = await self.rem.mtdome.tel_azimuth.next(
                    flush=True, timeout=self.fast_timeout
                )
                dome_el = await self.rem.mtdome.tel_lightWindScreen.next(
                    flush=True, timeout=self.fast_timeout
                )
                dome_az_diff = salobj.angle_diff(
                    dome_az.positionActual, dome_az.positionCommanded
                )
                dome_el_diff = salobj.angle_diff(
                    dome_el.positionActual, dome_el.positionCommanded
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

            in_position = await self.rem.mtmount.evt_axesInPosition.next(
                flush=False, timeout=timeout
            )

            # make sure timestamp of event is after command was acknowledged.
            if (
                cmd_ack is not None
                and in_position.private_sndStamp < cmd_ack.private_sndStamp
            ):
                self.log.debug("Received old event. Ignoring.")
            else:
                self.log.debug(
                    "MTMount axesInPosition got: "
                    f"elevation {in_position.elevation}, "
                    f"azimuth {in_position.azimuth}."
                )
                if in_position.elevation and in_position.azimuth:
                    if wait_settle:
                        self.log.info("Waiting for telescope to settle.")
                        await asyncio.sleep(self.tel_settle_time)
                    self.log.info("Telescope in position.")
                    return "Telescope in position."

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

            in_position = await self.rem.mtrotator.evt_inPosition.next(
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
        """Handle azEl slew to wait or not for the dome."""
        check = types.SimpleNamespace(
            dome=self.check.mtdome,
            mtdometrajectory=self.check.mtdometrajectory,
        )
        self.check.mtdome = wait_dome
        self.check.mtdometrajectory = wait_dome
        return check

    def unset_azel_slew_checks(self, checks):
        """Handle azEl slew to wait or not for the dome."""
        self.check.mtdome = checks.dome
        self.check.mtdometrajectory = checks.mtdometrajectory

    async def slew_dome_to(self, az, check=None):
        """Utility method to slew dome to a specified position.

        Parameters
        ----------
        az : `float` or `str`
            Azimuth angle for the dome (in deg).
        check : `types.SimpleNamespace` or `None`
            Override `self.check` for defining which resources are used.

        """
        # TODO: Implement (DM-21336).
        raise NotImplementedError("# TODO: Implement (DM-21336).")

    def close_dome(self):
        # TODO: Implement (DM-21336).
        raise NotImplementedError("# TODO: Implement (DM-21336).")

    def close_m1_cover(self):
        # TODO: Implement (DM-21336).
        raise NotImplementedError("# TODO: Implement (DM-21336).")

    def home_dome(self):
        # TODO: Implement (DM-21336).
        raise NotImplementedError("# TODO: Implement (DM-21336).")

    def open_dome_shutter(self):
        # TODO: Implement (DM-21336).
        raise NotImplementedError("# TODO: Implement (DM-21336).")

    def open_m1_cover(self):
        # TODO: Implement (DM-21336).
        raise NotImplementedError("# TODO: Implement (DM-21336).")

    def prepare_for_flatfield(self):
        # TODO: Implement (DM-21336).
        raise NotImplementedError("# TODO: Implement (DM-21336).")

    def prepare_for_onsky(self, settings=None):
        # TODO: Implement (DM-21336).
        raise NotImplementedError("# TODO: Implement (DM-21336).")

    def shutdown(self):
        # TODO: Implement (DM-21336).
        raise NotImplementedError("# TODO: Implement (DM-21336).")

    def stop_all(self):
        # TODO: Implement (DM-21336).
        raise NotImplementedError("# TODO: Implement (DM-21336).")

    def flush_offset_events(self):
        """Abstract method to flush events before and offset is performed."""
        self.rem.mtmount.evt_axesInPosition.flush()

    async def offset_done(self):
        """Wait for offset events."""
        await self.wait_for_mtmount_inposition(timeout=self.tel_settle_time)

    async def get_bore_sight_angle(self):
        """Get the instrument bore sight angle with respect to the telescope
        axis.
        """

        el = await self.rem.mtmount.tel_elevation.aget(timeout=self.fast_timeout)

        rotation_data = await self.rem.mtrotator.tel_rotation.aget(
            timeout=self.fast_timeout
        )
        # xml 7.1/8.0 backward compatibility.
        tel_el_actual_position = (
            el.actualPosition if hasattr(el, "actualPosition") else el.angleActual
        )
        angle = tel_el_actual_position - rotation_data.actualPosition

        return angle

    def _ready_to_take_data(self):
        """Placeholder, still needs to be implemented."""
        # TODO: Finish implementation.
        self._ready_to_take_data_future.set_result(True)

    @property
    def plate_scale(self):
        """Plate scale in mm/arcsec."""
        return mtcs_constants.plate_scale

    @property
    def ptg_name(self):
        """Return name of the pointing component."""
        return "mtptg"

    @property
    def CoordFrame(self):
        """Return CoordFrame enumeration."""
        return MTPtg.CoordFrame

    @property
    def RotFrame(self):
        """Return RotFrame enumeration."""
        return MTPtg.RotFrame

    @property
    def RotMode(self):
        """Return RotMode enumeration."""
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

        if self._usages is None:
            usages = super().usages

            usages[self.valid_use_cases.All] = UsagesResources(
                components_attr=self.components_attr,
                readonly=False,
                generics=[
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
                mtptg=[
                    "azElTarget",
                    "raDecTarget",
                    "planetTarget",
                    "stopTracking",
                    "offsetAzEl",
                    "offsetRADec",
                    "pointAddData",
                    "pointNewFile",
                    "pointAddData",
                    "timeAndDate",
                    "focusNameSelected",
                ],
            )

            usages[self.valid_use_cases.Slew] = UsagesResources(
                components_attr=self.components_attr,
                readonly=False,
                generics=["summaryState", "settingVersions", "heartbeat"],
                mtptg=[
                    "azElTarget",
                    "raDecTarget",
                    "planetTarget",
                    "stopTracking",
                    "offsetAzEl",
                    "offsetRADec",
                    "pointAddData",
                    "pointNewFile",
                    "pointAddData",
                    "timeAndDate",
                    "target",
                    "focusNameSelected",
                ],
                mtrotator=["rotation", "inPosition"],
                mtmount=["azimuth", "elevation", "axesInPosition"],
                mtdome=["azimuth", "lightWindScreen"],
            )

            usages[self.valid_use_cases.StartUp] = UsagesResources(
                components_attr=self.components_attr,
                readonly=False,
                generics=[
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
                mtptg=["azElTarget", "stopTracking", "focusNameSelected"],
            )

            usages[self.valid_use_cases.Shutdown] = UsagesResources(
                components_attr=self.components_attr,
                readonly=False,
                generics=[
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
                mtptg=["azElTarget", "stopTracking", "focusNameSelected"],
            )

            usages[self.valid_use_cases.PrepareForFlatfield] = UsagesResources(
                components_attr=self.components_attr,
                readonly=False,
                generics=[
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

            self._usages = usages

        return self._usages

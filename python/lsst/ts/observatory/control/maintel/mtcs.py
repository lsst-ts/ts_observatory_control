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
from astropy.coordinates import AltAz, ICRS, EarthLocation, Angle
from astroquery.simbad import Simbad

from ..remote_group import RemoteGroup, Usages

from ..utils import subtract_angles, parallactic_angle, handle_rottype, RotType

from lsst.ts import salobj

from lsst.ts.idl.enums import MTPtg


class MTCSUsages(Usages):
    """MTCS usages definition.

    Notes
    -----

    Additional usages definition:

    Slew: Enable all slew operations.

    StartUp: Enable startup operations.

    Shutdown: Enable shutdown operations.

    PrepareForFlatfield: Enable preparation for flat-field.
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


class MTCS(RemoteGroup):
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

        self.location = EarthLocation.from_geodetic(
            lon=-70.747698 * u.deg, lat=-30.244728 * u.deg, height=2663.0 * u.m
        )

        # Rotation matrix to take into account angle between camera and
        # boresight
        self.rotation_matrix = lambda angle: np.array(
            [
                [np.cos(np.radians(angle)), -np.sin(np.radians(angle)), 0.0],
                [np.sin(np.radians(angle)), np.cos(np.radians(angle)), 0.0],
                [0.0, 0.0, 1.0],
            ]
        )

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

        self.track_id_gen = salobj.index_generator()

    async def slew_object(
        self, name, rot_sky=0.0, rot_phys_sky=None, slew_timeout=240.0,
    ):
        """Slew to an object name.

        Use simbad to resolve the name and get coordinates.

        Parameters
        ----------
        name : `str`
            Target name.
        rot_sky : `float`, `str` or `astropy.coordinates.Angle`
            Specify rotation in sky coordinates, clock-wise, relative to the
            north celestial pole. Accepts float (deg), sexagesimal string
            (DD:MM:SS.S or DD MM SS.S) coordinates or
            `astropy.coordinates.Angle`
        rot_phys_sky : `float`, `str` or `astropy.coordinates.Angle`
            Specify rotation in mount physical coordinates.
            Accepts float (deg), sexagesimal string
            (DD:MM:SS.S or DD MM SS.S) coordinates or
            `astropy.coordinates.Angle`. See `slew_icrs` for a detailed
            explanation.
        slew_timeout : `float`
            Timeout for the slew command (second).

        See Also
        --------
        slew_icrs : Slew to an ICRS coordinates.

        """

        object_table = Simbad.query_object(name)

        if object_table is None:
            raise RuntimeError(f"Could not find {name} in Simbad database.")
        elif len(object_table) > 1:
            self.log.warning(f"Found more than one entry for {name}. Using first one.")

        self.log.info(
            f"Slewing to {name}: {object_table['RA'][0]} {object_table['DEC'][0]}"
        )

        await self.slew_icrs(
            ra=object_table["RA"][0],
            dec=object_table["DEC"][0],
            rot_sky=rot_sky,
            rot_phys_sky=rot_phys_sky,
            target_name=name,
            slew_timeout=slew_timeout,
        )

    async def slew_icrs(
        self,
        ra,
        dec,
        rot_sky=0.0,
        rot_phys_sky=None,
        target_name="slew_icrs",
        slew_timeout=240.0,
        stop_before_slew=True,
        wait_settle=True,
    ):
        """Slew the telescope and start tracking an Ra/Dec target in ICRS
        coordinate frame.

        Parameters
        ----------
        ra : `float`, `str` or `astropy.coordinates.Angle`
            Target RA, either as a float (hour), a sexagesimal string
            (HH:MM:SS.S or HH MM SS.S) coordinates or
            `astropy.coordinates.Angle`.
        dec : `float`, `str` or `astropy.coordinates.Angle`
            Target Dec, either as a float (deg), a sexagesimal string
            (DD:MM:SS.S or DD MM SS.S) coordinates or
            `astropy.coordinates.Angle`.
        rot_sky : `float`, `str` or `astropy.coordinates.Angle`
            Specify rotation in sky coordinates, clock-wise, relative to the
            north celestial pole. Accepts float (deg), sexagesimal string
            (DD:MM:SS.S or DD MM SS.S) coordinates or
            `astropy.coordinates.Angle`
        rot_phys_sky : `float`, `str` or `astropy.coordinates.Angle`
            Specify rotation in mount physical coordinates.
            Accepts float (deg), sexagesimal string
            (DD:MM:SS.S or DD MM SS.S) coordinates or
            `astropy.coordinates.Angle`. See notes for some details.
        target_name :  `str`
            Target name.
        slew_timeout : `float`
            Timeout for the slew command (second). Default is 240s.
        stop_before_slew : `bool`
            Stop tracking before starting the slew? This option is a
            workaround to some issues with the ATMCS not sending events
            reliably.
        wait_settle : `bool`
            Wait telescope to settle before returning? It `True` add an
            additional sleep of `self.tel_settle_time` to the telescope
            positioning algorithm. Otherwise the algorithm will return as soon
            as it receives `allAxesInPosition` event from the ATMCS.

        See Also
        --------
        slew_object : Slew to an object name.

        Notes
        -----
        When using `rot_phys_sky` to specify the rotator position in terms of
        physical coordinates, the rotator will still track the sky. The
        rotator will not be kept in a fixed position.

        """
        radec_icrs = ICRS(Angle(ra, unit=u.hourangle), Angle(dec, unit=u.deg))

        _rot, _rottype = handle_rottype(rot_sky=rot_sky, rot_phys_sky=rot_phys_sky)

        current_time = salobj.astropy_time_from_tai_unix(salobj.current_tai())

        current_time.location = self.location

        par_angle = parallactic_angle(
            self.location, current_time.sidereal_time("mean"), radec_icrs,
        )

        coord_frame_altaz = AltAz(location=self.location, obstime=current_time)

        alt_az = radec_icrs.transform_to(coord_frame_altaz)

        if _rottype == RotType.Sky:
            self.log.debug(f"Setting sky angle to {_rot}.")
        elif _rottype == RotType.Physical_Sky:

            self.log.debug(f"Setting rotator physical position to {_rot}.")

            _rot += par_angle + alt_az.alt

            self.log.debug(
                f"Parallactic angle: {par_angle.deg} | " f"Sky Angle: {_rot.deg}"
            )
        elif _rottype == RotType.Parallactic:

            raise RuntimeError(f"RotType {_rottype!r} not supported by MTCS.")

        else:
            valid_rottypes = [f"{rt!r}" for rt in RotType].__str__()
            raise RuntimeError(
                f"Unrecognized rottype {_rottype!r}. Should be one of {valid_rottypes}"
            )

        await self.slew(
            radec_icrs.ra.hour,
            radec_icrs.dec.deg,
            rotPA=_rot.deg,
            target_name=target_name,
            frame=MTPtg.CoordFrame.ICRS,
            epoch=2000,
            equinox=2000,
            parallax=0,
            pmRA=0,
            pmDec=0,
            rv=0,
            dRA=0,
            dDec=0,
            rot_frame=MTPtg.RotFrame.TARGET,
            rot_mode=MTPtg.RotMode.FIELD,
            slew_timeout=slew_timeout,
            stop_before_slew=stop_before_slew,
            wait_settle=wait_settle,
        )

    async def point_azel(
        self,
        az,
        el,
        rot_tel=0.0,
        target_name="azel_target",
        wait_dome=False,
        slew_timeout=1200.0,
    ):
        """Slew the telescope to a fixed alt/az position.

        Telescope will not track once it arrives in position.

        Parameters
        ----------
        az : `float`, `str` or astropy.coordinates.Angle
            Target Azimuth (degree). Accepts float (deg), sexagesimal string
            (DD:MM:SS.S or DD MM SS.S) coordinates or
            `astropy.coordinates.Angle`
        el : `float` or `str`
            Target Elevation (degree). Accepts float (deg), sexagesimal string
            (DD:MM:SS.S or DD MM SS.S) coordinates or
            `astropy.coordinates.Angle`
        rot_tel : `float` or `str`
            Specify rotator angle in mount physical coordinates.
            Accepts float (deg), sexagesimal string
            (DD:MM:SS.S or DD MM SS.S) coordinates or
            `astropy.coordinates.Angle`
        target_name : `str`
            Name of the position.
        wait_dome : `bool`
            Wait for dome to be in sync with the telescope? If preparing to
            take a flat, for instance, the dome will never be in sync.
        slew_timeout : `float`
            Timeout for the slew command (second).
        """
        self.rem.mtptg.cmd_azElTarget.set(
            targetName=target_name,
            azDegs=Angle(az, unit=u.deg).deg,
            elDegs=Angle(el, unit=u.deg).deg,
            rotPA=Angle(rot_tel, unit=u.deg).deg,
        )
        check_dome = self.check.dome
        self.check.dome = wait_dome
        check_mtdometrajectory = self.check.mtdometrajectory
        self.check.mtdometrajectory = wait_dome

        try:
            await self._slew_to(
                self.rem.mtptg.cmd_azElTarget, slew_timeout=slew_timeout
            )
        finally:
            self.check.dome = check_dome
            self.check.mtdometrajectory = check_mtdometrajectory

    async def slew(
        self,
        ra,
        dec,
        rotPA=0.0,
        target_name="slew_icrs",
        frame=MTPtg.CoordFrame.ICRS,
        epoch=2000,
        equinox=2000,
        parallax=0,
        pmRA=0,
        pmDec=0,
        rv=0,
        dRA=0,
        dDec=0,
        rot_frame=MTPtg.RotFrame.TARGET,
        rot_mode=MTPtg.RotMode.FIELD,
        slew_timeout=1200.0,
        stop_before_slew=True,
        wait_settle=True,
    ):
        """Intermediate level ra/dec slew command.

        This method provides an intermediate level between higher-level slew
        commands and the low-level handling command. It contains all the inputs
        from the MTPtg `raDecTarget` command plus some additional parameters.

        For general users, we recommend using one of the other higher level
        conterpairs; `slew_icrs` or `slew_object`.

        Parameters
        ----------

        ra : float
            Target Right Ascension (hour)
        dec : float
            Target Declination (degree)
        rotPA : float
            Desired rotator position angle for slew (degree).
        target_name : `str`
            Name of the target
        frame : `int`
            Target co-ordinate reference frame.
        epoch : `float`
            Target epoch in years e.g. 2000.0. Julian (J) epoch is assumed.
        equinox : `float`
            Target equinox in years e.g. 2000.0
        parallax : `float`
            Parallax (arcseconds).
        pmRA : `float`
            Proper Motion (RA) in RA Seconds/year.
        pmDec : `float`
            Proper motion (Dec) in Arcseconds/year.
        rv : `float`
            Radial velocity (km/sec).
        dRA : `float`
            Differential Track Rate in RA.
        rot_frame : `enum`
            Rotator coordinate frame (`ATPtg.RotFrame`).
            If `ATPtg.RotFrame.TARGET` follow sky, if `ATPtg.RotFrame.FIXED`
            keep rotator in a fixed position.
        rot_mode : `enum`
            Rotator position mode (`ATPtg.RotMode`).
            If `ATPtg.RotMode.FIELD` optimize for sky tracking, if
            `ATPtg.RotMode.SLIT` optimize for slit spectroscopy.
        slew_timeout : `float`
            Timeout for the slew command (second).
        stop_before_slew : `bool`
            Stop tracking before starting the slew? This option is a
            workaround to some issues with the ATMCS not sending events
            reliably.
        wait_settle : `bool`
            Wait telescope to settle before returning?

        See Also
        --------
        point_azel: Point to a fixed az/el position.
        slew_icrs: High-level slew and track an ICRS coordinate.
        slew_object: Slew to an object using Simbad resolved name.
        """
        self.rem.mtptg.cmd_raDecTarget.set(
            ra=ra,
            declination=dec,
            rotPA=rotPA,
            targetName=target_name,
            frame=frame,
            epoch=epoch,
            equinox=equinox,
            parallax=parallax,
            pmRA=pmRA,
            pmDec=pmDec,
            rv=rv,
            dRA=dRA,
            dDec=dDec,
            rotFrame=rot_frame,
            rotMode=rot_mode,
        )

        await self._slew_to(
            self.rem.mtptg.cmd_raDecTarget,
            slew_timeout=slew_timeout,
            stop_before_slew=stop_before_slew,
            wait_settle=wait_settle,
        )

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

        self.log.debug("Sending slew command.")

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

    async def stop_tracking(self):
        """Task to stop telescope tracking."""

        self.log.debug("Stop tracking.")

        await self.rem.mtptg.cmd_stopTracking.start(timeout=self.fast_timeout)

        # TODO: What else do I need to wait to make sure the telescope stopped?

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
                dome_az_diff = subtract_angles(
                    dome_az.positionActual, dome_az.positionCmd
                )
                dome_el_diff = subtract_angles(
                    dome_el.positionActual, dome_el.positionCmd
                )
                if np.abs(dome_az_diff) * u.deg < self.dome_slew_tolerance:
                    self._dome_az_in_position.set()

                if np.abs(dome_el_diff) * u.deg < self.dome_slew_tolerance:
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

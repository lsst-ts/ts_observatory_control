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

__all__ = ["ATCS", "ATCSUsages"]

import enum
import types
import asyncio

import numpy as np
import astropy.units as u
from astropy.coordinates import AltAz, ICRS, EarthLocation, Angle
from astroquery.simbad import Simbad

from ..remote_group import RemoteGroup, Usages
from ..utils import subtract_angles, parallactic_angle

from lsst.ts import salobj
from lsst.ts.idl.enums import ATPtg, ATDome, ATPneumatics, ATMCS


class RotType(enum.IntEnum):
    """Defines the different types of rotator strategies.

    Sky: Sky position angle strategy. The rotator is positioned with respect
         to the North axis so rot_angle=0. means y-axis is aligned with North.
         Angle grows clock-wise.

    Parallactic: This strategy is required for taking optimum spectra with
                 LATISS. If set to zero, the rotator is positioned so that the
                 y-axis (dispersion axis) is aligned with the parallactic
                 angle.

    Physical_Sky: This strategy allows users to select the **initial** position
                  of the rotator in terms of the physical rotator angle (in the
                  reference frame of the telescope). Note that the telescope
                  will resume tracking the sky rotation.
    """

    Sky = 0
    Parallactic = 1
    Physical_Sky = 2


class ATCSUsages(Usages):
    """ATCS usages definition.

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


class ATCS(RemoteGroup):
    """High level library for the Auxiliary Telescope Control System

    This is the high level interface for interacting with the CSCs that
    control the Auxiliary Telescope. Essentially this will allow the user to
    slew and track the telescope.

    Parameters
    ----------
    domain: `salobj.Domain`
        Domain to use of the Remotes. If `None`, create a new domain.
    log : `logging.Logger`
        Optional logging class to be used for logging operations. If `None`,
        creates a new logger. Useful to use in salobj.BaseScript and allow
        logging in the class use the script logging.
    intended_usage: `int`
        Optional integer that maps to a list of intended operations. This is
        used to limit the resources allocated by the class by gathering some
        knowledge about the usage intention. By default allocates all
        resources.

    Attributes
    ----------
    atmcs: salobj.Remote
    ataos: salobj.Remote
    atpneumatics: salobj.Remote
    athexapod: salobj.Remote
    atdome: salobj.Remote
    atdometrajectory: salobj.Remote
    check: SimpleNamespace
    log: logging.Logger
    """

    def __init__(self, domain=None, log=None, intended_usage=None):

        super().__init__(
            components=[
                "ATMCS",
                "ATPtg",
                "ATAOS",
                "ATPneumatics",
                "ATHexapod",
                "ATDome",
                "ATDomeTrajectory",
            ],
            domain=domain,
            log=log,
            intended_usage=intended_usage,
        )

        self.open_dome_shutter_time = 600.0

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
        self.tel_el_operate_pneumatics = 70.0
        self.tel_settle_time = 3.0

        self.tel_az_slew_tolerance = Angle(0.004 * u.deg)
        self.tel_el_slew_tolerance = Angle(0.004 * u.deg)
        self.tel_nasm_slew_tolerance = Angle(0.004 * u.deg)

        self.dome_park_az = 285.0
        self.dome_flat_az = 20.0
        self.dome_slew_tolerance = Angle(5.1 * u.deg)

        self.dome_az_in_position = asyncio.Event()
        self.dome_az_in_position.clear()

        self.track_id_gen = salobj.index_generator()

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
        self.rem.atptg.cmd_azElTarget.set(
            targetName=target_name,
            azDegs=Angle(az, unit=u.deg).deg,
            elDegs=Angle(el, unit=u.deg).deg,
            rotPA=Angle(rot_tel, unit=u.deg).deg,
        )
        check_atdome = self.check.atdome
        self.check.atdome = wait_dome
        check_atdometrajectory = self.check.atdometrajectory
        self.check.atdometrajectory = wait_dome

        try:
            await self._slew_to(
                self.rem.atptg.cmd_azElTarget, slew_timeout=slew_timeout
            )
        except Exception as e:
            self.check.atdome = check_atdome
            self.check.atdometrajectory = check_atdometrajectory
            raise e

    async def start_tracking(self):
        """Start tracking the current position of the telescope.

        Method returns once telescope and dome are in sync.
        """
        raise NotImplementedError("Start tracking not implemented yet.")

    async def slew_object(
        self, name, rot_sky=0.0, rot_par=None, rot_phys_sky=None, slew_timeout=240.0,
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
        rot_par :  `float`, `str` or `astropy.coordinates.Angle`
            Specify rotation with respect to the parallactic angle.
            Accepts float (deg), sexagesimal string (DD:MM:SS.S or DD MM SS.S)
            coordinates or `astropy.coordinates.Angle`
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
            rot_par=rot_par,
            rot_phys_sky=rot_phys_sky,
            target_name=name,
            slew_timeout=slew_timeout,
        )

    async def slew_icrs(
        self,
        ra,
        dec,
        rot_sky=0.0,
        rot_par=None,
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
        rot_par :  `float`, `str` or `astropy.coordinates.Angle`
            Specify rotation with respect to the parallactic angle.
            Accepts float (deg), sexagesimal string (DD:MM:SS.S or DD MM SS.S)
            coordinates or `astropy.coordinates.Angle`
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

        Raises
        ------
        RuntimeError: If both `rot_par` and `rot_tel` are specified.

        See Also
        --------
        slew_object : Slew to an object name.

        Notes
        -----
        If either `rot_par` or `rot_tel` are specified, `rot_sky` is ignored.

        When using `rot_phys_sky` to specify the rotator position in terms of
        physical coordinates, the rotator will still track the sky. The
        rotator will not be kept in a fixed position.

        """
        radec_icrs = ICRS(Angle(ra, unit=u.hourangle), Angle(dec, unit=u.deg))

        _rot, _rottype = self.handle_rottype(
            rot_sky=rot_sky, rot_par=rot_par, rot_phys_sky=rot_phys_sky
        )

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

            self.log.debug(
                f"Setting rotator position with respect to parallactic angle to {_rot}."
            )

            _rot += par_angle + 2 * alt_az.alt - 90.0

            self.log.debug(
                f"Parallactic angle: {par_angle.deg} | " f"Sky Angle: {_rot.deg}"
            )
        else:
            valid_rottypes = [f"{rt!r}" for rt in RotType].__str__()
            raise RuntimeError(
                f"Unrecognized rottype {_rottype}. Should be one of {valid_rottypes}"
            )

        await self.slew(
            radec_icrs.ra.hour,
            radec_icrs.dec.deg,
            rotPA=_rot.deg,
            target_name=target_name,
            frame=ATPtg.CoordFrame.ICRS,
            epoch=2000,
            equinox=2000,
            parallax=0,
            pmRA=0,
            pmDec=0,
            rv=0,
            dRA=0,
            dDec=0,
            rot_frame=ATPtg.RotFrame.TARGET,
            rot_mode=ATPtg.RotMode.FIELD,
            slew_timeout=slew_timeout,
            stop_before_slew=stop_before_slew,
            wait_settle=wait_settle,
        )

    async def slew(
        self,
        ra,
        dec,
        rotPA=0.0,
        target_name="slew_icrs",
        frame=ATPtg.CoordFrame.ICRS,
        epoch=2000,
        equinox=2000,
        parallax=0,
        pmRA=0,
        pmDec=0,
        rv=0,
        dRA=0,
        dDec=0,
        rot_frame=ATPtg.RotFrame.TARGET,
        rot_mode=ATPtg.RotMode.FIELD,
        slew_timeout=1200.0,
        stop_before_slew=True,
        wait_settle=True,
    ):
        """Slew the telescope and start tracking an Ra/Dec target.

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
        """
        self.rem.atptg.cmd_raDecTarget.set(
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
            self.rem.atptg.cmd_raDecTarget,
            slew_timeout=slew_timeout,
            stop_before_slew=stop_before_slew,
            wait_settle=wait_settle,
        )

    async def slew_to_planet(self, planet, rot_sky=0.0, slew_timeout=1200.0):
        """Slew and track a solar system body.

        Parameters
        ----------
        planet : `ATPtg.Planets`
            Enumeration with planet name.
        rot_sky : `float`
            Desired instrument position angle (degree), Eastwards from North.
        slew_timeout : `float`
            Timeout for the slew command (second).
        """
        self.rem.atptg.cmd_planetTarget.set(
            planetName=planet.value,
            dRA=0.0,
            dDec=0.0,
            rotPA=Angle(rot_sky, unit=u.deg).deg,
        )

        await self._slew_to(self.rem.atptg.cmd_planetTarget, slew_timeout=slew_timeout)

    async def slew_dome_to(self, az):
        """Utility method to slew dome to a specified position.

        This method works at cross purposes to ATDomeTrajectory, so this method
        disables ATDomeTrajectory and leaves it disabled. If ATDomeTrajectory
        is enabled while the dome is slewing to the requested position this
        method raises an exception.

        The method will return once the dome arrives in position, at which
        point all checks will be canceled before returning.

        Parameters
        ----------
        az : `float` or `str`
            Azimuth angle for the dome (in deg).
        """
        await salobj.set_summary_state(self.rem.atdometrajectory, salobj.State.DISABLED)

        self.rem.atdome.evt_azimuthInPosition.flush()

        target_az = Angle(az, unit=u.deg).deg
        await self.rem.atdome.cmd_moveAzimuth.set_start(
            azimuth=target_az, timeout=self.long_long_timeout
        )

        self.check.atmcs = False
        self.check.atdometrajectory = False
        self.check.atdome = True

        task_list = [
            asyncio.create_task(
                self.wait_for_inposition(timeout=self.long_long_timeout)
            ),
            asyncio.create_task(self.monitor_position()),
            asyncio.create_task(
                self.check_component_state("atdometrajectory", salobj.State.DISABLED)
            ),
        ]

        try:
            await self.process_as_completed(task_list)
        except Exception as e:
            self.check.atmcs = True
            self.check.atdometrajectory = True
            raise e

    async def prepare_for_flatfield(self):
        """A high level method to position the telescope and dome for flat
        field operations.

        The method will,

            1 - disable ATDomeTrajectory
            2 - send telescope to flat field position
            3 - send dome to flat field position
            4 - re-enable ATDomeTrajectory
        """
        await salobj.set_summary_state(self.rem.atdometrajectory, salobj.State.DISABLED)

        await self.open_m1_cover()

        atdometrajectory_check = self.check.atdometrajectory
        self.check.atdometrajectory = False

        try:
            await self.point_azel(
                target_name="FlatField position",
                az=self.tel_flat_az,
                el=self.tel_flat_el,
                wait_dome=False,
            )

            try:
                await self.stop_tracking()
            except asyncio.TimeoutError:
                self.log.debug("Timeout in stopping tracking. Continuing.")

            await self.slew_dome_to(self.dome_flat_az)
        except Exception as e:
            self.check.atdometrajectory = atdometrajectory_check
            raise e
        finally:
            await salobj.set_summary_state(
                self.rem.atdometrajectory, salobj.State.ENABLED
            )

    async def stop_tracking(self):
        """Task to stop telescope tracking."""

        self.log.debug("Stop tracking.")

        await self.rem.atptg.cmd_stopTracking.start(timeout=self.fast_timeout)

        try:
            self.rem.atmcs.evt_atMountState.flush()
            at_mount_state = await self.rem.atmcs.evt_atMountState.aget(
                timeout=self.long_timeout
            )
        except asyncio.TimeoutError:
            # TODO: DM-24529 Remove this when ATMCS sends events more reliably
            self.log.warning("Timeout waiting for atMountState event.")
        else:
            # TODO: DM-24525 remove hard coded 8 when real ATMCS is fixed.
            while at_mount_state.state not in (8, ATMCS.AtMountState.TRACKINGDISABLED):
                self.log.debug(
                    f"Tracking state: {ATMCS.AtMountState(at_mount_state.state)!r}."
                )
                at_mount_state = await self.rem.atmcs.evt_atMountState.next(
                    flush=False, timeout=self.long_timeout
                )

        try:
            self.rem.atmcs.evt_allAxesInPosition.flush()
            in_position = await self.rem.atmcs.evt_allAxesInPosition.aget(
                timeout=self.fast_timeout
            )
        except asyncio.TimeoutError:
            # TODO: DM-24529 Remove this when ATMCS sends events more reliably
            self.log.warning("Timeout waiting for allAxesInPosition event.")
        else:
            while in_position.inPosition:
                self.log.debug(f"In Position: {in_position.inPosition}.")
                in_position = await self.rem.atmcs.evt_allAxesInPosition.next(
                    flush=False, timeout=self.long_timeout
                )

    async def stop_all(self):
        """Stop telescope and dome."""

        stop_tasks = [
            self.rem.atdometrajectory.cmd_disable.start(timeout=self.fast_timeout),
            self.rem.atptg.cmd_stopTracking.start(timeout=self.fast_timeout),
            self.rem.atdome.cmd_stopMotion.start(timeout=self.fast_timeout),
            self.rem.atmcs.cmd_stopTracking.start(timeout=self.fast_timeout),
        ]

        stop_results = await asyncio.gather(*stop_tasks, return_exceptions=True)

        return stop_results

    async def check_tracking(self, track_duration=None):
        """Check tracking state.

        This method monitors all the required parameters for tracking a target;
        from telescope and pointing component to the dome.

        If any of those conditions fails, raise an exception.

        This method is useful in case an operation required tracking to be
        active and be interrupted in case tracking stops. One can start
        this method concurrently and monitor it for any exception. If an
        exception is raise, the concurrent task can be interrupted or marked
        as failed as appropriately.

        If a `track_duration` is specified, the method will return after the
        time has passed. Otherwise it will just check forever.

        Parameters
        ----------
        track_duration : `float` or `None`
            How long should tracking be checked for (second)? Must be a
            positive `float` or `None` (default).

        Returns
        -------
        done : `bool`
            True if tracking was successful.

        Raises
        ------
        RuntimeError

            If any of the conditions required for tracking is not met.
        """
        # TODO: Finish implementation of this method (DM-24488).

        task_list = []

        if track_duration is not None and track_duration > 0.0:
            task_list.append(asyncio.ensure_future(asyncio.sleep(track_duration)))

        for cmp in self.components:
            if getattr(self.check, cmp):
                self.log.debug(f"Adding {cmp} to check list")
                task_list.append(asyncio.ensure_future(self.check_component_state(cmp)))
                task_list.append(asyncio.ensure_future(self.check_comp_heartbeat(cmp)))
            else:
                self.log.debug(f"Skipping {cmp}")

        await self.process_as_completed(task_list)

    async def prepare_for_onsky(self, settings=None):
        """Prepare Auxiliary Telescope for on-sky operations.

        This method will perform the start of the night procedure for the
        ATCS component. It will enable all components, open the dome slit,
        open the telescope covers and activate AOS open loop corrections.

        Parameters
        ----------
        settings: `dict`
            Dictionary with settings to apply.  If `None` use the recommended
            settings.
        """

        await self.enable(settings=settings)

        self.log.debug("Slew telescope to park position.")
        self.check.atdometrajectory = False
        atdome_check = self.check.atdome
        await self.point_azel(
            target_name="Park position",
            az=self.tel_park_az,
            el=self.tel_park_el,
            wait_dome=False,
        )
        self.check.atdome = atdome_check

        try:
            await self.stop_tracking()
        except asyncio.TimeoutError:
            pass

        # Close m1 cover if it is open.
        await self.close_m1_cover()

        if self.check.atdome:

            self.log.debug("Homing dome azimuth.")

            await self.home_dome()

            self.log.debug("Moving dome to 90 degrees.")
            await self.slew_dome_to(az=90.0)

            self.log.info(
                "Check that dome CSC can communicate with shutter control box."
            )

            try:
                scb = await self.rem.atdome.evt_scbLink.aget(timeout=self.fast_timeout)
            except asyncio.TimeoutError:
                self.log.error(
                    "Timed out waiting for ATDome CSC scbLink status event. Can not "
                    "determine if CSC has communication with Shutter Control Box."
                    "If running this on a jupyter notebook you may try to add an"
                    "await asyncio.sleep(1.) before calling startup again to give the"
                    "remotes time to get information from DDS. You may also try to "
                    "re-cycle the ATDome CSC state to STANDBY and back to ENABLE."
                    "Cannot continue."
                )
                raise

            if not scb.active:
                raise RuntimeError(
                    "Dome CSC has no communication with Shutter Control Box. "
                    "Dome controllers may need to be rebooted for connection to "
                    "be established. Cannot continue."
                )

            self.log.info("Opening dome.")

            await self.open_dome_shutter()

        if self.check.atpneumatics:
            self.log.info("Open telescope cover.")
            await self.open_m1_cover()
            await self.open_m1_vent()

        await self.enable(settings=settings)

        if self.check.ataos:
            self.log.info("Enable ATAOS corrections.")

            await self.rem.ataos.cmd_enableCorrection.set_start(
                m1=True, hexapod=True, timeout=self.long_timeout
            )

    async def shutdown(self):
        """Shutdown ATTCS components.

        This method will perform the end of the night procedure for the
        ATTCS component. It will close the telescope cover, close the dome,
        move the telescope and dome to the park position and disable all
        components.
        """
        self.log.info("Disabling ATAOS corrections")

        try:

            await self.rem.ataos.cmd_disableCorrection.set_start(
                disableAll=True, timeout=self.long_timeout
            )
        except Exception as e:
            self.log.warning("Failed to disable ATAOS corrections. Continuing...")
            self.log.exception(e)

        self.log.info("Disable ATDomeTrajectory")

        await salobj.set_summary_state(self.rem.atdometrajectory, salobj.State.DISABLED)

        self.log.debug("Slew telescope to Park position.")

        try:
            self.check.atdometrajectory = False
            await self.point_azel(
                target_name="Park position",
                az=self.tel_park_az,
                el=self.tel_park_el,
                wait_dome=False,
            )
            await self.stop_tracking()
        except Exception as e:
            self.log.warning("Failed to slew telescope to park position. Continuing...")
            self.log.exception(e)
        finally:
            self.check.atdometrajectory = True

        await self.close_m1_cover()

        try:
            await self.close_m1_vent()
        except Exception:
            self.log.info("Error closing m1 vents.")

        self.log.info("Close dome.")

        await self.close_dome()

        self.log.debug("Slew dome to Park position.")
        await self.slew_dome_to(az=self.dome_park_az)

        self.log.info("Put all CSCs in standby")

        await self.standby()

    async def open_dome_shutter(self):
        """Task to open dome shutter and return when it is done.
        """

        self.rem.atdome.evt_shutterInPosition.flush()

        await self.rem.atdome.cmd_moveShutterMainDoor.set_start(
            open=True, timeout=self.open_dome_shutter_time
        )

        self.rem.atdome.evt_summaryState.flush()
        # TODO: (2019/12) ATDome should now be returning the command only when
        # the dome is fully open. I'll keep this here for now for backward
        # compatibility but we should remove this later, after verifying it
        # is working DM-24490.
        task_list = [
            asyncio.ensure_future(self.check_component_state("atdome")),
            asyncio.ensure_future(self.wait_for_atdome_shutter_inposition()),
        ]

        await self.process_as_completed(task_list)

    async def home_dome(self):
        """ Task to execute dome home command and wait for it to complete.
        """

        self.rem.atdome.evt_azimuthState.flush()

        await self.rem.atdome.cmd_homeAzimuth.start()

        await asyncio.sleep(self.fast_timeout)  # Give the dome time to start moving

        az_state = await self.rem.atdome.evt_azimuthState.next(
            flush=False, timeout=self.open_dome_shutter_time
        )
        while az_state.homing:
            self.log.info("Dome azimuth still homing.")
            az_state = await self.rem.atdome.evt_azimuthState.next(
                flush=False, timeout=self.open_dome_shutter_time
            )

    async def close_dome(self):
        """Task to close ATDome.
        """
        shutter_pos = await self.rem.atdome.evt_mainDoorState.aget(
            timeout=self.fast_timeout
        )

        if shutter_pos.state == ATDome.ShutterDoorState.OPENED:

            self.rem.atdome.evt_shutterInPosition.flush()

            await self.rem.atdome.cmd_closeShutter.set_start(
                timeout=self.open_dome_shutter_time
            )

            self.rem.atdome.evt_summaryState.flush()
            task_list = [
                asyncio.create_task(self.check_component_state("atdome")),
                asyncio.create_task(self.wait_for_atdome_shutter_inposition()),
            ]

            await self.process_as_completed(task_list)

        elif shutter_pos.state == ATDome.ShutterDoorState.CLOSED:
            self.log.info("ATDome Shutter Door is already closed. Ignoring.")
        else:
            raise RuntimeError(
                f"Shutter Door state is "
                f"{ATDome.ShutterDoorState(shutter_pos.state)}. "
                f"expected either {ATDome.ShutterDoorState.OPENED} or "
                f"{ATDome.ShutterDoorState.CLOSED}"
            )

    async def open_m1_cover(self):
        """Task to open m1 cover.

        Warnings
        --------
        The Mirror cover can only be opened if the telescope is pointing
        above `self.tel_el_operate_pneumatics` (=75 degrees). The method will
        check if the telescope is in an operational range and, if not, will
        move the telescope to an operational elevation, maintaining the same
        azimuth before opening the mirror cover. The telescope will be left
        in that same position in the end.
        """

        cover_state = await self.rem.atpneumatics.evt_m1CoverState.aget(
            timeout=self.fast_timeout
        )

        self.log.debug(
            f"Cover state {ATPneumatics.MirrorCoverState(cover_state.state)!r}"
        )

        if cover_state.state == ATPneumatics.MirrorCoverState.CLOSED:

            self.log.debug("Opening M1 cover.")

            # Check that telescope is in a good elevation to open cover.
            # If not, point to current azimuth and elevation 75 degrees
            # before opening the mirror cover.
            tel_pos = await self.rem.atmcs.tel_mount_AzEl_Encoders.next(
                flush=True, timeout=self.fast_timeout
            )

            if tel_pos.elevationCalculatedAngle[-1] < self.tel_el_operate_pneumatics:
                await self.point_azel(
                    az=tel_pos.azimuthCalculatedAngle[-1],
                    el=self.tel_el_operate_pneumatics,
                    wait_dome=False,
                )

            await self.rem.atpneumatics.cmd_openM1Cover.start(timeout=self.long_timeout)

            while cover_state.state != ATPneumatics.MirrorCoverState.OPENED:
                cover_state = await self.rem.atpneumatics.evt_m1CoverState.next(
                    flush=False, timeout=self.long_long_timeout
                )
                self.log.debug(
                    f"Cover state {ATPneumatics.MirrorCoverState(cover_state.state)!r}"
                )
                if cover_state.state == ATPneumatics.MirrorCoverState.FAULT:
                    raise RuntimeError(
                        f"Open cover failed. Cover state "
                        f"{ATPneumatics.MirrorCoverState(cover_state.state)!r}"
                    )
        elif cover_state.state == ATPneumatics.MirrorCoverState.OPENED:
            self.log.info(f"M1 cover already opened.")
        else:
            raise RuntimeError(
                f"M1 cover in {ATPneumatics.MirrorCoverState(cover_state.state)!r} "
                f"state. Expected {ATPneumatics.MirrorCoverState.OPENED!r} or "
                f"{ATPneumatics.MirrorCoverState.CLOSED!r}"
            )

    async def close_m1_cover(self):
        """Task to close m1 cover.

        Warnings
        --------
        The Mirror cover can only be closed if the telescope is pointing
        above `self.tel_el_operate_pneumatics` (=75 degrees). The method will
        check if the telescope is in an operational range and, if not, will
        move the telescope to an operational elevation, maintaining the same
        azimuth before closing the mirror cover. The telescope will be left
        in that same position in the end.
        """
        cover_state = await self.rem.atpneumatics.evt_m1CoverState.aget(
            timeout=self.fast_timeout
        )

        self.log.debug(
            f"Cover state {ATPneumatics.MirrorCoverState(cover_state.state)!r}"
        )

        if cover_state.state == ATPneumatics.MirrorCoverState.OPENED:

            self.log.debug("Closing M1 cover.")
            # Check that telescope is in a good elevation to close cover.
            # If not, point to current azimuth and elevation 75 degrees
            # before opening the mirror cover.
            tel_pos = await self.rem.atmcs.tel_mount_AzEl_Encoders.next(
                flush=True, timeout=self.fast_timeout
            )

            if tel_pos.elevationCalculatedAngle[-1] < self.tel_el_operate_pneumatics:
                await self.point_azel(
                    az=tel_pos.azimuthCalculatedAngle[-1],
                    el=self.tel_el_operate_pneumatics,
                    wait_dome=False,
                )

            await self.rem.atpneumatics.cmd_closeM1Cover.start(
                timeout=self.long_timeout
            )

            while cover_state.state != ATPneumatics.MirrorCoverState.CLOSED:
                cover_state = await self.rem.atpneumatics.evt_m1CoverState.next(
                    flush=False, timeout=self.long_long_timeout
                )
                self.log.debug(
                    f"Cover state {ATPneumatics.MirrorCoverState(cover_state.state)!r}"
                )

                if cover_state.state == ATPneumatics.MirrorCoverState.FAULT:
                    raise RuntimeError(
                        f"Open cover failed. Cover state "
                        f"{ATPneumatics.MirrorCoverState(cover_state.state)!r}"
                    )

        elif cover_state.state == ATPneumatics.MirrorCoverState.CLOSED:
            self.log.info(f"M1 cover already closed.")
        else:
            raise RuntimeError(
                f"M1 cover in {ATPneumatics.MirrorCoverState(cover_state.state)!r} "
                f"state. Expected {ATPneumatics.MirrorCoverState.OPENED!r} or "
                f"{ATPneumatics.MirrorCoverState.CLOSED!r}"
            )

    async def open_m1_vent(self):
        """Task to open m1 vents.
        """

        vent_state = await self.rem.atpneumatics.evt_m1VentsPosition.aget(
            timeout=self.fast_timeout
        )

        self.log.debug(
            f"M1 vent state {ATPneumatics.VentsPosition(vent_state.position)!r}"
        )

        if vent_state.position == ATPneumatics.VentsPosition.CLOSED:

            self.log.debug("Opening M1 vents.")

            try:
                await self.rem.atpneumatics.cmd_openM1CellVents.start(
                    timeout=self.long_timeout
                )
            except Exception:
                return

            vent_state = await self.rem.atpneumatics.evt_m1VentsPosition.aget()
            self.rem.atpneumatics.evt_m1VentsPosition.flush()
            while vent_state.position != ATPneumatics.VentsPosition.OPENED:
                vent_state = await self.rem.atpneumatics.evt_m1VentsPosition.next(
                    flush=False, timeout=self.long_long_timeout
                )
                self.log.debug(
                    f"M1 vent state {ATPneumatics.VentsPosition(vent_state.position)!r}"
                )
        elif vent_state.position == ATPneumatics.VentsPosition.OPENED:
            self.log.info(f"M1 vents already opened.")
        else:
            raise RuntimeError(
                f"Unrecognized M1 vent position: {vent_state.position!r}"
            )

    async def close_m1_vent(self):
        """Task to open m1 vents.
        """

        vent_state = await self.rem.atpneumatics.evt_m1VentsPosition.aget(
            timeout=self.fast_timeout
        )

        self.log.debug(
            f"M1 vent state {ATPneumatics.VentsPosition(vent_state.position)!r}"
        )

        if vent_state.position == ATPneumatics.VentsPosition.OPENED:

            self.log.debug("Closing M1 vents.")

            try:
                await self.rem.atpneumatics.cmd_closeM1CellVents.start(
                    timeout=self.long_timeout
                )
            except Exception:
                return

            vent_state = await self.rem.atpneumatics.evt_m1VentsPosition.next(
                flush=False, timeout=self.long_long_timeout
            )

            while vent_state.position != ATPneumatics.VentsPosition.CLOSED:
                vent_state = await self.rem.atpneumatics.evt_m1VentsPosition.next(
                    flush=True, timeout=self.long_long_timeout
                )
                self.log.debug(
                    f"M1 vent state {ATPneumatics.VentsPosition(vent_state.position)!r}"
                )
        elif vent_state.position == ATPneumatics.VentsPosition.CLOSED:
            self.log.info(f"M1 vents already closed.")
        else:
            raise RuntimeError(
                f"Unrecognized M1 vent position: {vent_state.position!r}"
            )

    async def _slew_to(
        self, slew_cmd, slew_timeout, stop_before_slew=True, wait_settle=True
    ):
        """Encapsulate "slew" activities.

        Parameters
        ----------
        slew_cmd : `coro`
            One of the slew commands from the atptg remote. Command need to be
            setup before calling this method.
        """

        self.log.debug("Sending command")

        if stop_before_slew:
            try:
                await self.stop_tracking()
            except Exception:
                pass
        else:
            self.rem.atmcs.evt_allAxesInPosition.flush()

        track_id = next(self.track_id_gen)

        try:
            current_target = await self.rem.atmcs.evt_target.next(
                flush=True, timeout=self.fast_timeout
            )
            if track_id <= current_target.trackId:
                self.track_id_gen = salobj.index_generator(current_target.trackId + 1)
                track_id = next(self.track_id_gen)

        except asyncio.TimeoutError:
            pass

        slew_cmd.set(trackId=track_id)

        ack = await slew_cmd.start(timeout=slew_timeout)
        self.dome_az_in_position.clear()

        self.log.debug("Scheduling check coroutines")

        self.scheduled_coro.append(
            asyncio.ensure_future(
                self.wait_for_inposition(timeout=slew_timeout, wait_settle=wait_settle)
            )
        )
        self.scheduled_coro.append(asyncio.ensure_future(self.monitor_position(ack)))

        for comp in self.components:
            if getattr(self.check, comp):
                getattr(self.rem, comp).evt_summaryState.flush()
                self.scheduled_coro.append(
                    asyncio.ensure_future(self.check_component_state(comp))
                )

        await self.process_as_completed(self.scheduled_coro)

    async def offset_azel(self, az, el, relative=False):
        """ Offset telescope in azimuth and elevation.

        Parameters
        ----------
        az : `float`
            Offset in azimuth (arcsec).
        el : `float`
            Offset in elevation (arcsec).
        relative : `bool`
            If `True` offset is applied relative to the current position, if
            `False` (default) offset replaces any existing offsets.
        """
        self.log.debug(f"Applying Az/El offset: {az}/ {el} ")
        self.rem.atmcs.evt_allAxesInPosition.flush()
        await self.rem.atptg.cmd_offsetAzEl.set_start(
            az=az, el=el, num=0 if not relative else 1
        )
        try:
            await self.rem.atmcs.evt_allAxesInPosition.next(
                flush=True, timeout=self.tel_settle_time
            )
        except asyncio.TimeoutError:
            pass
        self.log.debug("Waiting for telescope to settle.")
        await asyncio.sleep(self.tel_settle_time)
        self.log.debug("Done")

    async def offset_radec(self, ra, dec):
        """ Offset telescope in RA and Dec.

        Perform arc-length offset in sky coordinates. The magnitude of the
        offset is sqrt(ra^2 + dec^2) and the angle is the usual atan2(dec, ra).

        Parameters
        ----------
        ra : `float`
            Offset in ra (arcsec).
        dec : `float` or `str`
            Offset in dec (arcsec).

        """
        self.log.debug(f"Applying RA/Dec offset: {ra}/ {dec} ")
        await self.rem.atptg.cmd_offsetRADec.set_start(type=0, off1=ra, off2=dec, num=0)
        self.log.debug("Waiting for telescope to settle.")
        await asyncio.sleep(self.tel_settle_time)
        self.log.debug("Done")

    async def offset_xy(self, x, y, relative=False):
        """ Offset telescope in x and y.

        Parameters
        ----------
        x : `float`
            Offset in camera x-axis (arcsec).
        y : `float`
            Offset in camera y-axis (arcsec).
        relative : `bool`
            If `True` offset is applied relative to the current position, if
            `False` (default) offset replaces any existing offsets.
        """

        self.log.debug(f"Applying x/y offset: {x}/ {y} ")
        azel = await self.rem.atmcs.tel_mount_AzEl_Encoders.aget()
        nasmyth = await self.rem.atmcs.tel_mount_Nasmyth_Encoders.aget()
        angle = (
            np.mean(azel.elevationCalculatedAngle)
            - np.mean(nasmyth.nasmyth2CalculatedAngle)
            + 90.0
        )
        el, az, _ = np.matmul([x, y, 0.0], self.rotation_matrix(angle))

        await self.offset_azel(az, el, relative)

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

        if self.check.atmcs:
            status.append(
                await self.wait_for_atmcs_inposition(timeout, cmd_ack, wait_settle)
            )

        if self.check.atdome:
            status.append(await self.wait_for_atdome_inposition(timeout, cmd_ack))

        return f"{status!r}"

    async def wait_for_atmcs_inposition(self, timeout, cmd_ack=None, wait_settle=True):
        """Wait for inPosition of atmcs to be ready.

        Parameters
        ----------
        timeout: `float`
            How long should it wait before timing out.

        Returns
        -------
        status: `str`
            String with final status.

        Raises
        ------
        asyncio.TimeoutError
            If does not get a status update in less then `timeout` seconds.
        """
        while True:

            in_position = await self.rem.atmcs.evt_allAxesInPosition.next(
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
                    if wait_settle:
                        self.log.info("Waiting for telescope to settle.")
                        await asyncio.sleep(self.tel_settle_time)
                    self.log.info(f"Telescope in position.")
                    return f"Telescope in position."
                else:
                    self.log.debug(f"Telescope not in position")

    async def wait_for_atdome_inposition(self, timeout, cmd_ack=None):
        """Wait for inPosition of atdome to be ready.

        Parameters
        ----------
        timeout: `float`
            How long should it wait before timing out.

        Returns
        -------
        status: `str`
            String with final status.

        Raises
        ------
        asyncio.TimeoutError
            If does not get a status update in less then `timeout` seconds.
        """
        # FIXME: ATDome in position event is not working properly.
        # I will deactivate this method and rely on monitor_position for the
        # job
        await self.dome_az_in_position.wait()
        self.log.info(f"ATDome in position.")
        return f"ATDome in position."

    async def wait_for_atdome_shutter_inposition(self):
        """Wait for the atdome shutter to be in position.

        Returns
        -------
        status: `str`
            String with final status.

        Raises
        ------
        asyncio.TimeoutError
            If does not get in position before `self.open_dome_shutter_time`
        """
        timeout = self.open_dome_shutter_time

        while True:

            in_position = await self.rem.atdome.evt_shutterInPosition.next(
                flush=False, timeout=timeout
            )

            self.log.debug(f"Got: {in_position}")

            if in_position.inPosition:
                self.log.info("ATDome shutter in position.")
                return "ATDome shutter in position."
            else:
                self.log.debug("ATDome shutter not in position.")

    async def monitor_position(self, check_atmcs=None, check_atdome=None):
        """Monitor and log the position of the telescope and the dome.
        """
        # Wait for target events to be published before entering the loop.

        atmcs = self.check.atmcs if check_atmcs is None else check_atmcs
        atdome = self.check.atdome if check_atdome is None else check_atdome

        if atmcs:
            try:
                await self.rem.atmcs.evt_target.next(
                    flush=True, timeout=self.long_timeout
                )
            except asyncio.TimeoutError:
                raise RuntimeError(
                    "Not receiving target events from the ATMCS. "
                    "Check component for errors."
                )

        in_position = False

        while not in_position:
            if atmcs:
                comm_pos = await self.rem.atmcs.evt_target.next(
                    flush=True, timeout=self.fast_timeout
                )
                tel_pos = await self.rem.atmcs.tel_mount_AzEl_Encoders.next(
                    flush=True, timeout=self.fast_timeout
                )
                nasm_pos = await self.rem.atmcs.tel_mount_Nasmyth_Encoders.next(
                    flush=True, timeout=self.fast_timeout
                )

                alt_dif = subtract_angles(
                    comm_pos.elevation, tel_pos.elevationCalculatedAngle[-1]
                )
                az_dif = subtract_angles(
                    comm_pos.azimuth, tel_pos.azimuthCalculatedAngle[-1]
                )
                nasm1_dif = subtract_angles(
                    comm_pos.nasmyth1RotatorAngle, nasm_pos.nasmyth1CalculatedAngle[-1]
                )
                nasm2_dif = subtract_angles(
                    comm_pos.nasmyth2RotatorAngle, nasm_pos.nasmyth2CalculatedAngle[-1]
                )
                alt_in_position = (
                    Angle(np.abs(alt_dif) * u.deg) < self.tel_el_slew_tolerance
                )
                az_in_position = (
                    Angle(np.abs(az_dif) * u.deg) < self.tel_az_slew_tolerance
                )
                na1_in_position = (
                    Angle(np.abs(nasm1_dif) * u.deg) < self.tel_nasm_slew_tolerance
                )
                na2_in_position = (
                    Angle(np.abs(nasm2_dif) * u.deg) < self.tel_nasm_slew_tolerance
                )

            if atdome:
                dom_pos = await self.rem.atdome.tel_position.next(
                    flush=True, timeout=self.fast_timeout
                )
                dom_comm_pos = await self.rem.atdome.evt_azimuthCommandedState.aget(
                    timeout=self.fast_timeout
                )

                dom_az_dif = subtract_angles(
                    dom_comm_pos.azimuth, dom_pos.azimuthPosition
                )

                dom_in_position = (
                    Angle(np.abs(dom_az_dif) * u.deg) < self.dome_slew_tolerance
                )
                if dom_in_position:
                    self.dome_az_in_position.set()

            if atmcs and atdome:
                self.log.info(
                    f"[Telescope] delta Alt = {alt_dif:+08.3f}; delta Az = {az_dif:+08.3f}; "
                    f"delta N1 = {nasm1_dif:+08.3f}; delta N2 = {nasm2_dif:+08.3f} "
                    f"[Dome] delta Az = {dom_az_dif:+08.3f}"
                )
                in_position = (
                    alt_in_position
                    and az_in_position
                    and na1_in_position
                    and na2_in_position
                    and dom_in_position
                )
            elif atdome:
                self.log.info(f"[Dome] delta Az = {dom_az_dif:+08.3f}")
                in_position = dom_in_position
            elif atmcs:
                self.log.info(
                    f"[Telescope] delta Alt = {alt_dif:+08.3f}; delta Az= {az_dif:+08.3f}; "
                    f"delta N1 = {nasm1_dif:+08.3f}; delta N2 = {nasm2_dif:+08.3f} "
                )
                in_position = (
                    alt_in_position
                    and az_in_position
                    and na1_in_position
                    and na2_in_position
                )
            else:
                break

            await asyncio.sleep(1.0)

        if in_position:
            self.log.debug("Axes in position.")
        else:
            self.log.warning("Nothing to check.")

    async def check_target_status(self):
        """Check the targeting status of the atmcs.
        """
        while True:
            in_position = await self.rem.atmcs.evt_allAxesInPosition.next(flush=False)
            self.log.debug(f"Got {in_position.inPosition}")
            if in_position.inPosition is False:
                raise RuntimeError(f"ATMCS is no longer tracking.")

    async def focus_offset(self, offset):
        """ Apply focus offset.

        Returns after offset is aplied.

        Parameters
        ----------
        offset : float
            Offset in mm.

        """
        self.rem.athexapod.evt_positionUpdate.flush()
        await self.rem.ataos.cmd_applyFocusOffset.set_start(offset=offset)

        # TODO: Remove when DM-24491 is implemented.
        try:
            await self.rem.athexapod.evt_positionUpdate.next(
                flush=False, timeout=self.long_timeout
            )
        except asyncio.TimeoutError:
            self.log.warning("Did not received position update from ATHexapod.")
            pass

    async def add_point_data(self):
        """ Add current position to a point file. If a file is open it will
        append to that file. If no file is opened it will open a new one.

        """

        state = await self.get_state("atptg")
        if state != salobj.State.ENABLED:
            raise RuntimeError(
                f"ATPtg in {state!r}. Expected {salobj.State.ENABLED!r}."
            )

        # TODO: DM-24526 Check event to see if point file is opened.
        try:
            await self.rem.atptg.cmd_pointAddData.start()
        except salobj.AckError:
            self.log.debug("Opening new pointing file.")
            await self.rem.atptg.cmd_pointNewFile.start()
            await self.rem.atptg.cmd_pointAddData.start()

    @staticmethod
    def handle_rottype(rot_sky=0.0, rot_par=None, rot_phys_sky=None):
        """Handle different kinds of rotation strategies.

        From the given input the method will return an angle to be used
        (converted to `astropy.coordinates.Angle`) and a rotator positioning
        strategy; sky, parallactic or physical (see `RotType` for an
        explanation).

        Parameters
        ----------
        rot_sky : `float`, `str` or `astropy.coordinates.Angle`
            Has the same behavior of `rottype=RotType.Sky`.
        rot_par :  `float`, `str` or `astropy.coordinates.Angle`
            Has the same behavior of `rottype=RotType.Parallactic`.
        rot_phys_sky : `float`, `str` or `astropy.coordinates.Angle`
            Has the same behavior of `rottype=RotType.Physical_Sky`.

        Returns
        -------
        rotang: `astropy.coordinates.Angle`
            Selected rotation angle.
        rottype: `RotSky`
            Selected rotation type.

        Raises
        ------
        RuntimeError: If both `rot_par` and `rot_tel` are specified.

        """
        if rot_par is not None and rot_phys_sky is not None:
            raise RuntimeError(
                f"Cannot specify both `rot_par` and `rot_tel`. Got: rot_par={rot_par}, "
                f"rot_tel={rot_phys_sky}."
            )
        elif rot_par is not None:
            return Angle(rot_par, unit=u.deg), RotType.Parallactic
        elif rot_phys_sky is not None:
            return Angle(rot_phys_sky, unit=u.deg), RotType.Physical_Sky
        else:
            return Angle(rot_sky, unit=u.deg), RotType.Sky

    @property
    def valid_use_cases(self):
        """Returns valid usages.

        When subclassing, overwrite this method to return the proper enum.

        Returns
        -------
        usages: enum

        """
        return ATCSUsages()

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
                "moveAzimuth",
                "stopTracking",
                "stopMotion",
                "enableCorrection",
                "disableCorrection",
                "moveShutterMainDoor",
                "homeAzimuth",
                "closeShutter",
                "openM1Cover",
                "closeM1Cover",
                "openM1CellVents",
                "closeM1CellVents",
                "offsetAzEl",
                "offsetRADec",
                "summaryState",
                "settingVersions",
                "heartbeat",
                "applyFocusOffset",
                "pointAddData",
                "pointNewFile",
                "pointAddData",
                "allAxesInPosition",
                "atMountState",
                "azimuthCommandedState",
                "azimuthInPosition",
                "azimuthState",
                "m1CoverState",
                "m1VentsPosition",
                "mainDoorState",
                "positionUpdate",
                "scbLink",
                "target",
                "mount_AzEl_Encoders",
                "position",
                "mount_Nasmyth_Encoders",
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
                "stopMotion",
                "offsetAzEl",
                "offsetRADec",
                "applyFocusOffset",
                "pointAddData",
                "pointNewFile",
                "pointAddData",
                "allAxesInPosition",
                "atMountState",
                "azimuthCommandedState",
                "azimuthInPosition",
                "azimuthState",
                "positionUpdate",
                "shutterInPosition",
                "summaryState",
                "settingVersions",
                "heartbeat",
                "target",
                "mount_AzEl_Encoders",
                "position",
                "mount_Nasmyth_Encoders",
                "timeAndDate",
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
                "moveAzimuth",
                "stopTracking",
                "stopMotion",
                "enableCorrection",
                "moveShutterMainDoor",
                "homeAzimuth",
                "openM1Cover",
                "closeM1Cover",
                "openM1CellVents",
                "allAxesInPosition",
                "atMountState",
                "azimuthCommandedState",
                "azimuthInPosition",
                "azimuthState",
                "m1CoverState",
                "m1VentsPosition",
                "mainDoorState",
                "positionUpdate",
                "shutterInPosition",
                "scbLink",
                "summaryState",
                "settingVersions",
                "heartbeat",
                "target",
                "mount_AzEl_Encoders",
                "position",
                "mount_Nasmyth_Encoders",
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
                "moveAzimuth",
                "stopTracking",
                "stopMotion",
                "disableCorrection",
                "moveShutterMainDoor",
                "closeShutter",
                "closeM1Cover",
                "closeM1CellVents",
                "allAxesInPosition",
                "atMountState",
                "azimuthCommandedState",
                "azimuthInPosition",
                "azimuthState",
                "m1CoverState",
                "m1VentsPosition",
                "mainDoorState",
                "positionUpdate",
                "scbLink",
                "summaryState",
                "settingVersions",
                "heartbeat",
                "target",
                "mount_AzEl_Encoders",
                "position",
                "mount_Nasmyth_Encoders",
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
                "azElTarget",
                "moveAzimuth",
                "stopTracking",
                "stopMotion",
                "homeAzimuth",
                "openM1Cover",
                "openM1CellVents",
                "allAxesInPosition",
                "atMountState",
                "azimuthCommandedState",
                "azimuthInPosition",
                "azimuthState",
                "m1CoverState",
                "m1VentsPosition",
                "positionUpdate",
                "summaryState",
                "settingVersions",
                "heartbeat",
                "target",
                "mount_AzEl_Encoders",
                "position",
                "mount_Nasmyth_Encoders",
            ],
        )

        return usages

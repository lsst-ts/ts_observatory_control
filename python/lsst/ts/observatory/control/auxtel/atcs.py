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

__all__ = ["VentsPosition", "ATCS"]

import enum
import asyncio
import warnings

import numpy as np
import astropy.units as u
from astropy.time import Time
from astropy.coordinates import AltAz, ICRS, EarthLocation, Angle
from astroquery.simbad import Simbad

from ..base_group import BaseGroup
from ..utils import subtract_angles

from lsst.ts import salobj
from lsst.ts.idl.enums import ATPtg, ATDome, ATPneumatics, ATMCS


# FIXME: Use from idl.enums.ATPneumatics
class VentsPosition(enum.IntEnum):
    OPENED = 0
    CLOSED = 1
    PARTIALLYOPENED = 2


class ATCS(BaseGroup):
    """High level library for the Auxiliary Telescope Control System

    This is the high level interface for interacting with the CSCs that
    control the Auxiliary Telescope. Essentially this will allow the user to
    slew and track the telescope.

    Parameters
    ----------
    domain: `salobj.Domain`
        Domain to use of the Remotes. If `None`, create a new domain.

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

    def __init__(self, domain=None, log=None):

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

        # FIXME: Use enumeration. But enumeration is wrong
        self.instrument_port = 1

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
        rot_pa=0.0,
        target_name="azel_target",
        wait_dome=False,
        slew_timeout=1200.0,
    ):
        """Slew the telescope to a fixed alt/az position.

        Telescope will not track once it arrives in position.

        Parameters
        ----------
        az : `float` or `str`
            Target Azimuth (degree).
        el : `float` or `str`
            Target Elevation (degree).
        rot_pa : `float` or `str`
            Target rotator position angle (degree).
        target_name : `str`
            Name of the target.
        wait_dome : `bool`
            Wait for dome to be in sync with the telescope? If preparing to
            take a flat, for instance, the dome will never be in sync.
        slew_timeout : `float`
            Timeout for the slew command (second).
        """
        self.atptg.cmd_azElTarget.set(
            targetName=target_name,
            azDegs=Angle(az, unit=u.deg).deg,
            elDegs=Angle(el, unit=u.deg).deg,
            rotPA=Angle(rot_pa, unit=u.deg).deg,
        )
        check_atdome = self.check.atdome
        self.check.atdome = wait_dome
        check_atdometrajectory = self.check.atdometrajectory
        self.check.atdometrajectory = wait_dome

        try:
            await self._slew_to(self.atptg.cmd_azElTarget, slew_timeout=slew_timeout)
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
        self, name, rot_sky=None, pa_ang=None, rot_pa=0.0, slew_timeout=240.0
    ):
        """Slew to an object name.

        Use simbad to resolve the name and get coordinates.

        Parameters
        ----------
        name : `str`
            Target name.
        rot_sky : `float` or `str`
            Target sky position angle (deg). Default is `None`, which means
            use `rot_pa`.
        pa_ang :  `float` or `str`
            Set rotator so that the reference position is the parallactic
            angle. Meaning, if pa_ang=0. the rot_sky is set so that y-axis
            is aligned with the parallactic angle.
        rot_pa : `float` or `str`
            Target rotator position angle (deg). Ignored if `rot_sky` is
            given (Default = 0).
        slew_timeout : `float`
            Timeout for the slew command (second).

        """

        object_table = Simbad.query_object(name)

        if object_table is None:
            raise RuntimeError(f"Could not find {name} in Simbad database.")
        elif len(object_table) > 1:
            self.log.warning(f"Found more than one entry for {name}. Using first one.")

        self.log.info(
            f"Slewing to {name}: {object_table['RA'][0]} {object_table['DEC'][0]}"
        )

        # radec_icrs = ICRS(Angle(object_table['RA'][0], unit=u.hour),
        #                   Angle(object_table['DEC'][0], unit=u.deg))

        await self.slew_icrs(
            ra=object_table["RA"][0],
            dec=object_table["DEC"][0],
            rot_sky=rot_sky,
            pa_ang=pa_ang,
            rot_pa=rot_pa,
            target_name=name,
            slew_timeout=slew_timeout,
        )

    async def slew_icrs(
        self,
        ra,
        dec,
        rot_sky=None,
        pa_ang=None,
        rot_pa=0.0,
        target_name="slew_icrs",
        slew_timeout=240.0,
        stop_before_slew=True,
        wait_settle=True,
    ):
        """Slew the telescope and start tracking an Ra/Dec target in ICRS
        coordinate frame.

        Parameters
        ----------
        ra : `float` or `str`
            Target RA (hour).
        dec : `float` or `str`
            Target Dec (deg).
        rot_sky : `float` or `str`
            Target sky position angle (deg). Default is `None`, which means
            use `rot_pa`.
        pa_ang :  `float` or `str`
            Set rotator so that the reference position is the parallactic
            angle. Meaning, if pa_ang=0. the rot_sky is set so that y-axis
            is aligned with the parallactic angle.
        rot_pa : `float` or `str`
            Target rotator position angle (deg). Ignored if `rot_sky` is
            given (Default = 0).
        target_name :  `str`
            Target name.
        slew_timeout : `float`
            Timeout for the slew command (second).
        stop_before_slew : bool
            Stop tracking before starting the slew? This option is a
            workaround to some issues with the ATMCS not sending events
            reliably.

        """
        radec_icrs = ICRS(Angle(ra, unit=u.hour), Angle(dec, unit=u.deg))

        rot = rot_sky

        if rot is None and pa_ang is None:
            time_data = await self.atptg.tel_timeAndDate.next(
                flush=True, timeout=self.fast_timeout
            )

            curr_time_atptg = Time(time_data.tai, format="mjd", scale="tai")

            par_angle = parallactic_angle(
                self.location, Angle(time_data.lst, unit=u.hour), radec_icrs
            )

            coord_frame_altaz = AltAz(location=self.location, obstime=curr_time_atptg)

            alt_az = radec_icrs.transform_to(coord_frame_altaz)

            rot = par_angle.deg + Angle(rot_pa, unit=u.deg).deg + alt_az.alt.deg

            self.log.debug(
                f"Parallactic angle: {par_angle.deg} | "
                f"Sky Angle: {Angle(rot, unit=u.deg).deg}"
            )
        elif rot is None:
            time_data = await self.atptg.tel_timeAndDate.next(
                flush=True, timeout=self.fast_timeout
            )

            curr_time_atptg = Time(time_data.tai, format="mjd", scale="tai")

            par_angle = parallactic_angle(
                self.location, Angle(time_data.lst, unit=u.hour), radec_icrs
            )

            coord_frame_altaz = AltAz(location=self.location, obstime=curr_time_atptg)

            alt_az = radec_icrs.transform_to(coord_frame_altaz)

            rot = (
                par_angle.deg
                + Angle(pa_ang, unit=u.deg).deg
                + 2 * alt_az.alt.deg
                - 90.0
            )

            self.log.debug(
                f"Parallactic angle: {par_angle.deg} | "
                f"Sky Angle: {Angle(rot, unit=u.deg).deg}"
            )

        await self.slew(
            radec_icrs.ra.hour,
            radec_icrs.dec.deg,
            rotPA=rot,
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
        target_instance=None,
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
            desired rotator position angle for slew
        target_name : str
            Name of the target
        target_instance : int
            Deprecated.
        frame : int
        epoch : float
        equinox : float
        parallax : float
        pmRA : float
        pmDec : float
        rv : float
        dRA : float
        rot_frame : int
        rot_mode : int
        slew_timeout : `float`
            Timeout for the slew command (second).
        stop_before_slew : bool
            Stop tracking before starting the slew? This option is a
            workaround to some issues with the ATMCS not sending events
            reliably.
        """
        if target_instance is not None:
            warnings.warn(
                "The parameter `target_instance` is deprecated and will be "
                "removed in future releases ot observatory control software.",
                DeprecationWarning,
            )

        self.atptg.cmd_raDecTarget.set(
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
            self.atptg.cmd_raDecTarget,
            slew_timeout=slew_timeout,
            stop_before_slew=stop_before_slew,
            wait_settle=wait_settle,
        )

    async def slew_to_planet(self, planet, rot_pa=0.0, slew_timeout=1200.0):
        """Slew and track a solar system body.

        Parameters
        ----------
        planet : `ATPtg.Planets`
            Enumeration with planet name.
        rot_pa : `float`
            Desired instrument position angle (degree), Eastwards from North.
        slew_timeout : `float`
            Timeout for the slew command (second).
        """
        self.atptg.cmd_planetTarget.set(
            planetName=planet.value, dRA=0.0, dDec=0.0, rotPA=rot_pa,
        )

        await self._slew_to(self.atptg.cmd_planetTarget, slew_timeout=slew_timeout)

    async def slew_dome_to(self, az):
        """Utility method to slew dome to a specified position.

        This method operates against ATDomeTrajectory, which means it can
        only run if ATDomeTrajectory is disabled. As such, before moving the
        dome it will set ATDomeTrajectory state to DISABLED and Fail if
        ATDomeTrajectory transitions to ENABLED. In the end, it will leave
        ATDomeTrajectory in DISABLED state, otherwise it will try to
        synchronize the dome again.

        Parameters
        ----------
        az : `float` or `str`
            Azimuth angle for the dome (in deg).
        """
        await salobj.set_summary_state(self.atdometrajectory, salobj.State.DISABLED)

        self.atdome.evt_azimuthInPosition.flush()

        target_az = Angle(az, unit=u.deg).deg
        await self.atdome.cmd_moveAzimuth.set_start(
            azimuth=target_az, timeout=self.long_long_timeout
        )

        self.check.atmcs = False
        self.check.atdometrajectory = False
        self.check.atdome = True

        coro_list = [
            asyncio.create_task(
                self.wait_for_inposition(timeout=self.long_long_timeout)
            ),
            asyncio.create_task(self.monitor_position()),
            asyncio.create_task(
                self.check_component_state("atdometrajectory", salobj.State.DISABLED)
            ),
        ]

        for res in asyncio.as_completed(coro_list):
            try:
                await res
            except Exception:
                raise
            else:
                break
            finally:
                await self.cancel_not_done(coro_list)
                self.check.atmcs = True
                self.check.atdometrajectory = True

    async def prepare_for_flatfield(self):
        """A high level method to position the telescope and dome for flat
        field operations.

        The method will,

            1 - disable ATDomeTrajectory
            2 - send telescope to flat field position
            3 - send dome to flat field position
            4 - re-enable ATDomeTrajectory
        """
        await salobj.set_summary_state(self.atdometrajectory, salobj.State.DISABLED)

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
            await salobj.set_summary_state(self.atdometrajectory, salobj.State.ENABLED)

    async def stop_tracking(self):
        """Task to stop telescope tracking."""

        self.log.debug("Stop tracking.")
        at_mount_state = await self.atmcs.evt_atMountState.aget(
            timeout=self.long_timeout
        )

        self.log.debug(f"Mount tracking state is {at_mount_state.state}")

        try:
            in_position = await self.atmcs.evt_allAxesInPosition.aget(
                timeout=self.fast_timeout
            )
        except Exception:
            in_position = None

        # FIXME: Remove hard coded 9 when real ATMCS is fixed.
        if (
            at_mount_state.state == 9
            or at_mount_state.state == ATMCS.AtMountState.TRACKINGENABLED
        ):
            self.atmcs.evt_atMountState.flush()
            self.atmcs.evt_allAxesInPosition.flush()
            await self.atptg.cmd_stopTracking.start(timeout=self.fast_timeout)

        while at_mount_state.state not in (8, ATMCS.AtMountState.TRACKINGDISABLED):
            at_mount_state = await self.atmcs.evt_atMountState.next(
                flush=False, timeout=self.long_timeout
            )
            self.log.debug(f"Tracking state: {at_mount_state.state}.")

        if in_position is not None:
            self.log.debug(f"In Position: {in_position.inPosition}.")
            while in_position.inPosition:
                in_position = await self.atmcs.evt_allAxesInPosition.next(
                    flush=False, timeout=self.long_timeout
                )
                self.log.debug(f"In Position: {in_position.inPosition}.")

    async def stop_all(self):
        """Stop telescope and dome."""

        try:
            await self.atdometrajectory.cmd_disable.start(timeout=self.fast_timeout)
        except Exception:
            pass

        stop_tasks = [
            self.atptg.cmd_stopTracking.start(timeout=self.fast_timeout),
            self.atdome.cmd_stopMotion.start(timeout=self.fast_timeout),
            self.atmcs.cmd_stopTracking.start(timeout=self.fast_timeout),
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
        # TODO: properly implement this method

        self.log.debug("Setting up callbacks")

        coro_list = []

        if track_duration is not None and track_duration > 0.0:
            coro_list.append(asyncio.ensure_future(asyncio.sleep(track_duration)))

        for cmp in self.components:
            if getattr(self.check, cmp):
                self.log.debug(f"Adding {cmp} to check list")
                coro_list.append(asyncio.ensure_future(self.check_component_state(cmp)))
                # TODO: Implement verify method
                # coro_list.append(asyncio.ensure_future(self.verify(cmp)))
                # TODO: Not all components publish heartbeats!
                # coro_list.append(asyncio.ensure_future(self.check_component_hb(cmp)))
            else:
                self.log.debug(f"Skipping {cmp}")

        for res in asyncio.as_completed(coro_list):
            try:
                await res
            except Exception:
                raise
            else:
                break
            finally:
                await self.cancel_not_done(coro_list)

    async def startup(self, settings=None):
        """Startup ATTCS components.

        This method will perform the start of the night procedure for the
        ATTCS component. It will enable all components, open the dome slit,
        and open the telescope covers.

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
                scb = await self.atdome.evt_scbLink.aget(timeout=self.fast_timeout)
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

            await self.ataos.cmd_enableCorrection.set_start(
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

            await self.ataos.cmd_disableCorrection.set_start(
                disableAll=True, timeout=self.long_timeout
            )
        except Exception as e:
            self.log.warning("Failed to disable ATAOS corrections. Continuing...")
            self.log.exception(e)

        self.log.info("Disable ATDomeTrajectory")

        await salobj.set_summary_state(self.atdometrajectory, salobj.State.DISABLED)

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

        self.atdome.evt_shutterInPosition.flush()

        await self.atdome.cmd_moveShutterMainDoor.set_start(
            open=True, timeout=self.open_dome_shutter_time
        )

        self.atdome.evt_summaryState.flush()
        # TODO: (2019/12) ATDome is now returning the command only when
        # the dome is fully open. I'll keep this here for now for backward
        # compatibility but we should remove this later.
        # TODO: Monitor self.atdome.tel_position.mainDoorOpeningPercentage
        coro_list = [
            asyncio.ensure_future(self.check_component_state("atdome")),
            asyncio.ensure_future(self.wait_for_atdome_shutter_inposition()),
        ]

        for res in asyncio.as_completed(coro_list):
            try:
                await res
            except RuntimeError as rte:
                await self.cancel_not_done(coro_list)
                raise rte
            else:
                break

    async def home_dome(self):
        """ Task to execute dome home command and wait for it to complete.
        """

        self.atdome.evt_azimuthState.flush()

        await self.atdome.cmd_homeAzimuth.start()

        await asyncio.sleep(self.fast_timeout)  # Give the dome time to start moving

        az_state = await self.atdome.evt_azimuthState.next(
            flush=False, timeout=self.open_dome_shutter_time
        )
        while az_state.homing:
            self.log.info("Dome azimuth still homing.")
            az_state = await self.atdome.evt_azimuthState.next(
                flush=False, timeout=self.open_dome_shutter_time
            )

    async def close_dome(self):
        """Task to close ATDome.
        """
        shutter_pos = await self.atdome.evt_mainDoorState.aget(
            timeout=self.fast_timeout
        )

        if shutter_pos.state == ATDome.ShutterDoorState.OPENED:

            self.atdome.evt_shutterInPosition.flush()

            await self.atdome.cmd_closeShutter.set_start(
                timeout=self.open_dome_shutter_time
            )

            self.atdome.evt_summaryState.flush()
            # TODO: Monitor self.atdome.tel_position.mainDoorOpeningPercentage
            coro_list = [
                asyncio.create_task(self.check_component_state("atdome")),
                asyncio.create_task(self.wait_for_atdome_shutter_inposition()),
            ]

            for res in asyncio.as_completed(coro_list):
                try:
                    await res
                except RuntimeError as rte:
                    await self.cancel_not_done(coro_list)
                    raise rte
                else:
                    await self.cancel_not_done(coro_list)
                    break
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
        """

        cover_state = await self.atpneumatics.evt_m1CoverState.aget(
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
            tel_pos = await self.atmcs.tel_mount_AzEl_Encoders.next(
                flush=True, timeout=self.fast_timeout
            )

            if tel_pos.elevationCalculatedAngle[-1] < self.tel_el_operate_pneumatics:
                await self.point_azel(
                    az=tel_pos.azimuthCalculatedAngle[-1],
                    el=self.tel_el_operate_pneumatics,
                    wait_dome=False,
                )

            await self.atpneumatics.cmd_openM1Cover.start(timeout=self.long_timeout)

            while cover_state.state != ATPneumatics.MirrorCoverState.OPENED:
                cover_state = await self.atpneumatics.evt_m1CoverState.next(
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
        """
        cover_state = await self.atpneumatics.evt_m1CoverState.aget(
            timeout=self.fast_timeout
        )

        self.log.debug(
            f"Cover state {ATPneumatics.MirrorCoverState(cover_state.state)!r}"
        )

        if cover_state.state == ATPneumatics.MirrorCoverState.OPENED:

            self.log.debug("Closing M1 cover.")

            await self.atpneumatics.cmd_closeM1Cover.start(timeout=self.long_timeout)

            while cover_state.state != ATPneumatics.MirrorCoverState.CLOSED:
                cover_state = await self.atpneumatics.evt_m1CoverState.next(
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

        vent_state = await self.atpneumatics.evt_m1VentsPosition.aget(
            timeout=self.fast_timeout
        )

        self.log.debug(f"M1 vent state {VentsPosition(vent_state.position)}")

        if vent_state.position == VentsPosition.CLOSED:

            self.log.debug("Opening M1 vents.")

            try:
                await self.atpneumatics.cmd_openM1CellVents.start(
                    timeout=self.long_timeout
                )
            except Exception:
                return

            while vent_state.position != VentsPosition.OPENED:
                vent_state = await self.atpneumatics.evt_m1VentsPosition.next(
                    flush=False, timeout=self.long_long_timeout
                )
                self.log.debug(f"M1 vent state {VentsPosition(vent_state.position)}")
        elif vent_state.position == VentsPosition.OPENED:
            self.log.info(f"M1 vents already opened.")
        else:
            raise RuntimeError(f"Unrecognized M1 vent position: {vent_state.position}")

    async def close_m1_vent(self):
        """Task to open m1 vents.
        """

        vent_state = await self.atpneumatics.evt_m1VentsPosition.aget(
            timeout=self.fast_timeout
        )

        self.log.debug(f"M1 vent state {VentsPosition(vent_state.position)}")

        if vent_state.position == VentsPosition.OPENED:

            self.log.debug("Closing M1 vents.")

            try:
                await self.atpneumatics.cmd_closeM1CellVents.start(
                    timeout=self.long_timeout
                )
            except Exception:
                return

            while vent_state.position != VentsPosition.CLOSED:
                vent_state = await self.atpneumatics.evt_m1VentsPosition.next(
                    flush=False, timeout=self.long_long_timeout
                )
                self.log.debug(f"M1 vent state {VentsPosition(vent_state.position)}")
        elif vent_state.position == VentsPosition.CLOSED:
            self.log.info(f"M1 vents already closed.")
        else:
            raise RuntimeError(f"Unrecognized M1 vent position: {vent_state.position}")

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
            self.atmcs.evt_allAxesInPosition.flush()

        track_id = next(self.track_id_gen)

        try:
            current_target = await self.atmcs.evt_target.next(
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
                getattr(self, comp).evt_summaryState.flush()
                self.scheduled_coro.append(
                    asyncio.ensure_future(self.check_component_state(comp))
                )

        self.log.debug("process as completed...")
        for res in asyncio.as_completed(self.scheduled_coro):
            try:
                ret_val = await res
                self.log.debug(ret_val)
            except RuntimeError as rte:
                self.log.warning("RuntimeError, cancel_not_done.")
                await self.cancel_not_done(self.scheduled_coro)
                raise rte
            else:
                break

        await self.cancel_not_done(self.scheduled_coro)

    async def offset_azel(self, az, el, persistent=False):
        """ Offset telescope in azimuth and elevation.

        Parameters
        ----------
        az : `float`
            Offset in azimuth (arcsec).
        el : `float`
            Offset in elevation (arcsec).
        persistent : `bool`
            User persistent offset instead (default=False)? Persistent offsets
            are cumulative.

        """
        self.log.debug(f"Applying Az/El offset: {az}/ {el} ")
        self.atmcs.evt_allAxesInPosition.flush()
        await self.atptg.cmd_offsetAzEl.set_start(
            az=az, el=el, num=0 if not persistent else 1
        )
        try:
            await self.atmcs.evt_allAxesInPosition.next(
                flush=True, timeout=self.tel_settle_time
            )
        except asyncio.TimeoutError:
            pass
        self.log.debug("Waiting for telescope to settle.")
        await asyncio.sleep(self.tel_settle_time)
        self.log.debug("Done")

    async def offset_radec(self, ra, dec):
        """ Offset telescope in RA and Dec.

        Parameters
        ----------
        ra : `float`
            Offset in ra (arcsec).
        dec : `float` or `str`
            Offset in dec (arcsec).

        """
        self.log.debug(f"Applying RA/Dec offset: {ra}/ {dec} ")
        await self.atptg.cmd_offsetRADec.set_start(type=0, off1=ra, off2=dec, num=0)
        self.log.debug("Waiting for telescope to settle.")
        await asyncio.sleep(self.tel_settle_time)
        self.log.debug("Done")

    async def offset_xy(self, x, y, persistent=False):
        """ Offset telescope in x and y.

        Parameters
        ----------
        x : `float`
            Offset in camera x-axis (arcsec).
        y : `float`
            Offset in camera y-axis (arcsec).
        persistent : `bool`
            User persistent offset instead (default=False)? Persistent offsets
            are cumulative.
        """

        self.log.debug(f"Applying x/y offset: {x}/ {y} ")
        azel = await self.atmcs.tel_mount_AzEl_Encoders.aget()
        nasmyth = await self.atmcs.tel_mount_Nasmyth_Encoders.aget()
        angle = (
            np.mean(azel.elevationCalculatedAngle)
            - np.mean(nasmyth.nasmyth2CalculatedAngle)
            + 90.0
        )
        el, az, _ = np.matmul([x, y, 0.0], self.rotation_matrix(angle))

        await self.offset_azel(az, el, persistent)

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

            try:
                in_position = await self.atmcs.evt_allAxesInPosition.next(
                    flush=False, timeout=timeout
                )
            except IndexError:
                in_position = await self.atmcs.evt_allAxesInPosition.aget(
                    timeout=timeout
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

            in_position = await self.atdome.evt_shutterInPosition.next(
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
                await self.atmcs.evt_target.next(flush=True, timeout=self.long_timeout)
            except asyncio.TimeoutError:
                raise RuntimeError(
                    "Not receiving target events from the ATMCS. "
                    "Check component for errors."
                )
            except IndexError:
                try:
                    await self.atmcs.evt_target.aget(timeout=self.long_timeout)
                except asyncio.TimeoutError:
                    raise RuntimeError(
                        "Not receiving target events from the ATMCS. "
                        "Check component for errors."
                    )

        in_position = False

        while not in_position:
            if atmcs:
                comm_pos = await self.atmcs.evt_target.next(
                    flush=True, timeout=self.fast_timeout
                )
                tel_pos = await self.atmcs.tel_mount_AzEl_Encoders.next(
                    flush=True, timeout=self.fast_timeout
                )
                nasm_pos = await self.atmcs.tel_mount_Nasmyth_Encoders.next(
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
                dom_pos = await self.atdome.tel_position.next(
                    flush=True, timeout=self.fast_timeout
                )
                dom_comm_pos = await self.atdome.evt_azimuthCommandedState.aget(
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
                    f"[Telescope] delta Alt = {alt_dif:+08.3f} | delta Az = {az_dif:+08.3f} "
                    f"delta N1 = {nasm1_dif:+08.3f} delta N2 = {nasm2_dif:+08.3f} "
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
                    f"[Telescope] delta Alt = {alt_dif:+08.3f} | delta Az= {az_dif:+08.3f} "
                    f"delta N1 = {nasm1_dif:+08.3f} delta N2 = {nasm2_dif:+08.3f} "
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
            in_position = await self.atmcs.evt_allAxesInPosition.next(flush=False)
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
        self.athexapod.evt_positionUpdate.flush()
        await self.ataos.cmd_applyFocusOffset.set_start(offset=offset)

        try:
            await self.athexapod.evt_positionUpdate.next(
                flush=False, timeout=self.long_timeout
            )
        except asyncio.TimeoutError:
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

        try:
            await self.atptg.cmd_pointAddData.start()
        except salobj.AckError:
            self.log.debug("Opening new pointing file.")
            await self.atptg.cmd_pointNewFile.start()
            await self.atptg.cmd_pointAddData.start()


def parallactic_angle(location, lst, target):
    """
    Calculate the parallactic angle.

    Parameters
    ----------
    location: ``
        Observatory location.

    lst: ``
        Local sidereal time.

    target: ``
        The observing target coordinates.

    Returns
    -------
    `~astropy.coordinates.Angle`
        Parallactic angle.

    Notes
    -----
    The parallactic angle is the angle between the great circle that
    intersects a celestial object and the zenith, and the object's hour
    circle [1]_.

    .. [1] https://en.wikipedia.org/wiki/Parallactic_angle

    """

    # Eqn (14.1) of Meeus' Astronomical Algorithms
    H = (lst - target.ra).radian
    q = (
        np.arctan2(
            np.sin(H),
            (
                np.tan(location.lat.radian) * np.cos(target.dec.radian)
                - np.sin(target.dec.radian) * np.cos(H)
            ),
        )
        * u.rad
    )

    return Angle(q)

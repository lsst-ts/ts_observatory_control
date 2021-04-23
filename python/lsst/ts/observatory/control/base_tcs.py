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

__all__ = ["BaseTCS"]

import abc
import asyncio
import warnings

import numpy as np
import astropy.units as u
from astropy.coordinates import AltAz, ICRS, EarthLocation, Angle
from astroquery.simbad import Simbad

from . import RemoteGroup
from .utils import parallactic_angle, RotType, InstrumentFocus

from lsst.ts import salobj


class BaseTCS(RemoteGroup, metaclass=abc.ABCMeta):
    """Base class for Telescope Control System.

    Parameters
    ----------
    components : `list` [`str`]
        A list of strings with the names of the SAL components that are part
        of the telescope control system group.
    domain : `lsst.ts.salobj.Domain`
        Domain for remotes. If `None` create a domain.
    log : `logging.Logger`
        Optional logging class to be used for logging operations. If `None`,
        creates a new logger.
    intended_usage: `int`
        Optional integer that maps to a list of intended operations. This is
        used to limit the resources allocated by the class by gathering some
        knowledge about the usage intention. By default allocates all
        resources.

    """

    def __init__(self, components, domain=None, log=None, intended_usage=None):

        super().__init__(
            components=components,
            domain=domain,
            log=log,
            intended_usage=intended_usage,
        )

        self.location = EarthLocation.from_geodetic(
            lon=-70.747698 * u.deg, lat=-30.244728 * u.deg, height=2663.0 * u.m
        )

        self.track_id_gen = salobj.index_generator()

        self.instrument_focus = InstrumentFocus.Prime

        # FIXME: (DM-26454) Once this is published by the telescope components
        # it should read this from events.
        self.rotator_limits = [-90.0, +90.0]

        # Parity of x and y axis. These can be 1 or -1 depending on how the
        # x axis in the boresight is aligned with the telescope axis. For
        # instance, Nasmyth angle right has parity 1 and Nasmyth angle left has
        # parity -1, because the x-axis is reversed with respect to optical
        # axis.
        self.parity_x = 1.0
        self.parity_y = 1.0

        self._ready_to_take_data_future = salobj.make_done_future()
        self._ready_to_take_data_task = None

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
        getattr(self.rem, self.ptg_name).cmd_azElTarget.set(
            targetName=target_name,
            azDegs=Angle(az, unit=u.deg).deg,
            elDegs=Angle(el, unit=u.deg).deg,
            rotPA=Angle(rot_tel, unit=u.deg).deg,
        )
        check = self.set_azel_slew_checks(wait_dome=wait_dome)

        try:
            await self._slew_to(
                getattr(self.rem, self.ptg_name).cmd_azElTarget,
                slew_timeout=slew_timeout,
            )
        except salobj.AckError as ack_err:
            self.log.error(
                f"Command to slew to azEl target rejected: {ack_err.ackcmd.result}"
            )
            raise ack_err
        finally:
            self.unset_azel_slew_checks(check)

    async def start_tracking(self):
        """Start tracking the current position of the telescope.

        Method returns once telescope and dome are in sync.
        """
        raise NotImplementedError("Start tracking not implemented yet.")

    async def slew_object(
        self,
        name,
        rot=0.0,
        rot_type=RotType.SkyAuto,
        dra=0.0,
        ddec=0.0,
        az_wrap_strategy=None,
        time_on_target=0.0,
        slew_timeout=240.0,
    ):
        """Slew to an object name.

        Use simbad to resolve the name and get coordinates.

        Parameters
        ----------
        name : `str`
            Target name.
        rot : `float`, `str` or `astropy.coordinates.Angle`, optional
            Specify desired rotation angle. Strategy depends on `rot_type`
            parameter. Accepts float (deg), sexagesimal string (DD:MM:SS.S or
            DD MM SS.S) coordinates or `astropy.coordinates.Angle`
        rot_type :  `lsst.ts.observatory.control.utils.RotType`, optional
            Rotation type. This parameter defines how `rot_value` is threated.
            Default is `SkyAuto`, the rotator is positioned with respect to the
            North axis and is automacally wrapped if outside the limit. See
            `RotType` for more options.
        slew_timeout : `float`, optional
            Timeout for the slew command (second). Default is 240 seconds.

        Other Parameters
        ----------------
        dra : `float`, optional
            Differential Track Rate in RA (second/second). Default is 0.
        ddec : `float`, optional
            Differential Track Rate in Dec (arcsec/second). Default is 0.
        az_wrap_strategy : `azWrapStrategy` or `None`, optional
            Azimuth wrap strategy. By default use `maxTimeOnTarget=3`, which
            attempts to maximize the time on target. Other options are;
            1-noUnWrap, 2-optimize.
        time_on_target : `float`, optional
            Estimated time on target, in seconds. This is used by the
            optimize azimuth wrap algorithm to determine whether it needs to
            unwrap or not.

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
            rot=rot,
            rot_type=rot_type,
            target_name=name,
            dra=dra,
            ddec=ddec,
            slew_timeout=slew_timeout,
        )

    async def slew_icrs(
        self,
        ra,
        dec,
        rot=0.0,
        rot_type=RotType.SkyAuto,
        target_name="slew_icrs",
        dra=0.0,
        ddec=0.0,
        az_wrap_strategy=None,
        time_on_target=0.0,
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
        rot : `float`, `str` or `astropy.coordinates.Angle`
            Specify desired rotation angle. The value will have different
            meaning depending on the choince of `rot_type` parameter.
            Accepts float (deg), sexagesimal string (DD:MM:SS.S or DD MM SS.S)
            coordinates or `astropy.coordinates.Angle`
        rot_type :  `lsst.ts.observatory.control.utils.RotType`
            Rotation type. This parameter defines how `rot_value` is threated.
            Default is `SkyAuto`, the rotator is positioned with respect to the
            North axis and is automatically wrapped if outside the limit. See
            `RotType` for more options.
        target_name :  `str`
            Target name.
        slew_timeout : `float`
            Timeout for the slew command (second). Default is 240s.

        Other Parameters
        ----------------
        dra : `float`, optional
            Differential Track Rate in RA (second/second). Default is 0.
        ddec : `float`, optional
            Differential Track Rate in Dec (arcsec/second). Default is 0.
        az_wrap_strategy : `azWrapStrategy` or `None`, optional
            Azimuth wrap strategy. By default use `maxTimeOnTarget=3`, which
            attempts to maximize the time on target. Other options are;
            1-noUnWrap, 2-optimize.
        time_on_target : `float`, optional
            Estimated time on target, in seconds. This is used by the
            optimize azimuth wrap algorithm to determine whether it needs to
            unwrap or not.
        stop_before_slew : `bool`
            Stop tracking before starting the slew? This option is a
            workaround to some issues with the ATMCS not sending events
            reliably.
        wait_settle : `bool`
            Wait telescope to settle before returning? It `True` add an
            additional sleep of `self.tel_settle_time` to the telescope
            positioning algorithm. Otherwise the algorithm will return as soon
            as it receives `allAxesInPosition` event from the ATMCS.

        Returns
        -------
        radec_icrs : `astropy.coordinates.ICRS`
            Coordinates used in slew command.

        rot_angle : `astropy.coordinates.Angle`
            Angle used in command for rotator.

        See Also
        --------
        slew_object : Slew to an object name.

        """
        radec_icrs = ICRS(Angle(ra, unit=u.hourangle), Angle(dec, unit=u.deg))

        rot_angle = Angle(rot, unit=u.deg)

        current_tai = salobj.current_tai()
        current_time = salobj.astropy_time_from_tai_unix(current_tai)

        current_time.location = self.location

        par_angle = parallactic_angle(
            self.location,
            current_time.sidereal_time("mean"),
            radec_icrs,
        )

        alt_az = self.azel_from_radec(
            ra=radec_icrs.ra, dec=radec_icrs.dec, time_tai=current_tai
        )

        rot_frame = self.RotFrame.TARGET
        rot_track_frame = self.RotFrame.TARGET

        # compute rotator physical position if rot_angle is sky.
        rot_phys_val = salobj.angle_wrap_center(
            Angle(
                Angle(180.0, unit=u.deg)
                + par_angle
                + rot_angle
                - (
                    alt_az.alt
                    if self.instrument_focus == InstrumentFocus.Nasmyth
                    else 0.0
                ),
                unit=u.deg,
            )
        )

        if rot_type == RotType.Sky:
            self.log.debug(f"RotSky = {rot_angle}, RotPhys = {rot_phys_val}.")
        elif rot_type == RotType.SkyAuto:
            self.log.debug(f"Auto sky angle: {rot_angle}")
            if not (self.rotator_limits[0] < rot_phys_val.deg < self.rotator_limits[1]):
                self.log.debug(
                    f"Rotator angle out of limits {rot_angle} [{self.rotator_limits}]. Wrapping."
                )
                rot_angle = salobj.angle_wrap_center(
                    Angle(180.0, unit=u.deg) + rot_angle
                )
        elif rot_type == RotType.PhysicalSky:
            self.log.debug(
                f"Setting rotator physical position to {rot_angle}. Rotator will track sky."
            )
            rot_frame = self.RotFrame.FIXED
        elif rot_type == RotType.Parallactic:

            self.log.debug(
                f"Setting rotator position with respect to parallactic angle to {rot_angle}."
            )

            rot_angle = rot_phys_val + alt_az.alt - 90.0 * u.deg

            self.log.debug(
                f"Parallactic angle: {par_angle.deg} | " f"Sky Angle: {rot_angle.deg}"
            )
        elif rot_type == RotType.Physical:
            self.log.debug(
                f"Setting rotator to physical fixed position {rot_angle}. Rotator will not track."
            )
            rot_frame = self.RotFrame.FIXED
            rot_track_frame = self.RotFrame.FIXED
        else:
            valid_rottypes = ", ".join(repr(rt) for rt in RotType)
            raise RuntimeError(
                f"Unrecognized rottype {rot_type}. Should be one of {valid_rottypes}"
            )

        await self.slew(
            radec_icrs.ra.hour,
            radec_icrs.dec.deg,
            rotPA=rot_angle.deg,
            target_name=target_name,
            frame=self.CoordFrame.ICRS,
            epoch=2000,
            equinox=2000,
            parallax=0,
            pmRA=0,
            pmDec=0,
            rv=0,
            dRA=dra,
            dDec=ddec,
            rot_frame=rot_frame,
            rot_track_frame=rot_track_frame,
            az_wrap_strategy=az_wrap_strategy,
            time_on_target=time_on_target,
            rot_mode=self.RotMode.FIELD,
            slew_timeout=slew_timeout,
            stop_before_slew=stop_before_slew,
            wait_settle=wait_settle,
        )

        return radec_icrs, rot_angle

    async def slew(
        self,
        ra,
        dec,
        rotPA=0.0,
        target_name="slew_icrs",
        frame=None,
        epoch=2000,
        equinox=2000,
        parallax=0,
        pmRA=0,
        pmDec=0,
        rv=0,
        dRA=0,
        dDec=0,
        rot_frame=None,
        rot_track_frame=None,
        rot_mode=None,
        az_wrap_strategy=None,
        time_on_target=0.0,
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
            Rotator coordinate frame (`self.RotFrame`). Specify how to select
            the position of the rotator. If `self.RotFrame.TARGET` uses sky
            position angle. If `self.RotFrame.FIXED` uses rotator physical
            position.
        rot_track_frame : `enum`
            Rotator track frame (`self.RotFrame`). Specify the rotator tracking
            mode. If `self.RotFrame.TARGET`, follow sky. If
            `self.RotFrame.FIXED` keep rotator at fixed position.
        rot_mode : `enum`
            Rotator position mode (`self.RotMode`).
            If `self.RotMode.FIELD` optimize for sky tracking, if
            `self.RotMode.SLIT` optimize for slit spectroscopy.
        slew_timeout : `float`
            Timeout for the slew command (second).
        stop_before_slew : `bool`
            Stop tracking before starting the slew? This option is a
            workaround to some issues with the mount components not sending
            events reliably.
        wait_settle : `bool`
            Wait telescope to settle before returning?
        """
        # Compatibility between xml 7 and xml 8
        if hasattr(
            getattr(self.rem, self.ptg_name).cmd_raDecTarget.DataType(), "rotAngle"
        ):
            # xml >8
            getattr(self.rem, self.ptg_name).cmd_raDecTarget.set(
                ra=ra,
                declination=dec,
                targetName=target_name,
                frame=frame if frame is not None else self.CoordFrame.ICRS,
                rotAngle=rotPA,
                rotStartFrame=rot_frame
                if rot_frame is not None
                else self.RotFrame.TARGET,
                rotTrackFrame=rot_track_frame
                if rot_track_frame is not None
                else self.RotFrame.TARGET,
                azWrapStrategy=self.WrapStrategy.MAXTIMEONTARGET
                if az_wrap_strategy is None
                else az_wrap_strategy,
                timeOnTarget=time_on_target,
                epoch=epoch,
                equinox=equinox,
                parallax=parallax,
                pmRA=pmRA,
                pmDec=pmDec,
                rv=rv,
                dRA=dRA,
                dDec=dDec,
                rotMode=rot_mode if rot_mode is not None else self.RotMode.FIELD,
            )
        else:
            # xml 7
            _rot_frame = rot_frame if rot_frame is not None else self.RotFrame.TARGET
            self.log.debug(
                f"xml 7 compatibility mode: rotPA={rotPA}, rotFrame={_rot_frame}"
            )
            getattr(self.rem, self.ptg_name).cmd_raDecTarget.set(
                ra=ra,
                declination=dec,
                targetName=target_name,
                frame=frame if frame is not None else self.CoordFrame.ICRS,
                rotPA=rotPA,
                rotFrame=_rot_frame,
                epoch=epoch,
                equinox=equinox,
                parallax=parallax,
                pmRA=pmRA,
                pmDec=pmDec,
                rv=rv,
                dRA=dRA,
                dDec=dDec,
                rotMode=rot_mode if rot_mode is not None else self.RotMode.FIELD,
            )

            if rot_track_frame is not None:
                self.log.warning(
                    f"Recived {rot_track_frame!r}. Rotator tracking frame only available in xml 8 and up."
                )

        try:
            await self._slew_to(
                getattr(self.rem, self.ptg_name).cmd_raDecTarget,
                slew_timeout=slew_timeout,
                stop_before_slew=stop_before_slew,
                wait_settle=wait_settle,
            )
        except salobj.AckError as ack_err:
            self.log.error(
                f"Command to track target {target_name} rejected: {ack_err.ackcmd.result}"
            )
            raise ack_err

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
        getattr(self.rem, self.ptg_name).cmd_planetTarget.set(
            planetName=planet.value,
            dRA=0.0,
            dDec=0.0,
            rotPA=Angle(rot_sky, unit=u.deg).deg,
        )

        await self._slew_to(
            getattr(self.rem, self.ptg_name).cmd_planetTarget, slew_timeout=slew_timeout
        )

    async def offset_radec(self, ra, dec):
        """Offset telescope in RA and Dec.

        Perform arc-length offset in sky coordinates. The magnitude of the
        offset is sqrt(ra^2 + dec^2) and the angle is the usual atan2(dec, ra).

        Parameters
        ----------
        ra : `float`
            Offset in ra (arcsec).
        dec : `float` or `str`
            Offset in dec (arcsec).

        See Also
        --------
        offset_azel : Offset in local AzEl coordinates.
        offset_xy : Offsets in the detector X/Y plane.

        """
        self.log.debug(f"Applying RA/Dec offset: {ra}/{dec} ")

        await self._offset(
            offset_cmd=getattr(self.rem, self.ptg_name).cmd_offsetRADec.set_start(
                type=0, off1=ra, off2=dec, num=0
            )
        )

    async def offset_azel(self, az, el, relative=True, persistent=None, absorb=False):
        """Offset telescope in azimuth and elevation.

        For more information see the Notes section below or the package
        documentation in https://ts-observatory-control.lsst.io/.

        Parameters
        ----------
        az : `float`
            Offset in azimuth (arcsec).
        el : `float`
            Offset in elevation (arcsec).
        relative : `bool`
            If `True` (default) offset is applied relative to the current
            position, if `False` offset replaces any existing offsets.
        persistent : `bool` or `None`
            (Deprecated) Should the offset be absorbed and persisted between
            slews? Use of this parameter is deprecated. Use `absorb` instead.
        absorb : `bool`
            Should the offset be absorbed and persisted between slews?

        See Also
        --------
        offset_xy : Offsets in the detector X/Y plane.
        offset_radec : Offset in sky coordinates.
        reset_offsets : Reset offsets.

        Notes
        -----

        The `persistent` flag is deprecated. Use `absorb` instead.

        There are a couple different ways users can modify how offsets are
        treated via the input flags `relative` and `absorb`.

        These flags allows users to control the following behavior;

            1 - If the offset is relative to the current position
                (`relative=True`) or relative to the pointing origin (e.g. the
                initial slew position).

            2 - If the offset will only apply only to the current target
                (`absorb=False`) or if they will be absorbed by the pointing
                and persist after a new targets (`absorb=True`).

        By default `relative=True` and `absorb=False`, which means offsets
        will be relative to the current position and will reset after a slew.

        The default relative offsets will accumulate. For instance,

        >>> await tcs.offset_azel(az=10, el=0)
        >>> await tcs.offset_azel(az=0, el=10)

        Will result in a 10 arcsec offset in **both** azimuth and elevation.

        Non-relative offsets will overrides any previous non-relative offset.
        For instance, the pair of commands below:

        >>> await tcs.offset_azel(az=10, el=0)
        >>> await tcs.offset_azel(az=0, el=10)

        Results in only 10 arcsec offset in elevation, e.g., is equivalent to
        just doing the second command;

        >>> await tcs.offset_azel(az=0, el=10, relative=True)

        This is because the non-relative offset requested by the second command
        will reset the offset done on the previous command.

        It is important to keep in mind that these offsets can also be combined
        with one another. For instance, if you do;

        >>> await tcs.offset_azel(az=10, el=0)
        >>> await tcs.offset_azel(az=0, el=10)
        >>> await tcs.offset_azel(az=0, el=10, relative=False)

        You will get 10 arcsec offset in azimuth and 20 arcsec in elevation.

        Nevertheless, if after doing the above you do;

        >>> await tcs.offset_azel(az=0, el=0, relative=False)

        It will result in a 10 arcsec offset in **both** azimuth and elevation,
        from the relative offsets done previously.

        In all cases above, the offset will be overwritten if a new target is
        sent, e.g.;

        >>> await tcs.offset_azel(az=10, el=0, relative=True)
        >>> await tcs.offset_azel(az=0, el=10, relative=True)
        >>> await tcs.offset_azel(az=0, el=10)
        >>> await tcs.slew_object("HD 164461")  # reset all offsets above

        Will result in a slew with no offsets.

        If you want offsets to persist between slews use `absorb=True`.

        The `relative` flag applies the same way to absored offsets.

        The following sequence of commands;

        >>> await tcs.offset_azel(az=10, el=0, relative=True, absorb=True)
        >>> await tcs.offset_azel(az=0, el=10, relative=True, absorb=True)
        >>> await tcs.offset_azel(az=0, el=10, relative=False, absorb=True)
        >>> await tcs.slew_object("HD 164461")

        Will result in a slew offset by 10 arcsec in azimuth and 20 arcsec in
        elevation.

        """

        if persistent is not None:
            warnings.warn(
                "persistent flag is deprecated, use absorb instead.", DeprecationWarning
            )

        if absorb or persistent is True:
            self.log.debug(f"Calculating Az/El offset: {az}/{el} ")

            bore_sight_angle = await self.get_bore_sight_angle()

            x, y, _ = np.matmul(
                [-self.parity_x * az, -self.parity_y * el, 0.0],
                self.rotation_matrix(bore_sight_angle),
            )
            await self.offset_xy(x, y, relative=relative, absorb=True)
        else:
            self.log.debug(f"Applying Az/El offset: {az}/{el} ")

            await self._offset(
                offset_cmd=getattr(self.rem, self.ptg_name).cmd_offsetAzEl.set_start(
                    az=az, el=el, num=0 if not relative else 1
                )
            )

    async def offset_xy(self, x, y, relative=True, persistent=None, absorb=False):
        """Offsets in the detector X/Y plane.

        Offset the telescope field-of-view in the x and y direction.

        Parameters
        ----------
        x : `float`
            Offset in camera x-axis (arcsec).
        y : `float`
            Offset in camera y-axis (arcsec).
        relative : `bool`
            If `True` offset is applied relative to the current position, if
            `False` (default) offset replaces any existing offsets.
        persistent : `bool` or `None`
            (Deprecated) Should the offset be absorbed and persisted between
            slews? Use of this parameter is deprecated. Use `absorb` instead.
        absorb : `bool`
            Should the offset be absorbed and persisted between slews?

        See Also
        --------
        offset_azel : Offset in local AzEl coordinates.
        offset_radec : Offset in sky coordinates.
        reset_offsets : Reset offsets.

        Notes
        -----

        The `persistent` flag is deprecated. Use `absorb` instead.

        If the image is displayed with the x-axis in horizontal position,
        increasing from left to right, a positive x-offset will result in
        the field-of-view moving to the right, and therefore, the stellar
        positions will move to the left.

        If the image is diplayed with y-axis in vertical position, increasing
        from bottom to top, a positive y-offset will result in field-of-view
        moving up, and therefore, the stellar positions will move down.

        See the Notes section in `offset_azel` help page for more information
        about the `relative` and `persistent` flags.
        """

        if persistent is not None:
            warnings.warn(
                "persistent flag is deprecated, use absorb instead.", DeprecationWarning
            )

        if absorb or persistent is True:
            # Persistent offset in the pointing are done in x/y, in mm.
            # Need to convert inputs in arcsec to mm,
            self.log.debug(f"Persistent x/y offset: {x}/{y}")

            await self._offset(
                offset_cmd=getattr(self.rem, self.ptg_name).cmd_poriginOffset.set_start(
                    dx=x * self.plate_scale,
                    dy=y * self.plate_scale,
                    num=0 if not relative else 1,
                )
            )
        else:

            self.log.debug(f"Calculating x/y offset: {x}/{y} ")

            bore_sight_angle = await self.get_bore_sight_angle()

            el, az, _ = np.matmul(
                [self.parity_x * x, self.parity_y * y, 0.0],
                self.rotation_matrix(bore_sight_angle),
            )
            await self.offset_azel(az=az, el=el, relative=relative, absorb=False)

    async def reset_offsets(self, absorbed=True, non_absorbed=True):
        """Reset pointing offsets.

        By default reset all pointing offsets. User can specify if they want to
        reset only the absorbed and non-absorbed offsets as well.

        Parameters
        ----------
        absorbed : `bool`
            Reset absorbed offset? Default `True`.
        non_absorbed : `bool`
            Reset non-absorbed offset? Default `True`.

        Raises
        ------
        RuntimeError:
            If both absorbed and non_absorbed are `False`.

        """

        reset_offsets = []

        if not absorbed and not non_absorbed:
            raise RuntimeError("Select at least one offset to reset.")

        if absorbed:
            self.log.debug("Reseting absorbed offsets.")
            reset_offsets.append(
                getattr(self.rem, self.ptg_name).cmd_poriginClear.set_start(
                    num=0, timeout=self.fast_timeout
                )
            )
            reset_offsets.append(
                getattr(self.rem, self.ptg_name).cmd_poriginClear.set_start(
                    num=1, timeout=self.fast_timeout
                )
            )

        if non_absorbed:
            self.log.debug("Reseting non-absorbed offsets.")
            reset_offsets.append(
                getattr(self.rem, self.ptg_name).cmd_offsetClear.set_start(
                    num=0, timeout=self.fast_timeout
                )
            )
            reset_offsets.append(
                getattr(self.rem, self.ptg_name).cmd_offsetClear.set_start(
                    num=1, timeout=self.fast_timeout
                )
            )

        await asyncio.gather(*reset_offsets)

    async def add_point_data(self):
        """Add current position to a point file. If a file is open it will
        append to that file. If no file is opened it will open a new one.

        """

        state = await self.get_state(self.ptg_name)
        if state != salobj.State.ENABLED:
            raise RuntimeError(
                f"ATPtg in {state!r}. Expected {salobj.State.ENABLED!r}."
            )

        # TODO: DM-24526 Check event to see if point file is opened.
        try:
            await getattr(self.rem, self.ptg_name).cmd_pointAddData.start()
        except salobj.AckError:
            self.log.debug("Opening new pointing file.")
            await getattr(self.rem, self.ptg_name).cmd_pointNewFile.start(
                timeout=self.fast_timeout
            )
            await getattr(self.rem, self.ptg_name).cmd_pointAddData.start(
                timeout=self.fast_timeout
            )

    async def stop_tracking(self):
        """Task to stop telescope tracking."""

        self.log.debug("Stop tracking.")

        await getattr(self.rem, self.ptg_name).cmd_stopTracking.start(
            timeout=self.fast_timeout
        )

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

        for cmp in self.components_attr:
            if getattr(self.check, cmp):
                self.log.debug(f"Adding {cmp} to check list")
                task_list.append(asyncio.ensure_future(self.check_component_state(cmp)))
                task_list.append(asyncio.ensure_future(self.check_comp_heartbeat(cmp)))
            else:
                self.log.debug(f"Skipping {cmp}")

        await self.process_as_completed(task_list)

    async def _offset(self, offset_cmd):
        """Execute an offset command.

        Parameters
        ----------
        offset_cmd : `coroutine`, `asyncio.Task` or `asyncio.Future`
            An awaitable object (coroutines, Tasks, or Futures) with the
            offset command.

        See Also
        --------
        offset_azel : Offset in local AzEl coordinates.
        offset_xy : Offset in terms of boresight.
        offset_radec : Offset in sky coordinates.

        """
        self.flush_offset_events()

        await offset_cmd

        try:

            await self.offset_done()

        except asyncio.TimeoutError:

            self.log.debug("Timed out waiting for offset done events.")

        self.log.debug("Waiting for telescope to settle.")
        await asyncio.sleep(self.tel_settle_time)
        self.log.debug("Done")

    def ready_to_take_data(self):
        """Return a future object that will be done when the ATCS is ready to
        take data or raise an exception if something wrong happens while trying
        to determine the condition of the system.
        """
        if self._ready_to_take_data_future.done():
            self._ready_to_take_data_future = asyncio.Future()
            self._ready_to_take_data_task = asyncio.create_task(
                self._ready_to_take_data()
            )
        return self._ready_to_take_data_future

    def azel_from_radec(self, ra, dec, time=None):
        """Calculate Az/El coordinates from RA/Dec in ICRS.

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
        time : `astropy.time.core.Time` or `None`, optional
            The time which the coordinate trasformation is intended for. If
            `None` (default) use current time.

        Returns
        -------
        azel : `astropy.coordinates.AltAz`
            Astropy coordinates with azimuth and elevation.
        """
        radec_icrs = ICRS(Angle(ra, unit=u.hourangle), Angle(dec, unit=u.deg))

        if time is None:
            time = salobj.astropy_time_from_tai_unix(salobj.current_tai())

        time.location = self.location

        coord_frame_azel = AltAz(location=self.location, obstime=time)

        azel = radec_icrs.transform_to(coord_frame_azel)

        return azel

    def radec_from_azel(self, az, el, time=None):
        """Calculate Ra/Dec in ICRS coordinates from Az/El.

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
        time : `astropy.time.core.Time` or `None`, optional
            The time which the coordinate trasformation is intended for. If
            `None` (default) use current time.

        Returns
        -------
        radec_icrs : `astropy.coordinates.ICRS`
            Astropy coordinates with azimuth and elevation.
        """

        if time is None:
            time = salobj.astropy_time_from_tai_unix(salobj.current_tai())

        time.location = self.location

        coord_frame_azel = AltAz(
            alt=Angle(el, unit=u.deg),
            az=Angle(az, unit=u.deg),
            location=self.location,
            obstime=time,
        )

        radec_icrs = coord_frame_azel.transform_to(ICRS)

        return radec_icrs

    def parallactic_angle(self, ra, dec, time=None):
        """Return parallactic angle for the given Ra/Dec coordinates.

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
        time : `astropy.time.core.Time` or `None`, optional
            The time which the coordinate trasformation is intended for. If
            `None` (default) use current time.

        Returns
        -------
        pa_angle : `astropy.coordinates.Angle`
            Parallactic angle.
        """
        radec_icrs = ICRS(Angle(ra, unit=u.hourangle), Angle(dec, unit=u.deg))

        if time is None:
            time = salobj.astropy_time_from_tai_unix(salobj.current_tai())

        time.location = self.location

        pa_angle = parallactic_angle(
            self.location,
            time.sidereal_time("mean"),
            radec_icrs,
        )

        return pa_angle

    @property
    def instrument_focus(self):
        return self.__instrument_focus

    @instrument_focus.setter
    def instrument_focus(self, value):
        self.__instrument_focus = InstrumentFocus(value)

    @staticmethod
    def rotation_matrix(angle):
        """Rotation matrix."""
        return np.array(
            [
                [np.cos(np.radians(angle)), -np.sin(np.radians(angle)), 0.0],
                [np.sin(np.radians(angle)), np.cos(np.radians(angle)), 0.0],
                [0.0, 0.0, 1.0],
            ]
        )

    @abc.abstractmethod
    async def monitor_position(self, check=None):
        """Monitor and log the position of the telescope and the dome.

        Parameters
        ----------
        check : `types.SimpleNamespace` or `None`
            Override `self.check` for defining which resources are used.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    async def slew_dome_to(self, az, check=None):
        """Utility method to slew dome to a specified position.

        Parameters
        ----------
        az : `float` or `str`
            Azimuth angle for the dome (in deg).
        check : `types.SimpleNamespace` or `None`
            Override `self.check` for defining which resources are used.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    async def prepare_for_flatfield(self, check=None):
        """A high level method to position the telescope and dome for flat
        field operations.

        Parameters
        ----------
        check : `types.SimpleNamespace` or `None`
            Override `self.check` for defining which resources are used.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    async def stop_all(self):
        """Stop telescope and dome."""
        raise NotImplementedError()

    @abc.abstractmethod
    async def prepare_for_onsky(self, settings=None):
        """Prepare telescope for on-sky operations.

        Parameters
        ----------
        settings: `dict`
            Dictionary with settings to apply.  If `None` use the recommended
            settings.
        """
        raise NotImplementedError

    @abc.abstractmethod
    async def shutdown(self):
        """Shutdown components."""
        raise NotImplementedError()

    @abc.abstractmethod
    async def open_dome_shutter(self):
        """Task to open dome shutter and return when it is done."""
        raise NotImplementedError()

    @abc.abstractmethod
    async def home_dome(self):
        """Task to execute dome home command and wait for it to complete."""
        raise NotImplementedError()

    @abc.abstractmethod
    async def close_dome(self):
        """Task to close dome."""
        raise NotImplementedError()

    @abc.abstractmethod
    async def open_m1_cover(self):
        """Task to open m1 cover."""
        raise NotImplementedError()

    @abc.abstractmethod
    async def close_m1_cover(self):
        """Task to close m1 cover."""
        raise NotImplementedError()

    @abc.abstractmethod
    async def _slew_to(
        self, slew_cmd, slew_timeout, stop_before_slew=True, wait_settle=True
    ):
        """Encapsulate "slew" activities.

        Parameters
        ----------
        slew_cmd: `coro`
            One of the slew commands from the atptg remote. Command need to be
            setup before calling this method.
        slew_time: `float`
            Expected slew time in seconds.
        stop_before_slew: `bool`
            Stop tracking before slewing?
        wait_settle: `bool`
            After slew complets, add an addional settle wait before returning.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    async def wait_for_inposition(
        self, timeout, cmd_ack=None, wait_settle=True, check=None
    ):
        """Wait for both the ATMCS and ATDome to be in position.

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
        raise NotImplementedError

    @abc.abstractmethod
    def set_azel_slew_checks(self, wait_dome):
        """Abstract method to handle azEl slew to wait or not for the dome.

        Parameters
        ----------
        wait_dome: `bool`
            Should point_azel wait for the dome?
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def unset_azel_slew_checks(self, checks):
        """Abstract method to handle azEl slew to wait or not for the dome.

        Parameters
        ----------
        checks: `types.SimpleNamespace`
            Namespace with the same structure of `self.check` with values
            as before `set_azel_slew_checks` is called.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def flush_offset_events(self):
        """Abstract method to flush events before and offset is performed."""
        raise NotImplementedError()

    @abc.abstractmethod
    async def offset_done(self):
        """Wait for offset events."""
        raise NotImplementedError()

    @abc.abstractmethod
    async def get_bore_sight_angle(self):
        """Get the instrument bore sight angle with respect to the telescope
        axis.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    async def _ready_to_take_data(self):
        """Return a future object that will be done when the TCS is ready to
        take data or raise an exception if something wrong happens while trying
        to determine the condition of the system.
        """
        raise NotImplementedError()

    @property
    @abc.abstractmethod
    def plate_scale(self):
        """Plate scale in mm/arcsec."""
        raise NotImplementedError()

    @property
    @abc.abstractmethod
    def ptg_name(self):
        """Return name of the pointing component."""
        raise NotImplementedError()

    @property
    @abc.abstractmethod
    def CoordFrame(self):
        """Return CoordFrame enumeration."""
        raise NotImplementedError()

    @property
    @abc.abstractmethod
    def RotFrame(self):
        """Return RotFrame enumeration."""
        raise NotImplementedError()

    @property
    @abc.abstractmethod
    def RotMode(self):
        """Return RotMode enumeration."""
        raise NotImplementedError()

    @property
    @abc.abstractmethod
    def WrapStrategy(self):
        """Return WrapStrategy enumeration"""
        raise NotImplementedError()

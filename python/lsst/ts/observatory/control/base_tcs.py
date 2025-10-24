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
import contextlib
import enum
import logging
import typing
import warnings
from functools import partial
from os.path import splitext

import astropy.units as u
import numpy as np
import numpy.typing as npt
import pandas
from astropy.coordinates import ICRS, AltAz, Angle, EarthLocation, SkyCoord, get_sun
from astropy.table import Table
from astropy.time import Time
from astroquery.simbad import Simbad
from lsst.ts import salobj
from lsst.ts.utils import (
    angle_wrap_center,
    astropy_time_from_tai_unix,
    current_tai,
    index_generator,
)

from .remote_group import RemoteGroup
from .utils import (
    InstrumentFocus,
    RotType,
    calculate_parallactic_angle,
    get_catalogs_path,
)
from .utils.extras.dm_target_catalog import DM_STACK_AVAILABLE
from .utils.type_hints import (
    CoordFrameType,
    RotFrameType,
    RotModeType,
    WrapStrategyType,
)


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
    concurrent_operation : `bool`, optional
        If `False`, tasks like `enable` and other concurrent tasks will be done
        sequentially. Default=True.
    """

    def __init__(
        self,
        components: typing.List[str],
        domain: salobj.Domain | None = None,
        log: logging.Logger | None = None,
        intended_usage: int | None = None,
        concurrent_operation: bool = True,
    ) -> None:
        super().__init__(
            components=components,
            domain=domain,
            log=log,
            intended_usage=intended_usage,
            concurrent_operation=concurrent_operation,
        )

        self.location = EarthLocation.from_geodetic(
            lon=-70.747698 * u.deg, lat=-30.244728 * u.deg, height=2663.0 * u.m
        )

        self.track_id_gen = index_generator()

        self.instrument_focus = InstrumentFocus.Prime

        self.tel_settle_time = 3.0

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

        self._overslew_az = False

        self._ready_to_take_data_task: typing.Union[asyncio.Task, None] = None

        # Define alternative rotation angles to try when slewing the telescope.
        self._rot_angle_alternatives: typing.List[float] = [180.0, -180.0, 90.0, -90.0]

        # Dictionary to store name->coordinates of objects
        self._object_list: typing.Dict[str, ICRS] = dict()

        self._catalog: pandas.DataFrame = pandas.DataFrame([])
        self._catalog_coordinates: typing.Union[None, SkyCoord] = None

    def object_list_clear(self) -> None:
        """Remove all objects stored in the internal object list."""
        self.log.debug(f"Removing {len(self._object_list)} items from object list.")
        self._object_list = dict()

    def object_list_remove(self, name: str) -> None:
        """Remove object from object list.

        Parameters
        ----------
        name: `str`
            Object name.

        Raises
        ------
        RuntimeError
            If input object name not in the object list.
        """

        if name not in self._object_list:
            raise RuntimeError(f"Input object {name} not in object list.")
        else:
            self._object_list.pop(name)
            self.log.debug(f"Removed {name} from object list.")

    def object_list_add(self, name: str, radec: ICRS) -> None:
        """Add object to object list.

        Parameters
        ----------
        name: `str`
            Name of the object.
        object_table: `astropy.table.row.Row`
            Table row with object information.
        """
        if name not in self._object_list:
            self._object_list[name] = radec
        else:
            self.log.warning(f"{name} already in the object list.")

    def object_list_get(self, name: str) -> ICRS:
        """Get an object from the list or query Simbad and return it.

        Parameters
        ----------
        name: `str`
            Name of the object.

        Returns
        -------
        radec: `ICRS`
            Table row with object information.
        """

        if name not in self._object_list:
            object_table = self._query_object(name)

            if len(object_table) > 1:
                self.log.warning(
                    f"Found more than one entry for {name}. Using first one."
                )

            # Get RA and DEC keyword from table
            (ra_key, ra_coordinates) = (
                ("RA", u.hourangle) if "RA" in object_table.columns else ("ra", u.deg)
            )
            dec_key = "DEC" if "DEC" in object_table.columns else "dec"

            ra = Angle(object_table[0][ra_key], unit=ra_coordinates)
            dec = Angle(object_table[0][dec_key], unit=u.deg)

            radec_icrs = ICRS(
                ra=ra.to(u.hourangle),
                dec=dec,
            )

            self.object_list_add(name, radec_icrs)
        else:
            radec_icrs = self._object_list[name]

        return radec_icrs

    def object_list_get_all(self) -> typing.Set[str]:
        """Return list of objects in the object list.

        Returns
        -------
        object_list_names : `set`
            Set with the names of all targets in the object list.
        """
        return set(self._object_list.keys())

    def load_catalog(self, catalog_name: str) -> None:
        """Load a catalog from the available set.

        Parameters
        ----------
        catalog_name : `str`
            Name of the catalog to load. Must be a valid entry in the list
            of available catalogs.

        Raises
        ------
        RuntimeError
            If input `catalog_name` is not a valid entry in the list of
            available catalogs.
            If catalog was already loaded or not cleared before loading a new
            one.

        See Also
        --------
        list_available_catalogs: List available catalogs to load.
        """
        if self.is_catalog_loaded():
            raise RuntimeError(
                "Internal catalog is not empty. To load a new catalog, "
                "clear it with `clear_catalog` before loading a new one."
            )

        available_catalogs = self.list_available_catalogs()
        if catalog_name not in available_catalogs:
            raise RuntimeError(
                f"Catalog {catalog_name} not in the list of available catalogs. "
                f"Must be one of {available_catalogs}."
            )

        self.log.info(f"Loading {catalog_name}...")

        self._catalog = Table.read(
            get_catalogs_path() / f"{catalog_name}.pd",
            format="pandas.json",
        )

        self.log.debug("Creating coordinate catalog...")
        self._catalog_coordinates = SkyCoord(
            Angle(self._catalog["RA"], unit=u.hourangle),
            Angle(self._catalog["DEC"], unit=u.deg),
            frame="icrs",
        )

        self.log.debug(f"Loaded catalog with {len(self._catalog)} targets.")

    def list_available_catalogs(self) -> typing.Set[str]:
        """List of available catalogs to load.

        Returns
        -------
        catalog_names : `set`
            Set with the names of the available catalogs.

        See Also
        --------
        load_catalog: Load a catalog from the available set.
        """
        return set(
            [
                splitext(file_name.name)[0]
                for file_name in get_catalogs_path().glob("*.pd")
            ]
        )

    def clear_catalog(self) -> None:
        """Clear internal catalog."""
        if len(self._catalog) == 0:
            self.log.info("Catalog already cleared, nothing to do.")
        else:
            self.log.debug(f"Removing catalog with {len(self._catalog)} targets.")

            del self._catalog
            del self._catalog_coordinates

            self._catalog = pandas.DataFrame([])
            self._catalog_coordinates = None

    def is_catalog_loaded(self) -> bool:
        """Check if catalog is loaded.

        Returns
        -------
        `bool`
            `True` if catalog was loaded, `False` otherwise.
        """
        return len(self._catalog) != 0

    async def point_azel(
        self,
        az: float,
        el: float,
        rot_tel: float = 0.0,
        target_name: str = "azel_target",
        wait_dome: bool = False,
        slew_timeout: float = 1200.0,
    ) -> None:
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
                check=check,
            )
        except salobj.AckError as ack_err:
            self.log.error(
                f"Command to slew to azEl target rejected: {ack_err.ackcmd.result}"
            )
            raise ack_err

    async def start_tracking(
        self,
        slew_timeout: float = 1200.0,
    ) -> None:
        """Start tracking the current position of the telescope.

        Method returns once telescope and dome are in sync.
        """
        check = self.set_azel_slew_checks(wait_dome=True)
        await self._slew_to(
            getattr(self.rem, self.ptg_name).cmd_startTracking,
            slew_timeout=slew_timeout,
            check=check,
        )

    async def slew_object(
        self,
        name: str,
        rot: float = 0.0,
        rot_type: RotType = RotType.SkyAuto,
        dra: float = 0.0,
        ddec: float = 0.0,
        offset_x: float = 0.0,
        offset_y: float = 0.0,
        az_wrap_strategy: typing.Optional[enum.IntEnum] = None,
        time_on_target: float = 0.0,
        slew_timeout: float = 240.0,
    ) -> typing.Tuple[ICRS, Angle]:
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
        offset_x : `float`, optional
            Apply offset to original slew position (in arcsec).
        offset_y : `float`, optional
            Apply offset to original slew position (in arcsec).
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

        radec_icrs = self.object_list_get(name)

        self.log.info(
            f"Slewing to {name}: {radec_icrs.ra.to_string()} {radec_icrs.dec.to_string()}"
        )

        return await self.slew_icrs(
            ra=radec_icrs.ra.hour,
            dec=radec_icrs.dec.deg,
            rot=rot,
            rot_type=rot_type,
            target_name=name,
            dra=dra,
            ddec=ddec,
            offset_x=offset_x,
            offset_y=offset_y,
            az_wrap_strategy=az_wrap_strategy,
            time_on_target=time_on_target,
            slew_timeout=slew_timeout,
        )

    async def slew_icrs(
        self,
        ra: float,
        dec: float,
        rot: float = 0.0,
        rot_type: RotType = RotType.SkyAuto,
        target_name: str = "slew_icrs",
        dra: float = 0.0,
        ddec: float = 0.0,
        offset_x: float = 0.0,
        offset_y: float = 0.0,
        az_wrap_strategy: enum.IntEnum | None = None,
        time_on_target: float = 0.0,
        slew_timeout: float = 240.0,
        stop_before_slew: bool = False,
        wait_settle: bool = True,
    ) -> typing.Tuple[ICRS, Angle]:
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
        offset_x : `float`, optional
            Apply offset to original slew position (in arcsec).
        offset_y : `float`, optional
            Apply offset to original slew position (in arcsec).
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

        current_time = astropy_time_from_tai_unix(current_tai())

        current_time.location = self.location

        par_angle = calculate_parallactic_angle(
            self.location,
            current_time.sidereal_time("mean"),
            radec_icrs,
        )

        alt_az = self.azel_from_radec(
            ra=radec_icrs.ra, dec=radec_icrs.dec, time=current_time
        )

        rot_frame = self.RotFrame.TARGET
        rot_track_frame = self.RotFrame.TARGET

        # compute rotator physical position if rot_angle is sky.
        rot_phys_val = angle_wrap_center(
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
                rot_angle = angle_wrap_center(Angle(180.0, unit=u.deg) + rot_angle)
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

        slew_exception: typing.Union[None, Exception] = None

        for rot_angle_to_try in self.get_rot_angle_alternatives(rot_angle.deg):
            try:
                await self.slew(
                    radec_icrs.ra.hour,
                    radec_icrs.dec.deg,
                    rotPA=rot_angle_to_try,
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
                    offset_x=offset_x,
                    offset_y=offset_y,
                )
            except salobj.AckError as ack_error:
                if "rotator position angle out of range" in ack_error.ackcmd.result:
                    self.log.warning(
                        "Target out of rotator limit. Trying different angle."
                    )
                    continue
                elif "Target out of rotator limit" in ack_error.ackcmd.result:
                    self.log.warning(
                        "Target out of rotator limit. Trying different angle."
                    )
                    continue
                elif "out of slew limit margin" in ack_error.ackcmd.result:
                    self.log.warning(
                        "Target out of rotator slew limit margin. Trying different angle."
                    )
                    continue
                else:
                    raise ack_error
            except Exception as e:
                slew_exception = e
                break
            else:
                if self._overslew_az:
                    try:
                        overslew_az = 1.5 * 3600.0 * np.cos(alt_az.alt.rad)
                        self.log.info(
                            "Overslew Azimuth feature is enabled. Slewing past target position by"
                            f"{(overslew_az/3600.):.1f} degrees and waiting for settle."
                        )
                        await asyncio.sleep(self.tel_settle_time)
                        await self.offset_azel(az=overslew_az, el=0, relative=False)
                        await asyncio.sleep(self.tel_settle_time)
                        self.log.info("Slewing back to target position.")
                        await self.offset_azel(az=0, el=0, relative=False)
                    except salobj.AckError as ack_error:
                        if (
                            "out of range"
                            or "out of slew limit" in ack_error.ackcmd.result
                        ):
                            self.log.warning(
                                "Overslew is out of operational limits. Skipping overslew."
                            )
                            continue
                        else:
                            raise ack_error
                break
        if slew_exception is not None:
            raise slew_exception

        return radec_icrs, rot_angle

    async def slew(
        self,
        ra: float,
        dec: float,
        rotPA: float = 0.0,
        target_name: str = "slew_icrs",
        frame: typing.Optional[enum.IntEnum] = None,
        epoch: float = 2000.0,
        equinox: float = 2000.0,
        parallax: float = 0.0,
        pmRA: float = 0.0,
        pmDec: float = 0.0,
        rv: float = 0.0,
        dRA: float = 0.0,
        dDec: float = 0.0,
        rot_frame: typing.Optional[enum.IntEnum] = None,
        rot_track_frame: typing.Optional[enum.IntEnum] = None,
        rot_mode: typing.Optional[enum.IntEnum] = None,
        az_wrap_strategy: typing.Optional[enum.IntEnum] = None,
        time_on_target: float = 0.0,
        slew_timeout: float = 1200.0,
        stop_before_slew: bool = False,
        wait_settle: bool = True,
        offset_x: float = 0.0,
        offset_y: float = 0.0,
    ) -> None:
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
                rotStartFrame=(
                    rot_frame if rot_frame is not None else self.RotFrame.TARGET
                ),
                rotTrackFrame=(
                    rot_track_frame
                    if rot_track_frame is not None
                    else self.RotFrame.TARGET
                ),
                azWrapStrategy=(
                    self.WrapStrategy.MAXTIMEONTARGET
                    if az_wrap_strategy is None
                    else az_wrap_strategy
                ),
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

        getattr(self.rem, self.ptg_name).cmd_poriginOffset.set(
            dx=offset_x * self.plate_scale,
            dy=offset_y * self.plate_scale,
            num=0,
        )

        try:
            await self._slew_to(
                getattr(self.rem, self.ptg_name).cmd_raDecTarget,
                slew_timeout=slew_timeout,
                offset_cmd=getattr(self.rem, self.ptg_name).cmd_poriginOffset,
                stop_before_slew=stop_before_slew,
                wait_settle=wait_settle,
            )
        except salobj.AckError as ack_err:
            self.log.error(
                f"Command to track target {target_name} rejected: {ack_err.ackcmd.result}"
            )
            raise ack_err

    async def slew_to_planet(
        self, planet: enum.IntEnum, rot_sky: float = 0.0, slew_timeout: float = 1200.0
    ) -> None:
        """Slew and track a solar system body.

        Parameters
        ----------
        planet : `enum.IntEnum`
            Enumeration with planet name.
        rot_sky : `float`
            Desired instrument position angle (degree), Eastwards from North.
        slew_timeout : `float`, optional
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

    async def slew_ephem_target(
        self,
        ephem_file: str,
        target_name: str,
        rot_sky: float = 0.0,
        validate_only: bool = False,
        slew_timeout: float = 240.0,
    ) -> None:
        """
        Slew the telescope to a target defined by ephemeris data defined
        in a file.

        Parameters
        ----------
        ephem_file : str
            Name of the file containing ephemeris data.
        target_name : str
            Target name.
        rot_sky : float
            Desired instrument position angle (degree), Eastwards from North.
            Default is 0.0.
        validate_only : bool, optional
            If True, validate the target without changing the current demand.
            Default is False.
        slew_timeout : float, optional
            Timeout for the slew command in seconds, default is 1200
            seconds (20 minutes).
        """

        # Access the ephemTarget command from the pointing component
        ptg = getattr(self.rem, self.ptg_name)

        # Setting parameters. Not dealing with validation now.
        ptg.cmd_ephemTarget.set(
            ephemFile=ephem_file,
            targetName=target_name,
            dRA=0.0,
            dDec=0.0,
            rotPA=Angle(rot_sky, unit=u.deg).deg,
            validateOnly=validate_only,
            timeout=slew_timeout,
        )

        await self._slew_to(ptg.cmd_ephemTarget, slew_timeout=slew_timeout)
        self.log.info(f"Telescope slewed to target {target_name} using ephemeris data.")

    async def offset_radec(self, ra: float, dec: float, absorb: bool = False) -> None:
        """Offset telescope in RA and Dec.

        Perform arc-length offset in sky coordinates. The magnitude of the
        offset is sqrt(ra^2 + dec^2) and the angle is the usual atan2(dec, ra).

        Parameters
        ----------
        ra : `float`
            Offset in ra (arcsec).
        dec : `float` or `str`
            Offset in dec (arcsec).
        absorb : `bool`, optional
            Should the offset be absorbed and persisted between slews?
            (default: `False`)

        See Also
        --------
        offset_azel : Offset in local AzEl coordinates.
        offset_xy : Offsets in the detector X/Y plane.

        """
        self.log.debug(
            f"Applying RA/Dec offset: {ra}/{dec}{' (absorb)' if absorb else ''}"
        )

        await self._offset(
            offset_cmd=getattr(self.rem, self.ptg_name).cmd_offsetRADec.set_start(
                type=1, off1=ra, off2=dec, num=0
            )
        )

        if absorb:
            self.log.debug("Absorbing RA/Dec offset into pointing model")
            await getattr(self.rem, self.ptg_name).cmd_offsetAbsorb.set_start(
                num=0, timeout=self.fast_timeout
            )

    async def offset_azel(
        self,
        az: float,
        el: float,
        relative: bool = True,
        persistent: typing.Optional[bool] = None,
        absorb: bool = False,
    ) -> None:
        """Offset telescope in azimuth and elevation.

        For more information see the Notes section below or the package
        documentation in https://ts-observatory-control.lsst.io/.

        Parameters
        ----------
        az : `float`
            Offset in azimuth (arcsec).
        el : `float`
            Offset in elevation (arcsec).
        relative : `bool`, optional
            If `True` (default) offset is applied relative to the current
            position, if `False` offset replaces any existing offsets.
        persistent : `bool` or `None`, optional (deprecated)
            (Deprecated) Should the offset be absorbed and persisted between
            slews? Use of this parameter is deprecated. Use `absorb` instead.
        absorb : `bool`, optional
            Should the offset be absorbed and persisted between slews?
            (default: `False`)

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
                [self.parity_x * el, self.parity_y * az, 0.0],
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

    async def offset_xy(
        self,
        x: float,
        y: float,
        relative: bool = True,
        persistent: bool | None = None,
        absorb: bool = False,
    ) -> None:
        """Offsets in the detector X/Y plane.

        Offset the telescope field-of-view in the x and y direction.

        Parameters
        ----------
        x : `float`
            Offset in camera x-axis (arcsec).
        y : `float`
            Offset in camera y-axis (arcsec).
        relative : `bool`, optional
            If `True` (default) offset is applied relative to the current
            position, if `False` offset replaces any existing offsets.
        persistent : `bool` or `None`, optional (deprecated)
            (Deprecated) Should the offset be absorbed and persisted between
            slews? Use of this parameter is deprecated. Use `absorb` instead.
        absorb : `bool`, optional
            Should the offset be absorbed and persisted between slews?
            (default: `False`)

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

        If the image is displayed with y-axis in vertical position, increasing
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

    async def offset_rot(self, rot: float) -> None:
        """Apply a rotation offset.

        Parameters
        ----------
        rot : `float`
            Rotator offset (deg).
        """

        self.log.debug(f"Offset rotator position by {rot} deg.")

        await self._offset(
            offset_cmd=getattr(self.rem, self.ptg_name).cmd_rotOffset.set_start(
                iaa=rot,
                timeout=self.fast_timeout,
            )
        )

    async def offset_pa(self, angle: float, radius: float) -> None:
        """Offset the telescope based on a position angle and radius.

        Parameters
        ----------
        angle :  `float`
            Offset position angle, clockwise from North (degrees).
        radius : `float`
            Radial offset relative to target position (arcsec).
        """
        self.log.debug(f"Offset PA {angle=} deg, {radius=} arcsec.")

        await self._offset(
            offset_cmd=getattr(self.rem, self.ptg_name).cmd_offsetPA.set_start(
                angle=angle,
                radius=radius,
                timeout=self.fast_timeout,
            )
        )

    async def reset_offsets(
        self, absorbed: bool = True, non_absorbed: bool = True
    ) -> None:
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

    async def add_point_data(self) -> None:
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

    async def stop_tracking(self) -> None:
        """Task to stop telescope tracking."""

        self.log.debug("Stop tracking.")

        await getattr(self.rem, self.ptg_name).cmd_stopTracking.start(
            timeout=self.fast_timeout
        )

        await self.wait_tracking_stopped()

    async def wait_tracking_stopped(self) -> None:
        """Task to wait until tracking has stopped.

        Notes
        -----
        Concrete implementations should override this
        method. By default it is a no-op.
        """
        pass

    async def check_tracking(
        self, track_duration: typing.Optional[float] = None
    ) -> None:
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
        """
        # TODO: Finish implementation of this method (DM-24488).

        task_list: typing.List[asyncio.Task] = []

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

    async def _offset(
        self, offset_cmd: typing.Union[asyncio.Task, asyncio.Future]
    ) -> None:
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

        async with self.ready_to_offset():
            await offset_cmd

        try:
            await self.offset_done()

        except asyncio.TimeoutError:
            self.log.debug("Timed out waiting for offset done events.")

        self.log.debug("Waiting for telescope to settle.")
        await asyncio.sleep(self.tel_settle_time)
        self.log.debug("Done")

    @contextlib.asynccontextmanager
    async def ready_to_offset(self) -> typing.AsyncIterator[None]:
        """A context manager to handle preparing the telescope for offset.

        By default it does nothing.
        """
        yield

    async def ready_to_take_data(self) -> None:
        """Wait for the telescope control system to be ready to take data."""
        if (
            self._ready_to_take_data_task is None
            or self._ready_to_take_data_task.done()
        ):
            self._ready_to_take_data_task = asyncio.create_task(
                self._ready_to_take_data()
            )
        await self._ready_to_take_data_task

    async def enable_dome_following(self, check: typing.Any = None) -> None:
        """Enabled dome following mode."""

        if getattr(self.check if check is None else check, self.dome_trajectory_name):
            self.log.debug("Enable dome trajectory following.")

            await getattr(
                self.rem, self.dome_trajectory_name
            ).cmd_setFollowingMode.set_start(enable=True, timeout=self.fast_timeout)
        else:
            self.log.warning(
                "Dome trajectory check disable. Will not enable following."
            )

    async def disable_dome_following(self, check: typing.Any = None) -> None:
        """Disable dome following mode."""
        if getattr(self.check if check is None else check, self.dome_trajectory_name):
            self.log.debug("Disable dome trajectory following.")

            await getattr(
                self.rem, self.dome_trajectory_name
            ).cmd_setFollowingMode.set_start(enable=False, timeout=self.fast_timeout)
        else:
            self.log.warning(
                "Dome trajectory check disable. Will not disable following."
            )

    async def check_dome_following(self) -> bool:
        """Check if dome following is enabled.

        Returns
        -------
        dome_following : `bool`
            `True` is enabled `False` otherwise.
        """
        dome_followig = await getattr(
            self.rem, self.dome_trajectory_name
        ).evt_followingMode.aget(timeout=self.fast_timeout)

        return dome_followig.enabled

    def azel_from_radec(
        self,
        ra: typing.Union[float, str, Angle],
        dec: typing.Union[float, str, Angle],
        time: typing.Optional[Time] = None,
    ) -> AltAz:
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
            time = astropy_time_from_tai_unix(current_tai())

        time.location = self.location

        coord_frame_azel = AltAz(location=self.location, obstime=time)

        azel = radec_icrs.transform_to(coord_frame_azel)

        return azel

    def radec_from_azel(
        self,
        az: typing.Union[float, str, Angle],
        el: typing.Union[float, str, Angle],
        time: typing.Optional[Time] = None,
    ) -> ICRS:
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
            time = astropy_time_from_tai_unix(current_tai())

        time.location = self.location

        coord_frame_azel = SkyCoord(
            AltAz(
                alt=Angle(el, unit=u.deg),
                az=Angle(az, unit=u.deg),
                location=self.location,
                obstime=time,
            )
        )

        radec_icrs = coord_frame_azel.transform_to(ICRS)

        return radec_icrs

    def parallactic_angle(
        self,
        ra: typing.Union[float, str, Angle],
        dec: typing.Union[float, str, Angle],
        time: typing.Optional[Time] = None,
    ) -> Angle:
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
            time = astropy_time_from_tai_unix(current_tai())

        time.location = self.location

        pa_angle = calculate_parallactic_angle(
            self.location,
            time.sidereal_time("mean"),
            radec_icrs,
        )

        return pa_angle

    async def find_target(
        self,
        az: float,
        el: float,
        mag_limit: float,
        mag_range: float = 2.0,
        radius: float = 0.5,
    ) -> Table:
        """Make a cone search and return a target close to the specified
        position.

        Parameters
        ----------
        az: `float`
            Azimuth (in degrees).
        el: `float`
            Elevation (in degrees).
        mag_limit: `float`
            Minimum (brightest) V-magnitude limit.
        mag_range: `float`, optional
            Magnitude range. The maximum/faintest limit is defined as
            mag_limit+mag_range (default=2).
        radius: `float`, optional
            Radius of the cone search (default=2 degrees).

        Returns
        -------
        target : `astropy.Table`
            Target information.
        """

        target = None

        if self.is_catalog_loaded():
            self.log.debug("Searching internal catalog.")
            try:
                target = await self.find_target_local_catalog(
                    az=az,
                    el=el,
                    mag_limit=mag_limit,
                    mag_range=mag_range,
                    radius=radius,
                )
            except RuntimeError:
                self.log.info(
                    "Could not find suitable target in local catalog. Continue and try with Simbad."
                )

        if target is None:
            try:
                target = await self.find_target_simbad(
                    az=az,
                    el=el,
                    mag_limit=mag_limit,
                    mag_range=mag_range,
                    radius=radius,
                )
            except Exception as e:
                if DM_STACK_AVAILABLE:
                    self.log.warning(
                        "Failed to find target in Simbad. Searching DM Butler (this can take some time)."
                    )
                    target = await self.find_target_dm_butler(
                        az=az,
                        el=el,
                        mag_limit=mag_limit,
                        mag_range=mag_range,
                        radius=radius,
                    )
                else:
                    raise e

        return target

    async def find_target_simbad(
        self,
        az: float,
        el: float,
        mag_limit: float,
        mag_range: float = 2.0,
        radius: float = 0.5,
    ) -> str:
        """Make a cone search in the HD catalog using Simbad and return a
        target with magnitude inside the magnitude range, close to the
        specified position.

        Parameters
        ----------
        az: `float`
            Azimuth (in degrees).
        el: `float`
            Elevation (in degrees).
        mag_limit: `float`
            Minimum (brightest) V-magnitude limit.
        mag_range: `float`, optional
            Magnitude range. The maximum/faintest limit is defined as
            mag_limit+mag_range (default=2).
        radius: `float`, optional
            Radius of the cone search (default=2 degrees).

        Returns
        -------
        `str`
            Name of the target.

        Raises
        ------
        RuntimeError:
            If no object is found.
        """

        customSimbad = Simbad()

        customSimbad.add_votable_fields("V", "rvz_redshift", "ident")
        customSimbad.TIMEOUT = self.long_long_timeout

        radec = self.radec_from_azel(az=az, el=el)

        # Build the ADQL-like criteria for V magnitude + HD catalog
        criteria = (
            f"V>{mag_limit} AND V<{mag_limit + mag_range} AND ident.id LIKE 'HD%'"
        )

        query_callable = partial(
            customSimbad.query_region,
            coordinates=radec,
            radius=radius * u.deg,
            criteria=criteria,
        )

        loop = asyncio.get_event_loop()
        try:
            result_table = await loop.run_in_executor(None, query_callable)
        except Exception as e:
            self.log.exception("Querying Simbad failed.")
            raise RuntimeError(f"Query region for {radec} failed: {e!r}")

        if result_table is None or len(result_table) == 0:
            raise RuntimeError(f"No results found for region around {radec}.")

        result_table.sort("V")

        if "id" in result_table.colnames:
            target_ident_id = str(result_table["id"][0])
        elif "main_id" in result_table.colnames:
            target_ident_id = str(result_table["main_id"][0])
        elif "ident.id" in result_table.colnames:
            target_ident_id = str(result_table["ident.id"][0])
        else:
            raise KeyError(
                f"No suitable identifier column found in Simbad search for {radec}"
            )

        radec_icrs = ICRS(
            ra=Angle(result_table[0]["ra"], unit=u.deg),
            dec=Angle(result_table[0]["dec"], unit=u.deg),
        )

        self.object_list_add(f"{target_ident_id}".rstrip(), radec_icrs)

        return f"{target_ident_id}".rstrip()

    async def find_target_local_catalog(
        self,
        az: float,
        el: float,
        mag_limit: float,
        mag_range: float = 2.0,
        radius: float = 0.5,
    ) -> str:
        """Make a cone search in the internal catalog and return a target in
        the magnitude range, close to the specified position.

        Parameters
        ----------
        az: `float`
            Azimuth (in degrees).
        el: `float`
            Elevation (in degrees).
        mag_limit: `float`
            Minimum (brightest) V-magnitude limit.
        mag_range: `float`, optional
            Magnitude range. The maximum/faintest limit is defined as
            mag_limit+mag_range (default=2).
        radius: `float`, optional
            Radius of the cone search (default=2 degrees).

        Returns
        -------
        `str`
            Name of the target.

        Raises
        ------
        RuntimeError:
            If catalog is not loaded.
            If no object is found.
        """

        assert self._catalog_coordinates is not None, (
            "Catalog not loaded. Load a catalog with `load_catalog` before "
            "calling `find_target_local_catalog`."
        )

        radec_as_sky_coord = SkyCoord(self.radec_from_azel(az=az, el=el))

        mask_magnitude = np.bitwise_and(
            self._catalog["FLUX_V"] >= mag_limit,
            self._catalog["FLUX_V"] <= mag_limit + mag_range,
        )

        if np.sum(mask_magnitude) == 0:
            raise RuntimeError(
                f"No target in local catalog with magnitude between {mag_limit} and {mag_limit+mag_range}."
            )

        match = radec_as_sky_coord.match_to_catalog_sky(
            self._catalog_coordinates[mask_magnitude]
        )

        target_index = int(match[0])

        target = self._catalog[mask_magnitude][target_index]

        target_name = target["MAIN_ID"]

        if match[1][0] > radius * u.deg:
            raise RuntimeError(
                "Could not find a valid target in the specified radius. "
                f"Closest target is {target_name}, {match[1][0]:.2f} away."
            )

        radec_icrs = ICRS(
            ra=Angle(target["RA"], unit=u.hourangle),
            dec=Angle(target["DEC"], unit=u.deg),
        )
        self.object_list_add(target_name, radec_icrs)

        return target_name

    async def find_target_dm_butler(
        self,
        az: float,
        el: float,
        mag_limit: float,
        mag_range: float = 2.0,
        radius: float = 0.5,
    ) -> str:
        """Make a cone search in the butler source catalog and return a target
        in the magnitude range, close to the specified position.

        Parameters
        ----------
        az: `float`
            Azimuth (in degrees).
        el: `float`
            Elevation (in degrees).
        mag_limit: `float`
            Minimum (brightest) V-magnitude limit.
        mag_range: `float`, optional
            Magnitude range. The maximum/faintest limit is defined as
            mag_limit+mag_range (default=2).
        radius: `float`, optional
            Radius of the cone search (default=2 degrees).

        Returns
        -------
        `str`
            Name of the target.

        Raises
        ------
        RuntimeError:
            If DM stack is not available.
        """
        if not DM_STACK_AVAILABLE:
            raise RuntimeError("DM stack not available.")

        from lsst.ts.observatory.control.utils.extras.dm_target_catalog import (
            find_target_radec,
        )

        radec_search = self.radec_from_azel(az=az, el=el)

        target = find_target_radec(
            radec=radec_search,
            radius=Angle(radius, unit=u.deg),
            mag_limit=(mag_limit, mag_limit + mag_range),
        )

        ra_rep = target.ra.to_string(unit=u.hourangle, sep="", precision=2, pad=True)
        dec_recp = target.dec.to_string(sep="", precision=2, alwayssign=True, pad=True)
        target_name = f"GAIAJ{ra_rep}{dec_recp}"

        self.object_list_add(target_name, target)

        return target_name

    def _query_object(self, object_name: str) -> Table:
        """Get an object from its name.

        Parameters
        ----------
        object_name : `str`
            Object nade identifier as it appears in the internal catalog or a
            valid Simbad identifier.

        Returns
        -------
        `Table`
            Object information.
        """
        if self.is_catalog_loaded() and object_name in self._catalog["MAIN_ID"]:
            self.log.debug(f"Found {object_name} in internal catalog.")
            return self._catalog[self._catalog["MAIN_ID"] == object_name]
        else:
            self.log.debug(
                f"Object {object_name} not in internal catalog. Querying Simbad."
            )

            return self._query_object_from_simbad(object_name)

    def _query_object_from_simbad(self, object_name: str) -> Table:
        """Query object name from simbad.

        Parameters
        ----------
        object_name : `str`
            Object nade identifier as it appears in the internal catalog or a
            valid Simbad identifier.

        Returns
        -------
        target_info : `Table`
            Object information.

        Raises
        ------
        RuntimeError
            If no target is found.
        """
        target_info = Simbad.query_object(object_name)

        if target_info is None:
            raise RuntimeError(f"Could not find {object_name} in Simbad database.")
        return target_info

    async def _handle_in_position(
        self,
        in_position_event: salobj.type_hints.BaseMsgType,
        timeout: float,
        settle_time: float = 5.0,
        component_name: str = "",
        race_condition_timeout: float = 5.0,
        unreliable_in_position: bool = False,
    ) -> str:
        """Handle inPosition event.

        Parameters
        ----------
        in_position_event : `object`
            A reference to the in position event.
        timeout: `float`
            How long to wait for in position (in seconds).
        settle_time: `float`, optional
            Additional time to wait once in position (in seconds).
        component_name : `str`, optional
            The name of the component. This is used in log messages and to
            construct a return message when in position.
        race_condition_timeout : `float`
            Timeout to use when handling race condition (in seconds).

        Returns
        -------
        str
            Message indicating the component is in position.
        """
        self.log.debug(
            f"Wait for {component_name} in position event, (timeout={timeout}s)."
        )

        in_position_event.flush()
        try:
            in_position = await in_position_event.aget(timeout=self.fast_timeout)
        except asyncio.TimeoutError as e:
            raise RuntimeError(
                f"Timed out waiting for initial in position event from {component_name}."
            ) from e

        self.log.debug(f"{component_name} in position: {in_position.inPosition}.")

        _settle_time = max([settle_time, race_condition_timeout])

        if in_position.inPosition:
            self.log.debug(
                f"{component_name} already in position. Handling potential race condition."
            )
            try:
                in_position = await in_position_event.next(
                    flush=True,
                    timeout=_settle_time,
                )
                self.log.info(
                    f"{component_name} in position: {in_position.inPosition}."
                )
            except asyncio.TimeoutError:
                self.log.debug(
                    "No new in position event in the last "
                    f"{_settle_time}s. "
                    f"Assuming {component_name} in position."
                )
            except Exception:
                self.log.exception("Error handling potential race condition.")

        while not in_position.inPosition:
            in_position = await in_position_event.next(flush=False, timeout=timeout)
            if unreliable_in_position:
                self.log.info(
                    f"Handling unreliable in position event for {component_name}: {in_position.inPosition}."
                )
                try:
                    in_position = await in_position_event.next(
                        flush=False, timeout=settle_time
                    )
                    self.log.info(
                        f"Got {in_position.inPosition} while handling unreliable "
                        f"in position for {component_name}."
                    )
                except asyncio.TimeoutError:
                    self.log.debug(
                        "No new in position event while handling unreliable in position."
                    )
            else:
                self.log.info(
                    f"{component_name} in position: {in_position.inPosition}."
                )

        self.log.debug(
            f"{component_name} in position {in_position.inPosition}. "
            f"Waiting settle time {settle_time}s"
        )
        await asyncio.sleep(settle_time)

        return f"{component_name} in position."

    def get_rot_angle_alternatives(
        self, rot_angle: float
    ) -> typing.Generator[float, None, None]:
        """Generate rotator angle alternatives based on the input rotator
        angle.

        Parameters
        ----------
        rot_angle : `float`
            Desired rotator angle (in deg).

        Yields
        ------
        `float`
            Rotator angle alternatives (in deg).
        """

        yield rot_angle

        for rot_angle_alternative in self._rot_angle_alternatives:
            yield rot_angle + rot_angle_alternative

    def set_rot_angle_alternatives(
        self, rot_angle_alternatives: typing.List[float]
    ) -> None:
        """Set the rotator angle alternatives.

        It is not necessary to pass the 0. alternative, as it is added by
        default.

        Duplicated entries are also removed.

        Parameters
        ----------
        rot_angle_alternatives : typing.List[float]
            List of rotator angle alternatives (in deg).
        """

        self._rot_angle_alternatives = []

        [
            self._rot_angle_alternatives.append(rot_angle)  # type: ignore
            for rot_angle in rot_angle_alternatives
            if rot_angle != 0 and rot_angle not in self._rot_angle_alternatives
        ]

    def get_telescope_and_dome_vent_azimuth(self) -> tuple[float, float]:
        """Get the telescope and dome vent azimuth.

        Returns
        -------
        tel_vent_azimuth : `float`
            Azimuth to vent the telescope (in deg).
        dome_vent_azimuth : `float`
            Azimuth to vent the dome (in deg).
        """

        sun_az, _ = self.get_sun_azel()

        dome_vent_azimuth = Angle(sun_az - 180.0, unit=u.deg).wrap_at("360d").deg
        telescope_vent_azimuth = (
            Angle(dome_vent_azimuth - 90.0, unit=u.deg).wrap_at("180d").deg
        )

        return telescope_vent_azimuth, dome_vent_azimuth

    def get_sun_azel(self, time_tai: float | None = None) -> tuple[float, float]:
        """Get the sun azimuth and elevation.

        Parameters
        ----------
        time_tai : `float` or `None`, optional
            TAI timestamp to get sun position. If `None` compute current tai.

        Returns
        -------
        `tuple`[`float`, `float`]
            Sun elevation and azimuth in degrees.
        """

        sun_coordinates = get_sun(
            astropy_time_from_tai_unix(current_tai() if time_tai is None else time_tai)
        )
        sun_coordinates.location = self.location

        return sun_coordinates.altaz.az.value, sun_coordinates.altaz.alt.value

    @property
    def instrument_focus(self) -> InstrumentFocus:
        return self.__instrument_focus

    @instrument_focus.setter
    def instrument_focus(self, value: typing.Union[int, InstrumentFocus]) -> None:
        self.__instrument_focus = InstrumentFocus(value)

    @staticmethod
    def rotation_matrix(angle: float) -> npt.ArrayLike:
        """Rotation matrix."""
        return np.array(
            [
                [np.cos(np.radians(angle)), -np.sin(np.radians(angle)), 0.0],
                [np.sin(np.radians(angle)), np.cos(np.radians(angle)), 0.0],
                [0.0, 0.0, 1.0],
            ]
        )

    @abc.abstractmethod
    async def monitor_position(self, check: typing.Any = None) -> None:
        """Monitor and log the position of the telescope and the dome.

        Parameters
        ----------
        check : `types.SimpleNamespace` or `None`
            Override `self.check` for defining which resources are used.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    async def slew_dome_to(self, az: float, check: typing.Any = None) -> None:
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
    async def prepare_for_flatfield(self, check: typing.Any = None) -> None:
        """A high level method to position the telescope and dome for flat
        field operations.

        Parameters
        ----------
        check : `types.SimpleNamespace` or `None`
            Override `self.check` for defining which resources are used.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    async def stop_all(self) -> None:
        """Stop telescope and dome."""
        raise NotImplementedError()

    @abc.abstractmethod
    async def prepare_for_onsky(
        self, overrides: typing.Optional[typing.Dict[str, str]] = None
    ) -> None:
        """Prepare telescope for on-sky operations.

        Parameters
        ----------
        overrides: `dict`
            Dictionary with overrides to apply.  If `None` use the recommended
            overrides.
        """
        raise NotImplementedError

    @abc.abstractmethod
    async def shutdown(self) -> None:
        """Shutdown components."""
        raise NotImplementedError()

    @abc.abstractmethod
    async def open_dome_shutter(self) -> None:
        """Task to open dome shutter and return when it is done."""
        raise NotImplementedError()

    @abc.abstractmethod
    async def home_dome(self) -> None:
        """Task to execute dome home command and wait for it to complete."""
        raise NotImplementedError()

    @abc.abstractmethod
    async def close_dome(self) -> None:
        """Task to close dome."""
        raise NotImplementedError()

    @abc.abstractmethod
    async def open_m1_cover(self) -> None:
        """Task to open m1 cover."""
        raise NotImplementedError()

    @abc.abstractmethod
    async def close_m1_cover(self) -> None:
        """Task to close m1 cover."""
        raise NotImplementedError()

    @abc.abstractmethod
    async def _slew_to(
        self,
        slew_cmd: typing.Any,
        slew_timeout: float,
        offset_cmd: typing.Any = None,
        stop_before_slew: bool = False,
        wait_settle: bool = True,
        check: typing.Any = None,
    ) -> None:
        """Encapsulate "slew" activities.

        Parameters
        ----------
        slew_cmd: `coro`
            One of the slew commands from the ptg remote. Command need to be
            setup before calling this method.
        slew_time: `float`
            Expected slew time in seconds.
        offset_cmd: `coro`
            One of the offset commands from the ptg remote. Command need to be
            setup before calling this method.
        stop_before_slew: `bool`
            Stop tracking before slewing?
        wait_settle: `bool`
            After slew complets, add an addional settle wait before returning.
        check : `types.SimpleNamespace` or `None`, optional
            Override internal `check` attribute with a user-provided one.
            By default (`None`) use internal attribute.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    async def wait_for_inposition(
        self,
        timeout: float,
        wait_settle: bool,
        check: typing.Optional[typing.Any] = None,
    ) -> typing.List[str]:
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
    def set_azel_slew_checks(self, wait_dome: bool) -> None:
        """Abstract method to handle azEl slew to wait or not for the dome.

        Parameters
        ----------
        wait_dome: `bool`
            Should point_azel wait for the dome?
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def flush_offset_events(self) -> None:
        """Abstract method to flush events before and offset is performed."""
        raise NotImplementedError()

    @abc.abstractmethod
    async def offset_done(self) -> None:
        """Wait for offset events."""
        raise NotImplementedError()

    @abc.abstractmethod
    async def get_bore_sight_angle(self) -> float:
        """Get the instrument bore sight angle with respect to the telescope
        axis.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    async def _ready_to_take_data(self) -> None:
        """Wait until the TCS is ready to take data.

        Raise an exception if something goes wrong while trying to determine
        the condition of the system.
        """
        raise NotImplementedError()

    @property
    @abc.abstractmethod
    def plate_scale(self) -> float:
        """Plate scale in mm/arcsec."""
        raise NotImplementedError()

    @property
    @abc.abstractmethod
    def ptg_name(self) -> str:
        """Return name of the pointing component."""
        raise NotImplementedError()

    @property
    @abc.abstractmethod
    def dome_trajectory_name(self) -> str:
        """Return name of the DomeTrajectory component."""
        raise NotImplementedError()

    @property
    @abc.abstractmethod
    def CoordFrame(self) -> CoordFrameType:
        """Return CoordFrame enumeration."""
        raise NotImplementedError()

    @property
    @abc.abstractmethod
    def RotFrame(self) -> RotFrameType:
        """Return RotFrame enumeration."""
        raise NotImplementedError()

    @property
    @abc.abstractmethod
    def RotMode(self) -> RotModeType:
        """Return RotMode enumeration."""
        raise NotImplementedError()

    @property
    @abc.abstractmethod
    def WrapStrategy(self) -> WrapStrategyType:
        """Return WrapStrategy enumeration"""
        raise NotImplementedError()

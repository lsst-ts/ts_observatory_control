# This file is part of ts_observatory_control
#
# Developed for the Vera Rubin Observatory Data Management System.
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
import copy
import logging
import types
import asyncio
import unittest

import numpy as np

import astropy.units as units
from astropy.coordinates import Angle

from lsst.ts import idl
from lsst.ts import salobj

from lsst.ts.observatory.control.maintel.mtcs import MTCS, MTCSUsages
from lsst.ts.observatory.control.utils import RotType


class TestMTCS(unittest.IsolatedAsyncioTestCase):
    async def test_coord_facility(self):
        az = 0.0
        el = 75.0

        radec = self.mtcs.radec_from_azel(az=az, el=el)

        azel = self.mtcs.azel_from_radec(ra=radec.ra, dec=radec.dec)

        pa = self.mtcs.parallactic_angle(ra=radec.ra, dec=radec.dec)

        self.assertAlmostEqual(
            salobj.angle_diff(az, azel.az.value).value, 0.0, places=1
        )
        self.assertAlmostEqual(el, azel.alt.value, places=1)
        self.assertAlmostEqual(pa.value, 3.12, places=1)

        # Test passing a time that is 60s in the future
        obs_time = salobj.astropy_time_from_tai_unix(salobj.current_tai() + 60.0)

        radec = self.mtcs.radec_from_azel(az=az, el=el, time=obs_time)

        azel = self.mtcs.azel_from_radec(ra=radec.ra, dec=radec.dec, time=obs_time)

        pa = self.mtcs.parallactic_angle(ra=radec.ra, dec=radec.dec, time=obs_time)

        self.assertAlmostEqual(
            salobj.angle_diff(az, azel.az.value).value, 0.0, places=5
        )
        self.assertAlmostEqual(el, azel.alt.value, places=5)
        self.assertAlmostEqual(pa.value, 3.1269, places=2)

    async def test_set_azel_slew_checks(self):

        original_check = copy.copy(self.mtcs.check)

        check = self.mtcs.set_azel_slew_checks(True)

        for comp in self.mtcs.components_attr:
            self.assertEqual(
                getattr(self.mtcs.check, comp), getattr(original_check, comp)
            )

        for comp in {"mtdome", "mtdometrajectory"}:
            self.assertTrue(getattr(check, comp))

        check = self.mtcs.set_azel_slew_checks(False)

        for comp in {"mtdome", "mtdometrajectory"}:
            self.assertFalse(getattr(check, comp))

    async def test_slew_object(self):
        name = "HD 185975"
        ra = "20 28 18.7402"
        dec = "-87 28 19.938"

        await self.mtcs.slew_object(name=name, rot_type=RotType.Sky)

        self.mtcs.rem.mtptg.cmd_raDecTarget.set.assert_called_with(
            ra=Angle(ra, unit=units.hourangle).hour,
            declination=Angle(dec, unit=units.deg).deg,
            targetName=name,
            frame=self.mtcs.CoordFrame.ICRS,
            rotAngle=0.0,
            rotStartFrame=self.mtcs.RotFrame.TARGET,
            rotTrackFrame=self.mtcs.RotFrame.TARGET,
            azWrapStrategy=self.mtcs.WrapStrategy.MAXTIMEONTARGET,
            timeOnTarget=0.0,
            epoch=2000,
            equinox=2000,
            parallax=0,
            pmRA=0,
            pmDec=0,
            rv=0,
            dRA=0.0,
            dDec=0.0,
            rotMode=self.mtcs.RotMode.FIELD,
        )

        self.mtcs.rem.mtptg.cmd_poriginOffset.set.assert_called_with(dx=0, dy=0, num=0)

        self.mtcs.rem.mtptg.cmd_stopTracking.start.assert_called_with(
            timeout=self.mtcs.fast_timeout
        )

        self.mtcs.rem.mtmount.evt_axesInPosition.flush.assert_called()
        self.mtcs.rem.mtrotator.evt_inPosition.flush.assert_called()
        self.mtcs.rem.mtptg.cmd_raDecTarget.start.assert_called()
        self.mtcs.rem.mtptg.cmd_poriginOffset.start.assert_called_with(
            timeout=self.mtcs.fast_timeout
        )

    async def test_slew_icrs(self):

        name = "HD 185975"
        ra = "20:28:18.74"
        dec = "-87:28:19.9"

        await self.mtcs.slew_icrs(
            ra=ra, dec=dec, target_name=name, rot_type=RotType.Sky
        )

        self.mtcs.rem.mtptg.cmd_raDecTarget.set.assert_called_with(
            ra=Angle(ra, unit=units.hourangle).hour,
            declination=Angle(dec, unit=units.deg).deg,
            targetName=name,
            frame=self.mtcs.CoordFrame.ICRS,
            rotAngle=0.0,
            rotStartFrame=self.mtcs.RotFrame.TARGET,
            rotTrackFrame=self.mtcs.RotFrame.TARGET,
            azWrapStrategy=self.mtcs.WrapStrategy.MAXTIMEONTARGET,
            timeOnTarget=0.0,
            epoch=2000,
            equinox=2000,
            parallax=0,
            pmRA=0,
            pmDec=0,
            rv=0,
            dRA=0.0,
            dDec=0.0,
            rotMode=self.mtcs.RotMode.FIELD,
        )

        self.mtcs.rem.mtptg.cmd_poriginOffset.set.assert_called_with(dx=0, dy=0, num=0)

        self.mtcs.rem.mtptg.cmd_stopTracking.start.assert_called_with(
            timeout=self.mtcs.fast_timeout
        )

        self.mtcs.rem.mtmount.evt_axesInPosition.flush.assert_called()
        self.mtcs.rem.mtrotator.evt_inPosition.flush.assert_called()
        self.mtcs.rem.mtptg.cmd_raDecTarget.start.assert_called()
        self.mtcs.rem.mtptg.cmd_poriginOffset.start.assert_called_with(
            timeout=self.mtcs.fast_timeout
        )

    async def test_slew_icrs_no_stop(self):

        name = "HD 185975"
        ra = "20:28:18.74"
        dec = "-87:28:19.9"

        await self.mtcs.slew_icrs(
            ra=ra,
            dec=dec,
            target_name=name,
            stop_before_slew=False,
            rot_type=RotType.Sky,
        )

        self.mtcs.rem.mtptg.cmd_raDecTarget.set.assert_called_with(
            ra=Angle(ra, unit=units.hourangle).hour,
            declination=Angle(dec, unit=units.deg).deg,
            targetName=name,
            frame=self.mtcs.CoordFrame.ICRS,
            rotAngle=0.0,
            rotStartFrame=self.mtcs.RotFrame.TARGET,
            rotTrackFrame=self.mtcs.RotFrame.TARGET,
            azWrapStrategy=self.mtcs.WrapStrategy.MAXTIMEONTARGET,
            timeOnTarget=0.0,
            epoch=2000,
            equinox=2000,
            parallax=0,
            pmRA=0,
            pmDec=0,
            rv=0,
            dRA=0.0,
            dDec=0.0,
            rotMode=self.mtcs.RotMode.FIELD,
        )

        self.mtcs.rem.mtptg.cmd_poriginOffset.set.assert_called_with(dx=0, dy=0, num=0)

        self.mtcs.rem.mtptg.cmd_stopTracking.start.assert_not_called()

        self.mtcs.rem.mtmount.evt_axesInPosition.flush.assert_not_called()
        self.mtcs.rem.mtrotator.evt_inPosition.flush.assert_not_called()

        self.mtcs.rem.mtptg.cmd_raDecTarget.start.assert_called()
        self.mtcs.rem.mtptg.cmd_poriginOffset.start.assert_called_with(
            timeout=self.mtcs.fast_timeout
        )

    async def test_slew_icrs_rot(self):

        name = "HD 185975"
        ra = "20:28:18.74"
        dec = "-87:28:19.9"
        rot = 45.0

        await self.mtcs.slew_icrs(
            ra=ra, dec=dec, rot=rot, rot_type=RotType.Sky, target_name=name
        )

        self.mtcs.rem.mtptg.cmd_raDecTarget.set.assert_called_with(
            ra=Angle(ra, unit=units.hourangle).hour,
            declination=Angle(dec, unit=units.deg).deg,
            targetName=name,
            frame=self.mtcs.CoordFrame.ICRS,
            rotAngle=rot,
            rotStartFrame=self.mtcs.RotFrame.TARGET,
            rotTrackFrame=self.mtcs.RotFrame.TARGET,
            azWrapStrategy=self.mtcs.WrapStrategy.MAXTIMEONTARGET,
            timeOnTarget=0.0,
            epoch=2000,
            equinox=2000,
            parallax=0,
            pmRA=0,
            pmDec=0,
            rv=0,
            dRA=0.0,
            dDec=0.0,
            rotMode=self.mtcs.RotMode.FIELD,
        )

        self.mtcs.rem.mtptg.cmd_poriginOffset.set.assert_called_with(dx=0, dy=0, num=0)

        self.mtcs.rem.mtptg.cmd_stopTracking.start.assert_called_with(
            timeout=self.mtcs.fast_timeout
        )

        self.mtcs.rem.mtmount.evt_axesInPosition.flush.assert_called()
        self.mtcs.rem.mtrotator.evt_inPosition.flush.assert_called()
        self.mtcs.rem.mtptg.cmd_raDecTarget.start.assert_called()
        self.mtcs.rem.mtptg.cmd_poriginOffset.start.assert_called_with(
            timeout=self.mtcs.fast_timeout
        )

    async def test_slew_icrs_rot_physical(self):

        name = "HD 185975"
        ra = "20:28:18.74"
        dec = "-87:28:19.9"
        rot = 45.0

        await self.mtcs.slew_icrs(
            ra=ra, dec=dec, rot=rot, rot_type=RotType.Physical, target_name=name
        )

        self.mtcs.rem.mtptg.cmd_raDecTarget.set.assert_called_with(
            ra=Angle(ra, unit=units.hourangle).hour,
            declination=Angle(dec, unit=units.deg).deg,
            targetName=name,
            frame=self.mtcs.CoordFrame.ICRS,
            rotAngle=rot,
            rotStartFrame=self.mtcs.RotFrame.FIXED,
            rotTrackFrame=self.mtcs.RotFrame.FIXED,
            azWrapStrategy=self.mtcs.WrapStrategy.MAXTIMEONTARGET,
            timeOnTarget=0.0,
            epoch=2000,
            equinox=2000,
            parallax=0,
            pmRA=0,
            pmDec=0,
            rv=0,
            dRA=0.0,
            dDec=0.0,
            rotMode=self.mtcs.RotMode.FIELD,
        )

        self.mtcs.rem.mtptg.cmd_poriginOffset.set.assert_called_with(dx=0, dy=0, num=0)

        self.mtcs.rem.mtptg.cmd_stopTracking.start.assert_called_with(
            timeout=self.mtcs.fast_timeout
        )

        self.mtcs.rem.mtmount.evt_axesInPosition.flush.assert_called()
        self.mtcs.rem.mtrotator.evt_inPosition.flush.assert_called()
        self.mtcs.rem.mtptg.cmd_raDecTarget.start.assert_called()
        self.mtcs.rem.mtptg.cmd_poriginOffset.start.assert_called_with(
            timeout=self.mtcs.fast_timeout
        )

    async def test_slew_icrs_rot_physical_sky(self):

        name = "HD 185975"
        ra = "20:28:18.74"
        dec = "-87:28:19.9"
        rot = 45.0

        await self.mtcs.slew_icrs(
            ra=ra, dec=dec, rot=rot, rot_type=RotType.PhysicalSky, target_name=name
        )

        self.mtcs.rem.mtptg.cmd_raDecTarget.set.assert_called_with(
            ra=Angle(ra, unit=units.hourangle).hour,
            declination=Angle(dec, unit=units.deg).deg,
            targetName=name,
            frame=self.mtcs.CoordFrame.ICRS,
            rotAngle=rot,
            rotStartFrame=self.mtcs.RotFrame.FIXED,
            rotTrackFrame=self.mtcs.RotFrame.TARGET,
            azWrapStrategy=self.mtcs.WrapStrategy.MAXTIMEONTARGET,
            timeOnTarget=0.0,
            epoch=2000,
            equinox=2000,
            parallax=0,
            pmRA=0,
            pmDec=0,
            rv=0,
            dRA=0.0,
            dDec=0.0,
            rotMode=self.mtcs.RotMode.FIELD,
        )

        self.mtcs.rem.mtptg.cmd_poriginOffset.set.assert_called_with(dx=0, dy=0, num=0)

        self.mtcs.rem.mtptg.cmd_stopTracking.start.assert_called_with(
            timeout=self.mtcs.fast_timeout
        )

        self.mtcs.rem.mtmount.evt_axesInPosition.flush.assert_called()
        self.mtcs.rem.mtrotator.evt_inPosition.flush.assert_called()
        self.mtcs.rem.mtptg.cmd_raDecTarget.start.assert_called()
        self.mtcs.rem.mtptg.cmd_poriginOffset.start.assert_called_with(
            timeout=self.mtcs.fast_timeout
        )

    async def test_slew_icrs_with_offset(self):

        name = "HD 185975"
        ra = "20:28:18.74"
        dec = "-87:28:19.9"
        offset_x = 10.0
        offset_y = -10.0

        await self.mtcs.slew_icrs(
            ra=ra,
            dec=dec,
            rot_type=RotType.Sky,
            offset_x=offset_x,
            offset_y=offset_y,
            target_name=name,
        )

        self.mtcs.rem.mtptg.cmd_raDecTarget.set.assert_called_with(
            ra=Angle(ra, unit=units.hourangle).hour,
            declination=Angle(dec, unit=units.deg).deg,
            targetName=name,
            frame=self.mtcs.CoordFrame.ICRS,
            rotAngle=0.0,
            rotStartFrame=self.mtcs.RotFrame.TARGET,
            rotTrackFrame=self.mtcs.RotFrame.TARGET,
            azWrapStrategy=self.mtcs.WrapStrategy.MAXTIMEONTARGET,
            timeOnTarget=0.0,
            epoch=2000,
            equinox=2000,
            parallax=0,
            pmRA=0,
            pmDec=0,
            rv=0,
            dRA=0.0,
            dDec=0.0,
            rotMode=self.mtcs.RotMode.FIELD,
        )

        self.mtcs.rem.mtptg.cmd_poriginOffset.set.assert_called_with(
            dx=offset_x * self.mtcs.plate_scale,
            dy=offset_y * self.mtcs.plate_scale,
            num=0,
        )

        self.mtcs.rem.mtptg.cmd_stopTracking.start.assert_called_with(
            timeout=self.mtcs.fast_timeout
        )

        self.mtcs.rem.mtmount.evt_axesInPosition.flush.assert_called()
        self.mtcs.rem.mtrotator.evt_inPosition.flush.assert_called()
        self.mtcs.rem.mtptg.cmd_raDecTarget.start.assert_called()
        self.mtcs.rem.mtptg.cmd_poriginOffset.start.assert_called_with(
            timeout=self.mtcs.fast_timeout
        )

    async def test_slew_icrs_ccw_following_off(self):

        name = "HD 185975"
        ra = "20:28:18.74"
        dec = "-87:28:19.9"

        self._mtmount_evt_cameraCableWrapFollowing.enabled = 0

        with self.assertRaises(RuntimeError):
            await self.mtcs.slew_icrs(ra=ra, dec=dec, target_name=name)

        self.mtcs.rem.mtptg.cmd_raDecTarget.start.assert_not_awaited()

        self.mtcs.rem.mtptg.cmd_poriginOffset.start.assert_not_awaited()

        self.mtcs.rem.mtptg.cmd_stopTracking.start.assert_not_awaited()

    async def test_point_azel(self):

        az = 180.0
        el = 45.0
        rot_tel = 45
        target_name = "test_position"

        await self.mtcs.point_azel(
            az=az, el=el, rot_tel=rot_tel, target_name=target_name
        )

        self.mtcs.rem.mtptg.cmd_azElTarget.set.assert_called_with(
            targetName=target_name,
            azDegs=az,
            elDegs=el,
            rotPA=rot_tel,
        )

        self.mtcs.rem.mtptg.cmd_poriginOffset.set.assert_not_called()

        self.mtcs.rem.mtptg.cmd_stopTracking.start.assert_called_with(
            timeout=self.mtcs.fast_timeout
        )

        self.mtcs.rem.mtmount.evt_axesInPosition.flush.assert_called()
        self.mtcs.rem.mtrotator.evt_inPosition.flush.assert_called()

    async def test_enable_ccw_following(self):

        await self.mtcs.enable_ccw_following()

        self.mtcs.rem.mtmount.cmd_enableCameraCableWrapFollowing.start.assert_awaited_with(
            timeout=self.mtcs.fast_timeout
        )
        self.assertEqual(self._mtmount_evt_cameraCableWrapFollowing.enabled, 1)

    async def test_disable_ccw_following(self):

        await self.mtcs.disable_ccw_following()

        self.mtcs.rem.mtmount.cmd_disableCameraCableWrapFollowing.start.assert_awaited_with(
            timeout=self.mtcs.fast_timeout
        )
        self.assertEqual(self._mtmount_evt_cameraCableWrapFollowing.enabled, 0)

    async def test_offset_radec(self):

        # Test offset_radec
        ra_offset, dec_offset = 10.0, -10.0
        await self.mtcs.offset_radec(ra=ra_offset, dec=dec_offset)

        self.mtcs.rem.mtptg.cmd_offsetRADec.set_start.assert_called_with(
            type=0, off1=ra_offset, off2=dec_offset, num=0
        )

    async def test_offset_azel(self):

        az_offset, el_offset = 10.0, -10.0

        # Default call should yield relative=True, absorb=False
        await self.mtcs.offset_azel(az=az_offset, el=el_offset)

        self.mtcs.rem.mtptg.cmd_offsetAzEl.set_start.assert_called_with(
            az=az_offset, el=el_offset, num=1
        )

    async def test_offset_azel_with_defaults(self):

        az_offset, el_offset = 10.0, -10.0

        # Same as default but now pass the parameters
        await self.mtcs.offset_azel(
            az=az_offset, el=el_offset, relative=True, absorb=False
        )

        self.mtcs.rem.mtptg.cmd_offsetAzEl.set_start.assert_called_with(
            az=az_offset, el=el_offset, num=1
        )

    async def test_offset_azel_not_relative(self):

        az_offset, el_offset = 10.0, -10.0

        # Call with relative=False
        await self.mtcs.offset_azel(
            az=az_offset, el=el_offset, relative=False, absorb=False
        )

        self.mtcs.rem.mtptg.cmd_offsetAzEl.set_start.assert_called_with(
            az=az_offset, el=el_offset, num=0
        )

    async def test_offset_azel_relative_absorb(self):

        az_offset, el_offset = 10.0, -10.0

        # Call with relative=True and absorb=True
        await self.mtcs.offset_azel(
            az=az_offset, el=el_offset, relative=True, absorb=True
        )

        bore_sight_angle = (
            self._mtmount_tel_elevation.actualPosition
            - self._mtrotator_tel_rotation.actualPosition
        )

        x, y, _ = np.matmul(
            [el_offset, az_offset, 0.0],
            self.mtcs.rotation_matrix(bore_sight_angle),
        )

        self.mtcs.rem.mtptg.cmd_poriginOffset.set_start.assert_called_with(
            dx=x * self.mtcs.plate_scale, dy=y * self.mtcs.plate_scale, num=1
        )

    async def test_offset_azel_absorb(self):

        az_offset, el_offset = 10.0, -10.0

        # Call with relative=False and absorb=True
        await self.mtcs.offset_azel(
            az=az_offset, el=el_offset, relative=False, absorb=True
        )

        bore_sight_angle = (
            self._mtmount_tel_elevation.actualPosition
            - self._mtrotator_tel_rotation.actualPosition
        )

        x, y, _ = np.matmul(
            [el_offset, az_offset, 0.0],
            self.mtcs.rotation_matrix(bore_sight_angle),
        )

        self.mtcs.rem.mtptg.cmd_poriginOffset.set_start.assert_called_with(
            dx=x * self.mtcs.plate_scale, dy=y * self.mtcs.plate_scale, num=0
        )

    async def test_reset_offsets(self):

        await self.mtcs.reset_offsets()

        self.mtcs.rem.mtptg.cmd_poriginClear.set_start.assert_any_call(
            num=0, timeout=self.mtcs.fast_timeout
        )

        self.mtcs.rem.mtptg.cmd_poriginClear.set_start.assert_any_call(
            num=1, timeout=self.mtcs.fast_timeout
        )

        self.mtcs.rem.mtptg.cmd_offsetClear.set_start.assert_any_call(
            num=0, timeout=self.mtcs.fast_timeout
        )

        self.mtcs.rem.mtptg.cmd_offsetClear.set_start.assert_any_call(
            num=1, timeout=self.mtcs.fast_timeout
        )

    async def test_reset_offsets_absorbed(self):

        await self.mtcs.reset_offsets(absorbed=True, non_absorbed=False)

        self.mtcs.rem.mtptg.cmd_poriginClear.set_start.assert_any_call(
            num=0, timeout=self.mtcs.fast_timeout
        )

        self.mtcs.rem.mtptg.cmd_poriginClear.set_start.assert_any_call(
            num=1, timeout=self.mtcs.fast_timeout
        )

        self.mtcs.rem.mtptg.cmd_offsetClear.set_start.assert_not_called()

    async def test_reset_offsets_non_absorbed(self):

        await self.mtcs.reset_offsets(absorbed=False, non_absorbed=True)

        self.mtcs.rem.mtptg.cmd_poriginClear.set_start.assert_not_called()

        self.mtcs.rem.mtptg.cmd_offsetClear.set_start.assert_any_call(
            num=0, timeout=self.mtcs.fast_timeout
        )

        self.mtcs.rem.mtptg.cmd_offsetClear.set_start.assert_any_call(
            num=1, timeout=self.mtcs.fast_timeout
        )

    async def test_offset_xy(self):

        x_offset, y_offset = 10.0, -10.0

        # Default call should yield relative=True, absorb=False
        await self.mtcs.offset_xy(x=x_offset, y=y_offset)

        bore_sight_angle = (
            self._mtmount_tel_elevation.actualPosition
            - self._mtrotator_tel_rotation.actualPosition
        )

        el, az, _ = np.matmul(
            [x_offset, y_offset, 0.0],
            self.mtcs.rotation_matrix(bore_sight_angle),
        )

        self.mtcs.rem.mtptg.cmd_offsetAzEl.set_start.assert_called_with(
            az=az, el=el, num=1
        )

    async def test_offset_xy_with_defaults(self):

        x_offset, y_offset = 10.0, -10.0

        # Same as default but now pass the parameters
        await self.mtcs.offset_xy(x=x_offset, y=y_offset, relative=True, absorb=False)

        bore_sight_angle = (
            self._mtmount_tel_elevation.actualPosition
            - self._mtrotator_tel_rotation.actualPosition
        )

        el, az, _ = np.matmul(
            [x_offset, y_offset, 0.0],
            self.mtcs.rotation_matrix(bore_sight_angle),
        )

        self.mtcs.rem.mtptg.cmd_offsetAzEl.set_start.assert_called_with(
            az=az, el=el, num=1
        )

    async def test_offset_xy_not_relative(self):

        x_offset, y_offset = 10.0, -10.0

        # Call with relative=False
        await self.mtcs.offset_xy(x=x_offset, y=y_offset, relative=False, absorb=False)

        bore_sight_angle = (
            self._mtmount_tel_elevation.actualPosition
            - self._mtrotator_tel_rotation.actualPosition
        )

        el, az, _ = np.matmul(
            [x_offset, y_offset, 0.0],
            self.mtcs.rotation_matrix(bore_sight_angle),
        )

        self.mtcs.rem.mtptg.cmd_offsetAzEl.set_start.assert_called_with(
            az=az, el=el, num=0
        )

    async def test_offset_xy_relative_absorb(self):

        x_offset, y_offset = 10.0, -10.0

        # Call with relative=True and absorb=True
        await self.mtcs.offset_xy(x=x_offset, y=y_offset, relative=True, absorb=True)

        self.mtcs.rem.mtptg.cmd_poriginOffset.set_start.assert_called_with(
            dx=x_offset * self.mtcs.plate_scale,
            dy=y_offset * self.mtcs.plate_scale,
            num=1,
        )

    async def test_offset_xy_absorb(self):

        x_offset, y_offset = 10.0, -10.0

        # Call with relative=False and absorb=True
        await self.mtcs.offset_xy(x=x_offset, y=y_offset, relative=False, absorb=True)

        self.mtcs.rem.mtptg.cmd_poriginOffset.set_start.assert_called_with(
            dx=x_offset * self.mtcs.plate_scale,
            dy=y_offset * self.mtcs.plate_scale,
            num=0,
        )

    async def test_slew_dome_to(self):

        az = 90.0

        with self.assertRaises(NotImplementedError):
            await self.mtcs.slew_dome_to(az)

    async def test_close_dome(self):

        with self.assertRaises(NotImplementedError):
            await self.mtcs.close_dome()

    async def test_open_m1_cover(self):

        with self.assertRaises(NotImplementedError):
            await self.mtcs.open_m1_cover()

    async def test_close_m1_cover(self):

        with self.assertRaises(NotImplementedError):
            await self.mtcs.close_m1_cover()

    async def test_home_dome(self):

        with self.assertRaises(NotImplementedError):
            await self.mtcs.home_dome()

    async def test_open_dome_shutter(self):

        with self.assertRaises(NotImplementedError):
            await self.mtcs.open_dome_shutter()

    async def test_prepare_for_flatfield(self):

        with self.assertRaises(NotImplementedError):
            await self.mtcs.prepare_for_flatfield()

    async def test_prepare_for_onsky(self):

        with self.assertRaises(NotImplementedError):
            await self.mtcs.prepare_for_onsky()

    async def test_shutdown(self):

        with self.assertRaises(NotImplementedError):
            await self.mtcs.shutdown()

    async def test_stop_all(self):

        with self.assertRaises(NotImplementedError):
            await self.mtcs.stop_all()

    async def test_raise_m1m3(self):

        self._mtm1m3_evt_detailed_state.detailedState = (
            idl.enums.MTM1M3.DetailedState.PARKED
        )

        await self.mtcs.raise_m1m3()

        self.mtcs.rem.mtm1m3.evt_detailedState.aget.assert_awaited()
        self.mtcs.rem.mtm1m3.evt_detailedState.flush.assert_called()
        if hasattr(self.mtcs.rem.mtm1m3.cmd_raiseM1M3.DataType(), "raiseM1M3"):
            self.mtcs.rem.mtm1m3.cmd_raiseM1M3.set_start.assert_awaited_with(
                raiseM1M3=True, timeout=self.mtcs.long_timeout
            )
        else:
            self.mtcs.rem.mtm1m3.cmd_raiseM1M3.set_start.assert_awaited_with(
                timeout=self.mtcs.long_timeout
            )
        self.mtcs.rem.mtm1m3.evt_detailedState.next.assert_awaited_with(
            flush=False, timeout=self.mtcs.long_long_timeout
        )

    async def test_raise_m1m3_when_active(self):

        self._mtm1m3_evt_detailed_state.detailedState = (
            idl.enums.MTM1M3.DetailedState.ACTIVE
        )
        await self.mtcs.raise_m1m3()

        self.mtcs.rem.mtm1m3.evt_detailedState.aget.assert_awaited()
        self.mtcs.rem.mtm1m3.evt_detailedState.flush.assert_not_called()
        self.mtcs.rem.mtm1m3.cmd_raiseM1M3.set_start.assert_not_awaited()
        self.mtcs.rem.mtm1m3.evt_detailedState.next.assert_not_awaited()

    async def test_raise_m1m3_aborted(self):

        self._mtm1m3_evt_detailed_state.detailedState = (
            idl.enums.MTM1M3.DetailedState.PARKED
        )

        m1m3_raise_task = asyncio.create_task(self.mtcs.raise_m1m3())

        await asyncio.sleep(2.0)

        await self.execute_abort_raise_m1m3()

        with self.assertRaises(RuntimeError):
            await asyncio.wait_for(m1m3_raise_task, self.mtcs.fast_timeout)

        self.mtcs.rem.mtm1m3.evt_detailedState.aget.assert_awaited()
        self.mtcs.rem.mtm1m3.evt_detailedState.flush.assert_called()
        if hasattr(self.mtcs.rem.mtm1m3.cmd_raiseM1M3.DataType(), "raiseM1M3"):
            self.mtcs.rem.mtm1m3.cmd_raiseM1M3.set_start.assert_awaited_with(
                raiseM1M3=True, timeout=self.mtcs.long_timeout
            )
        else:
            self.mtcs.rem.mtm1m3.cmd_raiseM1M3.set_start.assert_awaited_with(
                timeout=self.mtcs.long_timeout
            )
        self.mtcs.rem.mtm1m3.evt_detailedState.next.assert_awaited_with(
            flush=False, timeout=self.mtcs.long_long_timeout
        )

    async def test_raise_m1m3_not_raisable(self):

        for m1m3_detailed_state in idl.enums.MTM1M3.DetailedState:
            if m1m3_detailed_state not in {
                idl.enums.MTM1M3.DetailedState.ACTIVE,
                idl.enums.MTM1M3.DetailedState.ACTIVEENGINEERING,
                idl.enums.MTM1M3.DetailedState.PARKED,
                idl.enums.MTM1M3.DetailedState.PARKEDENGINEERING,
            }:

                self.log.debug(
                    f"Test m1m3 raise fails if detailed state is {m1m3_detailed_state!r}"
                )
                self._mtm1m3_evt_detailed_state.detailedState = m1m3_detailed_state

                with self.assertRaises(RuntimeError):
                    await self.mtcs.raise_m1m3()

    async def test_lower_m1m3_when_active(self):

        self._mtm1m3_evt_detailed_state.detailedState = (
            idl.enums.MTM1M3.DetailedState.ACTIVE
        )

        await self.mtcs.lower_m1m3()

        self.mtcs.rem.mtm1m3.evt_detailedState.aget.assert_awaited()
        self.mtcs.rem.mtm1m3.evt_detailedState.flush.assert_called()
        if hasattr(self.mtcs.rem.mtm1m3.cmd_lowerM1M3.DataType(), "lowerM1M3"):
            self.mtcs.rem.mtm1m3.cmd_lowerM1M3.set_start.assert_awaited_with(
                lowerM1M3=True, timeout=self.mtcs.long_timeout
            )
        else:
            self.mtcs.rem.mtm1m3.cmd_lowerM1M3.set_start.assert_awaited_with(
                timeout=self.mtcs.long_timeout
            )
        self.mtcs.rem.mtm1m3.evt_detailedState.next.assert_awaited_with(
            flush=False, timeout=self.mtcs.long_long_timeout
        )

    async def test_lower_m1m3_when_parked(self):

        await self.mtcs.lower_m1m3()

        self.mtcs.rem.mtm1m3.evt_detailedState.aget.assert_awaited()
        self.mtcs.rem.mtm1m3.evt_detailedState.flush.assert_not_called()
        self.mtcs.rem.mtm1m3.cmd_lowerM1M3.set_start.assert_not_awaited()
        self.mtcs.rem.mtm1m3.evt_detailedState.next.assert_not_awaited()

    async def test_lower_m1m3_not_lowerable(self):

        for m1m3_detailed_state in idl.enums.MTM1M3.DetailedState:
            if m1m3_detailed_state not in {
                idl.enums.MTM1M3.DetailedState.ACTIVE,
                idl.enums.MTM1M3.DetailedState.ACTIVEENGINEERING,
                idl.enums.MTM1M3.DetailedState.PARKED,
                idl.enums.MTM1M3.DetailedState.PARKEDENGINEERING,
            }:

                self.log.debug(
                    f"Test m1m3 raise fails is detailed state is {m1m3_detailed_state!r}"
                )
                self._mtm1m3_evt_detailed_state.detailedState = m1m3_detailed_state

                with self.assertRaises(RuntimeError):
                    await self.mtcs.raise_m1m3()

    async def test_abort_raise_m1m3(self):

        self._mtm1m3_evt_detailed_state.detailedState = (
            idl.enums.MTM1M3.DetailedState.RAISING
        )

        await self.mtcs.abort_raise_m1m3()

        self.mtcs.rem.mtm1m3.cmd_abortRaiseM1M3.start.assert_awaited_with(
            timeout=self.mtcs.long_timeout
        )
        self.assertEqual(
            self._mtm1m3_evt_detailed_state.detailedState,
            idl.enums.MTM1M3.DetailedState.PARKED,
        )

    async def test_abort_raise_m1m3_active(self):

        self._mtm1m3_evt_detailed_state.detailedState = (
            idl.enums.MTM1M3.DetailedState.ACTIVE
        )

        with self.assertRaises(RuntimeError):
            await self.mtcs.abort_raise_m1m3()

        self.mtcs.rem.mtm1m3.cmd_abortRaiseM1M3.start.assert_not_awaited()

    async def test_abort_raise_m1m3_parked(self):

        self._mtm1m3_evt_detailed_state.detailedState = (
            idl.enums.MTM1M3.DetailedState.PARKED
        )

        await self.mtcs.abort_raise_m1m3()

        self.mtcs.rem.mtm1m3.cmd_abortRaiseM1M3.start.assert_not_awaited()

    def test_check_mtmount_interface(self):

        component = "MTMount"

        self.check_topic_attribute(
            attributes={"actualPosition"}, topic="elevation", component=component
        )
        self.check_topic_attribute(
            attributes={"actualPosition"}, topic="azimuth", component=component
        )
        self.check_topic_attribute(
            attributes={"enabled"},
            topic="logevent_cameraCableWrapFollowing",
            component=component,
        )

    def test_check_mtrotator_interface(self):
        for attribute in {"actualPosition"}:
            self.assertTrue(
                attribute
                in self.components_metadata["MTRotator"]
                .topic_info["rotation"]
                .field_info
            )

    def test_check_mtptg_interface(self):

        for attribute in {
            "ra",
            "declination",
            "targetName",
            "frame",
            "rotAngle",
            "rotStartFrame",
            "rotTrackFrame",
            "azWrapStrategy",
            "timeOnTarget",
            "epoch",
            "equinox",
            "parallax",
            "pmRA",
            "pmDec",
            "rv",
            "dRA",
            "dDec",
            "rotMode",
        }:
            self.assertTrue(
                attribute
                in self.components_metadata["MTPtg"]
                .topic_info["command_raDecTarget"]
                .field_info
            )

        for attribute in {
            "targetName",
            "azDegs",
            "elDegs",
            "rotPA",
        }:
            self.assertTrue(
                attribute
                in self.components_metadata["MTPtg"]
                .topic_info["command_azElTarget"]
                .field_info
            )

        for attribute in {
            "dx",
            "dy",
            "num",
        }:
            self.assertTrue(
                attribute
                in self.components_metadata["MTPtg"]
                .topic_info["command_poriginOffset"]
                .field_info
            )

        for attribute in {"type", "off1", "off2", "num"}:
            self.assertTrue(
                attribute
                in self.components_metadata["MTPtg"]
                .topic_info["command_offsetRADec"]
                .field_info
            )

        for attribute in {"az", "el", "num"}:
            self.assertTrue(
                attribute
                in self.components_metadata["MTPtg"]
                .topic_info["command_offsetAzEl"]
                .field_info
            )

    def check_topic_attribute(self, attributes, topic, component):
        for attribute in attributes:
            self.assertTrue(
                attribute
                in self.components_metadata[component].topic_info[topic].field_info
            )

    @classmethod
    def setUpClass(cls):
        """This classmethod is only called once, when preparing the unit
        test.
        """

        cls.log = logging.getLogger("TestMTCS")

        # Pass in a string as domain to prevent ATCS from trying to create a
        # domain by itself. When using DryTest usage, the class won't create
        # any remote. When this method is called there is no event loop
        # running so all asyncio facilities will fail to create. This is later
        # rectified in the asyncSetUp.
        cls.mtcs = MTCS(
            domain="FakeDomain", log=cls.log, intended_usage=MTCSUsages.DryTest
        )

        # Decrease telescope settle time to speed up unit test
        cls.mtcs.tel_settle_time = 0.25

        # Gather metadada information, needed to validate topics versions
        cls.components_metadata = dict(
            [
                (
                    component,
                    salobj.parse_idl(
                        component,
                        idl.get_idl_dir()
                        / f"sal_revCoded_{component.split(':')[0]}.idl",
                    ),
                )
                for component in cls.mtcs.components
            ]
        )
        cls.track_id_gen = salobj.index_generator(1)

    async def asyncSetUp(self):

        self.mtcs._create_asyncio_events()

        # MTMount data
        self._mtmount_evt_target = types.SimpleNamespace(
            trackId=next(self.track_id_gen),
            azimuth=0.0,
            elevation=80.0,
        )

        self._mtmount_evt_cameraCableWrapFollowing = types.SimpleNamespace(enabled=1)

        self._mtmount_tel_azimuth = types.SimpleNamespace(actualPosition=0.0)
        self._mtmount_tel_elevation = types.SimpleNamespace(actualPosition=80.0)

        self._mtmount_evt_axes_in_position = types.SimpleNamespace(
            elevation=True,
            azimuth=True,
        )

        # MTRotator data
        self._mtrotator_tel_rotation = types.SimpleNamespace(
            demandPosition=0.0,
            actualPosition=0.0,
        )
        self._mtrotator_evt_in_position = types.SimpleNamespace(inPosition=True)

        # MTDome data
        self._mtdome_tel_azimuth = types.SimpleNamespace(
            positionActual=0.0,
            positionCommanded=0.0,
        )

        self._mtdome_tel_light_wind_screen = types.SimpleNamespace(
            positionActual=0.0,
            positionCommanded=0.0,
        )

        # MTM1M3 data
        self._mtm1m3_evt_detailed_state = types.SimpleNamespace(
            detailedState=idl.enums.MTM1M3.DetailedState.PARKED
        )
        self._mtm1m3_raise_task = salobj.make_done_future()
        self._mtm1m3_lower_task = salobj.make_done_future()
        # Setup AsyncMock. The idea is to replace the placeholder for the
        # remotes (in mtcs.rem) by AsyncMock. The remote for each component is
        # replaced by an AsyncMock and later augmented to emulate the behavior
        # of the Remote->Controller interaction with side_effect and
        # return_value.
        for component in self.mtcs.components_attr:
            setattr(self.mtcs.rem, component, unittest.mock.AsyncMock())

        # Setup data to support summary state manipulation
        self.summary_state = dict(
            [
                (comp, types.SimpleNamespace(summaryState=int(salobj.State.ENABLED)))
                for comp in self.mtcs.components_attr
            ]
        )

        self.summary_state_queue = dict(
            [
                (comp, [types.SimpleNamespace(summaryState=int(salobj.State.ENABLED))])
                for comp in self.mtcs.components_attr
            ]
        )

        self.summary_state_queue_event = dict(
            [(comp, asyncio.Event()) for comp in self.mtcs.components_attr]
        )

        # Setup AsyncMock. The idea is to replace the placeholder for the
        # remotes (in atcs.rem) by AsyncMock. The remote for each component is
        # replaced by an AsyncMock and later augmented to emulate the behavior
        # of the Remote->Controller interaction with side_effect and
        # return_value.
        # By default all mocks are augmented to handle summary state setting.
        for component in self.mtcs.components_attr:
            setattr(
                self.mtcs.rem,
                component,
                unittest.mock.AsyncMock(
                    **{
                        "cmd_start.set_start.side_effect": self.set_summary_state_for(
                            component, salobj.State.DISABLED
                        ),
                        "cmd_enable.start.side_effect": self.set_summary_state_for(
                            component, salobj.State.ENABLED
                        ),
                        "cmd_disable.start.side_effect": self.set_summary_state_for(
                            component, salobj.State.DISABLED
                        ),
                        "cmd_standby.start.side_effect": self.set_summary_state_for(
                            component, salobj.State.STANDBY
                        ),
                        "evt_summaryState.next.side_effect": self.next_summary_state_for(
                            component
                        ),
                        "evt_summaryState.aget.side_effect": self.get_summary_state_for(
                            component
                        ),
                        "evt_heartbeat.next.side_effect": self.get_heartbeat,
                        "evt_heartbeat.aget.side_effect": self.get_heartbeat,
                        "evt_settingVersions.aget.return_value": None,
                    }
                ),
            )
            # A trick to support calling a regular method (flush) from an
            # AsyncMock. Basically, attach a regular Mock.
            getattr(self.mtcs.rem, f"{component}").evt_summaryState.attach_mock(
                unittest.mock.Mock(),
                "flush",
            )

        # Augment MTPtg
        self.mtcs.rem.mtptg.attach_mock(
            unittest.mock.AsyncMock(),
            "cmd_raDecTarget",
        )

        self.mtcs.rem.mtptg.cmd_raDecTarget.attach_mock(
            unittest.mock.Mock(
                **{
                    "return_value": types.SimpleNamespace(
                        **self.components_metadata["MTPtg"]
                        .topic_info["command_raDecTarget"]
                        .field_info
                    )
                }
            ),
            "DataType",
        )

        self.mtcs.rem.mtptg.attach_mock(
            unittest.mock.AsyncMock(),
            "cmd_poriginOffset",
        )

        self.mtcs.rem.mtptg.cmd_poriginOffset.attach_mock(
            unittest.mock.Mock(),
            "set",
        )

        self.mtcs.rem.mtptg.cmd_raDecTarget.attach_mock(
            unittest.mock.Mock(),
            "set",
        )

        self.mtcs.rem.mtptg.cmd_azElTarget.attach_mock(
            unittest.mock.Mock(),
            "set",
        )

        # Augment MTMount
        mtmount_mocks = {
            "evt_target.next.side_effect": self.mtmount_evt_target_next,
            "tel_azimuth.next.side_effect": self.mtmount_tel_azimuth_next,
            "tel_elevation.next.side_effect": self.mtmount_tel_elevation_next,
            "tel_elevation.aget.side_effect": self.mtmount_tel_elevation_next,
            "evt_axesInPosition.next.side_effect": self.mtmount_evt_axes_in_position_next,
            "evt_cameraCableWrapFollowing.aget.side_effect": self.mtmount_evt_cameraCableWrapFollowing,
            "cmd_enableCameraCableWrapFollowing.start.side_effect": self.mtmout_cmd_enable_ccw_following,
            "cmd_disableCameraCableWrapFollowing.start.side_effect": self.mtmout_cmd_disable_ccw_following,
        }
        self.mtcs.rem.mtmount.configure_mock(**mtmount_mocks)

        self.mtcs.rem.mtmount.evt_axesInPosition.attach_mock(
            unittest.mock.Mock(),
            "flush",
        )

        # Augment MTRotator
        self.mtcs.rem.mtrotator.configure_mock(
            **{
                "tel_rotation.next.side_effect": self.mtrotator_tel_rotation_next,
                "tel_rotation.aget.side_effect": self.mtrotator_tel_rotation_next,
                "evt_inPosition.next.side_effect": self.mtrotator_evt_in_position_next,
            }
        )

        self.mtcs.rem.mtrotator.evt_inPosition.attach_mock(
            unittest.mock.Mock(),
            "flush",
        )

        # Augment MTDome
        self.mtcs.rem.mtdome.configure_mock(
            **{
                "tel_azimuth.next.side_effect": self.mtdome_tel_azimuth_next,
                "tel_lightWindScreen.next.side_effect": self.mtdome_tel_light_wind_screen_next,
            }
        )

        # Augment MTM1M3
        self.mtcs.rem.mtm1m3.evt_detailedState.attach_mock(
            unittest.mock.Mock(),
            "flush",
        )
        self.mtcs.rem.mtm1m3.cmd_lowerM1M3.attach_mock(
            unittest.mock.Mock(
                return_value=types.SimpleNamespace(
                    **self.components_metadata["MTM1M3"]
                    .topic_info["command_lowerM1M3"]
                    .field_info
                )
            ),
            "DataType",
        )
        self.mtcs.rem.mtm1m3.cmd_raiseM1M3.attach_mock(
            unittest.mock.Mock(
                return_value=types.SimpleNamespace(
                    **self.components_metadata["MTM1M3"]
                    .topic_info["command_raiseM1M3"]
                    .field_info
                )
            ),
            "DataType",
        )
        m1m3_mocks = {
            "evt_detailedState.next.side_effect": self.mtm1m3_evt_detailed_state,
            "evt_detailedState.aget.side_effect": self.mtm1m3_evt_detailed_state,
            "cmd_raiseM1M3.set_start.side_effect": self.mtm1m3_cmd_raise_m1m3,
            "cmd_lowerM1M3.set_start.side_effect": self.mtm1m3_cmd_lower_m1m3,
            "cmd_abortRaiseM1M3.start.side_effect": self.mtm1m3_cmd_abort_raise_m1m3,
        }
        self.mtcs.rem.mtm1m3.configure_mock(**m1m3_mocks)

    async def get_heartbeat(self, *args, **kwargs):
        """Emulate heartbeat functionality."""
        await asyncio.sleep(1.0)
        return types.SimpleNamespace()

    async def mtmount_evt_target_next(self, *args, **kwargs):
        return self._mtmount_evt_target

    async def mtmount_tel_azimuth_next(self, *args, **kwargs):
        return self._mtmount_tel_azimuth

    async def mtmount_tel_elevation_next(self, *args, **kwargs):
        return self._mtmount_tel_elevation

    async def mtmount_evt_axes_in_position_next(self, *args, **kwargs):
        return self._mtmount_evt_axes_in_position

    async def mtmount_evt_cameraCableWrapFollowing(self, *args, **kwargs):
        return self._mtmount_evt_cameraCableWrapFollowing

    async def mtmout_cmd_enable_ccw_following(self, *args, **kwargs):
        self._mtmount_evt_cameraCableWrapFollowing.enabled = 1

    async def mtmout_cmd_disable_ccw_following(self, *args, **kwargs):
        self._mtmount_evt_cameraCableWrapFollowing.enabled = 0

    async def mtrotator_tel_rotation_next(self, *args, **kwargs):
        return self._mtrotator_tel_rotation

    async def mtrotator_evt_in_position_next(self, *args, **kwargs):
        return self._mtrotator_evt_in_position

    async def mtdome_tel_azimuth_next(self, *args, **kwargs):
        return self._mtdome_tel_azimuth

    async def mtdome_tel_light_wind_screen_next(self, *args, **kwargs):
        return self._mtdome_tel_light_wind_screen

    async def mtm1m3_evt_detailed_state(self, *args, **kwargs):
        await asyncio.sleep(1.0)
        return self._mtm1m3_evt_detailed_state

    async def mtm1m3_cmd_raise_m1m3(self, *args, **kwargs):
        raise_m1m3 = kwargs.get("raiseM1M3", True)

        if (
            raise_m1m3
            and self._mtm1m3_evt_detailed_state.detailedState
            == idl.enums.MTM1M3.DetailedState.PARKED
        ):
            self._mtm1m3_raise_task = asyncio.create_task(self.execute_raise_m1m3())
        else:
            raise RuntimeError(
                f"MTM1M3 current detailed state is {self._mtm1m3_evt_detailed_state.detailedState!r}."
            )

    async def mtm1m3_cmd_abort_raise_m1m3(self, *args, **kwargs):

        if self._mtm1m3_evt_detailed_state.detailedState in {
            idl.enums.MTM1M3.DetailedState.RAISINGENGINEERING,
            idl.enums.MTM1M3.DetailedState.RAISING,
        }:
            self._mtm1m3_abort_raise_task = asyncio.create_task(
                self.execute_abort_raise_m1m3()
            )
        else:
            raise RuntimeError("M1M3 Not raising. Cannot abort.")

    async def execute_raise_m1m3(self):
        self.log.debug("Start raising M1M3...")
        self._mtm1m3_evt_detailed_state.detailedState = (
            idl.enums.MTM1M3.DetailedState.RAISING
        )
        await asyncio.sleep(4.0)
        self.log.debug("Done raising M1M3...")
        self._mtm1m3_evt_detailed_state.detailedState = (
            idl.enums.MTM1M3.DetailedState.ACTIVE
        )

    async def mtm1m3_cmd_lower_m1m3(self, *args, **kwargs):
        lower_m1m3 = kwargs.get("lowerM1M3", True)

        if (
            lower_m1m3
            and self._mtm1m3_evt_detailed_state.detailedState
            == idl.enums.MTM1M3.DetailedState.ACTIVE
        ):
            self._mtm1m3_lower_task = asyncio.create_task(self.execute_lower_m1m3())
        else:
            raise RuntimeError(
                f"MTM1M3 current detailed state is {self._mtm1m3_evt_detailed_state.detailedState!r}."
            )

    async def execute_lower_m1m3(self):
        self.log.debug("Start lowering M1M3...")
        self._mtm1m3_evt_detailed_state.detailedState = (
            idl.enums.MTM1M3.DetailedState.LOWERING
        )
        await asyncio.sleep(4.0)
        self.log.debug("Done lowering M1M3...")
        self._mtm1m3_evt_detailed_state.detailedState = (
            idl.enums.MTM1M3.DetailedState.PARKED
        )

    async def execute_abort_raise_m1m3(self):

        if not self._mtm1m3_raise_task.done():
            self.log.debug("Cancel m1m3 raise task...")
            self._mtm1m3_raise_task.cancel()

        self.log.debug("Set m1m3 detailed state to lowering...")
        self._mtm1m3_evt_detailed_state.detailedState = (
            idl.enums.MTM1M3.DetailedState.LOWERING
        )
        await asyncio.sleep(4.0)
        self.log.debug("M1M3 raise task done, set detailed state to parked...")
        self._mtm1m3_evt_detailed_state.detailedState = (
            idl.enums.MTM1M3.DetailedState.PARKED
        )

    def get_summary_state_for(self, comp):
        async def get_summary_state(timeout=None):
            return self.summary_state[comp]

        return get_summary_state

    def next_summary_state_for(self, comp):
        async def next_summary_state(flush, timeout=None):
            if flush or len(self.summary_state_queue[comp]) == 0:
                self.summary_state_queue_event[comp].clear()
                self.summary_state_queue[comp] = []
            await asyncio.wait_for(
                self.summary_state_queue_event[comp].wait(), timeout=timeout
            )
            return self.summary_state_queue[comp].pop(0)

        return next_summary_state

    def set_summary_state_for(self, comp, state):
        async def set_summary_state(*args, **kwargs):
            self.summary_state[comp].summaryState = int(state)
            self.summary_state_queue[comp].append(
                copy.copy(self.summary_state[comp].summaryState)
            )
            self.summary_state_queue_event[comp].set()

        return set_summary_state


if __name__ == "__main__":
    unittest.main()

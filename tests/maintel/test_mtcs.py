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

import asyncio
import copy
import logging

import astropy.units as units
import numpy as np
import pytest
from astropy.coordinates import Angle
from lsst.ts import idl, utils
from lsst.ts.observatory.control.mock.mtcs_async_mock import MTCSAsyncMock
from lsst.ts.observatory.control.utils import RotType


class TestMTCS(MTCSAsyncMock):
    async def test_coord_facility(self) -> None:
        az = 0.0
        el = 75.0

        radec = self.mtcs.radec_from_azel(az=az, el=el)

        azel = self.mtcs.azel_from_radec(ra=radec.ra, dec=radec.dec)

        pa = self.mtcs.parallactic_angle(ra=radec.ra, dec=radec.dec)

        assert utils.angle_diff(az, azel.az.value).value == pytest.approx(0.0, abs=0.5)
        assert el == pytest.approx(azel.alt.value, abs=0.5)
        assert pa.value == pytest.approx(3.12, abs=0.5)

        # Test passing a time that is 60s in the future
        obs_time = utils.astropy_time_from_tai_unix(utils.current_tai() + 60.0)

        radec = self.mtcs.radec_from_azel(az=az, el=el, time=obs_time)

        azel = self.mtcs.azel_from_radec(ra=radec.ra, dec=radec.dec, time=obs_time)

        pa = self.mtcs.parallactic_angle(ra=radec.ra, dec=radec.dec, time=obs_time)

        utils.assert_angles_almost_equal(az, azel.az, max_diff=5e-5)
        assert el == pytest.approx(azel.alt.value, abs=5e-6)
        assert pa.value == pytest.approx(3.1269, abs=5e-2)

    async def test_set_azel_slew_checks(self) -> None:
        original_check = copy.copy(self.mtcs.check)

        check = self.mtcs.set_azel_slew_checks(True)

        for comp in self.mtcs.components_attr:
            assert getattr(self.mtcs.check, comp) == getattr(original_check, comp)

        for comp in {"mtdome", "mtdometrajectory"}:
            assert getattr(check, comp)

        check = self.mtcs.set_azel_slew_checks(False)

        for comp in {"mtdome", "mtdometrajectory"}:
            assert not getattr(check, comp)

    async def test_slew_object(self) -> None:
        await self.mtcs.enable()
        await self.mtcs.assert_all_enabled()

        name = "HD 185975"

        radec_icrs = self.mtcs.object_list_get(name)

        await self.mtcs.slew_object(name=name, rot_type=RotType.Sky)

        self.mtcs.rem.mtptg.cmd_raDecTarget.set.assert_called_with(
            ra=radec_icrs.ra.hour,
            declination=radec_icrs.dec.deg,
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

        self.mtcs.rem.mtptg.cmd_stopTracking.start.assert_not_awaited()

        self.mtcs.rem.mtmount.evt_elevationInPosition.flush.assert_called_once()
        self.mtcs.rem.mtmount.evt_azimuthInPosition.flush.assert_called_once()
        self.mtcs.rem.mtrotator.evt_inPosition.flush.assert_called_once()

        self.mtcs.rem.mtptg.cmd_raDecTarget.start.assert_called()
        self.mtcs.rem.mtptg.cmd_poriginOffset.start.assert_called_with(
            timeout=self.mtcs.fast_timeout
        )

    async def test_slew_icrs(self) -> None:
        await self.mtcs.enable()
        await self.mtcs.assert_all_enabled()

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

        self.mtcs.rem.mtptg.cmd_stopTracking.start.assert_not_awaited()

        self.mtcs.rem.mtmount.evt_elevationInPosition.flush.assert_called_once()
        self.mtcs.rem.mtmount.evt_azimuthInPosition.flush.assert_called_once()
        self.mtcs.rem.mtrotator.evt_inPosition.flush.assert_called_once()

        self.mtcs.rem.mtptg.cmd_raDecTarget.start.assert_called()
        self.mtcs.rem.mtptg.cmd_poriginOffset.start.assert_called_with(
            timeout=self.mtcs.fast_timeout
        )

    async def test_slew_icrs_stop(self) -> None:
        await self.mtcs.enable()
        await self.mtcs.assert_all_enabled()

        name = "HD 185975"
        ra = "20:28:18.74"
        dec = "-87:28:19.9"

        await self.mtcs.slew_icrs(
            ra=ra,
            dec=dec,
            target_name=name,
            stop_before_slew=True,
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

        self.mtcs.rem.mtptg.cmd_stopTracking.start.assert_awaited()

        self.mtcs.rem.mtmount.evt_elevationInPosition.flush.assert_called()
        self.mtcs.rem.mtmount.evt_azimuthInPosition.flush.assert_called()

        self.mtcs.rem.mtrotator.evt_inPosition.flush.assert_called()

        self.mtcs.rem.mtptg.cmd_raDecTarget.start.assert_called()
        self.mtcs.rem.mtptg.cmd_poriginOffset.start.assert_called_with(
            timeout=self.mtcs.fast_timeout
        )

    async def test_slew_icrs_rot(self) -> None:
        await self.mtcs.enable()
        await self.mtcs.assert_all_enabled()

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

        self.mtcs.rem.mtptg.cmd_stopTracking.start.assert_not_awaited()

        self.mtcs.rem.mtmount.evt_elevationInPosition.flush.assert_called_once()
        self.mtcs.rem.mtmount.evt_azimuthInPosition.flush.assert_called_once()
        self.mtcs.rem.mtrotator.evt_inPosition.flush.assert_called_once()

        self.mtcs.rem.mtptg.cmd_raDecTarget.start.assert_called()
        self.mtcs.rem.mtptg.cmd_poriginOffset.start.assert_called_with(
            timeout=self.mtcs.fast_timeout
        )

    async def test_slew_icrs_rot_physical(self) -> None:
        await self.mtcs.enable()
        await self.mtcs.assert_all_enabled()

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

        self.mtcs.rem.mtptg.cmd_stopTracking.start.assert_not_called()

        self.mtcs.rem.mtmount.evt_elevationInPosition.flush.assert_called_once()
        self.mtcs.rem.mtmount.evt_azimuthInPosition.flush.assert_called_once()
        self.mtcs.rem.mtrotator.evt_inPosition.flush.assert_called_once()

        self.mtcs.rem.mtptg.cmd_raDecTarget.start.assert_called()
        self.mtcs.rem.mtptg.cmd_poriginOffset.start.assert_called_with(
            timeout=self.mtcs.fast_timeout
        )

    async def test_slew_icrs_rot_physical_sky(self) -> None:
        await self.mtcs.enable()
        await self.mtcs.assert_all_enabled()

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

        self.mtcs.rem.mtptg.cmd_stopTracking.start.assert_not_called()

        self.mtcs.rem.mtmount.evt_elevationInPosition.flush.assert_called_once()
        self.mtcs.rem.mtmount.evt_azimuthInPosition.flush.assert_called_once()
        self.mtcs.rem.mtrotator.evt_inPosition.flush.assert_called_once()

        self.mtcs.rem.mtptg.cmd_raDecTarget.start.assert_called()
        self.mtcs.rem.mtptg.cmd_poriginOffset.start.assert_called_with(
            timeout=self.mtcs.fast_timeout
        )

    async def test_slew_icrs_with_offset(self) -> None:
        await self.mtcs.enable()
        await self.mtcs.assert_all_enabled()

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

        self.mtcs.rem.mtptg.cmd_stopTracking.start.assert_not_called()

        self.mtcs.rem.mtmount.evt_elevationInPosition.flush.assert_called_once()
        self.mtcs.rem.mtmount.evt_azimuthInPosition.flush.assert_called_once()
        self.mtcs.rem.mtrotator.evt_inPosition.flush.assert_called_once()

        self.mtcs.rem.mtptg.cmd_raDecTarget.start.assert_called()
        self.mtcs.rem.mtptg.cmd_poriginOffset.start.assert_called_with(
            timeout=self.mtcs.fast_timeout
        )

    async def test_slew_icrs_ccw_following_off(self) -> None:
        await self.mtcs.enable()
        await self.mtcs.assert_all_enabled()

        name = "HD 185975"
        ra = "20:28:18.74"
        dec = "-87:28:19.9"

        self._mtmount_evt_cameraCableWrapFollowing.enabled = 0

        # TODO DM-32545: Restore exception in slew method if dome
        # following is disabled.
        with self.assertLogs(self.log.name, level=logging.WARNING):
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

        self.mtcs.rem.mtptg.cmd_stopTracking.start.assert_not_awaited()

        self.mtcs.rem.mtmount.evt_elevationInPosition.flush.assert_called_once()
        self.mtcs.rem.mtmount.evt_azimuthInPosition.flush.assert_called_once()
        self.mtcs.rem.mtrotator.evt_inPosition.flush.assert_called_once()

        self.mtcs.rem.mtptg.cmd_raDecTarget.start.assert_called()
        self.mtcs.rem.mtptg.cmd_poriginOffset.start.assert_called_with(
            timeout=self.mtcs.fast_timeout
        )

    async def test_point_azel(self) -> None:
        await self.mtcs.enable()
        await self.mtcs.assert_all_enabled()

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

        self.mtcs.rem.mtmount.evt_elevationInPosition.flush.assert_called()
        self.mtcs.rem.mtmount.evt_azimuthInPosition.flush.assert_called()
        self.mtcs.rem.mtrotator.evt_inPosition.flush.assert_called()

    async def test_enable_ccw_following(self) -> None:
        await self.mtcs.enable_ccw_following()

        self.mtcs.rem.mtmount.cmd_enableCameraCableWrapFollowing.start.assert_awaited_with(
            timeout=self.mtcs.fast_timeout
        )
        assert self._mtmount_evt_cameraCableWrapFollowing.enabled == 1

    async def test_disable_ccw_following(self) -> None:
        await self.mtcs.disable_ccw_following()

        self.mtcs.rem.mtmount.cmd_disableCameraCableWrapFollowing.start.assert_awaited_with(
            timeout=self.mtcs.fast_timeout
        )
        assert self._mtmount_evt_cameraCableWrapFollowing.enabled == 0

    async def test_offset_radec(self) -> None:
        # Test offset_radec
        ra_offset, dec_offset = 10.0, -10.0
        await self.mtcs.offset_radec(ra=ra_offset, dec=dec_offset)

        self.mtcs.rem.mtptg.cmd_offsetRADec.set_start.assert_called_with(
            type=0, off1=ra_offset, off2=dec_offset, num=0
        )

    async def test_offset_azel(self) -> None:
        az_offset, el_offset = 10.0, -10.0

        # Default call should yield relative=True, absorb=False
        await self.mtcs.offset_azel(az=az_offset, el=el_offset)

        self.mtcs.rem.mtptg.cmd_offsetAzEl.set_start.assert_called_with(
            az=az_offset, el=el_offset, num=1
        )

    async def test_offset_azel_with_defaults(self) -> None:
        az_offset, el_offset = 10.0, -10.0

        # Same as default but now pass the parameters
        await self.mtcs.offset_azel(
            az=az_offset, el=el_offset, relative=True, absorb=False
        )

        self.mtcs.rem.mtptg.cmd_offsetAzEl.set_start.assert_called_with(
            az=az_offset, el=el_offset, num=1
        )

    async def test_offset_azel_not_relative(self) -> None:
        az_offset, el_offset = 10.0, -10.0

        # Call with relative=False
        await self.mtcs.offset_azel(
            az=az_offset, el=el_offset, relative=False, absorb=False
        )

        self.mtcs.rem.mtptg.cmd_offsetAzEl.set_start.assert_called_with(
            az=az_offset, el=el_offset, num=0
        )

    async def test_offset_azel_relative_absorb(self) -> None:
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

    async def test_offset_azel_absorb(self) -> None:
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

    async def test_reset_offsets(self) -> None:
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

    async def test_reset_offsets_absorbed(self) -> None:
        await self.mtcs.reset_offsets(absorbed=True, non_absorbed=False)

        self.mtcs.rem.mtptg.cmd_poriginClear.set_start.assert_any_call(
            num=0, timeout=self.mtcs.fast_timeout
        )

        self.mtcs.rem.mtptg.cmd_poriginClear.set_start.assert_any_call(
            num=1, timeout=self.mtcs.fast_timeout
        )

        self.mtcs.rem.mtptg.cmd_offsetClear.set_start.assert_not_called()

    async def test_reset_offsets_non_absorbed(self) -> None:
        await self.mtcs.reset_offsets(absorbed=False, non_absorbed=True)

        self.mtcs.rem.mtptg.cmd_poriginClear.set_start.assert_not_called()

        self.mtcs.rem.mtptg.cmd_offsetClear.set_start.assert_any_call(
            num=0, timeout=self.mtcs.fast_timeout
        )

        self.mtcs.rem.mtptg.cmd_offsetClear.set_start.assert_any_call(
            num=1, timeout=self.mtcs.fast_timeout
        )

    async def test_offset_xy(self) -> None:
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

    async def test_offset_xy_with_defaults(self) -> None:
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

    async def test_offset_xy_not_relative(self) -> None:
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

    async def test_offset_xy_relative_absorb(self) -> None:
        x_offset, y_offset = 10.0, -10.0

        # Call with relative=True and absorb=True
        await self.mtcs.offset_xy(x=x_offset, y=y_offset, relative=True, absorb=True)

        self.mtcs.rem.mtptg.cmd_poriginOffset.set_start.assert_called_with(
            dx=x_offset * self.mtcs.plate_scale,
            dy=y_offset * self.mtcs.plate_scale,
            num=1,
        )

    async def test_offset_xy_absorb(self) -> None:
        x_offset, y_offset = 10.0, -10.0

        # Call with relative=False and absorb=True
        await self.mtcs.offset_xy(x=x_offset, y=y_offset, relative=False, absorb=True)

        self.mtcs.rem.mtptg.cmd_poriginOffset.set_start.assert_called_with(
            dx=x_offset * self.mtcs.plate_scale,
            dy=y_offset * self.mtcs.plate_scale,
            num=0,
        )

    async def test_slew_dome_to(self) -> None:
        az = 90.0

        with pytest.raises(NotImplementedError):
            await self.mtcs.slew_dome_to(az)

    async def test_close_dome(self) -> None:
        with pytest.raises(NotImplementedError):
            await self.mtcs.close_dome()

    async def test_open_m1_cover(self) -> None:
        with pytest.raises(NotImplementedError):
            await self.mtcs.open_m1_cover()

    async def test_close_m1_cover(self) -> None:
        with pytest.raises(NotImplementedError):
            await self.mtcs.close_m1_cover()

    async def test_home_dome(self) -> None:
        with pytest.raises(NotImplementedError):
            await self.mtcs.home_dome()

    async def test_open_dome_shutter(self) -> None:
        with pytest.raises(NotImplementedError):
            await self.mtcs.open_dome_shutter()

    async def test_prepare_for_flatfield(self) -> None:
        with pytest.raises(NotImplementedError):
            await self.mtcs.prepare_for_flatfield()

    async def test_prepare_for_onsky(self) -> None:
        with pytest.raises(NotImplementedError):
            await self.mtcs.prepare_for_onsky()

    async def test_shutdown(self) -> None:
        with pytest.raises(NotImplementedError):
            await self.mtcs.shutdown()

    async def test_stop_all(self) -> None:
        with pytest.raises(NotImplementedError):
            await self.mtcs.stop_all()

    async def test_raise_m1m3(self) -> None:
        await self.mtcs.enable()
        await self.mtcs.assert_all_enabled()

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
            flush=False, timeout=self.mtcs.m1m3_raise_timeout
        )

    async def test_raise_m1m3_when_active(self) -> None:
        await self.mtcs.enable()
        await self.mtcs.assert_all_enabled()

        self._mtm1m3_evt_detailed_state.detailedState = (
            idl.enums.MTM1M3.DetailedState.ACTIVE
        )
        await self.mtcs.raise_m1m3()

        self.mtcs.rem.mtm1m3.evt_detailedState.aget.assert_awaited()
        self.mtcs.rem.mtm1m3.evt_detailedState.flush.assert_not_called()
        self.mtcs.rem.mtm1m3.cmd_raiseM1M3.set_start.assert_not_awaited()
        self.mtcs.rem.mtm1m3.evt_detailedState.next.assert_not_awaited()

    async def test_raise_m1m3_aborted(self) -> None:
        await self.mtcs.enable()
        await self.mtcs.assert_all_enabled()

        self._mtm1m3_evt_detailed_state.detailedState = (
            idl.enums.MTM1M3.DetailedState.PARKED
        )

        m1m3_raise_task = asyncio.create_task(self.mtcs.raise_m1m3())

        await asyncio.sleep(self.execute_raise_lower_m1m3_time / 2)

        await self.execute_abort_raise_m1m3()

        with pytest.raises(RuntimeError):
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
            flush=False, timeout=self.mtcs.m1m3_raise_timeout
        )

    async def test_assert_m1m3_detailed_state(self) -> None:
        self._mtm1m3_evt_detailed_state.detailedState = (
            idl.enums.MTM1M3.DetailedState.ACTIVE
        )

        for m1m3_detailed_state in idl.enums.MTM1M3.DetailedState:
            self.log.debug(f"{m1m3_detailed_state!r}")
            if m1m3_detailed_state != idl.enums.MTM1M3.DetailedState.ACTIVE:
                with pytest.raises(AssertionError):
                    await self.mtcs.assert_m1m3_detailed_state(
                        detailed_states={m1m3_detailed_state}
                    )
            else:
                assert (
                    await self.mtcs.assert_m1m3_detailed_state({m1m3_detailed_state})
                    is None
                )
            self.mtcs.rem.mtm1m3.evt_detailedState.aget.assert_awaited_with(
                timeout=self.mtcs.fast_timeout
            )
            self.mtcs.rem.mtm1m3.evt_detailedState.aget.reset_mock()

    async def test_raise_m1m3_not_raisable(self) -> None:
        await self.mtcs.enable()
        await self.mtcs.assert_all_enabled()

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

                with pytest.raises(RuntimeError):
                    await self.mtcs.raise_m1m3()

    async def test_lower_m1m3_when_active(self) -> None:
        await self.mtcs.enable()
        await self.mtcs.assert_all_enabled()

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
            flush=False, timeout=self.mtcs.m1m3_raise_timeout
        )

    async def test_lower_m1m3_when_parked(self) -> None:
        await self.mtcs.lower_m1m3()

        self.mtcs.rem.mtm1m3.evt_detailedState.aget.assert_awaited()
        self.mtcs.rem.mtm1m3.evt_detailedState.flush.assert_not_called()
        self.mtcs.rem.mtm1m3.cmd_lowerM1M3.set_start.assert_not_awaited()
        self.mtcs.rem.mtm1m3.evt_detailedState.next.assert_not_awaited()

    async def test_lower_m1m3_not_lowerable(self) -> None:
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

                with pytest.raises(RuntimeError):
                    await self.mtcs.raise_m1m3()

    async def test_abort_raise_m1m3(self) -> None:
        self._mtm1m3_evt_detailed_state.detailedState = (
            idl.enums.MTM1M3.DetailedState.RAISING
        )

        await self.mtcs.enable()
        await self.mtcs.assert_all_enabled()

        await self.mtcs.abort_raise_m1m3()

        self.mtcs.rem.mtm1m3.cmd_abortRaiseM1M3.start.assert_awaited_with(
            timeout=self.mtcs.long_timeout
        )
        assert (
            self._mtm1m3_evt_detailed_state.detailedState
            == idl.enums.MTM1M3.DetailedState.PARKED
        )

    async def test_abort_raise_m1m3_active(self) -> None:
        await self.mtcs.enable()
        await self.mtcs.assert_all_enabled()

        self._mtm1m3_evt_detailed_state.detailedState = (
            idl.enums.MTM1M3.DetailedState.ACTIVE
        )

        with pytest.raises(RuntimeError):
            await self.mtcs.abort_raise_m1m3()

        self.mtcs.rem.mtm1m3.cmd_abortRaiseM1M3.start.assert_not_awaited()

    async def test_abort_raise_m1m3_parked(self) -> None:
        await self.mtcs.enable()
        await self.mtcs.assert_all_enabled()

        self._mtm1m3_evt_detailed_state.detailedState = (
            idl.enums.MTM1M3.DetailedState.PARKED
        )

        await self.mtcs.abort_raise_m1m3()

        self.mtcs.rem.mtm1m3.cmd_abortRaiseM1M3.start.assert_not_awaited()

    async def test_enable_m1m3_balance_system(self) -> None:
        await self.mtcs.enable_m1m3_balance_system()

        if hasattr(self.mtcs.rem.mtm1m3, "evt_appliedBalanceForces"):
            self.mtcs.rem.mtm1m3.evt_appliedBalanceForces.aget.assert_awaited()
        else:
            self.mtcs.rem.mtm1m3.tel_appliedBalanceForces.aget.assert_awaited()
        self.mtcs.rem.mtm1m3.cmd_enableHardpointCorrections.start.assert_awaited_with(
            timeout=self.mtcs.long_timeout
        )

    async def test_enable_m1m3_balance_system_when_enabled(self) -> None:
        self._mtm1m3_evt_applied_balance_forces.forceMagnitude = 2000

        # Check that it logs a warning...
        with self.assertLogs(self.log.name, level=logging.WARNING):
            await self.mtcs.enable_m1m3_balance_system()

        self.mtcs.rem.mtm1m3.cmd_enableHardpointCorrections.start.assert_not_awaited()

    async def test_wait_m1m3_force_balance_system(self) -> None:
        await self._execute_enable_hardpoint_corrections()

        # Use a shorter timeout on wait_for than in the call to
        # wait_m1m3_force_balance_system. This will cause the call to timeout
        # if the call does not finish in the appropriate time (which is about)
        # 1 second shorter than fast_timeout.
        await asyncio.wait_for(
            self.mtcs.wait_m1m3_force_balance_system(timeout=self.mtcs.long_timeout),
            timeout=self.mtcs.fast_timeout,
        )

    async def test_wait_m1m3_force_balance_system_fail_when_off(self) -> None:
        with self.assertLogs(self.log.name, level=logging.WARNING), pytest.raises(
            RuntimeError
        ):
            await self.mtcs.wait_m1m3_force_balance_system(
                timeout=self.mtcs.long_timeout
            )

    async def test_reset_m1m3_forces(self) -> None:
        await self.mtcs.reset_m1m3_forces()

        self.mtcs.rem.mtm1m3.cmd_clearActiveOpticForces.start.assert_awaited_once()
        self.mtcs.rem.mtm1m3.cmd_clearActiveOpticForces.start.assert_awaited_with(
            timeout=self.mtcs.long_timeout
        )

    async def test_is_m1m3_in_engineering_mode(self) -> None:
        m1m3_engineering_states = self.mtcs.m1m3_engineering_states
        m1m3_non_engineering_states = {
            val
            for val in idl.enums.MTM1M3.DetailedState
            if val not in m1m3_engineering_states
        }

        for detailed_state in m1m3_engineering_states:
            self._mtm1m3_evt_detailed_state.detailedState = detailed_state
            assert await self.mtcs.is_m1m3_in_engineering_mode()

        for detailed_state in m1m3_non_engineering_states:
            self._mtm1m3_evt_detailed_state.detailedState = detailed_state
            assert not await self.mtcs.is_m1m3_in_engineering_mode()

    async def test_enter_m1m3_engineering_mode_in_eng_mode(self) -> None:
        for detailed_state in self.mtcs.m1m3_engineering_states:
            self._mtm1m3_evt_detailed_state.detailedState = detailed_state

            await self.mtcs.enter_m1m3_engineering_mode()
            assert await self.mtcs.is_m1m3_in_engineering_mode()
            self.mtcs.rem.mtm1m3.cmd_enterEngineering.start.assert_not_awaited()

    async def test_enter_m1m3_engineering_mode_not_in_eng_mode(self) -> None:
        m1m3_engineering_states = self.mtcs.m1m3_engineering_states
        m1m3_non_engineering_states = {
            val
            for val in idl.enums.MTM1M3.DetailedState
            if val not in m1m3_engineering_states
        }
        for detailed_state in m1m3_non_engineering_states:
            self._mtm1m3_evt_detailed_state.detailedState = detailed_state

            await self.mtcs.enter_m1m3_engineering_mode()

            assert await self.mtcs.is_m1m3_in_engineering_mode()
            self.mtcs.rem.mtm1m3.cmd_enterEngineering.start.assert_awaited_once()
            self.mtcs.rem.mtm1m3.cmd_enterEngineering.start.assert_awaited_with(
                timeout=self.mtcs.long_timeout
            )
            self.mtcs.rem.mtm1m3.cmd_enterEngineering.start.reset_mock()

    # TODO (DM-39458): Remove this workaround.
    async def test_enter_m1m3_engineering_mode_ignore_cmd_timeout(self) -> None:
        self.mtm1m3_cmd_enter_engineering_timeout = True

        m1m3_engineering_states = self.mtcs.m1m3_engineering_states
        m1m3_non_engineering_states = {
            val
            for val in idl.enums.MTM1M3.DetailedState
            if val not in m1m3_engineering_states
        }
        for detailed_state in m1m3_non_engineering_states:
            self._mtm1m3_evt_detailed_state.detailedState = detailed_state

            await self.mtcs.enter_m1m3_engineering_mode()

            assert await self.mtcs.is_m1m3_in_engineering_mode()
            self.mtcs.rem.mtm1m3.cmd_enterEngineering.start.assert_awaited_once()
            self.mtcs.rem.mtm1m3.cmd_enterEngineering.start.assert_awaited_with(
                timeout=self.mtcs.long_timeout
            )
            self.mtcs.rem.mtm1m3.cmd_enterEngineering.start.reset_mock()

    async def test_exit_m1m3_engineering_mode_in_eng_mode(self) -> None:
        for detailed_state in self.mtcs.m1m3_engineering_states:
            self._mtm1m3_evt_detailed_state.detailedState = detailed_state

            await self.mtcs.exit_m1m3_engineering_mode()
            assert not await self.mtcs.is_m1m3_in_engineering_mode()
            self.mtcs.rem.mtm1m3.cmd_exitEngineering.start.assert_awaited_once()
            self.mtcs.rem.mtm1m3.cmd_exitEngineering.start.assert_awaited_with(
                timeout=self.mtcs.long_timeout
            )
            self.mtcs.rem.mtm1m3.cmd_exitEngineering.start.reset_mock()

    async def test_exit_m1m3_engineering_mode_not_in_eng_mode(self) -> None:
        m1m3_engineering_states = self.mtcs.m1m3_engineering_states
        m1m3_non_engineering_states = {
            val
            for val in idl.enums.MTM1M3.DetailedState
            if val not in m1m3_engineering_states
        }
        for detailed_state in m1m3_non_engineering_states:
            self._mtm1m3_evt_detailed_state.detailedState = detailed_state

            await self.mtcs.exit_m1m3_engineering_mode()

            assert not await self.mtcs.is_m1m3_in_engineering_mode()
            self.mtcs.rem.mtm1m3.cmd_enterEngineering.start.assert_not_awaited()

    async def test_run_m1m3_hard_point_test(self) -> None:
        await self.mtcs.run_m1m3_hard_point_test(hp=1)

        self.mtcs.rem.mtm1m3.cmd_testHardpoint.set_start.assert_awaited_with(
            hardpointActuator=1,
            timeout=self.mtcs.long_timeout,
        )
        self.mtcs.rem.mtm1m3.evt_hardpointTestStatus.flush.assert_called()
        self.mtcs.rem.mtm1m3.evt_hardpointTestStatus.next.assert_awaited_with(
            flush=False,
            timeout=self.mtcs.timeout_hardpoint_test_status,
        )

    async def test_run_m1m3_hard_point_test_failed(self) -> None:
        self.desired_hp_test_final_status = idl.enums.MTM1M3.HardpointTest.FAILED

        with pytest.raises(RuntimeError):
            await self.mtcs.run_m1m3_hard_point_test(hp=1)

        self.mtcs.rem.mtm1m3.cmd_testHardpoint.set_start.assert_awaited_with(
            hardpointActuator=1,
            timeout=self.mtcs.long_timeout,
        )
        self.mtcs.rem.mtm1m3.evt_hardpointTestStatus.flush.assert_called()
        self.mtcs.rem.mtm1m3.evt_hardpointTestStatus.next.assert_awaited_with(
            flush=False,
            timeout=self.mtcs.timeout_hardpoint_test_status,
        )

    async def test_stop_m1m3_hard_point_test(self) -> None:
        await self.mtcs.stop_m1m3_hard_point_test(hp=1)

        self.mtcs.rem.mtm1m3.cmd_killHardpointTest.set_start.assert_awaited_with(
            hardpointActuator=1,
            timeout=self.mtcs.long_timeout,
        )

    async def test_run_m1m3_actuator_bump_test_default(self) -> None:
        actuator_id = self.mtcs.get_m1m3_actuator_secondary_ids()[0]

        await self.mtcs.run_m1m3_actuator_bump_test(
            actuator_id=actuator_id,
        )
        (
            primary_status,
            secondary_status,
        ) = await self.mtcs.get_m1m3_bump_test_status(actuator_id=actuator_id)

        self.mtcs.rem.mtm1m3.evt_forceActuatorBumpTestStatus.flush.assert_called()
        self.mtcs.rem.mtm1m3.cmd_forceActuatorBumpTest.set_start.assert_awaited_with(
            actuatorId=actuator_id,
            testPrimary=True,
            testSecondary=False,
            timeout=self.mtcs.long_timeout,
        )
        self.mtcs.rem.mtm1m3.evt_forceActuatorBumpTestStatus.next.assert_awaited_with(
            flush=False,
            timeout=self.mtcs.long_timeout,
        )

        assert actuator_id == actuator_id
        assert primary_status == idl.enums.MTM1M3.BumpTest.PASSED
        assert secondary_status == idl.enums.MTM1M3.BumpTest.NOTTESTED

    async def test_run_m1m3_actuator_bump_test_default_no_secondary(self) -> None:
        actuator_id = 101
        await self.mtcs.run_m1m3_actuator_bump_test(
            actuator_id=actuator_id,
        )
        (
            primary_status,
            secondary_status,
        ) = await self.mtcs.get_m1m3_bump_test_status(actuator_id=actuator_id)

        self.mtcs.rem.mtm1m3.evt_forceActuatorBumpTestStatus.flush.assert_called()
        self.mtcs.rem.mtm1m3.cmd_forceActuatorBumpTest.set_start.assert_awaited_with(
            actuatorId=actuator_id,
            testPrimary=True,
            testSecondary=False,
            timeout=self.mtcs.long_timeout,
        )
        self.mtcs.rem.mtm1m3.evt_forceActuatorBumpTestStatus.next.assert_awaited_with(
            flush=False,
            timeout=self.mtcs.long_timeout,
        )

        assert primary_status == idl.enums.MTM1M3.BumpTest.PASSED
        assert secondary_status is None

    async def test_run_m1m3_actuator_bump_test_primary_secondary(self) -> None:
        actuator_id = self.mtcs.get_m1m3_actuator_secondary_ids()[0]

        await self.mtcs.run_m1m3_actuator_bump_test(
            actuator_id=actuator_id,
            primary=True,
            secondary=True,
        )
        (
            primary_status,
            secondary_status,
        ) = await self.mtcs.get_m1m3_bump_test_status(actuator_id=actuator_id)

        self.mtcs.rem.mtm1m3.evt_forceActuatorBumpTestStatus.flush.assert_called()
        self.mtcs.rem.mtm1m3.cmd_forceActuatorBumpTest.set_start.assert_awaited_with(
            actuatorId=actuator_id,
            testPrimary=True,
            testSecondary=True,
            timeout=self.mtcs.long_timeout,
        )
        self.mtcs.rem.mtm1m3.evt_forceActuatorBumpTestStatus.next.assert_awaited_with(
            flush=False,
            timeout=self.mtcs.long_timeout,
        )

        assert primary_status == idl.enums.MTM1M3.BumpTest.PASSED
        assert secondary_status == idl.enums.MTM1M3.BumpTest.PASSED

    async def test_run_m1m3_actuator_bump_test_secondary(self) -> None:
        actuator_id = self.mtcs.get_m1m3_actuator_secondary_ids()[0]

        await self.mtcs.run_m1m3_actuator_bump_test(
            actuator_id=actuator_id,
            primary=False,
            secondary=True,
        )
        (
            primary_status,
            secondary_status,
        ) = await self.mtcs.get_m1m3_bump_test_status(actuator_id=actuator_id)

        self.mtcs.rem.mtm1m3.evt_forceActuatorBumpTestStatus.flush.assert_called()
        self.mtcs.rem.mtm1m3.cmd_forceActuatorBumpTest.set_start.assert_awaited_with(
            actuatorId=actuator_id,
            testPrimary=False,
            testSecondary=True,
            timeout=self.mtcs.long_timeout,
        )
        self.mtcs.rem.mtm1m3.evt_forceActuatorBumpTestStatus.next.assert_awaited_with(
            flush=False,
            timeout=self.mtcs.long_timeout,
        )

        assert primary_status == idl.enums.MTM1M3.BumpTest.NOTTESTED
        assert secondary_status == idl.enums.MTM1M3.BumpTest.PASSED

    async def test_run_m1m3_actuator_bump_test_fail(self) -> None:
        actuator_id = self.mtcs.get_m1m3_actuator_secondary_ids()[0]

        self.desired_bump_test_final_status = idl.enums.MTM1M3.BumpTest.FAILED

        with pytest.raises(RuntimeError):
            await self.mtcs.run_m1m3_actuator_bump_test(
                actuator_id=actuator_id,
            )
        (
            primary_status,
            secondary_status,
        ) = await self.mtcs.get_m1m3_bump_test_status(actuator_id=actuator_id)

        self.mtcs.rem.mtm1m3.evt_forceActuatorBumpTestStatus.flush.assert_called()
        self.mtcs.rem.mtm1m3.cmd_forceActuatorBumpTest.set_start.assert_awaited_with(
            actuatorId=actuator_id,
            testPrimary=True,
            testSecondary=False,
            timeout=self.mtcs.long_timeout,
        )
        self.mtcs.rem.mtm1m3.evt_forceActuatorBumpTestStatus.next.assert_awaited_with(
            flush=False,
            timeout=self.mtcs.long_timeout,
        )

        assert primary_status == idl.enums.MTM1M3.BumpTest.FAILED
        assert secondary_status == idl.enums.MTM1M3.BumpTest.NOTTESTED

    async def test_run_m1m3_actuator_bump_test_2nd_fail(self) -> None:
        self.desired_bump_test_final_status = idl.enums.MTM1M3.BumpTest.FAILED

        actuator_id = self.mtcs.get_m1m3_actuator_secondary_ids()[0]

        with pytest.raises(RuntimeError) as exception_info:
            await self.mtcs.run_m1m3_actuator_bump_test(
                actuator_id=actuator_id,
                primary=False,
                secondary=True,
            )
        assert f"Secondary bump test failed for actuator {actuator_id}" in str(
            exception_info.value
        )

        (
            primary_status,
            secondary_status,
        ) = await self.mtcs.get_m1m3_bump_test_status(actuator_id=actuator_id)

        self.mtcs.rem.mtm1m3.evt_forceActuatorBumpTestStatus.flush.assert_called()
        self.mtcs.rem.mtm1m3.cmd_forceActuatorBumpTest.set_start.assert_awaited_with(
            actuatorId=actuator_id,
            testPrimary=False,
            testSecondary=True,
            timeout=self.mtcs.long_timeout,
        )
        self.mtcs.rem.mtm1m3.evt_forceActuatorBumpTestStatus.next.assert_awaited_with(
            flush=False,
            timeout=self.mtcs.long_timeout,
        )

        assert primary_status == idl.enums.MTM1M3.BumpTest.NOTTESTED
        assert secondary_status == idl.enums.MTM1M3.BumpTest.FAILED

    async def test_run_m1m3_actuator_bump_test_both_fail(self) -> None:
        actuator_id = 102
        self.desired_bump_test_final_status = idl.enums.MTM1M3.BumpTest.FAILED

        with pytest.raises(RuntimeError):
            await self.mtcs.run_m1m3_actuator_bump_test(
                actuator_id=actuator_id,
                primary=True,
                secondary=True,
            )
        (
            primary_status,
            secondary_status,
        ) = await self.mtcs.get_m1m3_bump_test_status(actuator_id=actuator_id)

        assert primary_status == idl.enums.MTM1M3.BumpTest.FAILED
        assert secondary_status != idl.enums.MTM1M3.BumpTest.FAILED

        with pytest.raises(RuntimeError):
            await self.mtcs._wait_bump_test_ok(
                actuator_id=actuator_id, primary=False, secondary=True
            )

        (
            primary_status,
            secondary_status,
        ) = await self.mtcs.get_m1m3_bump_test_status(actuator_id=actuator_id)

        assert primary_status == idl.enums.MTM1M3.BumpTest.FAILED
        assert secondary_status == idl.enums.MTM1M3.BumpTest.FAILED

    async def test_stop_m1m3_bump_test_running(self) -> None:
        self._mtm1m3_evt_force_actuator_bump_test_status.actuatorId = 102

        await self.mtcs.stop_m1m3_bump_test()

        self.mtcs.rem.mtm1m3.evt_forceActuatorBumpTestStatus.aget.assert_awaited_with(
            timeout=self.mtcs.fast_timeout
        )
        self.mtcs.rem.mtm1m3.cmd_killForceActuatorBumpTest.start.assert_awaited_with(
            timeout=self.mtcs.long_timeout
        )

    async def test_stop_m1m3_bump_test_not_running(self) -> None:
        self._mtm1m3_evt_force_actuator_bump_test_status.actuatorId = -1

        await self.mtcs.stop_m1m3_bump_test()

        self.mtcs.rem.mtm1m3.evt_forceActuatorBumpTestStatus.aget.assert_awaited_with(
            timeout=self.mtcs.fast_timeout
        )
        self.mtcs.rem.mtm1m3.cmd_killForceActuatorBumpTest.start.assert_not_awaited()

    async def test_run_m1m3_actuator_bump_bad_secondary_index(self) -> None:
        primary_index = self.mtcs.get_m1m3_actuator_ids()
        secondary_index = self.mtcs.get_m1m3_actuator_secondary_ids()
        test_index = [index for index in primary_index if index not in secondary_index]

        for index in test_index:
            with pytest.raises(RuntimeError) as exception_info:
                await self.mtcs.run_m1m3_actuator_bump_test(
                    actuator_id=index,
                    primary=False,
                    secondary=True,
                )
            assert f"Actuator {index} does not have secondary axis." in str(
                exception_info.value
            )

    def test_get_m1m3_actuator_index(self) -> None:
        m1m3_actuator_ids = self.mtcs.get_m1m3_actuator_ids()
        n_actuators = len(m1m3_actuator_ids)
        for id in m1m3_actuator_ids:
            index = self.mtcs.get_m1m3_actuator_index(id)
            assert 0 <= index <= n_actuators

    def test_get_m1m3_actuator_index_invalid_id(self) -> None:
        with pytest.raises(RuntimeError):
            self.mtcs.get_m1m3_actuator_index(0)

        with pytest.raises(RuntimeError):
            self.mtcs.get_m1m3_actuator_index(1000)

    async def test_enable_m2_balance_system(self) -> None:
        await self.mtcs.enable_m2_balance_system()

        self.mtcs.rem.mtm2.evt_forceBalanceSystemStatus.aget.assert_awaited_once_with(
            timeout=self.mtcs.fast_timeout
        )
        self.mtcs.rem.mtm2.evt_forceBalanceSystemStatus.flush.assert_called()
        self.mtcs.rem.mtm2.cmd_switchForceBalanceSystem.set_start.assert_awaited_with(
            status=True, timeout=self.mtcs.long_timeout
        )
        self.mtcs.rem.mtm2.evt_forceBalanceSystemStatus.next.assert_awaited_with(
            flush=False, timeout=self.mtcs.long_timeout
        )

    async def test_enable_m2_balance_system_when_on(self) -> None:
        self._mtm2_evt_force_balance_system_status.status = True

        await self.mtcs.enable_m2_balance_system()

        self.mtcs.rem.mtm2.evt_forceBalanceSystemStatus.aget.assert_awaited_once_with(
            timeout=self.mtcs.fast_timeout
        )
        self.mtcs.rem.mtm2.evt_forceBalanceSystemStatus.flush.assert_called()
        self.mtcs.rem.mtm2.cmd_switchForceBalanceSystem.set_start.assert_not_awaited()
        self.mtcs.rem.mtm2.evt_forceBalanceSystemStatus.next.assert_not_awaited()

    async def test_reset_m2_forces(self) -> None:
        await self.mtcs.reset_m2_forces()

        self.mtcs.rem.mtm2.cmd_resetForceOffsets.start.assert_awaited_with(
            timeout=self.mtcs.long_timeout
        )

    async def test_enable_compensation_mode_for_hexapod_1(self) -> None:
        self._mthexapod_1_evt_compensation_mode.enabled = False

        await self.mtcs.enable_compensation_mode(component="mthexapod_1")

        assert self._mthexapod_1_evt_compensation_mode.enabled
        self.mtcs.rem.mthexapod_1.cmd_setCompensationMode.set_start.assert_awaited_with(
            enable=1, timeout=self.mtcs.long_timeout
        )

    async def test_enable_compensation_mode_for_hexapod_2(self) -> None:
        self._mthexapod_2_evt_compensation_mode.enabled = False

        await self.mtcs.enable_compensation_mode(component="mthexapod_2")

        assert self._mthexapod_2_evt_compensation_mode.enabled
        self.mtcs.rem.mthexapod_2.cmd_setCompensationMode.set_start.assert_awaited_with(
            enable=1, timeout=self.mtcs.long_timeout
        )

    async def test_enable_compensation_mode_when_enabled(self) -> None:
        self._mthexapod_1_evt_compensation_mode.enabled = True

        await self.mtcs.enable_compensation_mode(component="mthexapod_1")

        self.mtcs.rem.mthexapod_1.cmd_setCompensationMode.set_start.assert_not_awaited()

    async def test_enable_compensation_mode_bad_component(self) -> None:
        with pytest.raises(AssertionError):
            await self.mtcs.enable_compensation_mode(component="mtm1m3")

    async def test_disable_compensation_mode_for_hexapod_1(self) -> None:
        self._mthexapod_1_evt_compensation_mode.enabled = True

        await self.mtcs.disable_compensation_mode(component="mthexapod_1")

        assert not self._mthexapod_1_evt_compensation_mode.enabled
        self.mtcs.rem.mthexapod_1.cmd_setCompensationMode.set_start.assert_awaited_with(
            enable=0, timeout=self.mtcs.long_timeout
        )

    async def test_disable_compensation_mode_when_disabled(self) -> None:
        self._mthexapod_1_evt_compensation_mode.enabled = False

        await self.mtcs.disable_compensation_mode(component="mthexapod_1")

        self.mtcs.rem.mthexapod_1.cmd_setCompensationMode.set_start.assert_not_awaited()

    async def test_disable_compensation_mode_bad_component(self) -> None:
        with pytest.raises(AssertionError):
            await self.mtcs.enable_compensation_mode(component="mtm1m3")

    async def test_move_rotator(self) -> None:
        position = 10.0

        await self.mtcs.move_rotator(position=position)

        self.mtcs.rem.mtrotator.cmd_move.set_start.assert_awaited_with(
            position=position, timeout=self.mtcs.long_timeout
        )
        self.mtcs.rem.mtrotator.evt_inPosition.aget.assert_awaited_with(
            timeout=self.mtcs.fast_timeout
        )
        self.mtcs.rem.mtrotator.evt_inPosition.flush.assert_called()

        self.mtcs.rem.mtrotator.evt_inPosition.next.assert_awaited_with(
            timeout=self.mtcs.long_long_timeout, flush=False
        )

    async def test_move_camera_hexapod(self) -> None:
        hexapod_positions = dict([(axis, np.random.rand()) for axis in "xyzuv"])

        await self.mtcs.move_camera_hexapod(**hexapod_positions)

        for axis in hexapod_positions:
            assert (
                getattr(self._mthexapod_1_evt_uncompensated_position, axis)
                == hexapod_positions[axis]
            )

        self.mtcs.rem.mthexapod_1.cmd_move.set_start.assert_awaited_with(
            **hexapod_positions, w=0.0, sync=True, timeout=self.mtcs.long_timeout
        )

        assert self._mthexapod_1_evt_in_position.inPosition

        self.mtcs.rem.mthexapod_1.evt_inPosition.aget.assert_awaited_with(
            timeout=self.mtcs.fast_timeout
        )
        self.mtcs.rem.mthexapod_1.evt_inPosition.flush.assert_called()

        self.mtcs.rem.mthexapod_1.evt_inPosition.next.assert_awaited_with(
            timeout=self.mtcs.long_timeout, flush=False
        )

    async def test_move_m2_hexapod(self) -> None:
        hexapod_positions = dict([(axis, np.random.rand()) for axis in "xyzuv"])

        await self.mtcs.move_m2_hexapod(**hexapod_positions)

        for axis in hexapod_positions:
            assert (
                getattr(self._mthexapod_2_evt_uncompensated_position, axis)
                == hexapod_positions[axis]
            )

        self.mtcs.rem.mthexapod_2.cmd_move.set_start.assert_awaited_with(
            **hexapod_positions, w=0.0, sync=True, timeout=self.mtcs.long_timeout
        )

        assert self._mthexapod_2_evt_in_position.inPosition

        self.mtcs.rem.mthexapod_2.evt_inPosition.aget.assert_awaited_with(
            timeout=self.mtcs.fast_timeout
        )
        self.mtcs.rem.mthexapod_2.evt_inPosition.flush.assert_called()

        self.mtcs.rem.mthexapod_2.evt_inPosition.next.assert_awaited_with(
            timeout=self.mtcs.long_timeout, flush=False
        )

    async def test_offset_camera_hexapod(self) -> None:
        hexapod_positions = dict([(axis, np.random.rand()) for axis in "xyzuv"])

        await self.mtcs.offset_camera_hexapod(**hexapod_positions)

        for axis in hexapod_positions:
            assert (
                getattr(self._mthexapod_1_evt_uncompensated_position, axis)
                == hexapod_positions[axis]
            )

        self.mtcs.rem.mthexapod_1.cmd_offset.set_start.assert_awaited_with(
            **hexapod_positions, w=0.0, sync=True, timeout=self.mtcs.long_timeout
        )

        assert self._mthexapod_1_evt_in_position.inPosition

        self.mtcs.rem.mthexapod_1.evt_inPosition.aget.assert_awaited_with(
            timeout=self.mtcs.fast_timeout
        )
        self.mtcs.rem.mthexapod_1.evt_inPosition.flush.assert_called()

        self.mtcs.rem.mthexapod_1.evt_inPosition.next.assert_awaited_with(
            timeout=self.mtcs.long_timeout, flush=False
        )

    async def test_offset_m2_hexapod(self) -> None:
        hexapod_positions = dict([(axis, np.random.rand()) for axis in "xyzuv"])

        await self.mtcs.offset_m2_hexapod(**hexapod_positions)

        for axis in hexapod_positions:
            assert (
                getattr(self._mthexapod_2_evt_uncompensated_position, axis)
                == hexapod_positions[axis]
            )

        self.mtcs.rem.mthexapod_2.cmd_offset.set_start.assert_awaited_with(
            **hexapod_positions, w=0.0, sync=True, timeout=self.mtcs.long_timeout
        )

        assert self._mthexapod_2_evt_in_position.inPosition

        self.mtcs.rem.mthexapod_2.evt_inPosition.aget.assert_awaited_with(
            timeout=self.mtcs.fast_timeout
        )
        self.mtcs.rem.mthexapod_2.evt_inPosition.flush.assert_called()

        self.mtcs.rem.mthexapod_2.evt_inPosition.next.assert_awaited_with(
            timeout=self.mtcs.long_timeout, flush=False
        )

    async def test_reset_camera_hexapod_position(self) -> None:
        self._mthexapod_1_evt_uncompensated_position.z = 10.0

        await self.mtcs.reset_camera_hexapod_position()

        for axis in "xyzuvw":
            assert getattr(self._mthexapod_1_evt_uncompensated_position, axis) == 0.0

        assert self._mthexapod_1_evt_in_position.inPosition

        self.mtcs.rem.mthexapod_1.evt_inPosition.aget.assert_awaited_with(
            timeout=self.mtcs.fast_timeout
        )
        self.mtcs.rem.mthexapod_1.evt_inPosition.flush.assert_called()
        self.mtcs.rem.mthexapod_1.cmd_move.set_start.assert_awaited_with(
            x=0, y=0, z=0, u=0, v=0, w=0, sync=True, timeout=self.mtcs.long_timeout
        )
        self.mtcs.rem.mthexapod_1.evt_inPosition.next.assert_awaited_with(
            timeout=self.mtcs.long_timeout, flush=False
        )

    async def test_reset_m2_hexapod_position(self) -> None:
        self._mthexapod_2_evt_uncompensated_position.z = 10.0

        await self.mtcs.reset_m2_hexapod_position()

        for axis in "xyzuvw":
            assert getattr(self._mthexapod_2_evt_uncompensated_position, axis) == 0.0

        assert self._mthexapod_2_evt_in_position.inPosition

        self.mtcs.rem.mthexapod_2.evt_inPosition.aget.assert_awaited_with(
            timeout=self.mtcs.fast_timeout
        )
        self.mtcs.rem.mthexapod_2.evt_inPosition.flush.assert_called()
        self.mtcs.rem.mthexapod_2.cmd_move.set_start.assert_awaited_with(
            x=0, y=0, z=0, u=0, v=0, w=0, sync=True, timeout=self.mtcs.long_timeout
        )
        self.mtcs.rem.mthexapod_2.evt_inPosition.next.assert_awaited_with(
            timeout=self.mtcs.long_timeout, flush=False
        )

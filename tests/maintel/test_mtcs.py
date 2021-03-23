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
import unittest

import numpy as np

import astropy.units as u
from astropy.coordinates import Angle

from lsst.ts import salobj

from lsst.ts.observatory.control.mock import MTCSMock
from lsst.ts.observatory.control.maintel.mtcs import MTCS, MTCSUsages
from lsst.ts.observatory.control.utils import RemoteGroupTestCase, RotType

HB_TIMEOUT = 5  # Basic timeout for heartbeats
SLEW_TIMEOUT = 10  # Basic slewtime timeout for testing
MAKE_TIMEOUT = 60  # Timeout for make_script (sec)

np.random.seed(47)


class TestMTCS(RemoteGroupTestCase, unittest.IsolatedAsyncioTestCase):
    async def basic_make_group(self, usage=None, mock=True):

        if mock:
            self.mtcs_mock = MTCSMock()

        self.mtcs = MTCS(intended_usage=usage)

        return self.mtcs_mock, self.mtcs

    async def test_startup_shutdown(self):

        async with self.make_group(usage=MTCSUsages.StartUp + MTCSUsages.Shutdown):

            #  Check that all components are in STANDBY state
            for comp in self.mtcs.components_attr:
                if comp not in self.mtcs_mock.output_only:
                    with self.subTest("check initial state", component=comp):
                        state = await self.mtcs.get_state(comp)
                        self.assertEqual(state, salobj.State.STANDBY)

            # Enable all components
            await self.mtcs.enable()

            await asyncio.sleep(HB_TIMEOUT)

            # Check that all components are in ENABLED state
            for comp in self.mtcs.components_attr:
                if comp not in self.mtcs_mock.output_only:
                    with self.subTest("check enabled state", component=comp):
                        state = await self.mtcs.get_state(comp)
                        self.assertEqual(state, salobj.State.ENABLED)

            # Send all components to STANDBY state
            await self.mtcs.standby()

            await asyncio.sleep(HB_TIMEOUT)

            #  Check that all components are in STANDBY state
            for comp in self.mtcs.components_attr:
                if comp not in self.mtcs_mock.output_only:
                    with self.subTest("check final state", component=comp):
                        state = await self.mtcs.get_state(comp)
                        self.assertEqual(state, salobj.State.STANDBY)

    async def test_point_azel(self):

        async with self.make_group(
            timeout=MAKE_TIMEOUT,
            usage=MTCSUsages.StartUp + MTCSUsages.Shutdown + MTCSUsages.Slew,
            verbose=True,
        ):

            # enable all components

            await self.mtcs.enable()

            # slew telescope and rotator to random position,
            # do not wait for the dome
            # azimuth, random values between +/- 90.
            az_set = ((np.random.random() - 0.5) * 2.0) * 90.0
            # elevation, random values between 10 and 80.
            el_set = np.random.random() * 70.0 + 10.0
            # rotator, random value between +/- 90.
            rot_set = ((np.random.random() - 0.5) * 2.0) * 90.0

            await self.mtcs.point_azel(
                az=az_set,
                el=el_set,
                rot_tel=rot_set,
                target_name="random",
                wait_dome=False,
                slew_timeout=SLEW_TIMEOUT,
            )

            az_data = await self.mtcs.rem.mtmount.tel_azimuth.next(
                flush=True, timeout=HB_TIMEOUT
            )

            el_data = await self.mtcs.rem.mtmount.tel_elevation.next(
                flush=True, timeout=HB_TIMEOUT
            )

            rot_data = await self.mtcs.rem.mtrotator.tel_rotation.next(
                flush=True, timeout=HB_TIMEOUT
            )

            # xml 7.1/8.0 backward compatibility
            mtmount_actual_position_name = "actualPosition"
            if not hasattr(az_data, mtmount_actual_position_name):
                mtmount_actual_position_name = "angleActual"

            self.assertAlmostEqual(
                getattr(az_data, mtmount_actual_position_name), az_set, 4
            )
            self.assertAlmostEqual(
                getattr(el_data, mtmount_actual_position_name), el_set, 4
            )
            self.assertAlmostEqual(rot_data.demandPosition, rot_set, 4)

    async def test_slew_all(self):

        async with self.make_group(
            timeout=MAKE_TIMEOUT,
            usage=MTCSUsages.StartUp + MTCSUsages.Shutdown + MTCSUsages.Slew,
        ):

            # enable all components
            await self.mtcs.enable()

            # This is a circumpolar object, should be always vizible in
            # Pachon.
            name = "HD 185975"
            ra = Angle("20:28:18.74", unit=u.hourangle)
            dec = Angle("-87:28:19.9", unit=u.deg)

            # Test that slew command works with RA/Dec alone
            # This method only takes floats (ra in hourangle and dec in
            # degrees), so need to get the value of Angle.
            await self.mtcs.slew(ra.value, dec.value, slew_timeout=SLEW_TIMEOUT)

            # Test check_tracking; should not take longer than duration
            await asyncio.wait_for(self.mtcs.check_tracking(5), timeout=5.5)

            # Test check_tracking; should not less than duration
            with self.assertRaises(asyncio.TimeoutError):
                await asyncio.wait_for(self.mtcs.check_tracking(5), timeout=4.5)

            # Test slew_object
            await self.mtcs.slew_object(name=name, slew_timeout=SLEW_TIMEOUT)

            # Test slew_icrs
            await self.mtcs.slew_icrs(
                ra=ra, dec=dec, target_name=name, slew_timeout=SLEW_TIMEOUT
            )

            # Override self.mtcs.slew to check rottype different calls
            self.mtcs.slew = unittest.mock.AsyncMock()

            radec_icrs, rot_angle = await self.mtcs.slew_icrs(
                ra=ra, dec=dec, rot=0.0, target_name=name, rot_type=RotType.Parallactic
            )

            self.assertEqual(radec_icrs.ra, ra)
            self.assertEqual(radec_icrs.dec, dec)
            self.mtcs.slew.assert_awaited_with(
                ra.value,
                dec.value,
                rotPA=rot_angle.deg,
                target_name=name,
                frame=self.mtcs.CoordFrame.ICRS,
                epoch=2000,
                equinox=2000,
                parallax=0,
                pmRA=0,
                pmDec=0,
                rv=0,
                dRA=0,
                dDec=0,
                rot_frame=self.mtcs.RotFrame.TARGET,
                rot_mode=self.mtcs.RotMode.FIELD,
                stop_before_slew=True,
                wait_settle=True,
                slew_timeout=240.0,
            )

            self.mtcs.slew.reset_mock()

            radec_icrs, rot_angle = await self.mtcs.slew_icrs(
                ra=ra, dec=dec, rot=0.0, target_name=name, rot_type=RotType.PhysicalSky
            )

            self.assertEqual(radec_icrs.ra, ra)
            self.assertEqual(radec_icrs.dec, dec)
            self.mtcs.slew.assert_awaited_with(
                ra.value,
                dec.value,
                rotPA=rot_angle.deg,
                target_name=name,
                frame=self.mtcs.CoordFrame.ICRS,
                epoch=2000,
                equinox=2000,
                parallax=0,
                pmRA=0,
                pmDec=0,
                rv=0,
                dRA=0,
                dDec=0,
                rot_frame=self.mtcs.RotFrame.TARGET,
                rot_mode=self.mtcs.RotMode.FIELD,
                stop_before_slew=True,
                wait_settle=True,
                slew_timeout=240.0,
            )

            self.mtcs.slew.reset_mock()

            radec_icrs, rot_angle = await self.mtcs.slew_icrs(
                ra=ra, dec=dec, rot=0.0, target_name=name, rot_type=RotType.Physical
            )

            self.assertEqual(radec_icrs.ra, ra)
            self.assertEqual(radec_icrs.dec, dec)
            self.mtcs.slew.assert_awaited_with(
                ra.value,
                dec.value,
                rotPA=rot_angle.deg,
                target_name=name,
                frame=self.mtcs.CoordFrame.ICRS,
                epoch=2000,
                equinox=2000,
                parallax=0,
                pmRA=0,
                pmDec=0,
                rv=0,
                dRA=0,
                dDec=0,
                rot_frame=self.mtcs.RotFrame.FIXED,
                rot_mode=self.mtcs.RotMode.FIELD,
                stop_before_slew=True,
                wait_settle=True,
                slew_timeout=240.0,
            )

            # TODO: (DM-21336) Test a couple of failure situations.


if __name__ == "__main__":
    unittest.main()

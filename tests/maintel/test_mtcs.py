# This file is part of ts_standardscripts
#
# Developed for the LSST Data Management System.
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

import random
import unittest

import astropy.units as u
import numpy as np

from astropy.coordinates import Angle

import asynctest

from lsst.ts import salobj

# from lsst.ts.idl.enums import MTPtg

from lsst.ts.observatory.control.mock import MTCSMock
from lsst.ts.observatory.control.maintel.mtcs import MTCS, MTCSUsages
from lsst.ts.observatory.control.utils import RemoteGroupTestCase

HB_TIMEOUT = 5  # Basic timeout for heartbeats
SLEW_TIMEOUT = 10  # Basic slewtime timeout for testing
MAKE_TIMEOUT = 60  # Timeout for make_script (sec)

random.seed(47)  # for set_random_lsst_dds_domain


class TestMTCS(RemoteGroupTestCase, asynctest.TestCase):
    async def basic_make_group(self, usage=None):
        self.mtcs_mock = MTCSMock()

        self.mtcs = MTCS(intended_usage=usage)

        return self.mtcs_mock, self.mtcs

    async def test_startup_shutdown(self):

        async with self.make_group(usage=MTCSUsages.StartUp + MTCSUsages.Shutdown):

            #  Check that all components are in STANDBY state
            for comp in self.mtcs.components:
                if comp not in self.mtcs_mock.output_only:
                    with self.subTest("check initial state", component=comp):
                        state = await self.mtcs.get_state(comp)
                        self.assertEqual(state, salobj.State.STANDBY)

            # Enable all components
            await self.mtcs.enable()

            await asyncio.sleep(HB_TIMEOUT)

            # Check that all components are in ENABLED state
            for comp in self.mtcs.components:
                if comp not in self.mtcs_mock.output_only:
                    with self.subTest("check enabled state", component=comp):
                        state = await self.mtcs.get_state(comp)
                        self.assertEqual(state, salobj.State.ENABLED)

            # Send all components to STANDBY state
            await self.mtcs.standby()

            await asyncio.sleep(HB_TIMEOUT)

            #  Check that all components are in STANDBY state
            #  Check that all components are in STANDBY state
            for comp in self.mtcs.components:
                if comp not in self.mtcs_mock.output_only:
                    with self.subTest("check final state", component=comp):
                        state = await self.mtcs.get_state(comp)
                        self.assertEqual(state, salobj.State.STANDBY)

    async def test_point_azel(self):

        async with self.make_group(
            usage=MTCSUsages.StartUp + MTCSUsages.Shutdown + MTCSUsages.Slew
        ):

            # enable all components

            await self.mtcs.enable()

            # slew telescope and rotator to random position,
            # do not wait for the dome
            # azimuth, random values between +/- 90.
            az_set = ((np.random.random() - 0.5) * 2.0) * 90.0
            # elevation, random values between 10 and 80.
            el_set = np.random.random() * 70.0 + 10.0
            # rotator, rando value between +/- 90.
            rot_set = ((np.random.random() - 0.5) * 2.0) * 90.0

            ret_val = await self.mtcs.point_azel(
                az=az_set,
                el=el_set,
                rot_tel=rot_set,
                target_name="random",
                wait_dome=False,
                slew_timeout=SLEW_TIMEOUT,
            )

            print(f"Point azel returned: {ret_val}")

            az_rec = await self.mtcs.rem.mtmount.tel_Azimuth.next(
                flush=True, timeout=HB_TIMEOUT
            )

            el_rec = await self.mtcs.rem.mtmount.tel_Elevation.next(
                flush=True, timeout=HB_TIMEOUT
            )

            rot_rec = await self.mtcs.rem.rotator.tel_Application.next(
                flush=True, timeout=HB_TIMEOUT
            )

            self.assertEqual(az_rec.Azimuth_Angle_Set, az_set)
            self.assertEqual(el_rec.Elevation_Angle_Set, el_set)
            self.assertEqual(rot_rec.Demand, rot_set)

    async def test_slew_all(self):

        async with self.make_group(
            usage=MTCSUsages.StartUp + MTCSUsages.Shutdown + MTCSUsages.Slew
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

            # Test slew_object
            await self.mtcs.slew_object(name=name, slew_timeout=SLEW_TIMEOUT)

            # Test slew_icrs
            await self.mtcs.slew_icrs(
                ra=ra, dec=dec, target_name=name, slew_timeout=SLEW_TIMEOUT
            )

            # TODO: (DM-21336) Test a couple of failure situations.


if __name__ == "__main__":
    unittest.main()

import asyncio
import logging
import random
import unittest

import asynctest

from lsst.ts.idl.enums import ATPtg

from lsst.ts.observatory.control.mock import ATCSMock
from lsst.ts.observatory.control.auxtel.atcs import ATCS
from lsst.ts.observatory.control.utils import BaseGroupTestCase

HB_TIMEOUT = 5  # Basic timeout for heartbeats
MAKE_TIMEOUT = 60  # Timeout for make_script (sec)

random.seed(47)  # for set_random_lsst_dds_domain

logging.basicConfig(level=logging.DEBUG)


class TestATTCS(BaseGroupTestCase, asynctest.TestCase):
    async def basic_make_group(self):
        self.attcs_mock = ATCSMock()

        self.atmcs = self.attcs_mock.atmcs
        self.atptg = self.attcs_mock.atptg
        self.atdome = self.attcs_mock.atdome
        self.ataos = self.attcs_mock.ataos
        self.atpneumatics = self.attcs_mock.atpneumatics
        self.athexapod = self.attcs_mock.athexapod
        self.atdometrajectory = self.attcs_mock.atdometrajectory

        self.attcs = ATCS()

        return self.attcs_mock, self.attcs

    async def test_slew_all(self):

        async with self.make_group():

            await self.attcs.enable(
                {
                    "atmcs": "",
                    "atptg": "",
                    "atdome": "",
                    "ataos": "",
                    "atpneumatics": "",
                    "athexapod": "",
                    "atdometrajectory": "",
                }
            )

            ra = 0.0
            dec = -30.0

            with self.subTest("test_slew", ra=ra, dec=dec):

                await self.attcs.slew(
                    ra, dec, slew_timeout=self.attcs_mock.slew_time * 2.0
                )

            for planet in ATPtg.Planets:
                with self.subTest(f"test_slew_to_planet::{planet}", planet=planet):
                    await self.attcs.slew_to_planet(
                        planet, slew_timeout=self.attcs_mock.slew_time * 2.0
                    )

            with self.subTest("test_slew_fail_atptg_fault", ra=ra, dec=dec):

                with self.assertRaises(RuntimeError):
                    ret_val = await asyncio.gather(
                        self.attcs.slew(
                            ra, dec, slew_timeout=self.attcs_mock.slew_time * 2.0
                        ),
                        self.attcs_mock.atptg_wait_and_fault(1.0),
                        return_exceptions=True,
                    )
                    for val in ret_val:
                        if isinstance(val, Exception):
                            raise val

            await self.attcs.enable(
                {
                    "atmcs": "",
                    "atptg": "",
                    "atdome": "",
                    "ataos": "",
                    "atpneumatics": "",
                    "athexapod": "",
                    "atdometrajectory": "",
                }
            )

            with self.subTest("test_slew_fail_atmcs_fault", ra=ra, dec=dec):

                with self.assertRaises(RuntimeError):

                    ret_val = await asyncio.gather(
                        self.attcs.slew(
                            ra, dec, slew_timeout=self.attcs_mock.slew_time * 2.0
                        ),
                        self.attcs_mock.atmcs_wait_and_fault(1.0),
                        return_exceptions=True,
                    )

                    for val in ret_val:
                        if isinstance(val, Exception):
                            raise val

            await self.attcs.enable(
                {
                    "atmcs": "",
                    "atptg": "",
                    "atdome": "",
                    "ataos": "",
                    "atpneumatics": "",
                    "athexapod": "",
                    "atdometrajectory": "",
                }
            )

            with self.subTest("test_slew_toplanet_fail_atmcs_fault"):

                with self.assertRaises(RuntimeError):
                    ret_val = await asyncio.gather(
                        self.attcs.slew_to_planet(
                            ATPtg.Planets.JUPITER,
                            slew_timeout=self.attcs_mock.slew_time * 2.0,
                        ),
                        self.attcs_mock.atmcs_wait_and_fault(1.0),
                        return_exceptions=True,
                    )
                    for val in ret_val:
                        if isinstance(val, Exception):
                            raise val

            await self.attcs.enable(
                {
                    "atmcs": "",
                    "atptg": "",
                    "atdome": "",
                    "ataos": "",
                    "atpneumatics": "",
                    "athexapod": "",
                    "atdometrajectory": "",
                }
            )

            with self.subTest("test_slew_toplanet_fail_atptg_fault"):

                with self.assertRaises(RuntimeError):
                    ret_val = await asyncio.gather(
                        self.attcs.slew_to_planet(
                            ATPtg.Planets.JUPITER,
                            slew_timeout=self.attcs_mock.slew_time * 2.0,
                        ),
                        self.attcs_mock.atptg_wait_and_fault(1.0),
                        return_exceptions=True,
                    )
                    for val in ret_val:
                        if isinstance(val, Exception):
                            raise val

    async def test_startup_shutdown(self):

        async with self.make_group():

            # Testing when not passing settings for all components and only
            # atdome and ataos sent evt_settingVersions.
            # atdome sent a single label but ataos sends more then one.

            self.atdome.evt_settingVersions.set_put(
                recommendedSettingsLabels="setting4_atdome_set"
            )

            self.ataos.evt_settingVersions.set_put(
                recommendedSettingsLabels="setting4_ataos_set1,setting4_ataos2_set2"
            )

            # Give remotes some time to update their data.
            await asyncio.sleep(self.attcs.fast_timeout)

            with self.subTest("test::enable:settings_published"):
                await self.attcs.enable()

            for comp in self.attcs.components:
                with self.subTest("test::startup:settings_to_apply", comp=comp):
                    if comp == "atdome":
                        self.assertEqual(
                            self.attcs_mock.settings_to_apply[comp],
                            "setting4_atdome_set",
                        )
                    elif comp == "ataos":
                        self.assertEqual(
                            self.attcs_mock.settings_to_apply[comp],
                            "setting4_ataos_set1",
                        )
                    else:
                        self.assertEqual(self.attcs_mock.settings_to_apply[comp], "")

            await self.attcs.standby()

            settings = dict(
                zip(
                    self.attcs.components,
                    [f"setting4_{c}" for c in self.attcs.components],
                )
            )

            with self.subTest("test::startup::with settings", **settings):
                await self.attcs.startup(settings)

            for comp in settings:
                with self.subTest("test::startup:settings_to_apply", comp=comp):
                    self.assertEqual(
                        self.attcs_mock.settings_to_apply[comp], settings[comp]
                    )

            # Give remotes some time to update their data.
            await asyncio.sleep(self.attcs.fast_timeout)

            with self.subTest("test::shutdown"):
                await self.attcs.shutdown()


if __name__ == "__main__":
    unittest.main()

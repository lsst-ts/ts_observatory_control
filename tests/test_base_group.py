import logging
import random
import unittest

import asynctest

from lsst.ts import salobj

from lsst.ts.observatory.control.remote_group import (
    RemoteGroup,
    Usages,
    UsagesResources,
)
from lsst.ts.observatory.control.utils import RemoteGroupTestCase

random.seed(47)  # for set_random_lsst_dds_domain

logging.basicConfig()

HB_TIMEOUT = 5  # Heartbeat timeout (sec)
MAKE_TIMEOUT = 60  # Timeout for make_script (sec)


class TestBaseGroup(RemoteGroupTestCase, asynctest.TestCase):
    async def basic_make_group(self, usage=None):

        ntest = 4

        self.basegroup = RemoteGroup(
            components=[f"Test:{c_id+1}" for c_id in range(ntest)],
            intended_usage=usage,
        )

        self.mock_test = [salobj.TestCsc(index=c_id + 1) for c_id in range(ntest)]

        return (self.basegroup, *self.mock_test)

    async def test_usage_resources(self):

        use_case = UsagesResources(
            components_attr=["test_1", "test_2"], readonly=False, generics=["testTopic"]
        )

        self.assertIn("testTopic", use_case.include)

        use_case = UsagesResources(
            components_attr=["test_1", "test_2"], readonly=False, test_1=["testTopic1"]
        )

        self.assertIn("testTopic1", use_case.include)

        use_case = UsagesResources(
            components_attr=["test_1", "test_2"], readonly=False, test_2=["testTopic2"]
        )

        self.assertIn("testTopic2", use_case.include)

        use_case = UsagesResources(
            components_attr=["test_1", "test_2"],
            readonly=False,
            generics=["testTopic"],
            test_1=["testTopic1"],
            test_2=["testTopic2"],
        )

        self.assertIn("testTopic", use_case.include)
        self.assertIn("testTopic1", use_case.include)
        self.assertIn("testTopic2", use_case.include)

        with self.assertRaises(TypeError):
            UsagesResources(
                components_attr=["test_1", "test_2"],
                readonly=False,
                test_3=["testTopic3"],
            )

    async def test_inspect_settings(self):

        async with self.make_group(
            usage=Usages.StateTransition + Usages.MonitorHeartBeat
        ):

            settings = await self.basegroup.inspect_settings()

            for comp in self.basegroup.components_attr:
                with self.subTest(msg=f"Check settings for {comp}", component=comp):
                    self.assertIn(comp, settings)
                    self.assertTrue(len(settings[comp]) > 0)

            for comp in self.basegroup.components_attr:
                not_this = self.basegroup.components_attr.copy()
                not_this.remove(comp)
                settings = await self.basegroup.inspect_settings([comp])
                with self.subTest(
                    msg=f"Check individual settings for {comp}", component=comp
                ):
                    self.assertIn(comp, settings)
                    self.assertTrue(len(settings[comp]) > 0)

                for not_comp in not_this:
                    with self.subTest(
                        msg="{not_comp} not in settings.", component=comp
                    ):
                        self.assertNotIn(not_comp, settings)

            with self.assertRaises(RuntimeError):
                await self.basegroup.inspect_settings(["nocomp"])

    async def test_basic(self):

        async with self.make_group(
            usage=Usages.StateTransition + Usages.MonitorHeartBeat
        ):

            # Check that all CSCs go to enable State
            await self.basegroup.enable({})

            for comp in self.basegroup.components_attr:
                with self.subTest(msg=f"Check {comp} is enable", component=comp):
                    await getattr(self.basegroup.rem, comp).evt_heartbeat.next(
                        flush=True, timeout=HB_TIMEOUT
                    )
                    ss = await self.basegroup.get_state(comp)
                    self.assertEqual(ss, salobj.State.ENABLED)

            # Check that all CSCs go to standby
            await self.basegroup.standby()

            for comp in self.basegroup.components_attr:
                with self.subTest(msg=f"Check {comp} is in standby", component=comp):
                    await getattr(self.basegroup.rem, comp).evt_heartbeat.next(
                        flush=True, timeout=HB_TIMEOUT
                    )
                    ss = await self.basegroup.get_state(comp)
                    self.assertEqual(ss, salobj.State.STANDBY)


if __name__ == "__main__":
    unittest.main()

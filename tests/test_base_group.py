import logging
import random
import unittest

import asynctest

from lsst.ts import salobj

from lsst.ts.observatory.control.remote_group import RemoteGroup, Usages
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

        mock_test = [salobj.TestCsc(index=c_id + 1) for c_id in range(ntest)]

        return (self.basegroup, *mock_test)

    async def test_basic(self):

        async with self.make_group(
            usage=Usages.StateTransition + Usages.MonitorHeartBeat
        ):
            # Check that all CSCs go to enable State
            await self.basegroup.enable({})

            for comp in self.basegroup.components:
                with self.subTest(msg=f"Check {comp} is enable", component=comp):
                    await getattr(self.basegroup.rem, comp).evt_heartbeat.next(
                        flush=True, timeout=HB_TIMEOUT
                    )
                    ss = await self.basegroup.get_state(comp)
                    self.assertEqual(ss, salobj.State.ENABLED)

            # Check that all CSCs go to standby
            await self.basegroup.standby()

            for comp in self.basegroup.components:
                with self.subTest(msg=f"Check {comp} is in standby", component=comp):
                    await getattr(self.basegroup.rem, comp).evt_heartbeat.next(
                        flush=True, timeout=HB_TIMEOUT
                    )
                    ss = await self.basegroup.get_state(comp)
                    self.assertEqual(ss, salobj.State.STANDBY)


if __name__ == "__main__":
    unittest.main()

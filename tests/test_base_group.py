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
import typing
import unittest

import pytest
from lsst.ts import salobj
from lsst.ts.observatory.control.remote_group import (
    RemoteGroup,
    Usages,
    UsagesResources,
)
from lsst.ts.observatory.control.utils import RemoteGroupTestCase

HB_TIMEOUT = 5  # Heartbeat timeout (sec)
MAKE_TIMEOUT = 60  # Timeout for make_script (sec)


class TestBaseGroup(RemoteGroupTestCase, unittest.IsolatedAsyncioTestCase):
    async def basic_make_group(
        self, usage: typing.Optional[int] = None
    ) -> typing.Iterable[typing.Union[RemoteGroup, salobj.BaseCsc]]:

        self.ntest = 4

        self.basegroup = RemoteGroup(
            components=[f"Test:{c_id+1}" for c_id in range(self.ntest)],
            intended_usage=usage,
        )

        if usage != Usages.DryTest:
            self.mock_test = [
                salobj.TestCsc(index=c_id + 1) for c_id in range(self.ntest)
            ]
        else:
            self.mock_test = []

        return (self.basegroup, *self.mock_test)

    async def test_usage_resources(self) -> None:

        use_case = UsagesResources(
            components_attr=["test_1", "test_2"], readonly=False, generics=["testTopic"]
        )

        assert "testTopic" in use_case.include

        use_case = UsagesResources(
            components_attr=["test_1", "test_2"], readonly=False, test_1=["testTopic1"]
        )

        assert "testTopic1" in use_case.include

        use_case = UsagesResources(
            components_attr=["test_1", "test_2"], readonly=False, test_2=["testTopic2"]
        )

        assert "testTopic2" in use_case.include

        use_case = UsagesResources(
            components_attr=["test_1", "test_2"],
            readonly=False,
            generics=["testTopic"],
            test_1=["testTopic1"],
            test_2=["testTopic2"],
        )

        assert "testTopic" in use_case.include
        assert "testTopic1" in use_case.include
        assert "testTopic2" in use_case.include

        with pytest.raises(TypeError):
            UsagesResources(
                components_attr=["test_1", "test_2"],
                readonly=False,
                test_3=["testTopic3"],
            )

    async def test_basic(self) -> None:

        async with self.make_group(
            usage=Usages.StateTransition + Usages.MonitorHeartBeat
        ):

            # Check get heartbeat
            for comp in self.basegroup.components_attr:
                with self.subTest(msg=f"Check get heartbeat from {comp}.", comp=comp):
                    await self.basegroup.get_heartbeat(comp)

            # Check next heartbeat
            for comp in self.basegroup.components_attr:
                with self.subTest(msg=f"Check next heartbeat from {comp}.", comp=comp):
                    await self.basegroup.next_heartbeat(comp)

            # Check that all CSCs go to enable State
            await self.basegroup.enable({})

            for comp in self.basegroup.components_attr:
                with self.subTest(msg=f"Check {comp} is enable", component=comp):
                    ss = await self.basegroup.get_state(comp)
                    assert ss == salobj.State.ENABLED

            # Check that all CSCs go to standby
            await self.basegroup.standby()

            for comp in self.basegroup.components_attr:
                with self.subTest(msg=f"Check {comp} is in standby", component=comp):
                    ss = await self.basegroup.get_state(comp)
                    assert ss == salobj.State.STANDBY

            # Test assert liveliness
            await self.basegroup.assert_liveliness()

            # Send one CSC to offline and make sure it raises an exception
            await self.basegroup.set_state(salobj.State.OFFLINE, components=["test_1"])

            with pytest.raises(AssertionError):
                await self.basegroup.assert_liveliness()

            # Now check that if I ignore the offline component it works again
            self.basegroup.check.test_1 = False

            await self.basegroup.assert_liveliness()

    async def test_assert_enabled(self) -> None:
        async with self.make_group(
            usage=Usages.StateTransition + Usages.MonitorHeartBeat
        ):

            with pytest.raises(AssertionError):
                await self.basegroup.assert_all_enabled()

            await self.basegroup.enable()

            await self.basegroup.assert_all_enabled()

    async def test_get_simulation_mode(self) -> None:
        async with self.make_group(usage=Usages.CheckSimulationMode):

            component_simulation_mode = await self.basegroup.get_simulation_mode()

            assert len(component_simulation_mode) == len(self.basegroup.components_attr)

            for component in component_simulation_mode:
                assert component_simulation_mode[component].mode == 0

            component_simulation_mode = await self.basegroup.get_simulation_mode(
                ["test_1"]
            )

            assert len(component_simulation_mode) == 1

            assert component_simulation_mode["test_1"].mode == 0

    async def test_get_software_versions(self) -> None:
        async with self.make_group(usage=Usages.CheckSoftwareVersions):

            software_versions = await self.basegroup.get_software_versions()

            assert len(software_versions) == len(self.basegroup.components_attr)

            for i, component in enumerate(software_versions):
                assert (
                    software_versions[component].cscVersion == self.mock_test[i].version
                )

            software_versions = await self.basegroup.get_software_versions(["test_1"])

            assert len(software_versions) == 1

            assert software_versions["test_1"].cscVersion == self.mock_test[0].version

    async def test_get_work_components(self) -> None:
        async with self.make_group(usage=Usages.DryTest):
            work_components = self.basegroup.get_work_components()

            assert len(work_components) == self.ntest

            work_components = self.basegroup.get_work_components(["test_1"])

            assert len(work_components) == 1

            with pytest.raises(RuntimeError):
                self.basegroup.get_work_components(["bad_1"])

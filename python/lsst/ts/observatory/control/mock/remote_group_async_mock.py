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
# along with this program. If not, see <https://www.gnu.org/licenses/>.

__all__ = ["RemoteGroupAsyncMock"]

import abc
import asyncio
import copy
import itertools
import types
import typing
import unittest
import unittest.mock

from lsst.ts import salobj, utils
from lsst.ts.xml.component_info import ComponentInfo

from .. import RemoteGroup
from ..utils import KwArgsCoro, KwArgsFunc

HB_TIMEOUT = 5  # Heartbeat timeout (sec)
MAKE_TIMEOUT = 60  # Timeout for make_script (sec)


class RemoteGroupAsyncMock(
    unittest.IsolatedAsyncioTestCase,
    metaclass=abc.ABCMeta,
):
    """A utility class for unit tests with mocks."""

    summary_state_queue_event: typing.Dict[str, asyncio.Event]
    summary_state: typing.Dict[str, salobj.type_hints.BaseDdsDataType]
    summary_state_queue: typing.Dict[
        str, typing.List[salobj.type_hints.BaseDdsDataType]
    ]
    components_metadata: typing.Dict[str, ComponentInfo]
    component_commands_arguments: typing.Dict[str, typing.Dict[str, typing.Set[str]]]

    @property
    @abc.abstractmethod
    def remote_group(self) -> RemoteGroup:
        raise NotImplementedError()

    @staticmethod
    def get_component_metadata(
        components: typing.List[str],
    ) -> typing.Dict[str, typing.Any]:
        """Gather metadata information, needed to validate topics versions.

        Parameters
        ----------
        components : `list` of `str`
            List of components name in the "Name:index" format.

        Returns
        -------
        `dict`
            Component metadata.
        """

        return dict(
            [
                (
                    component,
                    ComponentInfo(salobj.name_to_name_index(component)[0], "unit-test"),
                )
                for component in components
            ]
        )

    def run(self, result: typing.Any = None) -> None:
        """Override `run` to set a random LSST_DDS_PARTITION_PREFIX
        and set LSST_SITE=test for every test.

        https://stackoverflow.com/a/11180583
        """
        salobj.set_random_lsst_dds_partition_prefix()
        with utils.modify_environ(LSST_SITE="test"):
            super().run(result)  # type: ignore

    async def asyncSetUp(self) -> None:
        """Setup AsyncMock.

        The idea is to replace the placeholder for the remotes (in atcs.rem) by
        AsyncMock. The remote for each component is replaced by an AsyncMock
        and later augmented to emulate the behavior of the Remote->Controller
        interaction with side_effect and return_value. By default all mocks are
        augmented to handle summary state setting.
        """

        self.components_metadata = self.get_component_metadata(
            self.remote_group.components
        )

        await self.setup_types()
        await self.setup_basic_mocks()
        await self.setup_mocks()

        self.remote_group.reset_checks()

        return await super().asyncSetUp()

    @abc.abstractmethod
    async def setup_types(self) -> None:
        raise NotImplementedError()

    async def setup_basic_mocks(self) -> None:
        """Setup basic mock for the components in the group.

        This method creates an AsyncMock with spec that matches the component.
        By default, each command on the CSC is configured with a mock that will
        check the keyword parameters against its interface. Also attach mocks
        for all events and telemetry.
        """
        self.component_commands_arguments = dict()
        self.summary_state = dict()
        self.summary_state_queue_event = dict()
        self.summary_state_queue = dict()

        for component, component_name in zip(
            self.remote_group.components_attr, self.remote_group.components
        ):
            self.set_component_commands_arguments(component, component_name)

            topics = self.get_component_topics(component_name)

            spec = self.get_spec_from_topics(topics)

            side_effects = self.get_side_effects_for(component, spec)

            self.summary_state[component] = self.get_sample(
                component=component_name, topic="logevent_summaryState"
            )

            self.summary_state[component].summaryState = salobj.State.STANDBY
            self.summary_state_queue[component] = []
            self.summary_state_queue_event[component] = asyncio.Event()

            # Set mock for the component remote. Note that we pass in spec and
            # side effects. When passing spec to an AsyncMock all values
            # receive a normal Mock. The side effects we create add AsyncMock
            # for the methods that are asynchronous, plus some augmented side
            # effects to deal with default CSC behavior.
            setattr(
                self.remote_group.rem,
                component,
                unittest.mock.AsyncMock(spec=spec, **side_effects),
            )

    def get_component_topics(self, component_name: str) -> typing.List[str]:
        """Get the names of all the topics for the component.

        Commands are renamed from command_* -> cmd_*, events logevent_* ->
        evt_* and elemetry topics receive the prefix "tel_".

        Parameters
        ----------
        component_name : `str`
            Name of the component, e.g. GenericCamera:1.

        Returns
        -------
        topics : `typing.List[str]`
            List of topics names.
        """
        topics = [
            topic_name for topic_name in self.components_metadata[component_name].topics
        ]

        return topics

    def set_component_commands_arguments(
        self, component: str, component_name: str
    ) -> None:
        """Set the dictionary with methods that checks the component commands
        arguments.

        These methods are later used in the mock to check the arguments passed
        to the commands set and set_start methods.

        Parameters
        ----------
        component : str
            The component attribute name, e.g. genericcamera_1.
        component_name : str
            The component name, e.g. GenericCamera:1.
        """
        self.component_commands_arguments[component] = dict(
            [
                (
                    str(topic_name).split(sep="_", maxsplit=1)[1],
                    set(
                        self.components_metadata[component_name]
                        .topics[topic_name]
                        .fields.keys()
                    ),
                )
                for topic_name in self.components_metadata[component_name].topics
                if "cmd_" in topic_name
            ]
        )

    def get_spec_from_topics(self, topics: typing.List[str]) -> typing.List[str]:
        """Generate a CSC spec from a list of topics.

        Parameters
        ----------
        topics : `list` of `str`
            Name ot the topics.

        Returns
        -------
        spec : `list` of `str`
            Expanded list of specs.

        Notes
        -----
        Expand each topic to contain the basic method set. Commands are
        expanded to have set, start and set_start, events and telemetry are
        expanded to have next, get, aget and flush.
        """
        spec = list(
            itertools.chain(
                *[
                    (
                        (
                            topic,
                            f"{topic}.set",
                            f"{topic}.start",
                            f"{topic}.set_start",
                            f"{topic}.DataType",
                        )
                        if topic.startswith("cmd_")
                        else (
                            topic,
                            f"{topic}.next",
                            f"{topic}.get",
                            f"{topic}.aget",
                            f"{topic}.flush",
                            f"{topic}.DataType",
                        )
                    )
                    for topic in topics
                ]
            )
        )

        return spec

    def get_side_effects_for(
        self, component: str, spec: typing.List[str]
    ) -> typing.Dict[str, typing.Any]:
        """Get side effects for a component spec.

        Parameters
        ----------
        component : str
            The name of the component.
        spec : `list` of `str`
            The "specification" for the component, this is a list of methods
            that need to be mocked.

        Returns
        -------
        side_effect : `dict`
            A dictionary with the side effects, which contains the spec as key
            and an AsyncMock as value.
        """
        side_effects: typing.Dict[str, typing.Any] = dict(
            [
                (
                    (topic, unittest.mock.AsyncMock())
                    if all(
                        [
                            not topic.endswith(sync_methods)
                            for sync_methods in [".get", ".set", ".flush", "DataType"]
                        ]
                    )
                    else (topic, unittest.mock.Mock())
                )
                for topic in spec
            ]
        )

        # Add mock to check input parameter on commands set_start (AsyncMock)
        # and set (Mock).
        side_effects.update(
            dict(
                list(
                    itertools.chain(
                        *[
                            (
                                (
                                    f"cmd_{command}.set_start.side_effect",
                                    self.get_async_check_command_args(
                                        component, command
                                    ),
                                ),
                                (
                                    f"cmd_{command}.set.side_effect",
                                    self.get_sync_check_command_args(
                                        component, command
                                    ),
                                ),
                            )
                            for command in self.component_commands_arguments[component]
                        ]
                    )
                )
            )
        )

        # Add mocks for state transition events, summary state and heartbeats.
        side_effects.update(
            {
                "cmd_start.set_start.side_effect": self.set_summary_state_for(
                    component, salobj.State.DISABLED
                ),
                "cmd_start.start.side_effect": self.set_summary_state_for(
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
                "evt_summaryState.flush.side_effect": self.flush_summary_state_for(
                    component
                ),
                "evt_heartbeat.next.side_effect": self.get_heartbeat,
                "evt_heartbeat.aget.side_effect": self.get_heartbeat,
            }
        )

        return side_effects

    def get_sample(self, component: str, topic: str) -> types.SimpleNamespace:
        """Generate a sample for the component topic.

        Parameters
        ----------
        component : `str`
            Name of the component.
        topic : `str`
            Name of the topic.

        Returns
        -------
        `types.SimpleNamespace`
            Namespace object with the topic data structure.
        """

        _topic = topic.replace("logevent_", "evt_").replace("command_", "cmd_")

        if _topic not in self.components_metadata[component].topics:
            raise RuntimeError(
                f"No topic {topic} -> {_topic} in {component}. "
                f"Available topics are {self.components_metadata[component].topics}"
            )
        return types.SimpleNamespace(
            **self.components_metadata[component].topics[_topic].fields
        )

    @abc.abstractmethod
    async def setup_mocks(self) -> None:
        raise NotImplementedError()

    def get_summary_state_for(
        self, comp: str
    ) -> typing.Callable[
        [typing.Optional[float]], typing.Coroutine[typing.Any, typing.Any, None]
    ]:
        async def get_summary_state(timeout: typing.Optional[float] = None) -> None:
            return self.summary_state[comp]

        return get_summary_state

    def get_async_check_command_args(self, component: str, command: str) -> KwArgsCoro:
        async def check_command(**kwargs: typing.Any) -> None:
            keyword_arguments = set(kwargs.keys())
            keyword_arguments.discard("timeout")
            difference = keyword_arguments.difference(
                self.component_commands_arguments[component][command]
            )
            assert len(difference) == 0, (
                f"Unexpected arguments {difference}. "
                f"Expected: {self.component_commands_arguments[component][command]}"
            )

        return check_command

    def get_sync_check_command_args(self, component: str, command: str) -> KwArgsFunc:
        def check_command(**kwargs: typing.Any) -> None:
            keyword_arguments = set(kwargs.keys())
            keyword_arguments.discard("timeout")
            difference = keyword_arguments.difference(
                self.component_commands_arguments[component][command]
            )
            assert len(difference) == 0, (
                f"Unexpected arguments {difference}. "
                f"Expected: {self.component_commands_arguments[component][command]}"
            )

        return check_command

    def next_summary_state_for(
        self, comp: str
    ) -> typing.Callable[
        [bool, typing.Optional[float]], typing.Coroutine[typing.Any, typing.Any, None]
    ]:
        async def next_summary_state(
            flush: bool, timeout: typing.Optional[float] = None
        ) -> salobj.type_hints.BaseMsgType:
            if flush or len(self.summary_state_queue[comp]) == 0:
                self.summary_state_queue_event[comp].clear()
                self.summary_state_queue[comp] = []
            await asyncio.wait_for(
                self.summary_state_queue_event[comp].wait(), timeout=timeout
            )
            return self.summary_state[comp]

        return next_summary_state

    def set_summary_state_for(
        self, comp: str, state: salobj.State
    ) -> typing.Callable[
        [typing.Any, typing.Any], typing.Coroutine[typing.Any, typing.Any, None]
    ]:
        async def set_summary_state(*args: typing.Any, **kwargs: typing.Any) -> None:
            self.summary_state[comp].summaryState = int(state)
            self.summary_state_queue[comp].append(copy.copy(self.summary_state[comp]))
            self.summary_state_queue_event[comp].set()

        return set_summary_state

    def flush_summary_state_for(self, comp: str) -> typing.Callable[[], None]:
        def flush_summary_state() -> None:
            self.summary_state_queue_event[comp].clear()
            self.summary_state_queue[comp] = []

        return flush_summary_state

    async def get_heartbeat(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> typing.Any:
        """Emulate heartbeat functionality."""
        await asyncio.sleep(1.0)
        return types.SimpleNamespace()

    def get_all_checks(self) -> typing.Any:
        """Get a copy of the check attribute from the remote group.

        Returns
        -------
        check : `types.SimpleNamespace`
            Copy of the check attribute.
        """
        check = copy.copy(self.remote_group.check)
        for comp in self.remote_group.components_attr:
            setattr(check, comp, True)
        return check

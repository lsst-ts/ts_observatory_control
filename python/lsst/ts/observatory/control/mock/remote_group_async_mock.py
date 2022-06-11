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
import copy
import types
import asyncio
import typing
import unittest
import unittest.mock

from lsst.ts import idl
from lsst.ts import salobj

from .. import RemoteGroup


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

    @property
    @abc.abstractmethod
    def remote_group(self) -> RemoteGroup:
        raise NotImplementedError()

    @staticmethod
    def get_component_metadata(
        components: typing.List[str],
    ) -> typing.Dict[str, typing.Any]:
        """Gather metadada information, needed to validate topics versions.

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
                    salobj.parse_idl(
                        component,
                        idl.get_idl_dir()
                        / f"sal_revCoded_{component.split(':')[0]}.idl",
                    ),
                )
                for component in components
            ]
        )

    async def asyncSetUp(self) -> None:
        """Setup AsyncMock.

        The idea is to replace the placeholder for the remotes (in atcs.rem) by
        AsyncMock. The remote for each component is replaced by an AsyncMock
        and later augmented to emulate the behavior of the Remote->Controller
        interaction with side_effect and return_value. By default all mocks are
        augmented to handle summary state setting.
        """

        await self.setup_types()
        await self.setup_basic_mocks()
        await self.setup_mocks()

        return await super().asyncSetUp()

    @abc.abstractmethod
    async def setup_types(self) -> None:
        raise NotImplementedError()

    async def setup_basic_mocks(self) -> None:
        for component in self.remote_group.components_attr:
            setattr(
                self.remote_group.rem,
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
                        "evt_configurationsAvailable.aget.return_value": None,
                    }
                ),
            )
            # A trick to support calling a regular method (flush) from an
            # AsyncMock. Basically, attach a regular Mock.
            getattr(self.remote_group.rem, f"{component}").evt_summaryState.attach_mock(
                unittest.mock.Mock(),
                "flush",
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
            return self.summary_state_queue[comp].pop(0)

        return next_summary_state

    def set_summary_state_for(
        self, comp: str, state: salobj.State
    ) -> typing.Callable[
        [typing.Any, typing.Any], typing.Coroutine[typing.Any, typing.Any, None]
    ]:
        async def set_summary_state(*args: typing.Any, **kwargs: typing.Any) -> None:
            self.summary_state[comp].summaryState = int(state)
            self.summary_state_queue[comp].append(
                copy.copy(self.summary_state[comp].summaryState)
            )
            self.summary_state_queue_event[comp].set()

        return set_summary_state

    async def get_heartbeat(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> typing.Any:
        """Emulate heartbeat functionality."""
        await asyncio.sleep(1.0)
        return types.SimpleNamespace()

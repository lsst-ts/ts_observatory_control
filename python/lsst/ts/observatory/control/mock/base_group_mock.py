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

__all__ = ["BaseGroupMock"]

import asyncio
import functools
import logging
import types
import typing

from lsst.ts import salobj

LONG_TIMEOUT = 30  # seconds
HEARTBEAT_INTERVAL = 1  # seconds
CLOSE_SLEEP = 5  # seconds

TBaseGroupMock = typing.TypeVar("TBaseGroupMock", bound="BaseGroupMock")


class BaseGroupMock:
    """Base Mock for groups of CSCs.

    This is useful for unit testing.

    Parameters
    ----------
    components : `list` [`str`]
        A list of strings with the names of the SAL components that are part
        of the group.
    output_only : `list` [`str`]
        A list of strings with the names of the SAL components that only send
        telemetry and events, but do not reply to commands. Components in this
        list must also be in the `components` list.

    Raises
    ------
    RuntimeError
        If a component is listed in `output_only` but not in `components`.

    """

    def __init__(
        self, components: typing.List[str], output_only: typing.Iterable[str] = ()
    ) -> None:
        self.log = logging.getLogger(type(self).__name__)

        self._components = components

        self.components = tuple([comp.lower() for comp in self._components])

        _controllers = {}
        self._component_names = set()
        self._output_only = set()

        bad_output_only_names = set()
        for component in output_only:
            if component not in components:
                bad_output_only_names.add(component)

        if len(bad_output_only_names) > 0:
            raise RuntimeError(
                f"Component(s) {bad_output_only_names} found in output_only but not in components list"
                f"({components}). Check spelling and make sure the components are listed in"
                " both entries."
            )

        for i, component in enumerate(self._components):
            name, index = salobj.name_to_name_index(component)
            rname = component.lower().replace(":", "_")
            self._component_names.add(rname)
            _controllers[rname] = salobj.Controller(name=name, index=index)
            if component in output_only:
                self._output_only.add(rname)

        self.controllers = types.SimpleNamespace(**_controllers)

        self.overrides: typing.Dict[str, str] = {}

        self.override: typing.Dict[str, str] = {}

        for comp in self.component_names:
            if comp not in self._output_only:
                getattr(self.controllers, comp).cmd_start.callback = functools.partial(
                    self.get_start_callback, comp=comp
                )
                getattr(self.controllers, comp).cmd_enable.callback = functools.partial(
                    self.get_enable_callback, comp=comp
                )
                getattr(self.controllers, comp).cmd_disable.callback = (
                    functools.partial(self.get_disable_callback, comp=comp)
                )
                getattr(self.controllers, comp).cmd_standby.callback = (
                    functools.partial(self.get_standby_callback, comp=comp)
                )
                getattr(self.controllers, comp).cmd_exitControl.callback = (
                    functools.partial(self.get_exitControl_callback, comp=comp)
                )
                if hasattr(getattr(self.controllers, comp), "cmd_enterControl"):
                    getattr(self.controllers, comp).cmd_enterControl.callback = (
                        functools.partial(self.get_enterControl_callback, comp=comp)
                    )

        for comp in self.output_only:
            for cmd in getattr(self.controllers, comp).salinfo.command_names:
                getattr(getattr(self.controllers, comp), f"cmd_{cmd}").callback = (
                    self.generic_raise_callback
                )

        self.start_task: typing.Union[asyncio.Task, asyncio.Future] = (
            asyncio.create_task(self.start_task_publish())
        )

        self.run_telemetry_loop = False

        self.task_list: typing.List[asyncio.Task] = []

        self.check_done_lock = asyncio.Lock()

        self.done_task: asyncio.Future = asyncio.Future()

    async def start_task_publish(self) -> None:
        self.run_telemetry_loop = True

        if self.start_task.done():
            raise RuntimeError("Start task already completed.")

        await asyncio.gather(
            *[
                getattr(self.controllers, name).start_task
                for name in self._component_names
            ]
        )

        for comp in self.component_names:
            if comp not in self.output_only:
                await getattr(self.controllers, comp).evt_summaryState.set_write(
                    summaryState=salobj.State.STANDBY
                )
                self.overrides[comp] = f"test_{comp}"
                if hasattr(
                    getattr(self.controllers, comp), "evt_configurationsAvailable"
                ):
                    await getattr(
                        self.controllers, comp
                    ).evt_configurationsAvailable.set_write(
                        overrides=f"{self.overrides[comp]},"
                    )
                self.task_list.append(
                    asyncio.create_task(self.publish_heartbeats_for(comp))
                )

    async def generic_callback(self, data: salobj.type_hints.BaseMsgType) -> None:
        await asyncio.sleep(HEARTBEAT_INTERVAL)

    async def generic_raise_callback(self, data: salobj.type_hints.BaseMsgType) -> None:
        """A generic callback function that will raise an exception if
        called.
        """
        raise RuntimeError("This command should not be called.")

    async def get_start_callback(
        self, data: salobj.type_hints.BaseMsgType, comp: str
    ) -> None:
        ss = getattr(self.controllers, comp).evt_summaryState

        if ss.data.summaryState != salobj.State.STANDBY:
            raise RuntimeError(
                f"{comp} current state is {salobj.State(ss.data.summaryState)!r}. "
                f"Expected {salobj.State.STANDBY!r}"
            )

        print(
            f"[{comp}] {ss.data.summaryState!r} -> {salobj.State.DISABLED!r} "
            f"[overrides: {data.configurationOverride}]"
        )

        await ss.set_write(summaryState=salobj.State.DISABLED)

        self.override[comp] = data.configurationOverride

        await asyncio.sleep(HEARTBEAT_INTERVAL)

    async def get_enable_callback(
        self, data: salobj.type_hints.BaseMsgType, comp: str
    ) -> None:
        ss = getattr(self.controllers, comp).evt_summaryState

        if ss.data.summaryState != salobj.State.DISABLED:
            raise RuntimeError(
                f"{comp} current state is {salobj.State(ss.data.summaryState)!r}. "
                f"Expected {salobj.State.DISABLED!r}"
            )

        print(f"[{comp}] {ss.data.summaryState!r} -> {salobj.State.ENABLED!r}")

        await ss.set_write(summaryState=salobj.State.ENABLED)

        await self.publish_detailed_state(comp, ss.data.summaryState)

        await asyncio.sleep(HEARTBEAT_INTERVAL)

    async def get_disable_callback(
        self, data: salobj.type_hints.BaseMsgType, comp: str
    ) -> None:
        ss = getattr(self.controllers, comp).evt_summaryState

        if ss.data.summaryState != salobj.State.ENABLED:
            raise RuntimeError(
                f"{comp} current state is {salobj.State(ss.data.summaryState)!r}. "
                f"Expected {salobj.State.ENABLED!r}."
            )
        print(f"[{comp}] {ss.data.summaryState!r} -> {salobj.State.DISABLED!r}")

        await ss.set_write(summaryState=salobj.State.DISABLED)

        await self.publish_detailed_state(comp, ss.data.summaryState)

        await asyncio.sleep(HEARTBEAT_INTERVAL)

    async def get_standby_callback(
        self, data: salobj.type_hints.BaseMsgType, comp: str
    ) -> None:
        ss = getattr(self.controllers, comp).evt_summaryState

        if ss.data.summaryState not in (salobj.State.DISABLED, salobj.State.FAULT):
            raise RuntimeError(
                f"{comp}: Current state is {salobj.State(ss.data.summaryState)!r}. "
                f"Expected {salobj.State.DISABLED!r} or {salobj.State.FAULT!r}"
            )

        print(f"[{comp}] {ss.data.summaryState!r} -> {salobj.State.STANDBY!r}")

        await ss.set_write(summaryState=salobj.State.STANDBY)

        await self.publish_detailed_state(comp, ss.data.summaryState)

        await asyncio.sleep(HEARTBEAT_INTERVAL)

    async def get_exitControl_callback(
        self, data: salobj.type_hints.BaseMsgType, comp: str
    ) -> None:
        ss = getattr(self.controllers, comp).evt_summaryState

        if ss.data.summaryState != salobj.State.STANDBY:
            raise RuntimeError(
                f"{comp}: Current state is {salobj.State(ss.data.summaryState)!r}. "
                f"Expected {salobj.State.STANDBY!r}."
            )

        print(f"[{comp}] {ss.data.summaryState!r} -> {salobj.State.OFFLINE!r}")

        await ss.set_write(summaryState=salobj.State.OFFLINE)

        await self.publish_detailed_state(comp, ss.data.summaryState)

        await self.check_done()

        await asyncio.sleep(HEARTBEAT_INTERVAL)

    async def get_enterControl_callback(
        self, data: salobj.type_hints.BaseMsgType, comp: str
    ) -> None:
        ss = getattr(self.controllers, comp).evt_summaryState

        if ss.data.summaryState != salobj.State.OFFLINE:
            raise RuntimeError(
                f"{comp}: Current state is {salobj.State(ss.data.summaryState)!r}. "
                f"Expected {salobj.State.OFFLINE!r}."
            )

        print(f"[{comp}] {ss.data.summaryState!r} -> {salobj.State.STANDBY!r}")

        await ss.set_write(summaryState=salobj.State.STANDBY)

        await self.publish_detailed_state(comp, ss.data.summaryState)

        await asyncio.sleep(HEARTBEAT_INTERVAL)

    async def publish_detailed_state(
        self, component: str, detailed_state: salobj.type_hints.BaseMsgType
    ) -> None:
        if hasattr(getattr(self.controllers, component), "evt_detailedState"):
            try:
                await getattr(self.controllers, component).evt_detailedState.set_write(
                    detailedState=salobj.State.ENABLED
                )
            except Exception:
                self.log.exception(f"Cannot publish detailed state for {component}.")

    async def check_done(self) -> None:
        """If all CSCs are in OFFLINE state, close group mock."""

        async with self.check_done_lock:
            is_offline = []

            for comp in self.component_names:
                is_offline.append(
                    getattr(self.controllers, comp).evt_summaryState.data.summaryState
                    == salobj.State.OFFLINE
                )

            if all(is_offline):
                print("Closing mock controller.")
                if not self.done_task.done():
                    self.done_task.set_result(None)

    async def publish_heartbeats_for(self, comp: str) -> None:
        while self.run_telemetry_loop:
            await getattr(self.controllers, comp).evt_heartbeat.write()
            await asyncio.sleep(HEARTBEAT_INTERVAL)

    @property
    def component_names(self) -> typing.Set[str]:
        return self._component_names

    @property
    def output_only(self) -> typing.Set[str]:
        return self._output_only

    async def close(self) -> None:
        self.run_telemetry_loop = False

        task_list: typing.List[asyncio.Task] = []

        try:
            print(f"Closing: {len(self.task_list)} tasks to wait.")
            await asyncio.sleep(CLOSE_SLEEP)
            for task in [_task for _task in self.task_list if not _task.done()]:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    print(f"Got unexpected exception cancelling task: {e}")

        except Exception:
            pass

        close_tasks = []
        for name in self.component_names:
            close_tasks.append(getattr(self.controllers, name).close())

        await asyncio.gather(*close_tasks, return_exceptions=True)

        for task in task_list:
            if isinstance(task, Exception):
                self.log.error("Exception in task.")
                raise task

    async def __aenter__(self: TBaseGroupMock) -> TBaseGroupMock:
        return self

    async def __aexit__(self, *args: typing.Any) -> None:
        await self.close()

    @classmethod
    async def amain(cls) -> None:
        """Make a group mock and run it."""
        print(f"Starting {cls.__name__} controller")
        async with cls() as csc:  # type: ignore # noqa
            print(f"{cls.__name__} controller running.")
            await csc.done_task

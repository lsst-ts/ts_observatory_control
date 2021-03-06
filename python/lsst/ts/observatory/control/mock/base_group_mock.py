# This file is part of ts_observatory_control.
#
# Developed for the LSST Telescope and Site Systems.
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

import types
import asyncio
import functools

from lsst.ts import salobj

LONG_TIMEOUT = 30  # seconds
HEARTBEAT_INTERVAL = 1  # seconds
CLOSE_SLEEP = 5  # seconds


class BaseGroupMock:
    """ Base Mock for groups of CSCs.

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

    def __init__(self, components, output_only=()):

        self._components = components

        self.components = [comp.lower() for comp in self._components]

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

        self.setting_versions = {}

        self.settings_to_apply = {}

        for comp in self.component_names:
            if comp not in self._output_only:
                getattr(self.controllers, comp).cmd_start.callback = functools.partial(
                    self.get_start_callback, comp=comp
                )
                getattr(self.controllers, comp).cmd_enable.callback = functools.partial(
                    self.get_enable_callback, comp=comp
                )
                getattr(
                    self.controllers, comp
                ).cmd_disable.callback = functools.partial(
                    self.get_disable_callback, comp=comp
                )
                getattr(
                    self.controllers, comp
                ).cmd_standby.callback = functools.partial(
                    self.get_standby_callback, comp=comp
                )

        for comp in self.output_only:
            for cmd in getattr(self.controllers, comp).salinfo.command_names:
                getattr(
                    getattr(self.controllers, comp), f"cmd_{cmd}"
                ).callback = self.generic_raise_callback

        self.start_task = asyncio.create_task(self.start_task_publish())

        self.run_telemetry_loop = False

        self.task_list = []

    async def start_task_publish(self):

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
                getattr(self.controllers, comp).evt_summaryState.set_put(
                    summaryState=salobj.State.STANDBY
                )
                self.setting_versions[comp] = f"test_{comp}"
                getattr(self.controllers, comp).evt_settingVersions.set_put(
                    recommendedSettingsVersion=f"{self.setting_versions[comp]},"
                )

    async def generic_callback(self, data):
        await asyncio.sleep(HEARTBEAT_INTERVAL)

    async def generic_raise_callback(self, data):
        """ A generic callback function that will raise an exception if called.
        """
        raise RuntimeError("This command should not be called.")

    async def get_start_callback(self, data, comp):
        ss = getattr(self.controllers, comp).evt_summaryState

        if ss.data.summaryState != salobj.State.STANDBY:
            raise RuntimeError(
                f"{comp} current state is {salobj.State(ss.data.summaryState)!r}. "
                f"Expected {salobj.State.STANDBY!r}"
            )

        print(
            f"[{comp}] {ss.data.summaryState!r} -> {salobj.State.DISABLED!r} "
            f"[settings: {data.settingsToApply}]"
        )

        ss.set_put(summaryState=salobj.State.DISABLED)

        self.settings_to_apply[comp] = data.settingsToApply

        await asyncio.sleep(HEARTBEAT_INTERVAL)

    async def get_enable_callback(self, data, comp):
        ss = getattr(self.controllers, comp).evt_summaryState

        if ss.data.summaryState != salobj.State.DISABLED:
            raise RuntimeError(
                f"{comp} current state is {salobj.State(ss.data.summaryState)!r}. "
                f"Expected {salobj.State.DISABLED!r}"
            )

        print(f"[{comp}] {ss.data.summaryState!r} -> {salobj.State.ENABLED!r}")

        ss.set_put(summaryState=salobj.State.ENABLED)

        await asyncio.sleep(HEARTBEAT_INTERVAL)

    async def get_disable_callback(self, data, comp):
        ss = getattr(self.controllers, comp).evt_summaryState

        if ss.data.summaryState != salobj.State.ENABLED:
            raise RuntimeError(
                f"{comp} current state is {salobj.State(ss.data.summaryState)!r}. "
                f"Expected {salobj.State.ENABLED!r}."
            )
        print(f"[{comp}] {ss.data.summaryState!r} -> {salobj.State.DISABLED!r}")

        ss.set_put(summaryState=salobj.State.DISABLED)

        await asyncio.sleep(HEARTBEAT_INTERVAL)

    async def get_standby_callback(self, data, comp):
        ss = getattr(self.controllers, comp).evt_summaryState

        if ss.data.summaryState not in (salobj.State.DISABLED, salobj.State.FAULT):
            raise RuntimeError(
                f"{comp}: Current state is {salobj.State(ss.data.summaryState)!r}. "
                f"Expected {salobj.State.DISABLED!r} or {salobj.State.FAULT!r}"
            )

        print(f"[{comp}] {ss.data.summaryState!r} -> {salobj.State.STANDBY!r}")

        ss.set_put(summaryState=salobj.State.STANDBY)

        await asyncio.sleep(HEARTBEAT_INTERVAL)

    @property
    def component_names(self):
        return self._component_names

    @property
    def output_only(self):
        return self._output_only

    async def close(self):

        self.run_telemetry_loop = False

        task_list = []

        try:
            task_list = await asyncio.wait_for(
                asyncio.gather(*self.task_list, return_exceptions=True),
                timeout=CLOSE_SLEEP,
            )
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

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()

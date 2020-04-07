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

import types
import asyncio
import logging

from lsst.ts import salobj

__all__ = ["BaseGroup"]


class BaseGroup:
    """

    """

    def __init__(self, components, domain=None, log=None):

        self.fast_timeout = 5.0
        self.long_timeout = 30.0
        self.long_long_timeout = 120.0

        self._components = components

        self._remotes = {}

        self.domain = domain if domain is not None else salobj.Domain()

        for i in range(len(self._components)):
            name, index = salobj.name_to_name_index(self._components[i])
            self._remotes[name.lower()] = salobj.Remote(
                domain=self.domain, name=name, index=index
            )

        self.scheduled_coro = []

        self.check = types.SimpleNamespace(
            **dict(zip(self.components, [True] * len(self.components)))
        )

        self.start_task = asyncio.gather(
            *[self._remotes[r].start_task for r in self._remotes]
        )

        if log is None:
            self.log = logging.getLogger(__name__)
        else:
            self.log = log

    async def get_state(self, comp):
        """Get summary state for component.

        Parameters
        ----------
        comp : `str`
            Name of the component.

        Returns
        -------
        state : `salobj.State`
            Current state of component.
        """
        ss = await self._remotes[comp].evt_summaryState.aget(timeout=self.fast_timeout)
        return salobj.State(ss.summaryState)

    async def check_component_state(self, comp, desired_state=salobj.State.ENABLED):
        """Given a component name wait for an event that specify that the
        state changes. If the event is not ENABLED, raise RuntimeError.

        This is to be used in conjunction with the `get_state_changed_callback`
        method.

        Parameters
        ----------
        comp : `str`
            Name of the component to follow. Must be one of:
            atmcs, atptg, ataos, atpneumatics, athexapod, atdome,
            atdometrajectory
        desired_state : `salobj.State`
            Desired state of the CSC.

        Raises
        ------
        RuntimeError
            If state is not `desired_state`.
        """
        first_pass = True
        while True:

            if first_pass:
                _state = await self._remotes[comp].evt_summaryState.aget()
                self._remotes[comp].evt_summaryState.flush()
                first_pass = False
            else:
                try:
                    _state = await self._remotes[comp].evt_summaryState.next(
                        flush=False
                    )
                except IndexError:
                    _state = await self._remotes[comp].evt_summaryState.aget()

            state = salobj.State(_state.summaryState)

            if state != desired_state:
                self.log.warning(f"{comp} not in {desired_state!r}: {state!r}")
                raise RuntimeError(
                    f"{comp} state is {state!r}, " f"expected {desired_state!r}"
                )
            else:
                self.log.debug(f"{comp}: {state!r}")

    async def check_comp_heartbeat(self, comp):
        """

        Parameters
        ----------
        comp

        Returns
        -------

        """

        while True:
            await self._remotes[comp].evt_heartbeat.next(
                flush=True, timeout=self.fast_timeout
            )

    async def standby(self):
        """ Put all CSCs in standby.
        """

        set_ss_tasks = []

        for comp in self.components:
            if getattr(self.check, comp):
                set_ss_tasks.append(
                    salobj.set_summary_state(
                        self._remotes[comp],
                        salobj.State.STANDBY,
                        timeout=self.long_long_timeout,
                    )
                )
            else:
                set_ss_tasks.append(self.get_state(comp))

        ret_val = await asyncio.gather(*set_ss_tasks, return_exceptions=True)

        error_flag = False
        error_msg = ""

        for i in range(len(self.components)):
            if isinstance(ret_val[i], Exception):
                error_flag = True
                error_msg += f"Unable to put {self.components[i]} in STANDBY\n"
                self.log.error(f"Unable to put {self.components[i]} in STANDBY")
                self.log.exception(ret_val[i])
            else:
                self.log.debug(f"[{self.components[i]}]::{ret_val[i]!r}")

        if error_flag:
            raise RuntimeError(error_msg)
        else:
            self.log.info("All components in standby.")

    async def enable(self, settings=None):
        """Enable all components.

        This method will enable all group components. Users can provide
        settings for the start command (in a dictionary). If no setting
        is given for a component, it will use the first available setting
        in `evt_settingVersions.recommendedSettingsLabels`.

        Parameters
        ----------
        settings: `dict`
            Dictionary with settings to apply.  If `None` use recommended
            settings.
        """
        self.log.debug("Gathering settings.")

        settings_all = {}
        if settings is not None:
            self.log.debug(f"Received settings from users.: {settings}")
            settings_all = settings.copy()

        for comp in self.components:
            if comp not in settings_all:
                self.log.debug(f"No settings for {comp}.")
                try:
                    sv = await getattr(self, comp).evt_settingVersions.aget(
                        timeout=self.fast_timeout
                    )
                except asyncio.TimeoutError:
                    sv = None

                if sv is not None:
                    settings_all[comp] = sv.recommendedSettingsLabels.split(",")[0]
                    self.log.debug(
                        f"Using {settings_all[comp]} from settingVersions event."
                    )
                else:
                    self.log.debug(
                        f"Couldn't get settingVersions event. Using empty settings."
                    )
                    settings_all[comp] = ""

        self.log.debug(f"Settings versions: {settings_all}")

        self.log.info("Enabling all components")

        set_ss_tasks = []

        for comp in self.components:
            if getattr(self.check, comp):
                self.log.debug(f"Enabling  {comp}")
                set_ss_tasks.append(
                    salobj.set_summary_state(
                        self._remotes[comp],
                        salobj.State.ENABLED,
                        settingsToApply=settings_all[comp],
                        timeout=self.long_long_timeout,
                    )
                )
            else:
                set_ss_tasks.append(self.get_state(comp))

        ret_val = await asyncio.gather(*set_ss_tasks, return_exceptions=True)

        error_flag = False
        error_msg = ""

        for i in range(len(self.components)):
            if isinstance(ret_val[i], Exception):
                error_flag = True
                error_msg += f"Unable to ENABLE {self.components[i]}\n"
                self.log.error(f"Unable to ENABLE {self.components[i]}")
                self.log.exception(ret_val[i])
            else:
                self.log.debug(f"[{self.components[i]}]::{ret_val[i]!r}")

        if error_flag:
            raise RuntimeError(error_msg)
        else:
            self.log.info("All components enabled.")

    @property
    def components(self):
        return list(self._remotes)

    @staticmethod
    async def cancel_not_done(coro_list):
        """Cancel all coroutines in `coro_list`.

        Parameters
        ----------
        coro_list : `list(coroutines)`
            A list of coroutines to cancel.
        """
        while len(coro_list) > 0:
            coro = coro_list.pop()
            if not coro.done():
                coro.cancel()
                try:
                    await coro
                except asyncio.CancelledError:
                    pass

    async def close(self):
        await self.cancel_not_done(self.scheduled_coro)
        await asyncio.gather(*[self._remotes[r].close() for r in self._remotes])
        await self.domain.close()

    async def __aenter__(self):
        await self.start_task
        return self

    async def __aexit__(self, *args):
        await self.close()

    def __getattribute__(self, item):
        if item in super().__getattribute__("_remotes"):
            return super().__getattribute__("_remotes")[item]
        else:
            return super().__getattribute__(item)

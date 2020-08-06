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
import traceback

from lsst.ts import salobj

__all__ = ["Usages", "RemoteGroup"]


class Usages:
    """Define usages for a `RemoteGroup`.

    When subclassing `RemoteGroup` you can subclass `Usages` and define new
    usages.

    Notes
    -----

    Usages definition:

    All: Enable all possible operations defined in the class. This is
    different than adding all topics from all components. It will only
    add those needed to run the methods defined in the class.

    StateTransition: Enable summary state transition.

    MonitorState: Enable monitoring of summary state.

    MonitorHeartBeat: Enable monitoring of heartbeat.
    """

    All = 0
    StateTransition = 1
    MonitorState = 1 << 1
    MonitorHeartBeat = 1 << 2

    def __iter__(self):
        return iter(
            [self.All, self.StateTransition, self.MonitorState, self.MonitorHeartBeat]
        )


class RemoteGroup:
    """High-level abstraction of a collection of `salobj.Remote`.

    A `salobj.Remote` provides a communication abstraction for Commandable
    SAL Componentes (CSCs). CSCs represents entities in the LSST observatory
    system that performs actions such as controlling/interfacing with hardware,
    logical operations and/and coordination of other CSCs. In general CSCs
    operate in logical groups to achieve certain kinds of operation; like
    slewing the telescope and taking images.

    Parameters
    ----------
    components : `list` [`str`]
        A list of strings with the names of the SAL components that are part
        of the group.
    domain : `salobj.Domain`
        Optional domain to use for the remotes. If `None` (Default), create a
        new remote.
    log : `logging.Logger`
        Optional logging class to be used for logging operations. If `None`,
        creates a new logger. Useful to use in salobj.BaseScript and allow
        logging in the class use the script logging.
    intended_usage : `int`
        Optional bitmask that maps to a list of intended operations. This is
        used to limit the resources allocated by the class by gathering some
        knowledge about the usage intention. By default allocates all
        resources.

    Attributes
    ----------
    components
    valid_use_cases
    usages
    rem :  `types.SimpleNamespace`
        Namespace with Remotes for all the components defined in the group.
        The name of the component is converted to all lowercase and indexed
        component have an underscore instead of a colon, e.g. MTMount ->
        mtmount, Hexapod:1 -> hexapod_1.
    check : `types.SimpleNamespace`
        Allow users to specify if a component should be part of operations. For
        each component in `rem`, there will be an equivalent (with same name)
        in this namespace, with a boolean value. When subclassing, users may
        use this flag to skip components in different kinds of operations as
        well.

    Notes
    -----

    The `components` list also accept indexed components, e.g.
    ["Test:1", "Test:2"].

    The `intended_usage` is a bitwise operation which allows users to construct
    use-cases by combining them, e.g.

    `BaseUsages.StateTransition | BaseUsages.MonitorHeartBeat`

    Also, note that `intended_usage=None` is different then
    `intended_usage=BaseUsages.All`. When set to `None` the class will load all
    available resources. When set to `BaseUsages.All`, the class will load the
    resources needed for all defined operations.

    """

    def __init__(self, components, domain=None, log=None, intended_usage=None):

        if log is None:
            self.log = logging.getLogger(type(self).__name__)
        else:
            self.log = log.getChild(type(self).__name__)

        self.fast_timeout = 5.0
        self.long_timeout = 30.0
        self.long_long_timeout = 120.0

        self._components = components
        self._component_names = []

        self.domain = domain if domain is not None else salobj.Domain()

        _remotes = {}

        for i, component in enumerate(self._components):
            name, index = salobj.name_to_name_index(component)
            resources = self.get_required_resources(component, intended_usage)
            rname = component.lower().replace(":", "_")
            self._component_names.append(rname)
            if resources.add_this:
                _remotes[rname] = salobj.Remote(
                    domain=self.domain,
                    name=name,
                    index=index,
                    readonly=resources.readonly,
                    include=resources.include,
                )
            else:
                _remotes[rname] = None

        self.rem = types.SimpleNamespace(**_remotes)

        self.scheduled_coro = []

        self.check = types.SimpleNamespace(
            **{component: True for component in self._component_names}
        )

        self.start_task = asyncio.gather(
            *[
                getattr(self.rem, c).start_task
                if getattr(self.rem, c) is not None
                else asyncio.sleep(0.0)
                for c in self._component_names
            ]
        )

    def get_required_resources(self, component, intended_usage):
        """Return the required resources based on the intended usage of the
        class.

         When subclassing, overwrite this method to add the child class
         use cases.

        Parameters
        ----------
        component: `str`
            Name of the component, with index (e.g. Test:1).

        intended_usage: `int`
            An integer constructed from the `self.valid_use_cases`. Usages can
            be combined to enable combined operations (see base class
            documentation). If None, returns appropriate values to load all
            resources.

        Returns
        -------
        resources: types.SimpleNamespace
            A simple namespaces with the following attributes:

            add_this: bool
                Should this remote be added to the collection?
            readonly: bool
                Create the remote for this component in readonly mode? Some
                operations does not require commanding.
            include: `list` [`str`]
                What topics should be included?

        Raises
        ------
        KeyError: If component is not in the list of components.

        """

        if component not in self._components:
            raise KeyError(
                f"Component {component} not in the list of components. "
                f"Must be one of {self._components}."
            )

        if intended_usage is None:
            # Include all resources
            self.log.debug(f"{component}: Adding all resources.")
            return types.SimpleNamespace(add_this=True, readonly=False, include=None)

        resources = types.SimpleNamespace(add_this=False, readonly=False, include=[])

        if intended_usage == self.valid_use_cases.All:
            resources.add_this = True
            resources.readonly = False
            resources.include = self.usages[self.valid_use_cases.All].include

            self.log.debug(
                f"{component}: add_this: {resources.add_this}, "
                f"readonly: {resources.readonly}, include: {resources.include}"
            )

            return resources

        for usage in self.valid_use_cases:
            if usage == 0:
                continue
            elif usage & intended_usage != 0:
                resources.add_this = resources.add_this or (
                    component in self.usages[usage].components
                )
                resources.readonly = resources.readonly and self.usages[usage].readonly
                for topic in self.usages[usage].include:
                    if topic not in resources.include:
                        resources.include.append(topic)

        self.log.debug(
            f"{component}: add_this: {resources.add_this}, "
            f"readonly: {resources.readonly}, include: {resources.include}"
        )
        return resources

    async def get_state(self, component, ignore_timeout=False):
        """Get summary state for component.

        Parameters
        ----------
        component : `str`
            Name of the component.
        ignore_timeout : `bool`
            If `True` will return None in case it times out getting the state.
            Default is `False`, which means raise `TimeoutError`.

        Returns
        -------
        state : `salobj.State` or `None`
            Current state of component.

        Raises
        ------
        `asyncio.TimeoutError`
            If can not get state in `self.fast_timeout` seconds.

        """
        try:
            ss = await getattr(self.rem, component).evt_summaryState.aget(
                timeout=self.fast_timeout
            )
            return salobj.State(ss.summaryState)
        except asyncio.TimeoutError as e:
            if ignore_timeout:
                return None
            else:
                raise e

    async def next_state(self, component):
        """Get summary state for component.

        Parameters
        ----------
        component : `str`
            Name of the component.

        Returns
        -------
        state : `salobj.State`
            Current state of component.
        """
        ss = await getattr(self.rem, component).evt_summaryState.next(
            flush=False, timeout=self.fast_timeout
        )
        return salobj.State(ss.summaryState)

    async def check_component_state(
        self, component, desired_state=salobj.State.ENABLED
    ):
        """Monitor the summary state of a component and raises an exception if
        it is or goes to a state different than the desired state.

        This method will run forever as long as the summary state remains
        unchanged. The intention is that this can run alongside an operation
        that require the component to be in a certain state, when the
        operation is completed, the task can be canceled.

        Parameters
        ----------
        component : `str`
            Name of the component to follow. Must be one of:
            atmcs, atptg, ataos, atpneumatics, athexapod, atdome,
            atdometrajectory
        desired_state : `salobj.State`
            Desired state of the CSC.

        Raises
        ------
        RuntimeError
            If state is not `desired_state`.
        KeyError
            If component is not found.
        """
        desired_state = salobj.State(desired_state)
        state_topic = getattr(self.rem, component).evt_summaryState
        state_topic.flush()
        data = await state_topic.aget()
        while True:
            state = salobj.State(data.summaryState)
            if state != desired_state:
                self.log.warning(f"{component} not in {desired_state!r}: {state!r}")
                raise RuntimeError(
                    f"{component} state is {state!r}, expected {desired_state!r}"
                )
            else:
                self.log.debug(f"{component}: {state!r}")
            data = await state_topic.next(flush=False)

    async def check_comp_heartbeat(self, component):
        """Monitor heartbeats from the specified component and raises and
        exception if not.

        This method will run forever as long as the component continues to
        send heartbeats. The intention is that this can run alongside an
        operation, to make sure the component remains responsive.

        Parameters
        ----------
        component : `str`
            Name of the component to follow. Must be one of:
            atmcs, atptg, ataos, atpneumatics, athexapod, atdome,
            atdometrajectory

        Raises
        ------
        asyncio.TimeoutError
            If the component does not send heartbeats in `self.fast_timeout`
            seconds.

        """

        while True:
            await getattr(self.rem, component).evt_heartbeat.next(
                flush=True, timeout=self.fast_timeout
            )

    async def expand_settings(self, settings=None):
        """Take an incomplete settings dict and fills it out according to
        events published by components.

        Parameters
        ----------
        settings : `dict`
            A dictionary with component name, setting name pair or `None`.

        Returns
        -------
        complete_settings : `dict`
            Dictionary with complete settings.

        """
        self.log.debug("Gathering settings.")

        complete_settings = {}
        if settings is not None:
            self.log.debug(f"Received settings from users.: {settings}")
            complete_settings = settings.copy()

        for comp in self.components:
            if comp not in complete_settings:
                self.log.debug(f"No settings for {comp}.")
                try:
                    sv = await getattr(self.rem, comp).evt_settingVersions.aget(
                        timeout=self.fast_timeout
                    )
                except asyncio.TimeoutError:
                    sv = None

                if sv is not None:
                    complete_settings[comp] = sv.recommendedSettingsLabels.split(",")[0]
                    self.log.debug(
                        f"Using {complete_settings[comp]} from settingVersions event."
                    )
                else:
                    self.log.debug(
                        "Couldn't get settingVersions event. Using empty settings."
                    )
                    complete_settings[comp] = ""

        self.log.debug(f"Settings versions: {complete_settings}")

        return complete_settings

    async def set_state(self, state, settings=None, components=None):
        """Set summary state for all components.

        Parameters
        ----------
        state : `salobj.State`
            Desired state.

        settings : `dict`
            Settings to apply for each component.

        components : `list[`str`]`
            List of components to set state, as they appear in
            `self.components`.

        Raises
        ------
        RuntimeError

            * If a component in `components` is not part of the group.

            * If it fails to transition one or more components.

        """

        if components is not None:
            work_components = set(components)

            for comp in work_components:
                if comp not in self.components:
                    raise RuntimeError(
                        f"Component {comp} not part of the group. Must be one of {self.components}."
                    )
        else:
            work_components = set(self.components)

        if settings is not None:
            settings_all = settings
        else:
            settings_all = dict([(comp, "") for comp in work_components])

        set_ss_tasks = []

        for comp in work_components:
            if getattr(self.check, comp):
                settingsToApply = settings_all[comp]
                if settingsToApply is None:
                    settingsToApply = ""
                set_ss_tasks.append(
                    salobj.set_summary_state(
                        getattr(self.rem, comp),
                        salobj.State(state),
                        settingsToApply=settingsToApply,
                        timeout=self.long_long_timeout,
                    )
                )
            else:
                set_ss_tasks.append(self.get_state(comp, ignore_timeout=True))

        ret_val = await asyncio.gather(*set_ss_tasks, return_exceptions=True)

        error_flag = False
        failed_components = []

        for i, comp in enumerate(work_components):
            if isinstance(ret_val[i], Exception):
                error_flag = True
                failed_components.append(comp)
                err_message = (
                    f"Unable to transition {self.components[i]} to "
                    f"{salobj.State(state)!r} {traceback.format_exc()}.\n"
                )
                err_traceback = traceback.format_exception(
                    etype=type(ret_val[i]),
                    value=ret_val[i],
                    tb=ret_val[i].__traceback__,
                )
                for trace in err_traceback:
                    err_message += trace
                self.log.error(err_message)
            else:
                self.log.debug(f"[{self.components[i]}]::{ret_val[i]!r}")

        if error_flag:
            raise RuntimeError(
                f"Failed to transition {failed_components} to "
                f"{salobj.State(state)!r}."
            )
        else:
            self.log.info(f"All components in {salobj.State(state)!r}.")

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

        self.log.info("Enabling all components")

        settings_all = await self.expand_settings(settings)

        await self.set_state(salobj.State.ENABLED, settings=settings_all)

    async def standby(self):
        """ Put all CSCs in standby.
        """

        await self.set_state(salobj.State.STANDBY)

    @property
    def components(self):
        """ List of components.
        """
        return self._component_names

    @property
    def valid_use_cases(self):
        """ Define valid usages.

        When subclassing, overwrite this method to return the proper enum.

        Returns
        -------
        usages: enum

        """
        return Usages()

    @property
    def usages(self):
        """ Define class usages.

        This property defines what remote resources are needed for each class
        usages. Each item in the dictionary contain a list of components,
        if the remotes will be used for "read only" operations an which
        topics will be required. The "key" of the dictionary is the
        usage enumeration value.

        Returns
        -------
        usages : `dict`
            Dictionary with class usages.

        """

        return {
            self.valid_use_cases.All: types.SimpleNamespace(
                components=self._components,
                readonly=False,
                include=[
                    "start",
                    "enable",
                    "disable",
                    "standby",
                    "exitControl",
                    "enterControl",
                    "summaryState",
                    "settingVersions",
                    "heartbeat",
                ],
            ),
            self.valid_use_cases.StateTransition: types.SimpleNamespace(
                components=self._components,
                readonly=False,
                include=[
                    "start",
                    "enable",
                    "disable",
                    "standby",
                    "exitControl",
                    "enterControl",
                    "summaryState",
                    "settingVersions",
                ],
            ),
            self.valid_use_cases.MonitorState: types.SimpleNamespace(
                components=self._components, readonly=True, include=["summaryState"],
            ),
            self.valid_use_cases.MonitorHeartBeat: types.SimpleNamespace(
                components=self._components, readonly=True, include=["heartbeat"],
            ),
        }

    async def process_as_completed(self, tasks):
        """ Process tasks are they complete.

        If the first task that finishes completes successfully, it will
        cancel all other tasks in the list, empty the input list and return the
        value of the task. If the task results in an exception, it will cancel
        all other tasks, empty the list and raise the exception.

        Parameters
        ----------
        tasks : `list`[`asyncio.Tasks`]
            List of asyncio tasks to process.

        """
        self.log.debug("process as completed...")

        for res in asyncio.as_completed(tasks):
            try:
                ret_val = await res
            except Exception as e:
                await self.cancel_not_done(tasks)
                raise e
            else:
                await self.cancel_not_done(tasks)
                return ret_val

    @staticmethod
    async def cancel_not_done(tasks):
        """Cancel all coroutines in `coro_list`.

        Remove futures from input tasks list and cancel them.

        Parameters
        ----------
        tasks : `list` [`futures`]
            A list of coroutines to cancel.
        """
        while len(tasks) > 0:
            task = tasks.pop()
            task.cancel()

    async def close(self):
        await self.cancel_not_done(self.scheduled_coro)
        await asyncio.gather(
            *[
                getattr(self.rem, c).close()
                if getattr(self.rem, c) is not None
                else asyncio.sleep(0.0)
                for c in self._component_names
            ]
        )
        await self.domain.close()

    async def __aenter__(self):
        await self.start_task
        return self

    async def __aexit__(self, *args):
        await self.close()

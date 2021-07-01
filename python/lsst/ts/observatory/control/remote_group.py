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

import types
import asyncio
import logging
import traceback

from lsst.ts import salobj

__all__ = ["Usages", "UsagesResources", "RemoteGroup"]


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


class UsagesResources:
    """Represent the resources needed for `Usages`.

    When defining `Usages` for a `RemoteGroup` of CSCs one need to specify what
    CSCs and topics are required. For instance, take the generic usage
    `Usages.StateTransition`. It is relevant to all CSCs in the group,
    requires the generic state transition commands (`start`, `enable`,
    `disable`, `standby`) and the generic events `summaryState` and
    `settingVersions`. To represent these resources for
    `Usages.StateTransition` we create a `UsagesResources` with those
    requirements, e.g.::

        UsagesResources(
            components_attr = self.components_attr,
            readonly = False,
            generics = [
                        "start",
                        "enable",
                        "disable",
                        "standby",
                        "summaryState",
                        "settingVersions"
                       ]
            )

    Parameters
    ----------
    components_attr : `list` of `str`
        Name of the components required for this use case. Names must follow
        the same format as that of the `components_attr` attribute in
        `RemoteGroup`, which is the name of the CSC in lowercase replacing the
        ":" by "_", e.g. Hexapod:1 is hexapod_1 and MTDomeTrajectory is
        mtdometrajectory.
    readonly : `bool`
        Should the remotes be readonly? That means no command can be sent to
        any component.
    generics : `list` of `str`
        List of generic topics (common to all components) required for this use
        case.
    **kwargs
        Used to specify list of topics for individual components. See Notes
        section bellow.

    Notes
    -----

    The kwargs argument can contain attributes with the name of the CSC, as it
    appears in the ``components_attr`` parameter list. They must be a list of
    strings with the name of the topics for the individual CSC. For example,::

        UsagesResources(
            components=["atcamera", "atarchiver", "atheaderservice"],
            readonly=False,
            generics=["summaryState"],
            atcamera=["takeImages", "endReadout"],
            atheaderservice=["largeFileObjectAvailable"],
        )

    Will include the `summaryState` event for ATCamera, ATArchiver and
    ATHeaderService components, plus `takeImages` and `endReadout` from
    ATCamera and `largeFileObjectAvailable` from ATHeaderService. No particular
    topic for ATArchiver would be included.

    Raises
    ------

    TypeError
        If `kwargs` argument is not in the `components` list.

    """

    def __init__(self, components_attr, readonly, generics=(), **kwargs):

        self.components_attr = frozenset(components_attr)

        self.readonly = readonly

        self.include = set(generics)

        for component in kwargs:
            if component in self.components_attr:
                self.include.update(kwargs[component])
            else:
                raise TypeError(
                    f"Unexpected keyword argument {component}. "
                    f"Valid additional arguments are {self.components_attr}."
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
    components : `list` of `str`
        List with the names of the CSCs that are part of the group. Format is
        the same as that used to initialize the `salobj.Remotes`, e.g.;
        "MTMount" or "Hexapod:1".
    components_attr : `list` of `str`
        List with the names of the `salobj.Remotes` for the CSCs that are part
        of the group. The name of the component is converted to all lowercase
        and indexed component have an underscore instead of a colon, e.g.
        MTMount -> mtmount, Hexapod:1 -> hexapod_1.
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

        self._components = dict(
            [
                (component, component.lower().replace(":", "_"))
                for component in components
            ]
        )

        self.domain, self._close_domain = (
            (domain, False) if domain is not None else (salobj.Domain(), True)
        )

        self._usages = None

        self.rem = types.SimpleNamespace()

        for component in self._components:
            name, index = salobj.name_to_name_index(component)
            rname = self._components[component]
            resources = self.get_required_resources(rname, intended_usage)

            if resources.add_this:
                setattr(
                    self.rem,
                    rname,
                    salobj.Remote(
                        domain=self.domain,
                        name=name,
                        index=index,
                        readonly=resources.readonly,
                        include=resources.include,
                    ),
                )
            else:
                setattr(self.rem, rname, None)

        self.scheduled_coro = []

        # Dict of component attribute name: remote, if present, else None
        attr_remotes = {attr: getattr(self.rem, attr) for attr in self.components_attr}

        # Mark components that were excluded from the resources to not be
        # checked.
        self.check = types.SimpleNamespace(
            **{c: remote is not None for c, remote in attr_remotes.items()}
        )

        start_task_list = [
            remote.start_task for remote in attr_remotes.values() if remote is not None
        ]

        if len(start_task_list) > 0:
            self.start_task = asyncio.gather(*start_task_list)
        else:
            self.start_task = None

    def components_to_check(self):
        """Return components for which check is enabled.

        Returns
        -------
        `list` of `str`
            Components to check.
        """
        return [
            component
            for component in self.components_attr
            if getattr(self.check, component)
        ]

    def get_required_resources(self, component, intended_usage):
        """Return the required resources based on the intended usage of the
        class.

         When subclassing, overwrite this method to add the child class
         use cases.

        Parameters
        ----------
        component: `str`
            Name of the component, with index as it appears in
            `components_attr` attribute (e.g. test_1 for the Test component
            with index 1).
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

        if component not in self.components_attr:
            raise KeyError(
                f"Component {component} not in the list of components. "
                f"Must be one of {self.components_attr}."
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
                    component in self.usages[usage].components_attr
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

    async def get_heartbeat(self, component):
        """Get last heartbeat for component.

        Parameters
        ----------
        component : `str`
            Name of the component.

        Returns
        -------
        heartbeat
            Last component heartbeat.
        """
        try:
            heartbeat = await getattr(self.rem, component).evt_heartbeat.aget(
                timeout=self.fast_timeout
            )
        except asyncio.TimeoutError:
            raise asyncio.TimeoutError(
                "No new or historical heartbeat from {component} received."
            )
        else:
            return heartbeat

    async def next_heartbeat(self, component):
        """Get next heartbeat for component.

        Parameters
        ----------
        component : `str`
            Name of the component.

        Returns
        -------
        heartbeat
            Last component heartbeat.
        """
        try:
            heartbeat = await getattr(self.rem, component).evt_heartbeat.next(
                flush=True, timeout=self.fast_timeout
            )
        except asyncio.TimeoutError:
            raise asyncio.TimeoutError(
                "No new heartbeat from {component} in the last {self.fast_timeout} seconds."
            )
        else:
            return heartbeat

    async def check_comp_heartbeat(self, component):
        """Monitor heartbeats from the specified component and raises and
        exception if not.

        This method will run forever as long as the component continues to
        send heartbeats. The intention is that this can run alongside an
        operation, to make sure the component remains responsive.

        Parameters
        ----------
        component : `str`
            Name of the component to follow. The name of the CSC follow the
            format CSCName or CSCName:index (for indexed components), e.g.
            "Hexapod:1" (for Hexapod with index=1) or "ATHexapod".

        Raises
        ------
        RuntimeError
            If the component does not send heartbeats in `self.fast_timeout`
            seconds.

        """

        while True:
            try:
                await getattr(self.rem, component).evt_heartbeat.next(
                    flush=True, timeout=self.fast_timeout
                )
            except asyncio.TimeoutError:
                raise RuntimeError(
                    f"No heartbeat from {component} received in {self.fast_timeout}s."
                )

    async def assert_liveliness(self):
        """Assert liveliness of components belonging to the group.

        The assertion is done by waiting for a new heartbeat from the
        component. The `check` feature will apply to the assertion so
        components marked with `check=False` will be skipped.

        Raises
        ------
        AssertionError
            If cannot get heartbeat for one or more components.
        """

        components_to_check = self.components_to_check()

        components_heartbeat = await asyncio.gather(
            *[self.next_heartbeat(component) for component in components_to_check],
            return_exceptions=True,
        )

        components_liveliness = dict(zip(components_to_check, components_heartbeat))

        exceptions = [
            component
            for component in components_liveliness
            if isinstance(components_liveliness[component], asyncio.TimeoutError)
        ]

        assert len(exceptions) == 0, f"No heartbeat from {exceptions}."

    async def inspect_settings(self, components_attr=None):
        """Return available settings.

        Inspect `settingVersions` from CSCs and return dictionary with all the
        available settings.

        Parameters
        ----------
        components_attr : `list` of `str` or `None`
            List of CSC names from the group to inspect settings. If `None`
            inspect all components in the group. The name of the CSC must be as
            it appears in the `components_attr` attribute, which is the name of
            the CSC in lowercase, replacing ":" by "_" for indexed components,
            e.g. "Hexapod:1" -> "hexapod_1" or "ATHexapod" -> "athexapod".

        Returns
        -------
        settings : `dict`
            Dictionary with valid settings. The dictionary key will be the csc
            name and the value a list of strings. The name of the CSC as it
            appears in the `components_attr` attribute, which is the name of
            the CSC in lowercase, replacing ":" by "_" for indexed components,
            e.g. "Hexapod:1" -> "hexapod_1" or "ATHexapod" -> "athexapod".

        Raises
        ------
        RuntimeError
            If an item in the parameter `components` list is not a CSC in the
            group.

        """

        settings = dict()

        for comp in (
            self.components_attr if components_attr is None else components_attr
        ):
            if comp not in self.components_attr:
                raise RuntimeError(
                    f"{comp} not in group. Must be one of {self.components_attr}."
                )
            elif getattr(self.check, comp):
                settings[comp] = None
            else:
                self.log.info(f"{comp} check is disabled, skipping.")

        for comp in settings:
            try:
                sv = await getattr(self.rem, comp).evt_settingVersions.aget(
                    timeout=self.fast_timeout
                )
            except asyncio.TimeoutError:
                sv = None

            if sv is not None:
                settings[comp] = sv.recommendedSettingsLabels.split(",")
            else:
                self.log.debug(
                    "Couldn't get settingVersions event. Using empty settings."
                )
                settings[comp] = [""]

        return settings

    async def expand_settings(self, settings=None):
        """Take an incomplete settings dict and fills it out according to
        events published by components.

        Parameters
        ----------
        settings : `dict` or `None`
            A dictionary with (name, settings) pair or `None`. The name of the
            as it appears in the `components_attr` attribute, which is the name
            of the CSC in lowercase, replacing ":" by "_" for indexed
            components, e.g. "Hexapod:1" -> "hexapod_1" or "ATHexapod" ->
            "athexapod".

        Returns
        -------
        complete_settings : `dict`
            Dictionary with complete settings.

        Raises
        ------
        RuntimeError
            If an item in the parameter `settings` dictionary is not a CSC in
            the group.

        """
        self.log.debug("Gathering settings.")

        complete_settings = {}
        if settings is not None:
            self.log.debug(f"Received settings from users.: {settings}")
            complete_settings = settings.copy()
            for comp in complete_settings:
                if comp not in self.components_attr:
                    raise RuntimeError(
                        f"{comp} not in group. Must be one of {self.components_attr}."
                    )

        incomplete_settings = await self.inspect_settings(
            components_attr=[
                comp for comp in self.components_attr if comp not in complete_settings
            ]
        )

        for comp in incomplete_settings:
            self.log.debug(f"Complete settings for {comp}.")
            complete_settings[comp] = incomplete_settings[comp][0]

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
            `self.components_attr`.

        Raises
        ------
        RuntimeError

            * If a component in `components` is not part of the group.

            * If it fails to transition one or more components.

        """

        if components is not None:
            work_components = list(components)

            for comp in work_components:
                if comp not in self.components_attr:
                    raise RuntimeError(
                        f"Component {comp} not part of the group. Must be one of {self.components_attr}."
                    )
        else:
            work_components = list(self.components_attr)

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
                    f"Unable to transition {comp} to "
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
                self.log.debug(f"[{comp}]::{ret_val[i]!r}")

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
        """Put all CSCs in standby."""

        await self.set_state(salobj.State.STANDBY)

    async def offline(self):
        """Put all CSCs in offline."""

        await self.set_state(salobj.State.OFFLINE)

    def set_rem_loglevel(self, level):
        """Set remotes log level.

        Useful to prevent the internal salobj warnings when read queues are
        filling up.

        Parameters
        ----------
        level : `int`
            Log level.
        """
        for component in self.components:
            logging.getLogger(component).setLevel(level)

    @property
    def components(self):
        """List of components names.

        The name of the CSC follow the format used in the class constructor,
        e.g. CSCName or CSCName:index (for indexed components), e.g.
        "Hexapod:1" (for Hexapod with index=1) or "ATHexapod".

        Returns
        -------
        components : `list` of `str`
            List of CSCs names.

        """
        return list(self._components.keys())

    @property
    def components_attr(self):
        """List of remotes names.

        The remotes names are reformatted to fit the requirements for object
        attributes. It will be the name of the CSC (as in ``components``) in
        lowercase, replacing the colon by an underscore, e.g. "Hexapod:1" ->
        "hexapod_1" or "ATHexapod" -> "athexapod".

        Returns
        -------
        components_attr : `list` of `str`
            List of remotes attribute names.

        """
        return list(self._components.values())

    @property
    def valid_use_cases(self):
        """Define valid usages.

        When subclassing, overwrite this method to return the proper enum.

        Returns
        -------
        usages: enum

        """
        return Usages()

    @property
    def usages(self):
        """Define class usages.

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

        if self._usages is None:
            self._usages = {
                self.valid_use_cases.All: UsagesResources(
                    components_attr=self.components_attr,
                    readonly=False,
                    generics=[
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
                self.valid_use_cases.StateTransition: UsagesResources(
                    components_attr=self.components_attr,
                    readonly=False,
                    generics=[
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
                self.valid_use_cases.MonitorState: UsagesResources(
                    components_attr=self.components_attr,
                    readonly=True,
                    generics=["summaryState"],
                ),
                self.valid_use_cases.MonitorHeartBeat: UsagesResources(
                    components_attr=self.components_attr,
                    readonly=True,
                    generics=["heartbeat"],
                ),
            }

        return self._usages

    async def process_as_completed(self, tasks):
        """Process tasks are they complete.

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
                for c in self.components_attr
                if getattr(self.rem, c) is not None
            ]
        )
        if self._close_domain:
            await self.domain.close()

    async def __aenter__(self):
        await self.start_task
        return self

    async def __aexit__(self, *args):
        await self.close()

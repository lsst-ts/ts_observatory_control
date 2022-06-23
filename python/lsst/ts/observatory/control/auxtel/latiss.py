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

__all__ = ["LATISS", "LATISSUsages"]

import asyncio
import logging
import typing

from lsst.ts import salobj

from ..utils import cast_int_or_str
from ..remote_group import Usages, UsagesResources
from ..base_camera import BaseCamera


class LATISSUsages(Usages):
    """LATISS usages definition.

    Notes
    -----

    Additional usages definition:

    * TakeImage: Enable Camera-only take image operations. Exclude
                 HeaderService, ATSpectrograph and OODS data.
    * Setup: Enable ATSpectrograph setup operations.
    * TakeImageFull: Enable all take image operations with additional support
                     events from HeaderService and OODS
    """

    TakeImage = 1 << 3
    Setup = 1 << 4
    TakeImageFull = 1 << 5
    DryTest = 1 << 6

    def __iter__(self) -> typing.Iterator[int]:

        return iter(
            [
                self.All,
                self.StateTransition,
                self.MonitorState,
                self.MonitorHeartBeat,
                self.TakeImage,
                self.Setup,
                self.TakeImageFull,
                self.DryTest,
            ]
        )


class LATISS(BaseCamera):
    """LSST Auxiliary Telescope Image and Slit less Spectrograph (LATISS).

    LATISS encapsulates core functionality from the following CSCs ATCamera,
    ATSpectrograph, ATHeaderService and ATOODS CSCs.

    Parameters
    ----------
    domain : `lsst.ts.salobj.Domain`
        Domain for remotes. If `None` create a domain.
    log : `logging.Logger`
        Optional logging class to be used for logging operations. If `None`,
        creates a new logger. Useful to use in salobj.BaseScript and allow
        logging in the class use the script logging.
    intended_usage: `int`
        Optional integer that maps to a list of intended operations. This is
        used to limit the resources allocated by the class by gathering some
        knowledge about the usage intention. By default allocates all
        resources.
    tcs_ready_to_take_data: `coroutine`
        A coroutine that waits for the telescope control system to be ready
        to take data.
    """

    def __init__(
        self,
        domain: typing.Optional[salobj.Domain] = None,
        log: typing.Optional[logging.Logger] = None,
        intended_usage: typing.Optional[int] = None,
        tcs_ready_to_take_data: typing.Optional[
            typing.Callable[[], typing.Awaitable]
        ] = None,
    ) -> None:

        super().__init__(
            components=["ATCamera", "ATSpectrograph", "ATHeaderService", "ATOODS"],
            instrument_setup_attributes=["filter", "grating", "linear_stage"],
            domain=domain,
            log=log,
            intended_usage=intended_usage,
            tcs_ready_to_take_data=tcs_ready_to_take_data,
        )

    @property
    def camera(self) -> salobj.Remote:
        """Camera remote."""
        return self.rem.atcamera

    def parse_sensors(self, sensors: typing.Union[str, None]) -> str:
        """Parse input sensors.

        For ATCamera this should always be an empty string.

        Parameters
        ----------
        sensors : `str`
            This field is ignored by LATISS.

        Returns
        -------
        sensors : `str`
            A valid set of sensors.
        """
        return ""

    async def setup_instrument(self, **kwargs: typing.Union[int, float, str]) -> None:
        """Implements abstract method to setup instrument.

        This method will call `setup_atspec` to set filter, grating and
        linear_stage.

        Parameters
        ----------
        **kwargs
            Arbitrary keyword arguments.

        See Also
        --------
        setup_atspec: Setup spectrograph.
        take_bias: Take series of bias.
        take_darks: Take series of darks.
        take_flats: Take series of flat-field images.
        take_object: Take series of object observations.
        take_engtest: Take series of engineering test observations.
        take_imgtype: Take series of images by image type.
        expose: Low level expose method.
        """

        self.check_kwargs(**kwargs)

        atspec_filter: typing.Union[int, str, None] = (
            cast_int_or_str(kwargs["filter"]) if "filter" in kwargs else None
        )
        atspec_grating: typing.Union[int, str, None] = (
            cast_int_or_str(kwargs["grating"]) if "grating" in kwargs else None
        )
        atspec_linear_stage: typing.Union[float, None] = (
            float(kwargs["linear_stage"]) if "linear_stage" in kwargs else None
        )

        await self.setup_atspec(
            filter=atspec_filter,
            grating=atspec_grating,
            linear_stage=atspec_linear_stage,
        )

    async def setup_atspec(
        self,
        filter: typing.Optional[typing.Union[int, str]] = None,
        grating: typing.Optional[typing.Union[int, str]] = None,
        linear_stage: typing.Optional[float] = None,
    ) -> None:
        """Encapsulates commands to setup spectrograph.

        Parameters
        ----------
        filter : `None` or `int` or `str`
            Filter id or name. If None, do not change the filter.
        grating : `None` or `int` or `str`
            Grating id or name.  If None, do not change the grating.
        linear_stage : `None` or `float`
            Linear stage position.  If None, do not change the linear stage.
        """

        setup_coroutines = []
        if filter is not None:
            if isinstance(filter, int):
                filter_kwargs = dict(filter=filter, name="")
            elif type(filter) == str:
                filter_kwargs = dict(filter=0, name=filter)
            else:
                raise RuntimeError(
                    f"Filter must be a string or an int, got "
                    f"{type(filter)}:{filter}"
                )
            setup_coroutines.append(
                self.rem.atspectrograph.cmd_changeFilter.set_start(
                    **filter_kwargs, timeout=self.long_timeout
                )
            )

        if grating is not None:
            if isinstance(grating, int):
                grating_kwargs = dict(disperser=grating, name="")
            elif type(grating) == str:
                grating_kwargs = dict(disperser=0, name=grating)
            else:
                raise RuntimeError(
                    f"Grating must be a string or an int, got "
                    f"{type(grating)}:{grating}"
                )
            setup_coroutines.append(
                self.rem.atspectrograph.cmd_changeDisperser.set_start(
                    **grating_kwargs, timeout=self.long_timeout
                )
            )

        if linear_stage is not None:
            setup_coroutines.append(
                self.rem.atspectrograph.cmd_moveLinearStage.set_start(
                    distanceFromHome=float(linear_stage), timeout=self.long_timeout
                )
            )

        if len(setup_coroutines) > 0:
            async with self.cmd_lock:
                await asyncio.gather(*setup_coroutines)

    async def get_setup(self) -> typing.Tuple[str, str, float]:
        """Get the current filter, grating and stage position

        Returns
        -------
        `str`
            Name of filter currently in the beam
        `str`
            Name of disperser currently in the beam
        `float`
            Position of linear stage holding the dispersers
        """

        filter_pos = await self.rem.atspectrograph.evt_reportedFilterPosition.aget(
            timeout=self.fast_timeout
        )
        grating_pos = await self.rem.atspectrograph.evt_reportedDisperserPosition.aget(
            timeout=self.fast_timeout
        )
        stage_pos = await self.rem.atspectrograph.evt_reportedLinearStagePosition.aget(
            timeout=self.fast_timeout
        )

        return filter_pos.name, grating_pos.name, stage_pos.position

    async def get_available_instrument_setup(
        self,
    ) -> typing.Tuple[typing.List[str], typing.List[str], typing.List[str]]:
        """Return available instrument setup.

        Returns
        -------
        available_filters: `list`
            List of available filters.
        available_gratings: `list`
            List of available gratings.
        linear_state_limits: `list`
            Min/Max values for linear state.

        See Also
        --------
        `tuple` of [`list` of `str`, `list` of `str`, `list` of `str`]
            Available instrument setups.
        """

        try:
            settings_applied_values = (
                await self.rem.atspectrograph.evt_settingsAppliedValues.aget(
                    timeout=self.fast_timeout
                )
            )
        except asyncio.TimeoutError:
            raise RuntimeError(
                "Could not determine instrument setup. "
                "Make sure ATSpectrograph is running, enabled and configured."
            )

        return (
            settings_applied_values.filterNames.split(","),
            settings_applied_values.gratingNames.split(","),
            [
                settings_applied_values.linearStageMinPos,
                settings_applied_values.linearStageMaxPos,
            ],
        )

    @property
    def valid_use_cases(self) -> LATISSUsages:
        """Returns valid usages.

        Returns
        -------
        usages: enum

        """
        return LATISSUsages()

    @property
    def usages(self) -> typing.Dict[int, UsagesResources]:

        if self._usages is None:
            usages = super().usages

            usages[self.valid_use_cases.All] = UsagesResources(
                components_attr=self.components_attr,
                readonly=False,
                generics=["summaryState"],
                atcamera=["takeImages", "endReadout"],
                atspectrograph=[
                    "changeFilter",
                    "changeDisperser",
                    "moveLinearStage",
                    "reportedFilterPosition",
                    "reportedDisperserPosition",
                    "reportedLinearStagePosition",
                ],
                atheaderservice=["largeFileObjectAvailable"],
            )
            usages[self.valid_use_cases.TakeImage] = UsagesResources(
                components_attr=["atcamera"],
                readonly=False,
                generics=["summaryState"],
                atcamera=["takeImages", "endReadout"],
            )
            usages[self.valid_use_cases.Setup] = UsagesResources(
                components_attr=["atspectrograph"],
                readonly=False,
                generics=["summaryState"],
                atspectrograph=[
                    "changeFilter",
                    "changeDisperser",
                    "moveLinearStage",
                    "reportedFilterPosition",
                    "reportedDisperserPosition",
                    "reportedLinearStagePosition",
                ],
            )
            usages[self.valid_use_cases.TakeImageFull] = UsagesResources(
                components_attr=["atcamera", "atspectrograph", "atheaderservice"],
                readonly=False,
                generics=["summaryState"],
                atcamera=["takeImages", "endReadout"],
                atheaderservice=["largeFileObjectAvailable"],
                atspectrograph=[
                    "changeFilter",
                    "changeDisperser",
                    "moveLinearStage",
                    "reportedFilterPosition",
                    "reportedDisperserPosition",
                    "reportedLinearStagePosition",
                ],
            )

            usages[self.valid_use_cases.DryTest] = UsagesResources(
                components_attr=(), readonly=True
            )

            self._usages = usages

        return self._usages

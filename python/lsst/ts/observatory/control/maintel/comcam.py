# This file is part of ts_observatory_control
#
# Developed for the Vera Rubin Observatory Telescope and Site System.
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

__all__ = ["ComCam", "ComCamUsages"]

import asyncio
import logging
import typing

from lsst.ts import salobj

from ..base_camera import BaseCamera
from ..remote_group import Usages, UsagesResources


class ComCamUsages(Usages):
    """ComCam usages definition.

    Notes
    -----

    Additional usages definition:

    * TakeImage: Enable Camera-only take image operations. Exclude
                 HeaderService and OODS data.
    * TakeImageFull: Enable all take image operations with additional support
                     events from HeaderService and OODS
    """

    TakeImage = 1 << 3
    TakeImageFull = 1 << 4
    DryTest = 1 << 6

    def __iter__(self) -> typing.Iterator[int]:
        return iter(
            [
                self.All,
                self.StateTransition,
                self.MonitorState,
                self.MonitorHeartBeat,
                self.TakeImage,
                self.TakeImageFull,
                self.DryTest,
            ]
        )


class ComCam(BaseCamera):
    """Commissioning Camera (ComCam).

    ComCam encapsulates core functionality from the following CSCs CCCamera,
    CCHeaderService and CCOODS CSCs.

    Parameters
    ----------
    domain : `lsst.ts.salobj.Domain`
        Domain for remotes. If `None` create a domain.
    tcs_ready_to_take_data: `coroutine`
        A coroutine that waits for the telescope control system to be ready
        to take data.
    """

    def __init__(
        self,
        domain: salobj.Domain | None = None,
        log: logging.Logger | None = None,
        intended_usage: int | None = None,
        tcs_ready_to_take_data: typing.Callable[[], typing.Awaitable] | None = None,
    ) -> None:
        super().__init__(
            components=["CCCamera", "CCHeaderService", "CCOODS"],
            instrument_setup_attributes=["filter"],
            domain=domain,
            log=log,
            intended_usage=intended_usage,
            tcs_ready_to_take_data=tcs_ready_to_take_data,
        )

        self.read_out_time = 2.0  # readout time (sec)
        self.shutter_time = 1  # time to open or close shutter (sec)
        self.filter_change_timeout = 60  # time for filter to get into position (sec)

        self.valid_imagetype.append("SPOT")

        self.cmd_lock = asyncio.Lock()

    async def take_spot(
        self,
        exptime: float,
        n: int = 1,
        group_id: typing.Optional[str] = None,
        test_type: typing.Optional[str] = None,
        reason: typing.Optional[str] = None,
        program: typing.Optional[str] = None,
        sensors: typing.Optional[str] = None,
        note: typing.Optional[str] = None,
        checkpoint: typing.Optional[typing.Callable[[str], typing.Awaitable]] = None,
        **kwargs: typing.Union[int, float, str],
    ) -> typing.List[int]:
        """Take a series of spot test images.

        Parameters
        ----------
        exptime : `float`
            Exposure time for flats.
        n : `int`
            Number of frames to take.
        group_id : `str`
            Optional group id for the data sequence. Will generate a common
            one for all the data if none is given.
        test_type : `str`
            Optional string to be added to the keyword testType image header.
        reason : `str`, optional
            Reason for the data being taken. This must be a short tag-like
            string that can be used to disambiguate a set of observations.
        program : `str`, optional
            Name of the program this data belongs to, e.g. WFD, DD, etc.
        sensors : `str`
            A colon delimited list of sensor names to use for the image.
        note : `str`
            A freeform string containing small notes about the image.
        checkpoint : `coro`
            A optional awaitable callback that accepts one string argument
            that is called before each bias is taken.

        """
        self.check_kwargs(**kwargs)

        return await self.take_imgtype(
            imgtype="SPOT",
            exptime=exptime,
            n=n,
            n_snaps=1,
            n_shift=None,
            row_shift=None,
            group_id=group_id,
            test_type=test_type,
            reason=reason,
            program=program,
            sensors=sensors,
            note=note,
            checkpoint=checkpoint,
            **kwargs,
        )

    @property
    def camera(self) -> salobj.Remote:
        """Camera remote."""
        return self.rem.cccamera

    def parse_sensors(self, sensors: typing.Union[str, None]) -> str:
        """Parse input sensors.

        Parameters
        ----------
        sensors : `str`
            A colon delimited list of sensor names to use for the image.

        Returns
        -------
        sensors : `str`
            A valid set of sensors.
        """
        return "" if sensors is None else sensors

    async def setup_instrument(self, **kwargs: typing.Union[int, float, str]) -> None:
        """Implements abstract method to setup instrument.

        This method will call `setup_filter` to set the camera filter.

        Parameters
        ----------
        **kwargs
            Arbitrary keyword arguments.

        See Also
        --------
        setup_filter: Setup camera filter.
        take_bias: Take series of bias.
        take_darks: Take series of darks.
        take_flats: Take series of flat-field images.
        take_object: Take series of object observations.
        take_engtest: Take series of engineering test observations.
        take_spot: Take series of spot images.
        take_imgtype: Take series of images by image type.
        expose: Low level expose method.
        """
        self.check_kwargs(**kwargs)

        filter_value = kwargs.get("filter", None)
        if (
            filter_value is not None
            and str(filter_value) != await self.get_current_filter()
        ):
            await self.setup_filter(filter=str(filter_value))

    async def setup_filter(
        self, filter: typing.Union[str, None]
    ) -> typing.Union[None, salobj.type_hints.BaseMsgType]:
        """Setup the filter for the camera.

        Parameters
        ----------
        filter : `str` or `None`
            Filter name. If None, do not change the filter.

        Returns
        -------
        `self.rem.cccamera.evt_endSetFilter.DataType` or `None`
            End set filter event data.
        """
        if filter is not None:
            async with self.cmd_lock:
                self.rem.cccamera.evt_endSetFilter.flush()
                await self.rem.cccamera.cmd_setFilter.set_start(
                    name=filter, timeout=self.filter_change_timeout
                )
                end_setFilter = await self.rem.cccamera.evt_endSetFilter.next(
                    flush=False, timeout=self.filter_change_timeout
                )
                self.log.info(f"Filter {end_setFilter.filterName} in position.")
                return end_setFilter
        else:
            return None

    async def get_current_filter(self) -> str:
        """Get the current filter.

        Returns
        -------
        `str`
            The filter in the light path.
        """
        try:
            end_setFilter = await self.rem.cccamera.evt_endSetFilter.aget(
                timeout=self.fast_timeout
            )
            return end_setFilter.filterName
        except asyncio.TimeoutError:
            raise RuntimeError(
                "Could not determine current filter. Either data was never published or historical "
                "data is not working properly."
            )

    async def get_available_filters(self) -> typing.List[str]:
        """Get the list of available filters.

        Returns
        -------
        `list` of `str`
            The set of filters available
        """
        try:
            available_filters = await self.rem.cccamera.evt_availableFilters.aget(
                timeout=self.fast_timeout
            )
            return available_filters.filterNames.split(":")
        except asyncio.TimeoutError:
            raise RuntimeError(
                "Could not determine available filters. Either data was never published or historical "
                "data is not working properly."
            )

    async def get_available_instrument_setup(self) -> typing.List[str]:
        """Return available instrument setup.

        See Also
        --------
        setup_instrument: Set up instrument.
        """
        return await self.get_available_filters()

    @property
    def valid_use_cases(self) -> ComCamUsages:
        """Returns valid usages.

        Returns
        -------
        usages: enum

        """
        return ComCamUsages()

    @property
    def usages(self) -> typing.Dict[int, UsagesResources]:
        if self._usages is None:
            usages = super().usages

            usages[self.valid_use_cases.All] = UsagesResources(
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
                    "configurationsAvailable",
                    "heartbeat",
                ],
                cccamera=[
                    "takeImages",
                    "setFilter",
                    "endReadout",
                    "startIntegration",
                    "endSetFilter",
                    "availableFilters",
                ],
                ccheaderservice=["largeFileObjectAvailable"],
            )

            usages[self.valid_use_cases.TakeImage] = UsagesResources(
                components_attr=["cccamera", "ccoods"],
                readonly=False,
                cccamera=[
                    "takeImages",
                    "setFilter",
                    "endReadout",
                    "startIntegration",
                    "endSetFilter",
                    "availableFilters",
                ],
                ccoods=[
                    "imageInOODS",
                ],
            )

            usages[self.valid_use_cases.TakeImageFull] = UsagesResources(
                components_attr=["cccamera", "ccheaderservice"],
                readonly=False,
                cccamera=[
                    "takeImages",
                    "setFilter",
                    "endReadout",
                    "endSetFilter",
                    "startIntegration",
                    "availableFilters",
                ],
                ccheaderservice=["largeFileObjectAvailable"],
            )

            self._usages = usages

        return self._usages

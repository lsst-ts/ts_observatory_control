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

__all__ = ["LATISS", "LATISSUsages"]

import asyncio

from ..remote_group import Usages, UsagesResources
from ..base_camera import BaseCamera


class LATISSUsages(Usages):
    """LATISS usages definition.

    Notes
    -----

    Additional usages definition:

    * TakeImage: Enable Camera-only take image operations. Exclude
                 HeaderService, ATSpectrograph and Archiver data.
    * Setup: Enable ATSpectrograph setup operations.
    * TakeImageFull: Enable all take image operations with additional support
                     events from HeaderService and Archiver
    """

    TakeImage = 1 << 3
    Setup = 1 << 4
    TakeImageFull = 1 << 5

    def __iter__(self):

        return iter(
            [
                self.All,
                self.StateTransition,
                self.MonitorState,
                self.MonitorHeartBeat,
                self.TakeImage,
                self.Setup,
                self.TakeImageFull,
            ]
        )


class LATISS(BaseCamera):
    """LSST Auxiliary Telescope Image and Slit less Spectrograph (LATISS).

    LATISS encapsulates core functionality from the following CSCs ATCamera,
    ATSpectrograph, ATHeaderService and ATArchiver CSCs.

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
    """

    def __init__(self, domain=None, log=None, intended_usage=None):

        super().__init__(
            components=["ATCamera", "ATSpectrograph", "ATHeaderService", "ATArchiver"],
            instrument_setup_attributes=["filter", "grating", "linear_stage"],
            domain=domain,
            log=log,
            intended_usage=intended_usage,
        )

    async def expose(
        self,
        exp_time,
        shutter,
        image_type,
        group_id,
        test_type=None,
        sensors=None,
        note=None,
    ):
        """Encapsulates the take image command.

        This basically consists of configuring and sending a takeImages
        command to the camera and waiting for an endReadout event.

        Parameters
        ----------
        exp_time : `float`
            The exposure time for the image, in seconds.
        shutter : `bool`
            Should activate the shutter? (False for bias and dark)
        image_type : `str`
            Image type (a.k.a. IMGTYPE) (e.g. e.g. BIAS, DARK, FLAT, FE55,
            XTALK, CCOB, SPOT...)
        group_id : `str`
            Image groupId. Used to fill in FITS GROUPID header
        test_type : `str`
            Optional string to be added to the keyword testType image header.
        sensors : `str`
            A colon delimited list of sensor names to use for the image.
        note : `str`
            Optional observer note to be added to the image header.

        Returns
        -------
        endReadout : ``self.atcam.evt_endReadout.DataType``
            End readout event data.

        See Also
        --------
        take_bias: Take series of bias.
        take_darks: Take series of darks.
        take_flats: Take series of flat-field images.
        take_object: Take series of object observations.
        take_engtest: Take series of engineering test observations.
        take_imgtype: Take series of images by image type.
        setup_instrument: Set up instrument.

        """
        async with self.cmd_lock:
            # FIXME: Current version of ATCamera software is not set up to take
            # images with numImages > 1, so this is fixed at 1 for now and we
            # loop through any set of images we want to take. (2019/03/11)

            if image_type == "BIAS" and exp_time > 0.0:
                self.log.warning("Image type is BIAS, ignoring exptime.")
                exp_time = 0.0
            elif bool(shutter) and exp_time < self.min_exptime:
                raise RuntimeError(
                    f"Minimum allowed open-shutter exposure time "
                    f"is {self.min_exptime}. Got {exp_time}."
                )

            key_value_map = f"groupId: {group_id},imageType: {image_type}"
            if test_type is not None:
                key_value_map += f",testType: {test_type}"
            else:
                key_value_map += f",testType: {image_type}"

            base_timeout = (
                self.read_out_time + self.long_timeout + self.long_long_timeout
            )
            self.rem.atcamera.evt_endReadout.flush()
            await self.rem.atcamera.cmd_takeImages.set_start(
                numImages=1,
                expTime=float(exp_time),
                shutter=bool(shutter),
                sensors="",  # For ATCamera this should always be empty string
                keyValueMap=key_value_map,
                obsNote=note if note is not None else "",
                timeout=base_timeout + exp_time,
            )
            end_readout = await self.rem.atcamera.evt_endReadout.next(
                flush=False, timeout=base_timeout
            )
            return end_readout

    async def setup_instrument(self, **kwargs):
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

        await self.setup_atspec(
            filter=kwargs.get("filter", None),
            grating=kwargs.get("grating", None),
            linear_stage=kwargs.get("linear_stage", None),
        )

    async def setup_atspec(self, filter=None, grating=None, linear_stage=None):
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
                return await asyncio.gather(*setup_coroutines)

    async def get_setup(self):
        """Get the current filter, grating and stage position

        Returns
        -------
        string
            Name of filter currently in the beam
        string
            Name of disperser currently in the beam
        float
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

    @property
    def valid_use_cases(self):
        """Returns valid usages.

        Returns
        -------
        usages: enum

        """
        return LATISSUsages()

    @property
    def usages(self):

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

            self._usages = usages

        return self._usages

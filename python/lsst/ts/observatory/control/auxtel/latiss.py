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

import types
import asyncio

import numpy as np
import astropy

from ..remote_group import RemoteGroup, Usages


class LATISSUsages(Usages):
    """LATISS usages definition.

    Notes
    -----

    Additional usages definition:

    TakeImage: Enable Camera-only take image operations. Exclude HeaderService,
    ATSpectrograph and Archiver data.

    Setup: Enable ATSpectrograph setup operations.

    TakeImageFull: Enable all take image operations with additional support
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


class LATISS(RemoteGroup):
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
            domain=domain,
            log=log,
            intended_usage=intended_usage,
        )

        # TODO: (DM-24550) Read these from settingsApplied event from ATCamera
        self.read_out_time = 2.0  # readout time (sec)
        self.shutter_time = 1.0  # time to open or close shutter (sec)
        self.min_exptime = 0.1  # minimum open-shutter exposure time

        self.valid_imagetype = ["BIAS", "DARK", "FLAT", "OBJECT", "ENGTEST"]

        self.cmd_lock = asyncio.Lock()

    async def take_bias(self, nbias, group_id=None, checkpoint=None):
        """Take a series of bias images.

        Parameters
        ----------
        nbias : `int`
            Number of bias frames to take.
        group_id : `str`
            Optional group id for the data sequence. Will generate a common
            one for all the data if none is given.
        checkpoint : `coro`
            A optional awaitable callback that accepts one string argument
            that is called before each bias is taken.

        """
        return await self.take_imgtype(
            imgtype="BIAS",
            exptime=0.0,
            n=nbias,
            group_id=group_id,
            checkpoint=checkpoint,
        )

    async def take_darks(self, exptime, ndarks, group_id=None, checkpoint=None):
        """Take a series of dark images.

        Parameters
        ----------
        exptime : `float`
            Exposure time for darks.
        ndarks : `int`
            Number of dark frames to take.
        group_id : `str`
            Optional group id for the data sequence. Will generate a common
            one for all the data if none is given.
        checkpoint : `coro`
            A optional awaitable callback that accepts one string argument
            that is called before each bias is taken.

        """
        return await self.take_imgtype(
            imgtype="DARK",
            exptime=exptime,
            n=ndarks,
            group_id=group_id,
            checkpoint=checkpoint,
        )

    async def take_flats(
        self,
        exptime,
        nflats,
        filter=None,
        grating=None,
        linear_stage=None,
        group_id=None,
        checkpoint=None,
    ):
        """Take a series of flat field images.

        Parameters
        ----------
        exptime : `float`
            Exposure time for flats.
        nflats : `int`
            Number of flat frames to take.
        filter : `None` or `int` or `str`
            Filter id or name. If None, do not change the filter.
        grating : `None` or `int` or `str`
            Grating id or name.  If None, do not change the grating.
        linear_stage : `None` or `float`
            Linear stage position.  If None, do not change the linear stage.
        group_id : `str`
            Optional group id for the data sequence. Will generate a common
            one for all the data if none is given.
        checkpoint : `coro`
            A optional awaitable callback that accepts one string argument
            that is called before each bias is taken.

        """
        return await self.take_imgtype(
            imgtype="FLAT",
            exptime=exptime,
            n=nflats,
            filter=filter,
            grating=grating,
            linear_stage=linear_stage,
            group_id=group_id,
            checkpoint=checkpoint,
        )

    async def take_object(
        self,
        exptime,
        n=1,
        filter=None,
        grating=None,
        linear_stage=None,
        group_id=None,
        checkpoint=None,
    ):
        """Take a series of object images.

        Object images are assumed to be looking through an open dome at the
        sky.

        Parameters
        ----------
        exptime : `float`
            Exposure time for flats.
        n : `int`
            Number of frames to take.
        filter : `None` or `int` or `str`
            Filter id or name. If None, do not change the filter.
        grating : `None` or `int` or `str`
            Grating id or name.  If None, do not change the grating.
        linear_stage : `None` or `float`
            Linear stage position.  If None, do not change the linear stage.
        group_id : `str`
            Optional group id for the data sequence. Will generate a common
            one for all the data if none is given.
        checkpoint : `coro`
            A optional awaitable callback that accepts one string argument
            that is called before each bias is taken.

        """
        return await self.take_imgtype(
            imgtype="OBJECT",
            exptime=exptime,
            n=n,
            filter=filter,
            grating=grating,
            linear_stage=linear_stage,
            group_id=group_id,
            checkpoint=checkpoint,
        )

    async def take_engtest(
        self,
        exptime,
        n=1,
        filter=None,
        grating=None,
        linear_stage=None,
        group_id=None,
        checkpoint=None,
    ):
        """Take a series of engineering test images.

        Parameters
        ----------
        exptime : `float`
            Exposure time for flats.
        n : `int`
            Number of frames to take.
        filter : `None` or `int` or `str`
            Filter id or name. If None, do not change the filter.
        grating : `None` or `int` or `str`
            Grating id or name.  If None, do not change the grating.
        linear_stage : `None` or `float`
            Linear stage position.  If None, do not change the linear stage.
        group_id : `str`
            Optional group id for the data sequence. Will generate a common
            one for all the data if none is given.
        checkpoint : `coro`
            A optional awaitable callback that accepts one string argument
            that is called before each bias is taken.

        """
        return await self.take_imgtype(
            imgtype="ENGTEST",
            exptime=exptime,
            n=n,
            filter=filter,
            grating=grating,
            linear_stage=linear_stage,
            group_id=group_id,
            checkpoint=checkpoint,
        )

    async def take_imgtype(
        self,
        imgtype,
        exptime,
        n,
        filter=None,
        grating=None,
        linear_stage=None,
        group_id=None,
        checkpoint=None,
    ):
        """Take a series of images of the specified image type.

        Parameters
        ----------
        exptime : `float`
            Exposure time for flats.
        n : `int`
            Number of frames to take.
        filter : `None` or `int` or `str`
            Filter id or name. If None, do not change the filter.
        grating : `None` or `int` or `str`
            Grating id or name.  If None, do not change the grating.
        linear_stage : `None` or `float`
            Linear stage position.  If None, do not change the linear stage.
        checkpoint : `coro`
            A optional awaitable callback that accepts one string argument
            that is called before each bias is taken.

        """

        if imgtype not in self.valid_imagetype:
            raise RuntimeError(
                f"Invalid imgtype:{imgtype}. Must be one of "
                f"{self.valid_imagetype!r}"
            )

        exp_ids = np.zeros(n, dtype=int)

        if group_id is None:
            self.log.debug("Generating group_id")
            group_id = self.next_group_id()

        if imgtype not in ["BIAS", "DARK"]:
            await self.setup_atspec(
                filter=filter, grating=grating, linear_stage=linear_stage
            )

        for i in range(n):
            tag = f"{imgtype} {i+1:04} - {n:04}"

            if checkpoint is not None:
                await checkpoint(tag)
            else:
                self.log.debug(tag)

            end_readout = await self.expose(
                exp_time=exptime if imgtype != "BIAS" else 0.0,
                shutter=imgtype not in ["BIAS", "DARK"],
                image_type=imgtype,
                group_id=group_id,
            )
            # parse out visitID from filename -
            # (Patrick comment) this is highly annoying
            _, _, i_prefix, i_suffix = end_readout.imageName.split("_")

            exp_ids[i] = int((i_prefix + i_suffix[1:]))

        return exp_ids

    async def expose(
        self,
        exp_time,
        shutter,
        image_type,
        group_id,
        science=True,
        guide=False,
        wfs=False,
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
        science : `bool`
            Mark image as science (default=True)?
        guide : `bool`
            Mark image as guide (default=False)?
        wfs : `bool`
            Mark image as wfs (default=False)?

        Returns
        -------
        endReadout : ``self.atcam.evt_endReadout.DataType``
            End readout event data.
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

            self.rem.atcamera.cmd_takeImages.set(
                numImages=1,
                expTime=float(exp_time),
                shutter=bool(shutter),
                imageType=str(image_type),
                groupId=str(group_id),
                science=bool(science),
                guide=bool(guide),
                wfs=bool(wfs),
            )

            timeout = self.read_out_time + self.long_timeout + self.long_long_timeout
            self.rem.atcamera.evt_endReadout.flush()
            await self.rem.atcamera.cmd_takeImages.start(timeout=timeout + exp_time)
            end_readout = await self.rem.atcamera.evt_endReadout.next(
                flush=False, timeout=timeout
            )
            return end_readout

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
                self.rem.atspectrograph.cmd_changeFilter.set(filter=filter, name="")
            elif type(filter) == str:
                self.rem.atspectrograph.cmd_changeFilter.set(filter=0, name=filter)
            else:
                raise RuntimeError(
                    f"Filter must be a string or an int, got "
                    f"{type(filter)}:{filter}"
                )
            setup_coroutines.append(
                self.rem.atspectrograph.cmd_changeFilter.start(
                    timeout=self.long_timeout
                )
            )

        if grating is not None:
            if isinstance(grating, int):
                self.rem.atspectrograph.cmd_changeDisperser.set(
                    disperser=grating, name=""
                )
            elif type(grating) == str:
                self.rem.atspectrograph.cmd_changeDisperser.set(
                    disperser=0, name=grating
                )
            else:
                raise RuntimeError(
                    f"Grating must be a string or an int, got "
                    f"{type(grating)}:{grating}"
                )
            setup_coroutines.append(
                self.rem.atspectrograph.cmd_changeDisperser.start(
                    timeout=self.long_timeout
                )
            )

        if linear_stage is not None:
            self.rem.atspectrograph.cmd_moveLinearStage.set(
                distanceFromHome=float(linear_stage)
            )
            setup_coroutines.append(
                self.rem.atspectrograph.cmd_moveLinearStage.start(
                    timeout=self.long_timeout
                )
            )

        if len(setup_coroutines) > 0:
            async with self.cmd_lock:
                return await asyncio.gather(*setup_coroutines)

    def next_group_id(self):
        """Get the next group ID.

        The group ID is the current TAI date and time as a string in ISO
        format. It has T separating date and time and no time zone suffix.
        Here is an example:
        "2020-01-17T22:59:05.721"
        """
        return astropy.time.Time.now().tai.isot

    @property
    def valid_use_cases(self):
        """Returns valid usages.

        When subclassing, overwrite this method to return the proper enum.

        Returns
        -------
        usages: enum

        """
        return LATISSUsages()

    @property
    def usages(self):

        usages = super().usages

        usages[self.valid_use_cases.All] = types.SimpleNamespace(
            components=self._components,
            readonly=False,
            include=[
                "takeImages",
                "changeFilter",
                "changeDisperser",
                "moveLinearStage",
                "summaryState",
                "endReadout",
                "largeFileObjectAvailable",
            ],
        )
        usages[self.valid_use_cases.TakeImage] = types.SimpleNamespace(
            components=["ATCamera"],
            readonly=False,
            include=["takeImages", "summaryState", "endReadout"],
        )
        usages[self.valid_use_cases.Setup] = types.SimpleNamespace(
            components=["ATSpectrograph"],
            readonly=False,
            include=[
                "changeFilter",
                "changeDisperser",
                "moveLinearStage",
                "summaryState",
            ],
        )
        usages[self.valid_use_cases.TakeImageFull] = types.SimpleNamespace(
            components=["ATCamera", "ATSpectrograph", "ATArchiver"],
            readonly=False,
            include=[
                "takeImages",
                "summaryState",
                "endReadout",
                "largeFileObjectAvailable",
            ],
        )

        return usages

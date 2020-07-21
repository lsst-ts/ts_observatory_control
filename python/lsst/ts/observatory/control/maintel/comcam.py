# This file is part of ts_observatory_control
#
# Developed for the LSST Telescope and Site System.
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
import types

from ..remote_group import Usages
from ..base_camera import BaseCamera


class ComCamUsages(Usages):
    """ComCam usages definition.

    Notes
    -----

    Additional usages definition:

    * TakeImage: Enable Camera-only take image operations. Exclude
                 HeaderService and Archiver data.
    * TakeImageFull: Enable all take image operations with additional support
                     events from HeaderService and Archiver
    """

    TakeImage = 1 << 3
    TakeImageFull = 1 << 4

    def __iter__(self):

        return iter(
            [
                self.All,
                self.StateTransition,
                self.MonitorState,
                self.MonitorHeartBeat,
                self.TakeImage,
                self.TakeImageFull,
            ]
        )


class ComCam(BaseCamera):
    """Commissioning Camera (ComCam).

    ComCam encapsulates core functionality from the following CSCs CCCamera,
    CCHeaderService and CCArchiver CSCs.

    Parameters
    ----------
    domain : `lsst.ts.salobj.Domain`
        Domain for remotes. If `None` create a domain.
    """

    def __init__(self, domain=None, log=None, intended_usage=None):

        super().__init__(
            components=["CCCamera", "CCHeaderService", "CCArchiver"],
            instrument_setup_attributes=["filter"],
            domain=domain,
            log=log,
            intended_usage=intended_usage,
        )

        self.read_out_time = 2.0  # readout time (sec)
        self.shutter_time = 1  # time to open or close shutter (sec)

        self.valid_imagetype.append("SPOT")

        self.cmd_lock = asyncio.Lock()

    async def take_spot(
        self,
        exptime,
        n=1,
        group_id=None,
        sensors=None,
        note=None,
        checkpoint=None,
        **kwargs,
    ):
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
            group_id=group_id,
            sensors=sensors,
            note=note,
            checkpoint=checkpoint,
            **kwargs,
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
            The classifier for the testing type. Usually the same as
            `image_type`.
        sensors : `str`
            A colon delimited list of sensor names to use for the image.
        note : `str`
            A freeform string containing small notes about the image.

        Returns
        -------
        endReadout : ``self.cccamera.evt_endReadout.DataType``
            End readout event data.
        """
        async with self.cmd_lock:
            # FIXME: Current version of CCCamera software is not set up to take
            # images with numImages > 1, so this is fixed at 1 for now and we
            # loop through any set of images we want to take.

            key_value_map = (
                f"imageType: {image_type}, groupId: {group_id}, "
                f"testType: {image_type if test_type is None else test_type}"
            )

            self.rem.cccamera.cmd_takeImages.set(
                numImages=1,
                expTime=float(exp_time),
                shutter=bool(shutter),
                keyValueMap=key_value_map,
                sensors="" if sensors is None else sensors,
                obsNote="" if note is None else note,
            )

            timeout = self.read_out_time + self.long_timeout + self.long_long_timeout
            self.rem.cccamera.evt_endReadout.flush()
            await self.rem.cccamera.cmd_takeImages.start(timeout=timeout + exp_time)
            end_readout = await self.rem.cccamera.evt_endReadout.next(
                flush=False, timeout=timeout
            )
            # 2020/07/01 Temporary fix until better messages can be sent to
            # handle the fast paced images like biases.
            if float(exp_time) < 10.0:
                await asyncio.sleep(5.0)
            return end_readout

    async def setup_instrument(self, **kwargs):
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
        await self.setup_filter(filter=kwargs.get("filter", None))

    async def setup_filter(self, filter):
        """Setup the filter for the camera.

        Parameters
        ----------
        filter : `None` or `int` or `str`
            Filter id or name. If None, do not change the filter.
        """
        if filter is None:
            return
        else:
            raise NotImplementedError("set_filter not available yet.")

    @property
    def valid_use_cases(self):
        """Returns valid usages.

        Returns
        -------
        usages: enum

        """
        return ComCamUsages()

    @property
    def usages(self):

        usages = super().usages

        usages[self.valid_use_cases.All] = types.SimpleNamespace(
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
                "takeImages",
                "setFilter",
                "endReadout",
                "largeFileObjectAvailable",
            ],
        )

        usages[self.valid_use_cases.TakeImage] = types.SimpleNamespace(
            components=["CCCamera"],
            readonly=False,
            include=["takeImages", "setFilter", "endReadout"],
        )

        usages[self.valid_use_cases.TakeImageFull] = types.SimpleNamespace(
            components=["CCCamera", "CCHeaderService", "CCArchiver"],
            readonly=False,
            include=[
                "takeImages",
                "setFilter",
                "endReadout",
                "largeFileObjectAvailable",
            ],
        )

        return usages

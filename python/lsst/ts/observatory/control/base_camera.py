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

__all__ = ["BaseCamera"]

import abc
import asyncio

import numpy as np
import astropy

from . import RemoteGroup


class BaseCamera(RemoteGroup, metaclass=abc.ABCMeta):
    """Base class for camera instruments.

    Parameters
    ----------
    components : `list` [`str`]
        A list of strings with the names of the SAL components that are part
        of the camera group.
    instrument_setup_attributes : `list` [`str`]
        Names of the attributes needed to setup the instrument for taking an
        exposure. This is used to check for bad input with functions calls.
    domain : `lsst.ts.salobj.Domain`
        Domain for remotes. If `None` create a domain.
    log : `logging.Logger`
        Optional logging class to be used for logging operations. If `None`,
        create a new logger.
    intended_usage: `int`
        Optional integer that maps to a list of intended operations. This is
        used to limit the resources allocated by the class by gathering some
        knowledge about the usage intention. By default allocates all
        resources.
    tcs_ready_to_take_data: `function`
        A function that returns an `asyncio.Future` object.
    """

    def __init__(
        self,
        components,
        instrument_setup_attributes,
        domain=None,
        log=None,
        intended_usage=None,
        tcs_ready_to_take_data=None,
    ):

        super().__init__(
            components=components,
            domain=domain,
            log=log,
            intended_usage=intended_usage,
        )

        self.read_out_time = 2.0  # readout time (sec)
        self.shutter_time = 1.0  # time to open or close shutter (sec)
        self.min_exptime = 0.1  # minimum open-shutter exposure time
        # Maximum time to wait for the tcs to report as ready to take data
        self.max_tcs_wait_time = 30.0

        self.valid_imagetype = ["BIAS", "DARK", "FLAT", "OBJECT", "ENGTEST"]

        self.instrument_setup_attributes = set(instrument_setup_attributes)

        self.cmd_lock = asyncio.Lock()

        self.ready_to_take_data = tcs_ready_to_take_data

    async def take_bias(
        self,
        nbias,
        group_id=None,
        test_type=None,
        sensors=None,
        note=None,
        checkpoint=None,
    ):
        """Take a series of bias images.

        Parameters
        ----------
        nbias : `int`
            Number of bias frames to take.
        group_id : `str`
            Optional group id for the data sequence. Will generate a common
            one for all the data if none is given.
        test_type : `str`
            Optional string to be added to the keyword testType image header.
        sensors : `str`
            A colon delimited list of sensor names to use for the image.
        note : `str`
            Optional observer note to be added to the image header.
        checkpoint : `coro`
            A optional awaitable callback that accepts one string argument
            that is called before each bias is taken.

        See Also
        --------
        take_darks: Take series of darks.
        take_flats: Take series of flat-field images
        take_object: Take series of object observations.
        take_engtest: Take series of engineering test observations.
        take_imgtype: Take series of images by image type.
        setup_instrument: Set up instrument.
        expose: Low level expose method.

        """
        return await self.take_imgtype(
            imgtype="BIAS",
            exptime=0.0,
            n=nbias,
            group_id=group_id,
            test_type=test_type,
            sensors=sensors,
            note=note,
            checkpoint=checkpoint,
        )

    async def take_darks(
        self,
        exptime,
        ndarks,
        group_id=None,
        test_type=None,
        sensors=None,
        note=None,
        checkpoint=None,
    ):
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
        test_type : `str`
            Optional string to be added to the keyword testType image header.
        sensors : `str`
            A colon delimited list of sensor names to use for the image.
        note : `str`
            Optional observer note to be added to the image header.
        checkpoint : `coro`
            A optional awaitable callback that accepts one string argument
            that is called before each bias is taken.

        See Also
        --------
        take_bias: Take series of bias.
        take_flats: Take series of flat-field images.
        take_object: Take series of object observations.
        take_engtest: Take series of engineering test observations.
        take_imgtype: Take series of images by image type.
        setup_instrument: Set up instrument.
        expose: Low level expose method.

        """
        return await self.take_imgtype(
            imgtype="DARK",
            exptime=exptime,
            n=ndarks,
            group_id=group_id,
            test_type=test_type,
            sensors=sensors,
            note=note,
            checkpoint=checkpoint,
        )

    async def take_flats(
        self,
        exptime,
        nflats,
        group_id=None,
        test_type=None,
        sensors=None,
        note=None,
        checkpoint=None,
        **kwargs,
    ):
        """Take a series of flat field images.

        Parameters
        ----------
        exptime : `float`
            Exposure time for flats.
        nflats : `int`
            Number of flat frames to take.
        group_id : `str`
            Optional group id for the data sequence. Will generate a common
            one for all the data if none is given.
        test_type : `str`
            Optional string to be added to the keyword testType image header.
        sensors : `str`
            A colon delimited list of sensor names to use for the image.
        note : `str`
            Optional observer note to be added to the image header.
        checkpoint : `coro`
            A optional awaitable callback that accepts one string argument
            that is called before each bias is taken.
        **kwargs
            Arbitrary keyword arguments.

        Notes
        -----
        This is an abstract method. To check additional inputs for instrument
        setup check `setup_instrument`.

        See Also
        --------
        take_bias: Take series of bias.
        take_darks: Take series of darks.
        take_object: Take series of object observations.
        take_engtest: Take series of engineering test observations.
        take_imgtype: Take series of images by image type.
        setup_instrument: Set up instrument.
        expose: Low level expose method.

        """

        self.check_kwargs(**kwargs)

        return await self.take_imgtype(
            imgtype="FLAT",
            exptime=exptime,
            n=nflats,
            group_id=group_id,
            test_type=test_type,
            sensors=sensors,
            note=note,
            checkpoint=checkpoint,
            **kwargs,
        )

    async def take_object(
        self,
        exptime,
        n=1,
        group_id=None,
        test_type=None,
        sensors=None,
        note=None,
        checkpoint=None,
        **kwargs,
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
        group_id : `str`
            Optional group id for the data sequence. Will generate a common
            one for all the data if none is given.
        test_type : `str`
            Optional string to be added to the keyword testType image header.
        sensors : `str`
            A colon delimited list of sensor names to use for the image.
        note : `str`
            Optional observer note to be added to the image header.
        checkpoint : `coro`
            A optional awaitable callback that accepts one string argument
            that is called before each bias is taken.
        **kwargs
            Arbitrary keyword arguments.

        See Also
        --------
        take_bias: Take series of bias.
        take_darks: Take series of darks.
        take_flats: Take series of flat-field images.
        take_engtest: Take series of engineering test observations.
        take_imgtype: Take series of images by image type.
        setup_instrument: Set up instrument.
        expose: Low level expose method.

        """

        self.check_kwargs(**kwargs)

        return await self.take_imgtype(
            imgtype="OBJECT",
            exptime=exptime,
            n=n,
            group_id=group_id,
            test_type=test_type,
            sensors=sensors,
            note=note,
            checkpoint=checkpoint,
            **kwargs,
        )

    async def take_engtest(
        self,
        exptime,
        n=1,
        group_id=None,
        test_type=None,
        sensors=None,
        note=None,
        checkpoint=None,
        **kwargs,
    ):
        """Take a series of engineering test images.

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
        sensors : `str`
            A colon delimited list of sensor names to use for the image.
        note : `str`
            Optional observer note to be added to the image header.
        checkpoint : `coro`
            A optional awaitable callback that accepts one string argument
            that is called before each bias is taken.
        **kwargs
            Arbitrary keyword arguments.

        See Also
        --------
        take_bias: Take series of bias.
        take_darks: Take series of darks.
        take_flats: Take series of flat-field images.
        take_object: Take series of object observations.
        take_imgtype: Take series of images by image type.
        setup_instrument: Set up instrument.
        expose: Low level expose method.

        """

        self.check_kwargs(**kwargs)

        return await self.take_imgtype(
            imgtype="ENGTEST",
            exptime=exptime,
            n=n,
            group_id=group_id,
            test_type=test_type,
            sensors=sensors,
            note=note,
            checkpoint=checkpoint,
            **kwargs,
        )

    async def take_imgtype(
        self,
        imgtype,
        exptime,
        n,
        group_id=None,
        test_type=None,
        sensors=None,
        note=None,
        checkpoint=None,
        **kwargs,
    ):
        """Take a series of images of the specified image type.

        Parameters
        ----------
        exptime : `float`
            Exposure time for flats.
        n : `int`
            Number of frames to take.
        test_type : `str`
            Optional string to be added to the keyword testType image header.
        sensors : `str`
            A colon delimited list of sensor names to use for the image.
        note : `str`
            Optional observer note to be added to the image header.
        checkpoint : `coro`
            A optional awaitable callback that accepts one string argument
            that is called before each bias is taken.
        **kwargs
            Arbitrary keyword arguments.

        See Also
        --------
        take_bias: Take series of bias.
        take_darks: Take series of darks.
        take_flats: Take series of flat-field images.
        take_object: Take series of object observations.
        take_engtest: Take series of engineering test observations.
        setup_instrument: Set up instrument.
        expose: Low level expose method.

        Raises
        ------
        RuntimeError
            If TCS takes took long to report

        """

        self.check_kwargs(**kwargs)

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
            await self.setup_instrument(**kwargs)

        if imgtype == "OBJECT" and self.ready_to_take_data is not None:
            self.log.debug(f"imagetype: {imgtype}, wait for TCS to be ready.")
            try:
                await asyncio.wait_for(
                    self.ready_to_take_data(),
                    timeout=self.max_tcs_wait_time,
                )
            except asyncio.TimeoutError:
                raise RuntimeError(
                    "Timeout waiting for TCS to report as ready to take data "
                    f"(timeout={self.max_tcs_wait_time})."
                )
        elif imgtype == "OBJECT" and self.ready_to_take_data is None:
            self.log.debug(f"imagetype: {imgtype}, TCS synchronization not configured.")
        else:
            self.log.debug(f"imagetype: {imgtype}, skip TCS synchronization.")

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
                test_type=test_type,
                sensors=sensors,
                note=note,
            )
            # parse out visitID from filename -
            # (Patrick comment) this is highly annoying
            _, _, i_prefix, i_suffix = end_readout.imageName.split("_")

            exp_ids[i] = int((i_prefix + i_suffix[1:]))

        return exp_ids

    def check_kwargs(self, **kwags):
        """Utility method to verify that kwargs are in
        `self.instrument_setup_attributes`.

        Raises
        ------
        RuntimeError:
            If keyword in kwargs is not in `self.instrument_setup_attributes.`

        """

        for key in kwags:
            if key not in self.instrument_setup_attributes:
                raise RuntimeError(
                    f"Invalid argument {key}."
                    f" Must be one of {self.instrument_setup_attributes}."
                )

    def get_key_value_map(
        self,
        image_type,
        group_id,
        test_type=None,
        reason=None,
        program=None,
    ):
        """Parse inputs into a valid key-value string for the cameras.

        Parameters
        ----------
        image_type : `str`
            Image type (a.k.a. IMGTYPE) (e.g. e.g. BIAS, DARK, FLAT, FE55,
            XTALK, CCOB, SPOT...)
        group_id : `str`
            Image groupId. Used to fill in FITS GROUPID header
        test_type : `str`, optional
            The classifier for the testing type. Usually the same as
            `image_type`.
        reason : `str`, optional
            Reason for the data being taken. This must be a short tag-like
            string that can be used to disambiguate a set of observations.
        program : `str`, optional
            Name of the program this data belongs to, e.g. WFD, DD, etc.
        """

        key_value_map = (
            f"imageType: {image_type}, groupId: {group_id}, "
            f"testType: {image_type if test_type is None else test_type}"
        )

        if reason is not None:
            key_value_map += f", reason: {reason}"

        if program is not None:
            key_value_map += f", program: {program}"

        return key_value_map

    @property
    @abc.abstractmethod
    def camera(self):
        """Camera remote."""
        raise NotImplementedError()

    @abc.abstractmethod
    async def setup_instrument(self, **kwargs):
        """Generic method called during `take_imgtype` to setup instrument.

        Parameters
        ----------
        **kwargs
            Arbitrary keyword arguments.

        See Also
        --------
        take_bias: Take series of bias.
        take_darks: Take series of darks.
        take_flats: Take series of flat-field images.
        take_object: Take series of object observations.
        take_engtest: Take series of engineering test observations.
        take_imgtype: Take series of images by image type.
        expose: Low level expose method.

        """
        raise NotImplementedError()

    @abc.abstractmethod
    async def get_available_instrument_setup(self):
        """Return available instrument setup.

        See Also
        --------
        setup_instrument: Set up instrument.
        """
        raise NotImplementedError()

    @abc.abstractmethod
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
            Image type (a.k.a. IMGTYPE) (e.g. BIAS, DARK, FLAT, FE55,
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
        raise NotImplementedError()

    @staticmethod
    def next_group_id():
        """Get the next group ID.

        The group ID is the current TAI date and time as a string in ISO
        format. It has T separating date and time and no time zone suffix.
        Here is an example:
        "2020-01-17T22:59:05.721"

        Return
        ------
        group_id : `string`
        """
        # TODO: Use static method from QueueModel. (DM-21336)
        # This has some consequences because ts_scriptqueue becomes a
        # dependency of ts_observatory_control, which impacts the build
        # environment.
        # from lsst.ts.scriptqueue.queue_model import QueueModel
        # QueueModel.next_group_id()
        return astropy.time.Time.now().tai.isot

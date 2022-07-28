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
import logging
import typing

import astropy

from lsst.ts import salobj

from . import RemoteGroup
from .utils import CameraExposure


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
    tcs_ready_to_take_data: `coroutine`
        A coroutine that waits for the telescope control system to be ready
        to take data.
    """

    def __init__(
        self,
        components: typing.List[str],
        instrument_setup_attributes: typing.List[str],
        domain: typing.Optional[salobj.Domain] = None,
        log: typing.Optional[logging.Logger] = None,
        intended_usage: typing.Optional[int] = None,
        tcs_ready_to_take_data: typing.Callable[[], typing.Awaitable] = None,
    ) -> None:

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

        self.valid_imagetype = [
            "BIAS",
            "DARK",
            "FLAT",
            "OBJECT",
            "ENGTEST",
            "ACQ",
            "CWFS",
            "FOCUS",
            "STUTTERED",
        ]

        self._stuttered_imgtype = {"STUTTERED"}

        self.instrument_setup_attributes = set(instrument_setup_attributes)

        self.cmd_lock = asyncio.Lock()

        self.ready_to_take_data = tcs_ready_to_take_data

        self.max_n_snaps_warning = 2

    async def take_bias(
        self,
        nbias: int,
        group_id: typing.Optional[str] = None,
        test_type: typing.Optional[str] = None,
        reason: typing.Optional[str] = None,
        program: typing.Optional[str] = None,
        sensors: typing.Optional[str] = None,
        note: typing.Optional[str] = None,
        checkpoint: typing.Optional[typing.Callable[[str], typing.Awaitable]] = None,
    ) -> typing.List[int]:
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
        reason : `str`, optional
            Reason for the data being taken. This must be a short tag-like
            string that can be used to disambiguate a set of observations.
        program : `str`, optional
            Name of the program this data belongs to, e.g. WFD, DD, etc.
        sensors : `str`
            A colon delimited list of sensor names to use for the image.
        note : `str`
            Optional observer note to be added to the image header.
        checkpoint : `coro`
            A optional awaitable callback that accepts one string argument
            that is called before each bias is taken.

        Returns
        -------
        `list` of `int`
            List of exposure ids.

        See Also
        --------
        take_darks: Take series of darks images.
        take_flats: Take series of flats images.
        take_object: Take series of object images.
        take_engtest: Take series of engineering test images.
        take_focus: Take series of focus images.
        take_cwfs: Take series of curvature wavefront sensing images.
        take_acq: Take series of acquisition images.
        take_stuttered: Take series of stuttered images.
        take_imgtype: Take series of images of specified imgage type.
        setup_instrument: Set up instrument.
        expose: Low level expose method.
        """
        return await self.take_imgtype(
            imgtype="BIAS",
            exptime=0.0,
            n=nbias,
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
        )

    async def take_darks(
        self,
        exptime: float,
        ndarks: int,
        group_id: typing.Optional[str] = None,
        test_type: typing.Optional[str] = None,
        reason: typing.Optional[str] = None,
        program: typing.Optional[str] = None,
        sensors: typing.Optional[str] = None,
        note: typing.Optional[str] = None,
        checkpoint: typing.Optional[typing.Callable[[str], typing.Awaitable]] = None,
    ) -> typing.List[int]:
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
        reason : `str`, optional
            Reason for the data being taken. This must be a short tag-like
            string that can be used to disambiguate a set of observations.
        program : `str`, optional
            Name of the program this data belongs to, e.g. WFD, DD, etc.
        note : `str`
            Optional observer note to be added to the image header.
        checkpoint : `coro`
            A optional awaitable callback that accepts one string argument
            that is called before each bias is taken.

        Returns
        -------
        `list` of `int`
            List of exposure ids.

        See Also
        --------
        take_bias: Take series of bias images.
        take_flats: Take series of flats images.
        take_object: Take series of object images.
        take_engtest: Take series of engineering test images.
        take_focus: Take series of focus images.
        take_cwfs: Take series of curvature wavefront sensing images.
        take_acq: Take series of acquisition images.
        take_stuttered: Take series of stuttered images.
        take_imgtype: Take series of images of specified imgage type.
        setup_instrument: Set up instrument.
        expose: Low level expose method.
        """
        return await self.take_imgtype(
            imgtype="DARK",
            exptime=exptime,
            n=ndarks,
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
        )

    async def take_flats(
        self,
        exptime: float,
        nflats: int,
        group_id: typing.Optional[str] = None,
        test_type: typing.Optional[str] = None,
        reason: typing.Optional[str] = None,
        program: typing.Optional[str] = None,
        sensors: typing.Optional[str] = None,
        note: typing.Optional[str] = None,
        checkpoint: typing.Optional[typing.Callable[[str], typing.Awaitable]] = None,
        **kwargs: typing.Union[int, float, str],
    ) -> typing.List[int]:
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
        reason : `str`, optional
            Reason for the data being taken. This must be a short tag-like
            string that can be used to disambiguate a set of observations.
        program : `str`, optional
            Name of the program this data belongs to, e.g. WFD, DD, etc.
        sensors : `str`
            A colon delimited list of sensor names to use for the image.
        note : `str`
            Optional observer note to be added to the image header.
        checkpoint : `coro`
            A optional awaitable callback that accepts one string argument
            that is called before each bias is taken.
        **kwargs
            Arbitrary keyword arguments.

        Returns
        -------
        `list` of `int`
            List of exposure ids.

        Notes
        -----
        This is an abstract method. To check additional inputs for instrument
        setup check `setup_instrument`.

        See Also
        --------
        take_bias: Take series of bias images.
        take_darks: Take series of darks images.
        take_object: Take series of object images.
        take_engtest: Take series of engineering test images.
        take_focus: Take series of focus images.
        take_cwfs: Take series of curvature wavefront sensing images.
        take_acq: Take series of acquisition images.
        take_stuttered: Take series of stuttered images.
        take_imgtype: Take series of images of specified imgage type.
        setup_instrument: Set up instrument.
        expose: Low level expose method.
        """

        self.check_kwargs(**kwargs)

        return await self.take_imgtype(
            imgtype="FLAT",
            exptime=exptime,
            n=nflats,
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

    async def take_object(
        self,
        exptime: float,
        n: int = 1,
        n_snaps: int = 1,
        group_id: typing.Optional[str] = None,
        test_type: typing.Optional[str] = None,
        reason: typing.Optional[str] = None,
        program: typing.Optional[str] = None,
        sensors: typing.Optional[str] = None,
        note: typing.Optional[str] = None,
        checkpoint: typing.Optional[typing.Callable[[str], typing.Awaitable]] = None,
        **kwargs: typing.Union[int, float, str],
    ) -> typing.List[int]:
        """Take a series of object images.

        Object images are assumed to be looking through an open dome at the
        sky.

        Parameters
        ----------
        exptime : `float`
            Exposure time for flats.
        n : `int`, optional
            Number of frames to take (default=1).
        n_snaps : `int`
            Number of snaps to take (default=1).
        group_id : `str`, optional
            Optional group id for the data sequence. Will generate a common
            one for all the data if none is given.
        test_type : `str`, optional
            Optional string to be added to the keyword testType image header.
        reason : `str`, optional
            Reason for the data being taken. This must be a short tag-like
            string that can be used to disambiguate a set of observations.
        program : `str`, optional
            Name of the program this data belongs to, e.g. WFD, DD, etc.
        sensors : `str`, optional
            A colon delimited list of sensor names to use for the image.
        note : `str`, optional
            Optional observer note to be added to the image header.
        checkpoint : `coro`, optional
            A optional awaitable callback that accepts one string argument
            that is called before each bias is taken.
        **kwargs
            Arbitrary keyword arguments.

        Returns
        -------
        `list` of `int`
            List of exposure ids.

        See Also
        --------
        take_bias: Take series of bias images.
        take_darks: Take series of darks images.
        take_flats: Take series of flats images.
        take_engtest: Take series of engineering test images.
        take_focus: Take series of focus images.
        take_cwfs: Take series of curvature wavefront sensing images.
        take_acq: Take series of acquisition images.
        take_stuttered: Take series of stuttered images.
        take_imgtype: Take series of images of specified imgage type.
        setup_instrument: Set up instrument.
        expose: Low level expose method.

        Notes
        -----

        Object images support two nested ways of sequencing images; a regular
        sequence of independent observations (controlled by the `n` parameter)
        and sequence of snaps (controlled by the `n_snaps` parameter).

        In fact the `n` parameter specify the number of "snaps" and `n_snaps`
        specify how many images per "snap". Therefore, `n=2` and `n_snaps=2` is
        interpreted as 2 sequences of snaps, each snap with 2 images,
        accounting for 2x2=4 images total.

        Snaps provide a special way of data aggregation employed by the data
        reduction pipeline and should be used only in specific cases. In
        general snaps are either 1 or 2 images, larger numbers are allowed but
        discouraged (and will result in a warning message).
        """

        self.check_kwargs(**kwargs)

        return await self.take_imgtype(
            imgtype="OBJECT",
            exptime=exptime,
            n=n,
            n_snaps=n_snaps,
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

    async def take_engtest(
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
        reason : `str`, optional
            Reason for the data being taken. This must be a short tag-like
            string that can be used to disambiguate a set of observations.
        program : `str`, optional
            Name of the program this data belongs to, e.g. WFD, DD, etc.
        sensors : `str`
            A colon delimited list of sensor names to use for the image.
        note : `str`
            Optional observer note to be added to the image header.
        checkpoint : `coro`
            A optional awaitable callback that accepts one string argument
            that is called before each bias is taken.
        **kwargs
            Arbitrary keyword arguments.

        Returns
        -------
        `list` of `int`
            List of exposure ids.

        See Also
        --------
        take_bias: Take series of bias images.
        take_darks: Take series of darks images.
        take_flats: Take series of flats images.
        take_object: Take series of object images.
        take_focus: Take series of focus images.
        take_cwfs: Take series of curvature wavefront sensing images.
        take_acq: Take series of acquisition images.
        take_stuttered: Take series of stuttered images.
        take_imgtype: Take series of images of specified imgage type.
        setup_instrument: Set up instrument.
        expose: Low level expose method.
        """

        self.check_kwargs(**kwargs)

        return await self.take_imgtype(
            imgtype="ENGTEST",
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

    async def take_focus(
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
        """Take images for classical focus sequence.

        Focus sequence consists of applying an initialy large focus offset,
        then, continually take data and move focus back in the direction of to
        the original position, until it has passed it by a similar amount in
        that direction.

        By detecting a bright source in a focus sequence and finding the
        focus position with smaller full-width-half-maximum, we can estimate
        the best focus position.

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
            Optional observer note to be added to the image header.
        checkpoint : `coro`
            A optional awaitable callback that accepts one string argument
            that is called before each bias is taken.
        **kwargs
            Arbitrary keyword arguments.

        Returns
        -------
        `list` of `int`
            List of exposure ids.

        See Also
        --------
        take_bias: Take series of bias images.
        take_darks: Take series of darks images.
        take_flats: Take series of flats images.
        take_object: Take series of object images.
        take_engtest: Take series of engineering test images.
        take_cwfs: Take series of curvature wavefront sensing images.
        take_acq: Take series of acquisition images.
        take_stuttered: Take series of stuttered images.
        take_imgtype: Take series of images of specified imgage type.
        setup_instrument: Set up instrument.
        expose: Low level expose method.
        """

        self.check_kwargs(**kwargs)

        return await self.take_imgtype(
            imgtype="FOCUS",
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

    async def take_cwfs(
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
        """Take images for curvature wavefront sensing.

        Curvature wavefront sensing images are usually extremely out of focus
        images that are processed to determine the wavefront errors of the
        telescope optics. These results can later be processed thought a
        sensitivity matrix to yield optical corrections.

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
            Optional observer note to be added to the image header.
        checkpoint : `coro`
            A optional awaitable callback that accepts one string argument
            that is called before each bias is taken.
        **kwargs
            Arbitrary keyword arguments.

        Returns
        -------
        `list` of `int`
            List of exposure ids.

        See Also
        --------
        take_bias: Take series of bias images.
        take_darks: Take series of darks images.
        take_flats: Take series of flats images.
        take_object: Take series of object images.
        take_engtest: Take series of engineering test images.
        take_focus: Take series of focus images.
        take_acq: Take series of acquisition images.
        take_stuttered: Take series of stuttered images.
        take_imgtype: Take series of images of specified imgage type.
        setup_instrument: Set up instrument.
        expose: Low level expose method.
        """

        self.check_kwargs(**kwargs)

        return await self.take_imgtype(
            imgtype="CWFS",
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

    async def take_acq(
        self,
        exptime: float = 1.0,
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
        """Take acquisition images.

        Acquisition images are generaly used to check the position of the
        targets in the FoV, the image quality after a focus/cwfs sequence
        or any other quick verification purposes.

        Because they are supposed to be short exposures, this method provide a
        default value for the exposure time of 1 second, so one can call it
        with no argument.

        Parameters
        ----------
        exptime : `float`, optional
            Exposure time for flats.
        n : `int`, optional
            Number of frames to take.
        group_id : `str`, optional
            Optional group id for the data sequence. Will generate a common
            one for all the data if none is given.
        test_type : `str`, optional
            Optional string to be added to the keyword testType image header.
        reason : `str`, optional
            Reason for the data being taken. This must be a short tag-like
            string that can be used to disambiguate a set of observations.
        program : `str`, optional
            Name of the program this data belongs to, e.g. WFD, DD, etc.
        sensors : `str`
            A colon delimited list of sensor names to use for the image.
        note : `str`
            Optional observer note to be added to the image header.
        checkpoint : `coro`
            A optional awaitable callback that accepts one string argument
            that is called before each bias is taken.
        **kwargs
            Arbitrary keyword arguments.

        Returns
        -------
        `list` of `int`
            List of exposure ids.

        See Also
        --------
        take_bias: Take series of bias images.
        take_darks: Take series of darks images.
        take_flats: Take series of flats images.
        take_object: Take series of object images.
        take_engtest: Take series of engineering test images.
        take_focus: Take series of focus images.
        take_cwfs: Take series of curvature wavefront sensing images.
        take_stuttered: Take series of stuttered images.
        take_imgtype: Take series of images of specified imgage type.
        setup_instrument: Set up instrument.
        expose: Low level expose method.
        """

        self.check_kwargs(**kwargs)

        return await self.take_imgtype(
            imgtype="ACQ",
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

    async def take_stuttered(
        self,
        exptime: float,
        n_shift: int,
        row_shift: int,
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
        """Take stuttered images.

        Stuttered image consists of starting an acquisition "manually", then
        doing subsequent row-shifts of the image readout for a given number of
        times. This allows one to take rapid sequence of observations of
        sources as the detector does not need to readout completely, but the
        images end up with an odd appearence, as the field offsets at each
        iteration.

        Parameters
        ----------
        exptime : `float`
            Exposure time (in seconds).
        n_shift : `int`
            Number of shift-expose sequences.
        row_shift : `int`
            How many rows to shift at each sequence.
        n : `int`, optional
            Number of frames to take.
        group_id : `str`, optional
            Optional group id for the data sequence. Will generate a common
            one for all the data if none is given.
        test_type : `str`, optional
            Optional string to be added to the keyword testType image header.
        reason : `str`, optional
            Reason for the data being taken. This must be a short tag-like
            string that can be used to disambiguate a set of observations.
        program : `str`, optional
            Name of the program this data belongs to, e.g. WFD, DD, etc.
        sensors : `str`
            A colon delimited list of sensor names to use for the image.
        note : `str`
            Optional observer note to be added to the image header.
        checkpoint : `coro`
            A optional awaitable callback that accepts one string argument
            that is called before each bias is taken.
        **kwargs
            Arbitrary keyword arguments.

        Returns
        -------
        `list` of `int`
            List of exposure ids.

        See Also
        --------
        take_bias: Take series of bias images.
        take_darks: Take series of darks images.
        take_flats: Take series of flats images.
        take_object: Take series of object images.
        take_engtest: Take series of engineering test images.
        take_focus: Take series of focus images.
        take_cwfs: Take series of curvature wavefront sensing images.
        take_acq: Take series of acquisition images.
        take_imgtype: Take series of images of specified imgage type.
        setup_instrument: Set up instrument.
        expose: Low level expose method.
        """

        self.assert_support_stuttered()

        self.check_kwargs(**kwargs)

        await self.setup_instrument(**kwargs)

        return await self.take_imgtype(
            imgtype="STUTTERED",
            exptime=exptime,
            n=n,
            n_snaps=1,
            n_shift=n_shift,
            row_shift=row_shift,
            group_id=group_id,
            test_type=test_type,
            reason=reason,
            program=program,
            sensors=sensors,
            note=note,
            checkpoint=checkpoint,
            **kwargs,
        )

    async def take_imgtype(
        self,
        imgtype: str,
        exptime: float,
        n: int,
        n_snaps: int = 1,
        n_shift: typing.Optional[int] = None,
        row_shift: typing.Optional[int] = None,
        group_id: typing.Optional[str] = None,
        test_type: typing.Optional[str] = None,
        reason: typing.Optional[str] = None,
        program: typing.Optional[str] = None,
        sensors: typing.Optional[str] = None,
        note: typing.Optional[str] = None,
        checkpoint: typing.Optional[typing.Callable[[str], typing.Awaitable]] = None,
        **kwargs: typing.Union[int, float, str],
    ) -> typing.List[int]:
        """Take a series of images of the specified image type.

        Parameters
        ----------
        exptime : `float`
            Exposure time for flats.
        n : `int`
            Number of frames to take.
        n_snaps : `int`
            Number of snaps to take (default=1).
        test_type : `str`
            Optional string to be added to the keyword testType image header.
        n_shift : `int`, optional
            Number of shift-expose sequences. Only used for stuttered images.
        row_shift : `int`, optional
            How many rows to shift at each sequence. Only used for stuttered
            images.
        reason : `str`, optional
            Reason for the data being taken. This must be a short tag-like
            string that can be used to disambiguate a set of observations.
        program : `str`, optional
            Name of the program this data belongs to, e.g. WFD, DD, etc.
        sensors : `str`, optional
            A colon delimited list of sensor names to use for the image.
        note : `str`, optional
            Optional observer note to be added to the image header.
        checkpoint : `coro`
            A optional awaitable callback that accepts one string argument
            that is called before each bias is taken.
        **kwargs
            Arbitrary keyword arguments.

        Returns
        -------
        `list` of `int`
            List of exposure ids.

        See Also
        --------
        take_bias: Take series of bias images.
        take_darks: Take series of darks images.
        take_flats: Take series of flats images.
        take_object: Take series of object images.
        take_engtest: Take series of engineering test images.
        take_focus: Take series of focus images.
        take_cwfs: Take series of curvature wavefront sensing images.
        take_acq: Take series of acquisition images.
        take_stuttered: Take series of stuttered images.
        setup_instrument: Set up instrument.
        expose: Low level expose method.

        Raises
        ------
        RuntimeError
            If TCS takes took long to report.
        """

        self.check_kwargs(**kwargs)

        if imgtype not in self.valid_imagetype:
            raise RuntimeError(
                f"Invalid imgtype:{imgtype}. Must be one of "
                f"{self.valid_imagetype!r}"
            )

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

        if checkpoint is not None:
            await checkpoint(f"Expose {n} {imgtype}")

        camera_exposure = CameraExposure(
            exp_time=exptime if imgtype != "BIAS" else 0.0,
            shutter=imgtype not in ["BIAS", "DARK"],
            image_type=imgtype,
            group_id=group_id,
            n=n,
            n_snaps=n_snaps,
            n_shift=n_shift,
            row_shift=row_shift,
            test_type=test_type,
            reason=reason,
            program=program,
            sensors=sensors,
            note=note,
        )

        return await self.expose(camera_exposure=camera_exposure)

    def check_kwargs(self, **kwargs: typing.Union[int, float, str, None]) -> None:
        """Utility method to verify that kwargs are in
        `self.instrument_setup_attributes`.

        Parameters
        ----------
        **kwargs
            Optional keyword,value pair.

        Raises
        ------
        RuntimeError:
            If keyword in kwargs is not in `self.instrument_setup_attributes.`
        """

        for key in kwargs:
            if key not in self.instrument_setup_attributes:
                raise RuntimeError(
                    f"Invalid argument {key}."
                    f" Must be one of {self.instrument_setup_attributes}."
                )

    @property
    @abc.abstractmethod
    def camera(self) -> salobj.Remote:
        """Camera remote."""
        raise NotImplementedError()

    @abc.abstractmethod
    async def setup_instrument(self, **kwargs: typing.Union[int, float, str]) -> None:
        """Generic method called during `take_imgtype` to setup instrument.

        Parameters
        ----------
        **kwargs
            Arbitrary keyword arguments.

        See Also
        --------
        take_bias: Take series of bias images.
        take_darks: Take series of darks images.
        take_flats: Take series of flats images.
        take_object: Take series of object images.
        take_engtest: Take series of engineering test images.
        take_focus: Take series of focus images.
        take_cwfs: Take series of curvature wavefront sensing images.
        take_acq: Take series of acquisition images.
        take_stuttered: Take series of stuttered images.
        take_imgtype: Take series of images of specified imgage type.
        expose: Low level expose method.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    async def get_available_instrument_setup(self) -> typing.Any:
        """Return available instrument setup.

        See Also
        --------
        setup_instrument: Set up instrument.
        """
        raise NotImplementedError()

    async def expose(self, camera_exposure: CameraExposure) -> typing.List[int]:
        """Encapsulates the take image command.

        This basically consists of configuring and sending a takeImages
        command to the camera and waiting for an endReadout event.

        Parameters
        ----------
        camera_exposure : CameraExposure
            Camera exposure definitions.

        Returns
        -------
        exp_ids : `list` of `int`
            List of exposure ids.

        See Also
        --------
        take_bias: Take series of bias images.
        take_darks: Take series of darks images.
        take_flats: Take series of flats images.
        take_object: Take series of object images.
        take_engtest: Take series of engineering test images.
        take_focus: Take series of focus images.
        take_cwfs: Take series of curvature wavefront sensing images.
        take_acq: Take series of acquisition images.
        take_stuttered: Take series of stuttered images.
        take_imgtype: Take series of images of specified imgage type.
        setup_instrument: Set up instrument.
        """
        exp_ids = []

        async with self.cmd_lock:

            if camera_exposure.image_type == "BIAS" and camera_exposure.exp_time > 0.0:
                self.log.warning("Image type is BIAS, ignoring exptime.")
                camera_exposure.exp_time = 0.0
            elif (
                bool(camera_exposure.shutter)
                and camera_exposure.exp_time < self.min_exptime
            ):
                raise RuntimeError(
                    f"Minimum allowed open-shutter exposure time "
                    f"is {self.min_exptime}. Got {camera_exposure.exp_time}."
                )

            exp_ids = await self.handle_take_images(camera_exposure=camera_exposure)

        return exp_ids

    async def handle_take_images(
        self, camera_exposure: CameraExposure
    ) -> typing.List[int]:
        """Handle take images command.

        Parameters
        ----------
        camera_exposure : CameraExposure
            Camera exposure definitions.

        Returns
        -------
        exp_ids : list of int
            List of exposure ids.
        """

        if camera_exposure.image_type not in self._stuttered_imgtype:
            return await self._handle_take_images(camera_exposure=camera_exposure)
        else:
            return await self._handle_take_stuttered(camera_exposure=camera_exposure)

    async def _handle_take_images(
        self, camera_exposure: CameraExposure
    ) -> typing.List[int]:
        """Handle taking series of images using the camera takeImages command.

        Parameters
        ----------
        camera_exposure : CameraExposure
            Camera exposure definitions.

        Returns
        -------
        exp_ids : list of int
            List of exposure ids.
        """
        if camera_exposure.n_snaps > self.max_n_snaps_warning:
            self.log.warning(
                f"Specified number of snaps {camera_exposure.n_snaps} larger "
                f"than maximum recommended value {self.max_n_snaps_warning}."
            )

        exp_ids = []
        for _ in range(camera_exposure.n):
            exp_ids += await self._handle_snaps(camera_exposure)

        return exp_ids

    async def _handle_snaps(self, camera_exposure: CameraExposure) -> typing.List[int]:
        """Handle taking snaps using camera takeImages command.

        Parameters
        ----------
        camera_exposure : CameraExposure
            Camera exposure definitions.

        Returns
        -------
        exp_ids : list of int
            List of exposure ids.

        Raises
        ------
        RuntimeError:
            If timeout waiting for endReadout event from the camera.
        """
        key_value_map = camera_exposure.get_key_value_map()

        self.camera.cmd_takeImages.set(
            numImages=camera_exposure.n_snaps,
            expTime=float(camera_exposure.exp_time),
            shutter=bool(camera_exposure.shutter),
            keyValueMap=key_value_map,
            sensors=self.parse_sensors(camera_exposure.sensors),
            obsNote="" if camera_exposure.note is None else camera_exposure.note,
        )

        take_images_timeout = (
            float(camera_exposure.exp_time) + self.read_out_time
        ) * camera_exposure.n + self.long_long_timeout

        self.camera.evt_endReadout.flush()
        await self.camera.cmd_takeImages.start(timeout=take_images_timeout)

        exp_ids: typing.List[int] = []

        for _ in range(camera_exposure.n_snaps):
            try:
                exp_id = await self.next_exposure_id()
            except asyncio.TimeoutError:
                raise RuntimeError(
                    "Timeout waiting for endReadout event. "
                    f"Expected {camera_exposure.n_snaps} got {len(exp_ids)}."
                )

            exp_ids.append(exp_id)

        return exp_ids

    async def _handle_take_stuttered(
        self, camera_exposure: CameraExposure
    ) -> typing.List[int]:
        """Handle taking series of images using a combination of shift/discard
        rows.

        This method makes sure that enable/disable and start/end of stuttered
        images are protected. If, for any reason, the operation is cancelled
        while executing, it will still end the exposure and disable calibration
        mode.

        Parameters
        ----------
        camera_exposure : CameraExposure
            Camera exposure definitions.

        Returns
        -------
        exp_ids : list of int
            List of exposure ids.
        """
        self.log.info("Enabling camera calibration mode.")
        await self.camera.cmd_enableCalibration.start(timeout=self.long_timeout)

        exp_ids = []

        key_value_map = camera_exposure.get_key_value_map()

        assert type(camera_exposure.n_shift) is int

        try:
            for i in range(camera_exposure.n):

                await self.camera.cmd_clear.set_start(
                    nClears=2, timeout=self.long_timeout
                )

                self.camera.evt_endReadout.flush()

                self.log.info(f"Start exposure {i+1} of {camera_exposure.n}")

                # We need to set the timeout parameter in the startImage
                # command. This only works if we call set first and then start.
                self.camera.cmd_startImage.set(
                    shutter=camera_exposure.shutter,
                    keyValueMap=key_value_map,
                    timeout=(
                        self.fast_timeout
                        + camera_exposure.exp_time * (camera_exposure.n_shift + 1)
                    ),
                )

                await self.camera.cmd_startImage.start(timeout=self.fast_timeout)

                try:
                    await self._handle_expose_shift(camera_exposure)
                finally:
                    self.log.info(f"End exposure {i+1} of {camera_exposure.n}")
                    await self.camera.cmd_endImage.start(timeout=self.long_timeout)

                exp_ids.append(await self.next_exposure_id())
        finally:
            self.log.info("Disabling camera calibration mode.")
            await self.camera.cmd_disableCalibration.start(timeout=self.long_timeout)

        return exp_ids

    async def _handle_expose_shift(self, camera_exposure: CameraExposure) -> None:
        """Handle exposing and shifting the camera register.

        Parameters
        ----------
        camera_exposure : CameraExposure
        """

        assert type(camera_exposure.n_shift) is int

        for i in range(camera_exposure.n_shift - 1):
            self.log.debug(
                f"Exposing {i+1} of {camera_exposure.n_shift} for {camera_exposure.exp_time} seconds."
            )
            await asyncio.sleep(camera_exposure.exp_time)
            self.log.debug(f"Shifting {camera_exposure.row_shift} rows.")
            await self.camera.cmd_discardRows.set_start(
                nRows=camera_exposure.row_shift, timeout=self.long_timeout
            )

        self.log.debug("Last shift-expose sequence.")
        await asyncio.sleep(camera_exposure.exp_time)

    async def next_exposure_id(self) -> int:
        """Get the exposure id from the next endReadout event.

        Await for the next `camera.evt_endReadout` event, without flushing,
        parse the `imageName` into YYYYMMDD and sequence number and construct
        an integer that represents the exposude id.

        Returns
        -------
        int
            Exposure id from next endReadout event.
        """
        end_readout = await self.camera.evt_endReadout.next(
            flush=False, timeout=self.long_long_timeout
        )
        # parse out visitID from filename
        # (Patrick comment) this is highly annoying
        _, _, yyyymmdd, seq_num = end_readout.imageName.split("_")

        return int((yyyymmdd + seq_num[1:]))

    @staticmethod
    def next_group_id() -> str:
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

    @abc.abstractmethod
    def parse_sensors(self, sensors: typing.Union[str, None]) -> str:
        """Parse input sensors.

        Parameters
        ----------
        sensors : `str` or `None`
            A colon delimited list of sensor names to use for the image.

        Returns
        -------
        sensors : `str`
            A validated set of colon delimited list of sensor names to use for
            the image.
        """
        raise NotImplementedError()

    def assert_support_stuttered(self) -> None:
        """Verify the camera support taking stuttered images.

        Raises
        ------
        AssertionError
            If stuttered image is not supported.
        """
        stuttered_commands = {
            "cmd_enableCalibration",
            "cmd_disableCalibration",
            "cmd_startImage",
            "cmd_endImage",
            "cmd_discardRows",
        }
        missing_stuttered_commands = [
            command
            for command in stuttered_commands
            if not hasattr(self.camera, command)
        ]
        assert not missing_stuttered_commands, (
            f"Missing commands: {', '.join(missing_stuttered_commands)}. "
            "Instrument does not support stuttered images. "
        )

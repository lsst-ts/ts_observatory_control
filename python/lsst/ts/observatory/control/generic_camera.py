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
# along with this program. If not, see <https://www.gnu.org/licenses/>.

__all__ = ["GenericCamera"]

import logging
import typing

from lsst.ts import salobj

from .base_camera import BaseCamera


class GenericCamera(BaseCamera):
    """Generic camera high level class.

    This class is designed to operate the generic camera CSC using the same
    `BaseCamera` interface.

    Parameters
    ----------
    index : `int`
        Generic camera index.
    domain : `salobj.Domain`
        Domain to use of the Remotes. If `None`, create a new domain.
    log : `logging.Logger`
        Optional logging class to be used for logging operations. If `None`,
        creates a new logger. Useful to use in salobj.BaseScript and allow
        logging in the class use the script logging.
    intended_usage: `int`
        Optional integer that maps to a list of intended operations. This is
        used to limit the resources allocated by the class by gathering some
        knowledge about the usage intention. By default allocates all
        resources.
    instrument_setup_attributes : `list` [`str`], optional
        Optional names of the attributes needed to setup the instrument for
        taking an exposure. This is used to check for bad input with functions
        calls.
    tcs_ready_to_take_data : `coroutine`
        A coroutine that waits for the telescope control system to be ready
        to take data.
    """

    def __init__(
        self,
        index: int,
        domain: typing.Optional[salobj.Domain] = None,
        log: typing.Optional[logging.Logger] = None,
        intended_usage: typing.Optional[int] = None,
        instrument_setup_attributes: typing.Optional[typing.List[str]] = None,
        tcs_ready_to_take_data: typing.Callable[[], typing.Awaitable] = None,
    ) -> None:

        self.index = index

        super().__init__(
            components=[f"GenericCamera:{index}"],
            instrument_setup_attributes=[]
            if instrument_setup_attributes is None
            else instrument_setup_attributes,
            domain=domain,
            log=log,
            intended_usage=intended_usage,
            tcs_ready_to_take_data=tcs_ready_to_take_data,
        )

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
        return ""

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
        pass

    async def get_available_instrument_setup(self) -> typing.Any:
        """Return available instrument setup.

        See Also
        --------
        setup_instrument: Set up instrument.
        """
        return []

    @property
    def camera(self) -> salobj.Remote:
        """Camera remote."""
        return getattr(self.rem, f"genericcamera_{self.index}")

    async def start_live_view(self, exptime: float) -> None:
        """Start live view mode on Generic Camera.

        Parameters
        ----------
        exptime : `float`
            Exposure time for the live view mode (in seconds). This also
            defines the frequency of updates.
        """

        await self.rem.genericcamera_1.cmd_startLiveView.set_start(
            expTime=exptime,
            timeout=self.fast_timeout,
        )

    async def stop_live_view(self) -> None:
        """Stop live view mode on Generic Camera."""

        await self.rem.genericcamera_1.cmd_stopLiveView.start(timeout=self.fast_timeout)

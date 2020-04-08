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

__all__ = ["ATCalSys"]

import asyncio

from ..remote_group import RemoteGroup


class ATCalSys(RemoteGroup):
    """ Implement high level ATCalSys functionality.

    Parameters
    ----------
    domain: `salobj.Domain`
        Domain to use of the Remotes. If `None`, create a new domain.
    electrometer_index : `int`
        Electrometer index.
    fiber_spectrograph_index : `int`
        FiberSpectrograph index.
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

    def __init__(
        self,
        electrometer_index=1,
        fiber_spectrograph_index=-1,
        domain=None,
        log=None,
        intended_usage=None,
    ):

        self.electrometer_index = electrometer_index
        self.fiber_spectrograph_index = fiber_spectrograph_index

        super().__init__(
            components=[
                f"Electrometer:{electrometer_index}",
                f"ATMonochromator",
                f"FiberSpectrograph:{fiber_spectrograph_index}",
            ],
            domain=domain,
            log=log,
            intended_usage=intended_usage,
        )

    async def setup_monochromator(self, wavelength, entrance_slit, exit_slit, grating):
        """Setup Monochromator.

        Parameters
        ----------
        wavelength : `float`
            Wavelength in nm.
        entrance_slit : `float`
            Size of entrance slit in mm.
        exit_slit : `float`
            Size of exist slit in mm.
        grating : `int`
            Grating to select.

        """

        await self.rem.atmonochromator.cmd_updateMonochromatorSetup.set_start(
            wavelength=wavelength,
            gratingType=grating,
            fontExitSlitWidth=exit_slit,
            fontEntranceSlitWidth=entrance_slit,
            timeout=self.long_timeout,
        )

    async def electrometer_scan(self, duration):
        """Perform an electrometer scan for the specified duration and return
        a large file object topic.

        Parameters
        ----------
        duration : `float`
            Total duration of scan.

        Returns
        -------
        lfo : ``self.electrometer.evt_largeFileObjectAvailable.DataType``
            Large File Object Available event message.

        """

        self.electrometer.evt_largeFileObjectAvailable.flush()

        await self.electrometer.cmd_startScanDt.set_start(
            scanDuration=duration, timeout=duration + self.long_timeout
        )

        lfo = await self.electrometer.evt_largeFileObjectAvailable.next(
            timeout=self.long_timeout, flush=False
        )

        return lfo

    async def take_fiber_spectrum_after(
        self, delay, image_type, integration_time, lamp, wait_for=None
    ):
        """Wait, then start an acquisition with the fiber spectrograph.

        By default, this method will wait for `delay` seconds then start
        an acquisition with the fiber spectrograph. Optionally the user may
        provide a coroutine that will be awaited before the delay starts.

        Parameters
        ----------
        delay : `float`
            Seconds to wait before starting fiber spectrograph acquisition.
        image_type : `str`
            Type of each image.
        integration_time : `float`
            Integration time for the fiber spectrum (seconds).
        lamp : `str`
            Name of lamp for each image.
        wait_for : `coro`
            An awaitable that will be waited before delay and processing. If
            None, ignored.

        Returns
        -------
        large_file_data : ``fiberspectrograph.evt_largeFileObjectAvailable.DataType``  # noqa: W505
            Large file object available event data.
        """
        if wait_for is not None:
            await wait_for
        await asyncio.sleep(delay)

        timeout = integration_time + self.long_timeout

        fs_lfo_coro = self.fiberspectrograph.evt_largeFileObjectAvailable.next(
            timeout=self.long_timeout, flush=True
        )

        self.fiberspectrograph.cmd_expose.set(
            imageType=image_type, integrationTime=integration_time, lamp=lamp,
        )

        await self.fiberspectrograph.cmd_expose.start(timeout=timeout)

        return await fs_lfo_coro

    @property
    def electrometer(self):
        return getattr(self.rem, f"electrometer_{self.electrometer_index}")

    @property
    def fiberspectrograph(self):
        return getattr(self.rem, f"fiberspectrograph{self.fiber_spectrograph_index}")

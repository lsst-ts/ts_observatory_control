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

__all__ = ["ComCamMock"]

import asyncio
import logging

import astropy

from lsst.ts import salobj
from .base_group_mock import BaseGroupMock

index_gen = salobj.index_generator()


class ComCamMock(BaseGroupMock):
    """Mock the behavior of the combined components that make up ComCam.

    This is useful for unit testing.
    """

    def __init__(self):
        self.components = ("cccamera", "ccheaderservice", "ccarchiver")

        super().__init__(["CCCamera", "CCHeaderService", "CCArchiver"])

        self.cccamera.cmd_takeImages.callback = self.cmd_take_images_callback

        self.readout_time = 2.0
        self.shutter_time = 1.0

        self.nimages = 0
        self.exptime_list = []

        self.log = logging.getLogger(__name__)

        self.end_readout_task = None

        self.camera_filter = None

        self.start_task = asyncio.gather(
            self.cccamera.start_task, self.ccheaderservice.start_task
        )

    @property
    def cccamera(self):
        return self.controllers.cccamera

    @property
    def ccheaderservice(self):
        return self.controllers.ccheaderservice

    @property
    def ccarchiver(self):
        return self.controllers.ccarchiver

    async def cmd_take_images_callback(self, data):
        """Emulate take image command."""
        one_exp_time = data.expTime + self.readout_time
        if data.shutter:
            one_exp_time += self.shutter_time
        await asyncio.sleep(one_exp_time * data.numImages)
        self.end_readout_task = asyncio.create_task(self.end_readout(data))

    async def end_readout(self, data):
        """Wait `self.readout_time` and send endReadout event."""
        self.log.debug(f"end_readout started: sleep {self.readout_time}")
        await asyncio.sleep(self.readout_time)
        self.nimages += 1
        self.exptime_list.append(data.expTime)
        date_id = astropy.time.Time.now().tai.isot.split("T")[0].replace("-", "")
        image_name = f"test_comcam_{date_id}_{next(index_gen)}"
        self.log.debug(f"sending endReadout: {image_name}")
        self.cccamera.evt_endReadout.set_put(imageName=image_name)
        self.log.debug("sending LFOA")
        self.ccheaderservice.evt_largeFileObjectAvailable.put()
        self.log.debug("end_readout done")

    async def close(self):
        if self.end_readout_task is not None:
            try:
                await asyncio.wait_for(
                    self.end_readout_task, timeout=self.readout_time * 2.0
                )
            except asyncio.TimeoutError:
                self.end_readout_task.cancel()
                try:
                    await self.end_readout_task
                except Exception:
                    pass
            except Exception:
                pass

        await super().close()

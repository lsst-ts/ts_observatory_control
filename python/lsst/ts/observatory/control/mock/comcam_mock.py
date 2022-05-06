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

__all__ = ["ComCamMock"]

import asyncio
import logging

import astropy

from lsst.ts import utils
from .base_group_mock import BaseGroupMock

index_gen = utils.index_generator()


class ComCamMock(BaseGroupMock):
    """Mock the behavior of the combined components that make up ComCam.

    This is useful for unit testing.
    """

    def __init__(self):
        self.components = ("cccamera", "ccheaderservice", "ccoods")

        super().__init__(["CCCamera", "CCHeaderService", "CCOODS"])

        self.cccamera.cmd_takeImages.callback = self.cmd_take_images_callback
        self.cccamera.cmd_setFilter.callback = self.cmd_setFilter_callback
        self.cccamera.cmd_enableCalibration.callback = (
            self.cmd_enable_calibration_callback
        )
        self.cccamera.cmd_clear.callback = self.cmd_clear_callback
        self.cccamera.cmd_startImage.callback = self.cmd_start_image_callback
        self.cccamera.cmd_endImage.callback = self.cmd_end_image_callback
        self.cccamera.cmd_disableCalibration.callback = (
            self.cmd_disable_calibration_callback
        )
        self.cccamera.cmd_discardRows.callback = self.cmd_discard_rows_callback

        self.cccamera_start_image_time = None
        self.cccamera_calibration_mode = False
        self.cccamera_image_started = False

        self.readout_time = 2.0
        self.shutter_time = 1.0
        self.short_time = 0.1

        self.nimages = 0
        self.exptime_list = []

        self.log = logging.getLogger(__name__)

        self.end_readout_coro = None
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
    def ccoods(self):
        return self.controllers.ccoods

    async def cmd_take_images_callback(self, data):
        """Emulate take image command."""

        if self.cccamera_calibration_mode:
            raise RuntimeError("Calibration mode on, cannot run take images.")

        for i in range(data.numImages):

            if self.cccamera_image_started:
                raise RuntimeError("Image started, cannot take image.")

            one_exp_time = data.expTime
            if data.shutter:
                one_exp_time += self.shutter_time
            await asyncio.sleep(one_exp_time)
            self.end_readout_task = asyncio.create_task(self.end_readout(data))
            if i < data.numImages - 1:
                await self.end_readout_task

    async def cmd_enable_calibration_callback(self, data):
        self.cccamera_calibration_mode = True
        await asyncio.sleep(self.short_time)

    async def cmd_clear_callback(self, data):
        await asyncio.sleep(self.short_time)

    async def cmd_start_image_callback(self, data):
        await asyncio.sleep(self.short_time)
        self.cccamera_image_started = True
        self.cccamera_start_image_time = utils.current_tai()
        self.end_readout_coro = self.end_readout(data)

    async def cmd_end_image_callback(self, data):
        await asyncio.sleep(self.short_time)
        self.end_readout_task = asyncio.create_task(self.end_readout_coro)

    async def cmd_disable_calibration_callback(self, data):
        self.cccamera_calibration_mode = True
        await asyncio.sleep(self.short_time)

    async def cmd_discard_rows_callback(self, data):
        await asyncio.sleep(self.short_time)

    async def end_readout(self, data):
        """Wait `self.readout_time` and send endReadout event."""
        self.log.debug(f"end_readout started: sleep {self.readout_time}")
        await asyncio.sleep(self.readout_time)

        self.cccamera_image_started = False
        self.nimages += 1
        if hasattr(data, "expTime"):
            self.exptime_list.append(data.expTime)
        elif self.cccamera_start_image_time is not None:
            self.exptime_list.append(
                utils.current_tai() - self.cccamera_start_image_time
            )

        date_id = astropy.time.Time.now().tai.isot.split("T")[0].replace("-", "")
        image_name = f"test_comcam_{date_id}_{next(index_gen)}"
        self.log.debug(f"sending endReadout: {image_name} :: {data}")

        additional_keys, additional_values = list(
            zip(
                *[
                    key_value.strip().split(":", maxsplit=1)
                    for key_value in data.keyValueMap.split(",")
                ]
            )
        )

        await self.cccamera.evt_endReadout.set_write(
            imageName=image_name,
            additionalKeys=":".join([key.strip() for key in additional_keys]),
            additionalValues=":".join([value.strip() for value in additional_values]),
        )
        self.log.debug("sending LFOA")
        await self.ccheaderservice.evt_largeFileObjectAvailable.write()
        self.log.debug("end_readout done")

    async def cmd_setFilter_callback(self, data):
        """Emulate the setFilter command."""
        self.end_set_filter_task = asyncio.create_task(self.end_set_filter(data))

    async def end_set_filter(self, data):
        """Wait for the filter to change and send endSetFilter event."""
        await asyncio.sleep(1)
        await self.cccamera.evt_endSetFilter.set_write(filterName=data.name)
        self.log.debug("sending endSetFilter")
        self.camera_filter = data.name

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

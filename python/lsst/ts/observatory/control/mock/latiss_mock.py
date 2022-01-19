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

__all__ = ["LATISSMock"]

import astropy
import asyncio
import logging

from lsst.ts import salobj

from .base_group_mock import BaseGroupMock

CLOSE_SLEEP = 5  # seconds

index_gen = salobj.index_generator()


class LATISSMock(BaseGroupMock):
    """Mock the behavior of the combined components that make out LATISS.

    This is useful for unit testing.
    """

    def __init__(self):

        self.components = ("atspec", "atcam", "atheaderservice", "atarchiver")

        super().__init__(
            ["ATSpectrograph", "ATCamera", "ATHeaderService", "ATArchiver"]
        )

        self.atcam.cmd_takeImages.callback = self.cmd_take_images_callback
        self.atspec.cmd_changeFilter.callback = self.cmd_changeFilter_callback
        self.atspec.cmd_changeDisperser.callback = self.cmd_changeDisperser_callback
        self.atspec.cmd_moveLinearStage.callback = self.cmd_moveLinearStage_callback

        self.readout_time = 1.0
        self.shutter_time = 0.5

        self.nimages = 0
        self.exptime_list = []

        self.latiss_filter = None
        self.latiss_filter_name = None
        self.latiss_grating = None
        self.latiss_grating_name = None
        self.latiss_linear_stage = None

        self.end_readout_task = None

        self.log = logging.getLogger(__name__)

    @property
    def atspec(self):
        return self.controllers.atspectrograph

    @property
    def atcam(self):
        return self.controllers.atcamera

    @property
    def atheaderservice(self):
        return self.controllers.atheaderservice

    @property
    def atarchiver(self):
        return self.controllers.atarchiver

    async def cmd_take_images_callback(self, data):
        """Emulate take image command."""
        if data.numImages == 0:
            raise RuntimeError("numImages must be larger than 0.")

        for i in range(data.numImages):
            one_exp_time = data.expTime
            if data.shutter:
                one_exp_time += self.shutter_time
            await asyncio.sleep(one_exp_time)
            self.end_readout_task = asyncio.create_task(self.end_readout(data))
            if i < data.numImages - 1:
                await self.end_readout_task

    async def end_readout(self, data):
        """Wait `self.readout_time` and send endReadout event."""
        self.log.debug(f"end_readout started: sleep {self.readout_time}")
        await asyncio.sleep(self.readout_time)
        self.nimages += 1
        self.exptime_list.append(data.expTime)
        date_id = astropy.time.Time.now().tai.isot.split("T")[0].replace("-", "")
        image_name = f"test_latiss_{date_id}_{next(index_gen)}"
        self.log.debug(f"sending endReadout: {image_name}")

        additional_keys, additional_values = list(
            zip(
                *[
                    key_value.strip().split(":", maxsplit=1)
                    for key_value in data.keyValueMap.split(",")
                ]
            )
        )

        self.atcam.evt_endReadout.set_put(
            imageName=image_name,
            additionalKeys=":".join([key.strip() for key in additional_keys]),
            additionalValues=":".join([value.strip() for value in additional_values]),
        )
        self.log.debug("sending LFOA")
        self.atheaderservice.evt_largeFileObjectAvailable.put()
        self.log.debug("end_readout done")

    async def cmd_changeFilter_callback(self, data):
        """Emulate change filter command"""
        await asyncio.sleep(0.1)
        self.atspec.evt_filterInPosition.put()
        self.atspec.evt_reportedFilterPosition.set_put(
            slot=data.filter, name=f"filter{data.filter}", band="r"
        )
        self.latiss_filter = data.filter

    async def cmd_changeDisperser_callback(self, data):
        """Emulate change filter command"""
        await asyncio.sleep(0.1)
        self.atspec.evt_disperserInPosition.put()
        self.atspec.evt_reportedDisperserPosition.put()
        self.atspec.evt_reportedDisperserPosition.set_put(
            slot=data.disperser, name=f"grating{data.disperser}", band="R100"
        )
        self.latiss_grating = data.disperser

    async def cmd_moveLinearStage_callback(self, data):
        """Emulate change filter command"""
        await asyncio.sleep(0.1)
        self.atspec.evt_linearStageInPosition.put()
        self.atspec.evt_reportedLinearStagePosition.set_put(
            position=data.distanceFromHome
        ),
        self.latiss_linear_stage = data.distanceFromHome

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

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

__all__ = ["LATISSMock"]

import astropy
import asyncio
import logging

from lsst.ts import salobj

CLOSE_SLEEP = 5  # seconds

index_gen = salobj.index_generator()


class LATISSMock:
    """Mock the behavior of the combined components that make out LATISS.

    This is useful for unit testing.
    """

    def __init__(self):

        self.components = ("atspec", "atcam", "atheaderservice", "atarchiver")

        self.atcam = salobj.Controller(name="ATCamera")
        self.atspec = salobj.Controller(name="ATSpectrograph")
        self.atheaderservice = salobj.Controller(name="ATHeaderService")
        self.atarchiver = salobj.Controller(name="ATArchiver")

        self.atcam.cmd_takeImages.callback = self.cmd_take_images_callback
        self.atspec.cmd_changeFilter.callback = self.cmd_changeFilter_callback
        self.atspec.cmd_changeDisperser.callback = self.cmd_changeDisperser_callback
        self.atspec.cmd_moveLinearStage.callback = self.cmd_moveLinearStage_callback

        self.setting_versions = {}

        self.settings_to_apply = {}

        for comp in self.components:
            getattr(self, comp).cmd_start.callback = self.get_start_callback(comp)
            getattr(self, comp).cmd_enable.callback = self.get_enable_callback(comp)
            getattr(self, comp).cmd_disable.callback = self.get_disable_callback(comp)
            getattr(self, comp).cmd_standby.callback = self.get_standby_callback(comp)

        self.readout_time = 1.0
        self.shutter_time = 0.5

        self.nimages = 0
        self.exptime_list = []

        self.latiss_filter = None
        self.latiss_grating = None
        self.latiss_linear_stage = None

        self.end_readout_task = None

        self.log = logging.getLogger(__name__)

        self.start_task = asyncio.create_task(self.start_task_publish())

    async def start_task_publish(self):

        await asyncio.gather(
            self.atspec.start_task,
            self.atcam.start_task,
            self.atheaderservice.start_task,
            self.atarchiver.start_task,
        )

        for comp in (self.atspec, self.atcam, self.atheaderservice, self.atarchiver):
            comp.evt_summaryState.set_put(summaryState=salobj.State.STANDBY)

    def get_start_callback(self, comp):
        def callback(data):

            ss = getattr(self, comp).evt_summaryState

            if ss.data.summaryState != salobj.State.STANDBY:
                raise RuntimeError(
                    f"Current state is {salobj.State(ss.data.summaryState)}."
                )

            ss.set_put(summaryState=salobj.State.DISABLED)

            self.settings_to_apply[comp] = data.settingsToApply

        return callback

    def get_enable_callback(self, comp):
        def callback(data):

            ss = getattr(self, comp).evt_summaryState

            if ss.data.summaryState != salobj.State.DISABLED:
                raise RuntimeError(
                    f"Current state is {salobj.State(ss.data.summaryState)}."
                )

            ss.set_put(summaryState=salobj.State.ENABLED)

        return callback

    def get_disable_callback(self, comp):
        def callback(data):

            ss = getattr(self, comp).evt_summaryState

            if ss.data.summaryState != salobj.State.ENABLED:
                raise RuntimeError(
                    f"Current state is {salobj.State(ss.data.summaryState)}."
                )

            ss.set_put(summaryState=salobj.State.DISABLED)

        return callback

    def get_standby_callback(self, comp):
        def callback(data):

            ss = getattr(self, comp).evt_summaryState

            if ss.data.summaryState not in (salobj.State.DISABLED, salobj.State.FAULT):
                raise RuntimeError(
                    f"[{comp}]: Current state is {salobj.State(ss.data.summaryState)!r}. "
                    f"Expected {salobj.State.DISABLED!r} or {salobj.State.FAULT!r}"
                )

            ss.set_put(summaryState=salobj.State.STANDBY)

        return callback

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
        self.atcam.evt_endReadout.set_put(imageName=image_name)
        self.log.debug(f"sending LFOA")
        self.atheaderservice.evt_largeFileObjectAvailable.put()
        self.log.debug(f"end_readout done")

    async def cmd_changeFilter_callback(self, data):
        """Emulate change filter command"""
        await asyncio.sleep(0.1)
        self.atspec.evt_filterInPosition.put()
        self.atspec.evt_reportedFilterPosition.put()
        self.latiss_filter = data.filter

    async def cmd_changeDisperser_callback(self, data):
        """Emulate change filter command"""
        await asyncio.sleep(0.1)
        self.atspec.evt_disperserInPosition.put()
        self.atspec.evt_reportedDisperserPosition.put()
        self.latiss_grating = data.disperser

    async def cmd_moveLinearStage_callback(self, data):
        """Emulate change filter command"""
        await asyncio.sleep(0.1)
        self.atspec.evt_linearStageInPosition.put()
        self.atspec.evt_reportedLinearStagePosition.put()
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

        for comp in (self.atspec, self.atcam, self.atheaderservice, self.atarchiver):
            await comp.close()

    async def __aenter__(self):
        await asyncio.gather(self.start_task)
        return self

    async def __aexit__(self, *args):
        await self.close()

        await asyncio.sleep(CLOSE_SLEEP)

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

import asyncio
import logging
import typing

import astropy
from lsst.ts import salobj, utils

from .base_group_mock import BaseGroupMock

CLOSE_SLEEP = 5  # seconds

index_gen = utils.index_generator()


class LATISSMock(BaseGroupMock):
    """Mock the behavior of the combined components that make out LATISS.

    This is useful for unit testing.
    """

    def __init__(self) -> None:
        self.components = ("atspec", "atcam", "atheaderservice", "atoods")

        super().__init__(["ATSpectrograph", "ATCamera", "ATHeaderService", "ATOODS"])

        self.atcam.cmd_takeImages.callback = self.cmd_take_images_callback
        self.atcam.cmd_enableCalibration.callback = self.cmd_enable_calibration_callback
        self.atcam.cmd_clear.callback = self.cmd_clear_callback
        self.atcam.cmd_startImage.callback = self.cmd_start_image_callback
        self.atcam.cmd_endImage.callback = self.cmd_end_image_callback
        self.atcam.cmd_disableCalibration.callback = (
            self.cmd_disable_calibration_callback
        )
        self.atcam.cmd_discardRows.callback = self.cmd_discard_rows_callback
        self.atspec.cmd_changeFilter.callback = self.cmd_changeFilter_callback
        self.atspec.cmd_changeDisperser.callback = self.cmd_changeDisperser_callback
        self.atspec.cmd_moveLinearStage.callback = self.cmd_moveLinearStage_callback

        self.atcam_start_image_time = None
        self.atcam_calibration_mode = False
        self.atcam_image_started = False

        self.readout_time = 1.0
        self.shutter_time = 0.5
        self.short_time = 0.1

        self.nimages = 0
        self.exptime_list: typing.List[float] = []

        self.latiss_filter = None
        self.latiss_filter_name = None
        self.latiss_grating = None
        self.latiss_grating_name = None
        self.latiss_linear_stage = None

        self.end_readout_coro: typing.Optional[
            typing.Coroutine[typing.Any, typing.Any, typing.Any]
        ] = None
        self.end_readout_task: typing.Optional[asyncio.Task] = None

        self.log = logging.getLogger(__name__)

    @property
    def atspec(self) -> salobj.Controller:
        return self.controllers.atspectrograph

    @property
    def atcam(self) -> salobj.Controller:
        return self.controllers.atcamera

    @property
    def atheaderservice(self) -> salobj.Controller:
        return self.controllers.atheaderservice

    @property
    def atoods(self) -> salobj.Controller:
        return self.controllers.atoods

    async def cmd_take_images_callback(
        self, data: salobj.type_hints.BaseMsgType
    ) -> None:
        """Emulate take image command."""
        if self.atcam_calibration_mode:
            raise RuntimeError("Calibration mode on, cannot run takeImages.")

        if data.numImages == 0:
            raise RuntimeError("numImages must be larger than 0.")

        for i in range(data.numImages):
            if self.atcam_image_started:
                raise RuntimeError("Image started, cannot take image.")

            self.atcam_image_started = True
            one_exp_time = data.expTime
            if data.shutter:
                one_exp_time += self.shutter_time
            await asyncio.sleep(one_exp_time)
            self.end_readout_task = asyncio.create_task(self.end_readout(data))
            if i < data.numImages - 1:
                await self.end_readout_task

    async def cmd_enable_calibration_callback(
        self, data: salobj.type_hints.BaseMsgType
    ) -> None:
        self.atcam_calibration_mode = True
        await asyncio.sleep(self.short_time)

    async def cmd_clear_callback(self, data: salobj.type_hints.BaseMsgType) -> None:
        await asyncio.sleep(self.short_time)

    async def cmd_start_image_callback(
        self, data: salobj.type_hints.BaseMsgType
    ) -> None:
        await asyncio.sleep(self.short_time)
        self.atcam_image_started = True
        self.atcam_start_image_time = utils.current_tai()
        self.end_readout_coro = self.end_readout(data)

    async def cmd_end_image_callback(self, data: salobj.type_hints.BaseMsgType) -> None:
        await asyncio.sleep(self.short_time)
        assert self.end_readout_coro is not None
        self.end_readout_task = asyncio.create_task(self.end_readout_coro)

    async def cmd_disable_calibration_callback(
        self, data: salobj.type_hints.BaseMsgType
    ) -> None:
        self.atcam_calibration_mode = True
        await asyncio.sleep(self.short_time)

    async def cmd_discard_rows_callback(
        self, data: salobj.type_hints.BaseMsgType
    ) -> None:
        await asyncio.sleep(self.short_time)

    async def end_readout(self, data: salobj.type_hints.BaseMsgType) -> None:
        """Wait `self.readout_time` and send endReadout event."""
        self.log.debug(f"end_readout started: sleep {self.readout_time}")
        await asyncio.sleep(self.readout_time)

        self.atcam_image_started = False
        self.nimages += 1
        if hasattr(data, "expTime"):
            self.exptime_list.append(data.expTime)
        else:
            self.exptime_list.append(utils.current_tai() - self.atcam_image_started)

        date_id = astropy.time.Time.now().tai.isot.split("T")[0].replace("-", "")
        image_name = f"test_latiss_{date_id}_{next(index_gen)}"
        self.log.debug(f"sending endReadout: {image_name} :: {data}")

        additional_keys, additional_values = list(
            zip(
                *[
                    key_value.strip().split(":", maxsplit=1)
                    for key_value in data.keyValueMap.split(",")
                ]
            )
        )

        await self.atcam.evt_endReadout.set_write(
            imageName=image_name,
            additionalKeys=":".join([key.strip() for key in additional_keys]),
            additionalValues=":".join([value.strip() for value in additional_values]),
        )
        self.log.debug("sending LFOA")
        await self.atheaderservice.evt_largeFileObjectAvailable.write()
        self.log.debug("end_readout done")

    async def cmd_changeFilter_callback(
        self, data: salobj.type_hints.BaseMsgType
    ) -> None:
        """Emulate change filter command"""
        await asyncio.sleep(0.1)
        await self.atspec.evt_filterInPosition.write()
        await self.atspec.evt_reportedFilterPosition.set_write(
            slot=data.filter, name=f"filter{data.filter}", band="r"
        )
        self.latiss_filter = data.filter

    async def cmd_changeDisperser_callback(
        self, data: salobj.type_hints.BaseMsgType
    ) -> None:
        """Emulate change filter command"""
        await asyncio.sleep(0.1)
        await self.atspec.evt_disperserInPosition.write()
        await self.atspec.evt_reportedDisperserPosition.write()
        await self.atspec.evt_reportedDisperserPosition.set_write(
            slot=data.disperser, name=f"grating{data.disperser}", band="R100"
        )
        self.latiss_grating = data.disperser

    async def cmd_moveLinearStage_callback(
        self, data: salobj.type_hints.BaseMsgType
    ) -> None:
        """Emulate change filter command"""
        await asyncio.sleep(0.1)
        await self.atspec.evt_linearStageInPosition.write()
        await self.atspec.evt_reportedLinearStagePosition.set_write(
            position=data.distanceFromHome
        ),
        self.latiss_linear_stage = data.distanceFromHome

    async def close(self) -> None:
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

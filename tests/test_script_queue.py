# This file is part of ts_observatory_control
#
# Developed for the Vera Rubin Observatory Telescope and Site Subsystem.
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

import typing
import yaml
import types
import asyncio
import logging
import unittest

from lsst.ts import idl
from lsst.ts import salobj

from lsst.ts.observatory.control import Usages
from lsst.ts.observatory.control.script_queue import ScriptQueue
from lsst.ts.observatory.control.mock import RemoteGroupAsyncMock

HB_TIMEOUT = 5  # Heartbeat timeout (sec)
MAKE_TIMEOUT = 60  # Timeout for make_script (sec)


class TestScriptQueue(RemoteGroupAsyncMock):
    log: logging.Logger
    script_queue: ScriptQueue
    components_metadata: typing.Dict[str, salobj.IdlMetadata]

    @classmethod
    def setUpClass(cls) -> None:
        """This classmethod is only called once, when preparing the unit
        test.
        """

        cls.log = logging.getLogger(__name__)

        cls.script_queue = ScriptQueue(
            queue_index=idl.enums.ScriptQueue.SalIndex.MAIN_TEL,
            domain="FakeDomain",
            log=cls.log,
            intended_usage=Usages.DryTest,
        )

        # Gather metadada information, needed to validate topics versions
        cls.components_metadata = cls.get_component_metadata(
            cls.script_queue.components
        )

        return super().setUpClass()

    @property
    def remote_group(self) -> ScriptQueue:
        return self.script_queue

    async def setup_types(self) -> None:

        self.available_scripts = types.SimpleNamespace(
            **self.components_metadata["ScriptQueue:1"]
            .topic_info["logevent_availableScripts"]
            .field_info
        )
        self.available_scripts.standard = (
            "std_script1,std_script2,auxtel/std_script1,maintel/std_script1,"
        )
        self.available_scripts.external = (
            "ext_script1,ext_script2,auxtel/ext_script1,maintel/ext_script1,"
        )

        self.config_schema = types.SimpleNamespace(
            **self.components_metadata["ScriptQueue:1"]
            .topic_info["logevent_configSchema"]
            .field_info
        )
        self.config_schema.configSchema = """
$schema: http://json-schema.org/draft-07/schema#
$id: https://github.com/lsst-ts/ts_standardscripts/base_slew.yaml
title: BaseTrackTarget v1
description: Configuration for BaseTrackTarget.
type: object
properties:
  ra:
    description: ICRS right ascension (hour).
    type: number
    minimum: 0
    maximum: 24
  dec:
    description: ICRS declination (deg).
    type: number
    minimum: -90
    maximum: 90
  name:
    description: Target name
    type: string
required:
    - ra
    - dec
    - name
additionalProperties: false
        """

        self.logevent_queue = types.SimpleNamespace(
            **self.components_metadata["ScriptQueue:1"]
            .topic_info["logevent_queue"]
            .field_info
        )
        self.logevent_queue.enabled = True
        self.logevent_queue.running = True

    async def setup_mocks(self) -> None:

        self.script_queue.rem.scriptqueue_1.evt_availableScripts.attach_mock(
            unittest.mock.Mock(),
            "flush",
        )
        self.script_queue.rem.scriptqueue_1.evt_configSchema.attach_mock(
            unittest.mock.Mock(),
            "flush",
        )
        self.script_queue.rem.scriptqueue_1.evt_queue.attach_mock(
            unittest.mock.Mock(),
            "flush",
        )

        self.script_queue.rem.scriptqueue_1.configure_mock(
            **{
                "evt_availableScripts.next.return_value": self.available_scripts,
                "evt_configSchema.next.return_value": self.config_schema,
                "cmd_pause.start.side_effect": self.script_queue_cmd_pause,
                "cmd_pause.set_start.side_effect": self.script_queue_cmd_pause,
                "cmd_resume.start.side_effect": self.script_queue_cmd_resume,
                "cmd_resume.set_start.side_effect": self.script_queue_cmd_resume,
                "evt_queue.next.side_effect": self.get_logevent_queue,
                "evt_queue.aget.side_effect": self.get_logevent_queue,
            }
        )

    async def test_list_standard_scripts(self) -> None:

        standard_scripts = await self.script_queue.list_standard_scripts()

        self.script_queue.rem.scriptqueue_1.evt_availableScripts.flush.assert_called_once()
        self.script_queue.rem.scriptqueue_1.evt_availableScripts.next.assert_awaited_with(
            flush=False,
            timeout=self.script_queue.fast_timeout,
        )
        self.script_queue.rem.scriptqueue_1.cmd_showAvailableScripts.start.assert_awaited_with(
            timeout=self.script_queue.fast_timeout,
        )
        assert standard_scripts == self.available_scripts.standard.split(",")

    async def test_list_external_scripts(self) -> None:

        external_scripts = await self.script_queue.list_external_scripts()

        self.script_queue.rem.scriptqueue_1.evt_availableScripts.flush.assert_called_once()
        self.script_queue.rem.scriptqueue_1.evt_availableScripts.next.assert_awaited_with(
            flush=False,
            timeout=self.script_queue.fast_timeout,
        )
        self.script_queue.rem.scriptqueue_1.cmd_showAvailableScripts.start.assert_awaited_with(
            timeout=self.script_queue.fast_timeout,
        )

        assert external_scripts == self.available_scripts.external.split(",")

    async def test_get_script_schema(self) -> None:

        schema = await self.script_queue.get_script_schema(
            is_standard=True,
            script="std_script1",
        )

        self.assert_get_script_schema_calls()
        assert schema == self.config_schema.configSchema

    async def test_validate_config_good(self) -> None:

        config = dict(ra=10, dec=-30, name="target")

        await self.script_queue.validate_config(
            is_standard=True,
            script="std_script1",
            config=config,
        )

        self.assert_get_script_schema_calls()

    async def test_validate_config_err(self) -> None:

        config = dict(ra=10, dec=-30)

        with self.assertRaisesRegex(
            RuntimeError, expected_regex="'name' is a required property"
        ):
            await self.script_queue.validate_config(
                is_standard=True,
                script="std_script1",
                config=config,
            )

        self.assert_get_script_schema_calls()

    async def test_add(self) -> None:

        is_standard = True
        script = "std_script1"
        config = dict(ra=10, dec=-30, name="target")

        await self.script_queue.add(
            is_standard=is_standard,
            script=script,
            config=config,
        )

        self.assert_add(
            is_standard=is_standard,
            script=script,
            config=config,
        )

    async def test_add_standard(self) -> None:

        script = "std_script1"
        config = dict(ra=10, dec=-30, name="target")

        await self.script_queue.add_standard(
            script=script,
            config=config,
        )

        self.assert_add(
            is_standard=True,
            script=script,
            config=config,
        )

    async def test_add_external(self) -> None:

        script = "ext_script1"
        config = dict(ra=10, dec=-30, name="target")

        await self.script_queue.add_external(
            script=script,
            config=config,
        )

        self.assert_add(
            is_standard=False,
            script=script,
            config=config,
        )

    async def test_get_queue(self) -> None:

        queue = await self.script_queue.get_queue()

        assert queue == self.logevent_queue
        self.script_queue.rem.scriptqueue_1.evt_queue.aget.assert_awaited_with(
            timeout=self.script_queue.fast_timeout
        )

    async def test_wait_queue_paused_when_queue_paused(self) -> None:

        self.logevent_queue.running = False

        await self.script_queue.wait_queue_paused()

        self.script_queue.rem.scriptqueue_1.evt_queue.flush.assert_called()
        self.script_queue.rem.scriptqueue_1.evt_queue.aget.assert_awaited_with(
            timeout=self.script_queue.fast_timeout
        )
        self.script_queue.rem.scriptqueue_1.evt_queue.next.assert_not_awaited()

    async def test_wait_queue_paused_when_queue_running(self) -> None:

        self.logevent_queue.running = True

        self.script_queue.long_timeout = 5.0

        with self.assertRaisesRegex(
            RuntimeError,
            expected_regex=f"No queue event received in the last {self.script_queue.long_timeout}s.",
        ):
            await self.script_queue.wait_queue_paused()

        self.script_queue.rem.scriptqueue_1.evt_queue.aget.assert_awaited_with(
            timeout=self.script_queue.fast_timeout
        )
        self.script_queue.rem.scriptqueue_1.evt_queue.flush.assert_called()
        self.script_queue.rem.scriptqueue_1.evt_queue.next.assert_awaited_with(
            flush=False,
            timeout=self.script_queue.long_timeout,
        )

    async def test_wait_queue_running_when_queue_paused(self) -> None:

        self.logevent_queue.running = False

        self.script_queue.long_timeout = 5.0

        with self.assertRaisesRegex(
            RuntimeError,
            expected_regex=f"No queue event received in the last {self.script_queue.long_timeout}s.",
        ):
            await self.script_queue.wait_queue_running()

        self.script_queue.rem.scriptqueue_1.evt_queue.aget.assert_awaited_with(
            timeout=self.script_queue.fast_timeout
        )
        self.script_queue.rem.scriptqueue_1.evt_queue.flush.assert_called()
        self.script_queue.rem.scriptqueue_1.evt_queue.next.assert_awaited_with(
            flush=False,
            timeout=self.script_queue.long_timeout,
        )

    async def test_wait_queue_running_when_queue_running(self) -> None:

        self.logevent_queue.running = True

        await self.script_queue.wait_queue_running()

        self.script_queue.rem.scriptqueue_1.evt_queue.flush.assert_called()
        self.script_queue.rem.scriptqueue_1.evt_queue.aget.assert_awaited_with(
            timeout=self.script_queue.fast_timeout
        )
        self.script_queue.rem.scriptqueue_1.evt_queue.next.assert_not_awaited()

    async def test_pause_when_running(self) -> None:

        self.logevent_queue.running = True

        await self.script_queue.pause()

        self.script_queue.rem.scriptqueue_1.evt_queue.aget.assert_awaited_with(
            timeout=self.script_queue.fast_timeout
        )
        self.script_queue.rem.scriptqueue_1.evt_queue.flush.assert_called()
        self.script_queue.rem.scriptqueue_1.cmd_pause.start.assert_awaited_with(
            timeout=self.script_queue.fast_timeout
        )
        self.script_queue.rem.scriptqueue_1.evt_queue.next.assert_awaited_with(
            flush=False, timeout=self.script_queue.long_timeout
        )

    async def test_pause_when_paused(self) -> None:

        self.logevent_queue.running = False

        await self.script_queue.pause()

        self.script_queue.rem.scriptqueue_1.evt_queue.aget.assert_awaited_with(
            timeout=self.script_queue.fast_timeout
        )
        self.script_queue.rem.scriptqueue_1.evt_queue.flush.assert_not_called()
        self.script_queue.rem.scriptqueue_1.cmd_pause.start.assert_not_awaited()
        self.script_queue.rem.scriptqueue_1.evt_queue.next.assert_not_awaited()

    async def test_resume_when_running(self) -> None:

        self.logevent_queue.running = True

        await self.script_queue.resume()

        self.script_queue.rem.scriptqueue_1.evt_queue.aget.assert_awaited_with(
            timeout=self.script_queue.fast_timeout
        )
        self.script_queue.rem.scriptqueue_1.evt_queue.flush.assert_not_called()
        self.script_queue.rem.scriptqueue_1.cmd_resume.start.assert_not_awaited()
        self.script_queue.rem.scriptqueue_1.evt_queue.next.assert_not_awaited()

    async def test_resume_when_paused(self) -> None:

        self.logevent_queue.running = False

        await self.script_queue.resume()

        self.script_queue.rem.scriptqueue_1.evt_queue.aget.assert_awaited_with(
            timeout=self.script_queue.fast_timeout
        )
        self.script_queue.rem.scriptqueue_1.evt_queue.flush.assert_called()

        self.script_queue.rem.scriptqueue_1.cmd_resume.start.assert_awaited_with(
            timeout=self.script_queue.fast_timeout
        )
        self.script_queue.rem.scriptqueue_1.evt_queue.next.assert_awaited_with(
            flush=False, timeout=self.script_queue.long_timeout
        )

        assert self.logevent_queue.running

    def assert_get_script_schema_calls(self) -> None:

        self.script_queue.rem.scriptqueue_1.evt_configSchema.flush.assert_called_once()
        self.script_queue.rem.scriptqueue_1.cmd_showSchema.set_start.assert_awaited_with(
            isStandard=True,
            path="std_script1",
            timeout=self.script_queue.fast_timeout,
        )
        self.script_queue.rem.scriptqueue_1.evt_configSchema.next.assert_awaited_with(
            flush=False,
            timeout=self.script_queue.long_timeout,
        )

    def assert_add(
        self,
        is_standard: bool,
        script: str,
        config: typing.Dict[str, typing.Any],
        description: str = "",
        log_level: int = logging.DEBUG,
        pause_checkpoint: str = "",
    ) -> None:

        self.script_queue.rem.scriptqueue_1.cmd_add.set_start.assert_awaited_with(
            isStandard=is_standard,
            path=script,
            config=yaml.safe_dump(config),
            descr=description,
            location=idl.enums.ScriptQueue.Location.LAST,
            logLevel=log_level,
            pauseCheckpoint=pause_checkpoint,
            timeout=self.script_queue.long_timeout,
        )

    async def script_queue_cmd_pause(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> None:
        asyncio.create_task(self._set_queue_state(False))

    async def script_queue_cmd_resume(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> None:
        asyncio.create_task(self._set_queue_state(True))

    async def get_logevent_queue(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> types.SimpleNamespace:
        await asyncio.sleep(1.0)
        return self.logevent_queue

    async def _set_queue_state(self, state: bool) -> None:
        await asyncio.sleep(2.0)
        self.logevent_queue.running = state

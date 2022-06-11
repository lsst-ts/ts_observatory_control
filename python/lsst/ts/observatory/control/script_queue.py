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

__all__ = ["ScriptQueue"]

import asyncio
import logging
import typing
import jsonschema

from lsst.ts import idl
from lsst.ts import salobj
import yaml
from .remote_group import RemoteGroup


class ScriptQueue(RemoteGroup):
    """High level class to operate the ScriptQueue.

    Parameters
    ----------
    queue_index : `idl.enums.ScriptQueue.SalIndex`
        Script queue index enumeration.
    domain : `salobj.Domain`
        Domain for remotes. If `None`, creates a domain.
    log : `logging.Logger`
        Optional logging class to be used for logging operations. If `None`,
        creates a new logger.
    intended_usage : `int`
        Optional bitmask that maps to a list of intended operations. This is
        used to limit the resources allocated by the class by gathering some
        knowledge about the usage intention. By default allocates all
        resources.
    """

    def __init__(
        self,
        queue_index: idl.enums.ScriptQueue.SalIndex,
        domain: typing.Optional[typing.Union[salobj.Domain, str]] = None,
        log: logging.Logger = None,
        intended_usage: int = None,
    ) -> None:

        self.queue_index = queue_index

        super().__init__(
            components=[f"ScriptQueue:{queue_index}"],
            domain=domain,
            log=log,
            intended_usage=intended_usage,
        )

    @property
    def queue_remote(self) -> salobj.Remote:
        return getattr(self.rem, f"scriptqueue_{self.queue_index}")

    async def add_standard(
        self,
        script: str,
        config: dict,
        description: str = "",
        log_level: int = logging.DEBUG,
        pause_checkpoint: str = "",
    ) -> None:
        """Add standard script to the script queue.

        Parameters
        ----------
        script : `str`
            Script path.
        config : `dict`
            Script configuration.
        description : `str`, optional
            Short description of why you are running the script
            (default: empty).
        log_level : `int`, optional
            Script log level (default: DEBUG).
        pause_checkpoint : `str`, optional
            Pause the script at the specified checkpoint (default: empty).
        """
        await self.add(
            is_standard=True,
            script=script,
            config=config,
            description=description,
            log_level=log_level,
            pause_checkpoint=pause_checkpoint,
        )

    async def add_external(
        self,
        script: str,
        config: dict,
        description: str = "",
        log_level: int = logging.DEBUG,
        pause_checkpoint: str = "",
    ) -> None:
        """Add external script to the script queue.

        Parameters
        ----------
        script : `str`
            Script path.
        config : `dict`
            Script configuration.
        description : `str`, optional
            Short description of why you are running the script
            (default: empty).
        log_level : `int`, optional
            Script log level (default: DEBUG).
        pause_checkpoint : `str`, optional
            Pause the script at the specified checkpoint (default: empty).
        """
        await self.add(
            is_standard=False,
            script=script,
            config=config,
            description=description,
            log_level=log_level,
            pause_checkpoint=pause_checkpoint,
        )

    async def add(
        self,
        is_standard: bool,
        script: str,
        config: dict,
        description: str = "",
        log_level: int = logging.DEBUG,
        pause_checkpoint: str = "",
    ) -> None:
        """Add script to the script queue.

        Parameters
        ----------
        is_standard : `bool`
            Is script standard?
        script : `str`
            Script path.
        config : `dict`
            Script configuration.
        description : `str`, optional
            Short description of why you are running the script
            (default: empty).
        log_level : `int`, optional
            Script log level (default: DEBUG).
        pause_checkpoint : `str`, optional
            Pause the script at the specified checkpoint (default: empty).
        """
        await self.queue_remote.cmd_add.set_start(
            isStandard=is_standard,
            path=script,
            config=yaml.safe_dump(config),
            descr=description,
            location=idl.enums.ScriptQueue.Location.LAST,
            logLevel=log_level,
            pauseCheckpoint=pause_checkpoint,
            timeout=self.long_timeout,
        )

    async def pause(self) -> None:
        """Pause script queue."""

        queue = await self.get_queue()

        if queue.running:
            self.queue_remote.evt_queue.flush()
            await self.queue_remote.cmd_pause.start(timeout=self.fast_timeout)
            await self.wait_queue_paused()
        else:
            self.log.info("Queue already paused.")

    async def resume(self) -> None:
        """Resume script queue."""

        queue = await self.get_queue()

        if not queue.running:
            self.queue_remote.evt_queue.flush()
            await self.queue_remote.cmd_resume.start(timeout=self.fast_timeout)
            await self.wait_queue_running()
        else:
            self.log.info("Queue already running.")

    async def get_queue(self) -> salobj.type_hints.BaseMsgType:
        """Get the last sample of evt_queue.

        Returns
        -------
        queue : `ScriptQueue.evt_queue.DataType`
            Last queue event sample.

        Raises
        ------
        RuntimeError:
            If no sample is received in `fast_timeout` seconds.
        """

        try:
            queue = await self.queue_remote.evt_queue.aget(timeout=self.fast_timeout)
        except asyncio.TimeoutError:
            raise RuntimeError(
                f"No queue event received in the last {self.fast_timeout}s."
            )

        return queue

    async def wait_queue_paused(self) -> None:
        """Wait until queue is paused.

        Raises
        ------
        RuntimeError
            If queue does not report as paused.
        """
        try:
            await asyncio.wait_for(
                self._handle_wait_queue_state(running=False),
                timeout=self.long_timeout,
            )
        except asyncio.TimeoutError:
            raise RuntimeError(
                f"No queue event received in the last {self.long_timeout}s."
            )

    async def wait_queue_running(self) -> None:
        """Wait until queue is running.

        Raises
        ------
        RuntimeError
            If queue does not report as running.
        """
        try:
            await asyncio.wait_for(
                self._handle_wait_queue_state(running=True),
                timeout=self.long_timeout,
            )
        except asyncio.TimeoutError:
            raise RuntimeError(
                f"No queue event received in the last {self.long_timeout}s."
            )

    async def _handle_wait_queue_state(self, running: bool) -> None:
        """Handle waiting for the queue to report as paused.

        Parameters
        ----------
        running : `bool`
            The expected state of the queue.
        """

        self.queue_remote.evt_queue.flush()

        queue = await self.get_queue()

        self.log.debug(f"Queue running? {queue.running}, expected {running}.")

        while queue.running != running:
            queue = await self.queue_remote.evt_queue.next(
                flush=False, timeout=self.long_timeout
            )
            self.log.debug(f"Queue running? {queue.running}, expected {running}.")

    async def validate_config(
        self, is_standard: bool, script: str, config: typing.Dict[str, typing.Any]
    ) -> None:
        """Validade script configuration.

        Parameters
        ----------
        is_standard : `bool`
            Is the script standard script?
        script : `str`
            Path of the script.
        config : `dict`
            Configuration to validate.

        Raises
        ------
        RuntimeError:
            If configuration fails validation.
        """
        script_schema = await self.get_script_schema(
            is_standard=is_standard,
            script=script,
        )

        config_validator = salobj.DefaultingValidator(
            schema=yaml.safe_load(script_schema)
        )

        validation_error_message = None

        try:
            config_validator.validate(config)
        except jsonschema.ValidationError as validation_error:
            validation_error_message = validation_error.message

        if validation_error_message is not None:
            raise RuntimeError(validation_error_message)
        else:
            self.log.info("Configuration OK!")

    async def get_script_schema(self, is_standard: bool, script: str) -> str:
        """Get script schema.

        Parameters
        ----------
        is_standard : `bool`
            Is the script standard script?
        script : `str`
            Path of the script.

        Returns
        -------
        `str`
            Script schema.
        """

        self.queue_remote.evt_configSchema.flush()

        await self.queue_remote.cmd_showSchema.set_start(
            isStandard=is_standard,
            path=script,
            timeout=self.fast_timeout,
        )

        script_schema = await self.queue_remote.evt_configSchema.next(
            flush=False, timeout=self.long_timeout
        )

        return script_schema.configSchema

    async def list_standard_scripts(self) -> typing.List[str]:
        """List standard scripts.

        Returns
        -------
        `list` of `str`
            List of standard script names.
        """

        available_scripts = await self._get_available_scripts()

        return available_scripts.standard.split(",")

    async def list_external_scripts(self) -> typing.List[str]:
        """List external scripts.

        Returns
        -------
        `list` of `str`
            List of external script names.
        """

        available_scripts = await self._get_available_scripts()

        return available_scripts.external.split(",")

    async def _get_available_scripts(self) -> salobj.type_hints.BaseMsgType:
        """Get available scripts from the script queue.

        Returns
        -------
        `ScriptQueue.evt_availableScripts.DataType`
            evt_availableScripts sample.
        """
        self.queue_remote.evt_availableScripts.flush()
        await self.queue_remote.cmd_showAvailableScripts.start(
            timeout=self.fast_timeout
        )
        return await self.queue_remote.evt_availableScripts.next(
            flush=False, timeout=self.fast_timeout
        )

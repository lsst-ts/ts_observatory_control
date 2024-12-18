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

__all__ = ["ATCS", "ATCSUsages"]

import asyncio
import copy
import enum
import logging
import typing

import astropy.units as u
import numpy as np
from astropy.coordinates import Angle
from lsst.ts import salobj, utils
from lsst.ts.idl.enums import ATMCS, ATDome, ATPneumatics, ATPtg
from lsst.ts.utils import angle_diff

from ..base_tcs import BaseTCS
from ..constants import atcs_constants
from ..remote_group import Usages, UsagesResources
from ..utils import InstrumentFocus


class ATCSUsages(Usages):
    """ATCS usages definition.

    Notes
    -----

    Additional usages definition:

    * Slew: Enable all slew operations.
    * StartUp: Enable startup operations.
    * Shutdown: Enable shutdown operations.
    * PrepareForFlatfield: Enable preparation for flat-field.
    * OffsettingForATAOS: Enable offsetting from ATAOS
    * DryTest: Disable all CSCs. Mostly used for unit testing.
    """

    Slew = 1 << 3
    StartUp = 1 << 4
    Shutdown = 1 << 5
    PrepareForFlatfield = 1 << 6
    OffsettingForATAOS = 1 << 7
    DryTest = 1 << 8

    def __iter__(self) -> typing.Iterator[int]:
        return iter(
            [
                self.All,
                self.StateTransition,
                self.MonitorState,
                self.MonitorHeartBeat,
                self.Slew,
                self.StartUp,
                self.Shutdown,
                self.PrepareForFlatfield,
                self.OffsettingForATAOS,
                self.DryTest,
            ]
        )


class ATCS(BaseTCS):
    """High level library for the Auxiliary Telescope Control System

    This is the high level interface for interacting with the CSCs that
    control the Auxiliary Telescope. Essentially this will allow the user to
    slew and track the telescope.

    Parameters
    ----------
    domain: `salobj.Domain`
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

    Attributes
    ----------
    atmcs: salobj.Remote
    ataos: salobj.Remote
    atpneumatics: salobj.Remote
    athexapod: salobj.Remote
    atdome: salobj.Remote
    atdometrajectory: salobj.Remote
    check: SimpleNamespace
    log: logging.Logger
    """

    def __init__(
        self,
        domain: typing.Optional[salobj.Domain] = None,
        log: typing.Optional[logging.Logger] = None,
        intended_usage: typing.Optional[int] = None,
    ) -> None:
        super().__init__(
            components=[
                "ATMCS",
                "ATPtg",
                "ATAOS",
                "ATPneumatics",
                "ATHexapod",
                "ATDome",
                "ATDomeTrajectory",
            ],
            domain=domain,
            log=log,
            intended_usage=intended_usage,
        )

        self.instrument_focus = InstrumentFocus.Nasmyth

        # FIXME: (DM-26454) Once this is published by the telescope components
        # it should read this from events.
        self.rotator_limits = [-270.0, +270.0]

        self.open_dome_shutter_time = 600.0
        self.open_dropout_door_time = 300.0

        self.tel_park_el = 80.0
        self.tel_park_az = 0.0
        self.tel_park_rot = 0.0
        self.tel_flat_el = 39.0
        self.tel_flat_az = 188.7
        self.tel_flat_rot = 0.0
        self.tel_vent_el = 17.0
        self.tel_vent_az = 90.0
        self.tel_el_operate_pneumatics = 70.0

        self.tel_az_slew_tolerance = Angle(0.004 * u.deg)
        self.tel_el_slew_tolerance = Angle(0.004 * u.deg)
        self.tel_nasm_slew_tolerance = Angle(0.004 * u.deg)

        self.dome_open_az = 90.0
        self.dome_park_az = 285.0
        self.dome_flat_az = 3.0
        self.dome_vent_open_shutter_time = 30.0

        self.dome_slew_tolerance = Angle(5.1 * u.deg)

        self._dome_slew_max_iter = 4

        if hasattr(self.rem.atmcs, "tel_mount_AzEl_Encoders"):
            self.rem.atmcs.tel_mount_AzEl_Encoders.callback = (
                self.mount_AzEl_Encoders_callback
            )

        if hasattr(self.rem.atmcs, "evt_target"):
            self.rem.atmcs.evt_target.callback = self.atmcs_target_callback

        self._tel_position = None
        self._tel_position_updated: typing.Union[None, asyncio.Event] = None

        self._tel_target = None
        self._tel_target_updated: typing.Union[None, asyncio.Event] = None

        self.dome_az_in_position: typing.Union[None, asyncio.Event] = None

        self._monitor_position = True

        self._overslew_az = True

        try:
            self._create_asyncio_events()
        except RuntimeError:
            self.log.error(
                """Could not create asyncio events. Event loop is probably not running and cannot
                create one. Class may not work. If this is a unit test call `_create_asyncio_events`
                once an event loop is established.
                """
            )

    def _create_asyncio_events(self) -> None:
        """Create asyncio event loop for internal data."""
        self._tel_position_updated = asyncio.Event()
        self._tel_target_updated = asyncio.Event()
        self.dome_az_in_position = asyncio.Event()
        self.dome_az_in_position.set()

    def stop_monitor(self) -> None:
        """Stop any monitor position."""
        self.log.debug("Stopping monitor.")
        self._monitor_position = False

    def enable_monitor(self) -> None:
        """Enable monitor."""
        if not self._monitor_position:
            self.log.debug("Enabling monitor.")
            self._monitor_position = True
        else:
            self.log.debug("Monitor already enabled.")

    def is_monitor_enabled(self) -> bool:
        """Is monitor position flag enabled?"""
        return self._monitor_position

    async def is_dome_homed(self) -> bool:
        """Verify if the dome is homed.

        Returns
        -------
        dome_homed : `bool`
            `True` if dome is homed, `False` otherwise.
        """

        azimuth_state = await self.rem.atdome.evt_azimuthState.aget(
            timeout=self.fast_timeout
        )

        return azimuth_state.homed

    async def mount_AzEl_Encoders_callback(
        self, data: salobj.type_hints.BaseDdsDataType
    ) -> None:
        """Callback function to update the telescope position telemetry
        topic.
        """
        assert self._tel_position_updated is not None
        self._tel_position = data
        self._tel_position_updated.set()

    async def atmcs_target_callback(
        self, data: salobj.type_hints.BaseDdsDataType
    ) -> None:
        """Callback function to update the telescope target event topic."""
        assert self._tel_target_updated is not None
        self._tel_target = data
        self._tel_target_updated.set()

    async def next_telescope_position(
        self, timeout: typing.Optional[float] = None
    ) -> salobj.type_hints.BaseDdsDataType:
        """Wait for next telescope position to become available and return
        data.

        Parameters
        ----------
        timeout: `float`
            How long to wait for target to arrive (in seconds). Default is
            `None`, which means, wait for ever.

        Returns
        -------
        data: `ATMCS_tel_mount_AzEl_Encoders`

        Raises
        ------
        asyncio.TimeoutError
            If no new data is seen in less then `timeout` seconds.
        """
        assert self._tel_position_updated is not None

        self._tel_position_updated.clear()
        await asyncio.wait_for(self._tel_position_updated.wait(), timeout=timeout)
        return self._tel_position

    async def next_telescope_target(
        self, timeout: typing.Optional[float] = None
    ) -> salobj.type_hints.BaseDdsDataType:
        """Wait for next telescope position to become available and return
        data.

        Parameters
        ----------
        timeout: `float`
            How long to wait for target to arrive (in seconds). Default is
            `None`, which means, wait for ever.

        Returns
        -------
        data: `ATMCS_tel_mount_AzEl_Encoders`

        Raises
        ------
        asyncio.TimeoutError
            If no new data is seen in less then `timeout` seconds.
        """
        assert self._tel_target_updated is not None

        self._tel_target_updated.clear()
        await asyncio.wait_for(self._tel_target_updated.wait(), timeout=timeout)
        return self._tel_target

    @property
    def telescope_position(self) -> salobj.type_hints.BaseDdsDataType:
        return self._tel_position

    @property
    def telescope_target(self) -> salobj.type_hints.BaseDdsDataType:
        return self._tel_target

    async def slew_dome_to(self, az: float, check: typing.Any = None) -> None:
        """Utility method to slew dome to a specified position.

        This method works at cross purposes to ATDomeTrajectory, so this method
        disables ATDomeTrajectory and leaves it disabled. If ATDomeTrajectory
        is enabled while the dome is slewing to the requested position this
        method raises an exception.

        The method will return once the dome arrives in position, at which
        point all checks will be canceled before returning.

        Parameters
        ----------
        az : `float` or `str`
            Azimuth angle for the dome (in deg).
        check : `types.SimpleNamespace` or `None`
            Override `self.check` for defining which resources are used.

        Raises
        ------
        RuntimeError:
            If ATDome is ENABLED while slewing the dome.
        """

        # Creates a copy of check so it can modify it freely to control what
        # needs to be verified at each stage of the process.
        _check = copy.copy(self.check) if check is None else copy.copy(check)

        if not _check.atdome:
            raise RuntimeError(
                "ATDome is deactivated. Activate it by setting `check.atdome=True` before slewing."
                "In some cases users deactivate a component on purpose."
                "Make sure it is clear to operate the dome before doing so."
            )

        await self.disable_dome_following(_check)

        self.rem.atdome.evt_azimuthInPosition.flush()

        target_az = Angle(az, unit=u.deg).deg
        await self.rem.atdome.cmd_moveAzimuth.set_start(
            azimuth=target_az, timeout=self.long_long_timeout
        )

        # This is operating in a copy of the SimpleNamespace, so it is ok to
        # edit here and let it as is.
        _check.atmcs = False

        monitor_position_task = asyncio.create_task(self.monitor_position(check=_check))

        try:
            for i in range(self._dome_slew_max_iter):
                self.log.debug(
                    f"[{i+1/self._dome_slew_max_iter}] Slewing dome to {az}..."
                )

                await self._handle_in_position(
                    in_position_event=self.rem.atdome.evt_azimuthInPosition,
                    timeout=self.long_long_timeout,
                    settle_time=self.tel_settle_time,
                    component_name="ATDome",
                )
                dome_azimuth_in_position = (
                    await self.rem.atdome.evt_azimuthInPosition.aget(
                        timeout=self.fast_timeout
                    )
                )

                if dome_azimuth_in_position.inPosition:
                    self.log.debug("Dome in position.")
                    break
                else:
                    self.log.debug(
                        "Dome not in position, probably overshoot. Repositioning..."
                    )
                    await self.rem.atdome.cmd_moveAzimuth.set_start(
                        azimuth=target_az, timeout=self.long_long_timeout
                    )
        finally:
            self.stop_monitor()

            await monitor_position_task

    async def prepare_for_flatfield(self, check: typing.Any = None) -> None:
        """A high level method to position the telescope and dome for flat
        field operations.

        The method will,

            1 - disable ATDomeTrajectory
            2 - close the dome shutter (if open)
            3 - send telescope to flat field position
            4 - send dome to flat field position
            5 - re-enable ATDomeTrajectory

        Parameters
        ----------
        check : `types.SimpleNamespace` or `None`
            Override `self.check` for defining which resources are used.
        """

        await self.assert_all_enabled(
            message="All components need to be enabled to prepare for flat field."
        )

        # Creates a copy of check so it can modify it freely to control what
        # needs to be verified at each stage of the process.
        check_bckup = copy.copy(self.check) if check is None else copy.copy(check)
        check_ops = copy.copy(self.check) if check is None else copy.copy(check)

        await self.disable_dome_following(check_ops)

        await self.home_dome()
        await self.close_dome()

        await self.disable_ataos_corrections()
        await self.open_m1_cover()
        await self.enable_ataos_corrections()

        check_ops.atdometrajectory = False

        try:
            await self.point_azel(
                target_name="FlatField position",
                az=self.tel_flat_az,
                el=self.tel_flat_el,
                rot_tel=self.tel_flat_rot,
                wait_dome=False,
            )

            try:
                await self.stop_tracking()
            except asyncio.TimeoutError:
                self.log.debug("Timeout in stopping tracking. Continuing.")

            await self.slew_dome_to(self.dome_flat_az, check_ops)
        finally:
            # recover check
            self.check = copy.copy(check_bckup)
            await salobj.set_summary_state(
                self.rem.atdometrajectory, salobj.State.ENABLED
            )

    async def stop_tracking(self) -> None:
        """Task to stop telescope tracking."""

        self.log.debug("Stop tracking.")

        await self.rem.atptg.cmd_stopTracking.start(timeout=self.fast_timeout)

        try:
            self.rem.atmcs.evt_atMountState.flush()
            at_mount_state = await self.rem.atmcs.evt_atMountState.aget(
                timeout=self.long_timeout
            )
        except asyncio.TimeoutError:
            # TODO: DM-24529 Remove this when ATMCS sends events more reliably
            self.log.warning("Timeout waiting for atMountState event.")
        else:
            # TODO: DM-24525 remove hard coded 8 when real ATMCS is fixed.
            while at_mount_state.state not in (8, ATMCS.AtMountState.TRACKINGDISABLED):
                try:
                    self.log.debug(
                        f"Tracking state: {ATMCS.AtMountState(at_mount_state.state)!r}"
                    )
                except ValueError:
                    self.log.warning(f"Unknown tracking state: {at_mount_state.state}")
                at_mount_state = await self.rem.atmcs.evt_atMountState.next(
                    flush=False, timeout=self.long_timeout
                )

        try:
            self.rem.atmcs.evt_allAxesInPosition.flush()
            in_position = await self.rem.atmcs.evt_allAxesInPosition.aget(
                timeout=self.fast_timeout
            )
        except asyncio.TimeoutError:
            # TODO: DM-24529 Remove this when ATMCS sends events more reliably
            self.log.warning("Timeout waiting for allAxesInPosition event.")
        else:
            while in_position.inPosition:
                self.log.debug(f"In Position: {in_position.inPosition}.")
                in_position = await self.rem.atmcs.evt_allAxesInPosition.next(
                    flush=False, timeout=self.long_timeout
                )

    async def stop_all(self) -> None:
        """Stop telescope and dome."""

        stop_tasks = [
            self.rem.atdometrajectory.cmd_disable.start(timeout=self.fast_timeout),
            self.rem.atptg.cmd_stopTracking.start(timeout=self.fast_timeout),
            self.rem.atdome.cmd_stopMotion.start(timeout=self.fast_timeout),
            self.rem.atmcs.cmd_stopTracking.start(timeout=self.fast_timeout),
        ]

        await asyncio.gather(*stop_tasks, return_exceptions=True)

    async def stop_dome(self) -> None:
        """Stop all dome motion."""

        await self.rem.atdome.cmd_stopMotion.start(timeout=self.fast_timeout)

    async def prepare_for_vent(self, partially_open_dome: bool = False) -> None:
        """Prepare Auxiliary Telescope for venting.

        Parameters
        ----------
        partially_open_dome: `bool`
            Partially open the dome after positioning the telescope and dome?
        """

        await self.assert_all_enabled(
            message="All components need to be enabled to prepare for venting."
        )

        await self.disable_dome_following()

        await self.home_dome()

        await self.disable_ataos_corrections()

        await self.close_m1_cover()

        await self.close_dome()

        await self.enable_ataos_corrections()

        tel_vent_azimuth, dome_vent_azimuth = self.get_telescope_and_dome_vent_azimuth()

        self.log.info(
            f"Dome vent azimuth: {dome_vent_azimuth}. Telescope will be at: {tel_vent_azimuth}."
        )
        await self.point_azel(
            target_name="Vent Position",
            az=tel_vent_azimuth,
            el=self.tel_vent_el,
            rot_tel=self.tel_park_rot,
            wait_dome=False,
        )
        await self.stop_tracking()
        await self.disable_ataos_corrections()

        await self.slew_dome_to(dome_vent_azimuth)

        if partially_open_dome:
            open_dome_tasks = asyncio.create_task(self.open_dome_shutter())

            self.log.info(
                f"Waiting {self.dome_vent_open_shutter_time}s for the dome to open."
            )

            await asyncio.sleep(self.dome_vent_open_shutter_time)

            await self.stop_dome()

            await self.cancel_not_done([open_dome_tasks])
        else:
            self.log.info("Fully opening the dome to vent.")

            await self.open_dome_shutter()

    async def prepare_for_onsky(
        self, overrides: typing.Optional[typing.Dict[str, str]] = None
    ) -> None:
        """Prepare Auxiliary Telescope for on-sky operations.

        This method will perform the start of the night procedure for the
        ATCS component. It will enable all components, open the dome slit,
        open the telescope covers and activate AOS open loop corrections.

        Parameters
        ----------
        overrides: `dict`
            Dictionary with overrides to apply.  If `None` use the recommended
            overrides.
        """

        await self.assert_all_enabled(
            message="All components need to be enabled to prepare for sky observations."
        )

        await self.disable_dome_following()

        self.log.debug("Slew telescope to open position.")

        await self.point_azel(
            target_name="Park position",
            az=self.dome_open_az,
            el=self.tel_park_el,
            rot_tel=self.tel_park_rot,
            wait_dome=False,
        )
        try:
            await self.stop_tracking()
        except asyncio.TimeoutError:
            pass

        await self.disable_ataos_corrections()

        # Close m1 cover if it is open.
        await self.close_m1_cover()

        if self.check.atdome:
            await self._check_atdome_scb_link()

            self.log.debug("Homing dome azimuth.")

            await self.home_dome()

            self.log.debug(f"Moving dome to {self.dome_open_az} degrees.")
            await self.slew_dome_to(az=self.dome_open_az)

            self.log.info("Opening dome.")

            await self.open_dome_shutter()

        if self.check.atpneumatics:
            self.log.info("Open telescope cover.")
            try:
                await self.open_m1_cover()
            except Exception:
                self.log.exception("Failed to open M1 cover. Continuing.")

            try:
                await self.open_m1_vent()
            except Exception:
                self.log.exception("Failed to open M1 vent. Continuing.")

        if self.check.ataos:
            await self.enable_ataos_corrections()

        await self.enable_dome_following()

        self.log.info("Prepare for on sky finished.")

    async def _check_atdome_scb_link(self) -> None:
        """Check the ATDome connection with the moving enclosure."""

        self.log.debug("Check that dome CSC can communicate with shutter control box.")

        try:
            scb = await self.rem.atdome.evt_scbLink.aget(timeout=self.fast_timeout)
        except asyncio.TimeoutError:
            self.log.error(
                "Timed out waiting for ATDome CSC scbLink status event. Can not "
                "determine if CSC has communication with Shutter Control Box. "
                "If running this on a jupyter notebook you may try to add an "
                "await asyncio.sleep(1.) before calling startup again to give the "
                "remotes time to get information from DDS. You may also try to "
                "re-cycle the ATDome CSC state to STANDBY and back to ENABLE. "
                "Cannot continue."
            )
            raise

        if not scb.active:
            raise RuntimeError(
                "Dome CSC has no communication with Shutter Control Box. "
                "Dome controllers may need to be rebooted for connection to "
                "be established. Cannot continue."
            )

    async def enable_ataos_corrections(self) -> None:
        """Enable ATAOS corrections."""

        if not await self.in_pneumatics_operational_range():
            await self.slew_to_pneumatics_operational_range()

        self.log.info("Enabling ATAOS corrections.")

        await self.rem.ataos.cmd_enableCorrection.set_start(
            m1=True, hexapod=True, atspectrograph=True, timeout=self.long_timeout
        )

    async def disable_ataos_corrections(self, ignore_fail: bool = True) -> None:
        """Disable ATAOS corrections."""

        if not await self.in_pneumatics_operational_range():
            await self.slew_to_pneumatics_operational_range()

        self.log.debug("Disabling ATAOS corrections.")

        try:
            await self.rem.ataos.cmd_disableCorrection.set_start(
                disableAll=True, timeout=self.long_timeout
            )
        except Exception as e:
            self.log.exception("Failed to disable ATAOS corrections. Continuing...")
            if not ignore_fail:
                raise e

    async def shutdown(self) -> None:
        """Shutdown ATTCS components.

        This method will perform the end of the night procedure for the
        ATTCS component. It will close the telescope cover, close the dome,
        move the telescope and dome to the park position and disable all
        components.
        """
        # Create a copy of check to restore at the end.
        check = copy.copy(self.check)

        self.log.info("Disabling ATAOS corrections")

        if check.ataos:
            await self.disable_ataos_corrections()
        else:
            self.log.debug("Skip disabling ATAOS corrections.")

        if check.atpneumatics:
            self.log.debug("Closing M1 cover vent gates.")

            await self.close_m1_cover()

            try:
                await self.close_m1_vent()
            except Exception:
                self.log.exception("Error closing m1 vents.")
        else:
            self.log.warning(
                "Skipping closing M1 cover and vent gates. If mirror is openend, "
                "will not be able to close the dome slit."
            )

        if check.atdome:
            self.log.info("Close dome.")

            try:
                await self.close_dome()
            except Exception as e:
                self.log.error(
                    "Failed to close the dome. Cannot continue with shutdown operation. "
                    "Check system for errors and try again."
                )
                raise e

            self.log.debug("Slew dome to Park position.")
            await self.slew_dome_to(az=self.dome_park_az, check=check)
        else:
            self.log.warning(
                "Skipping closing dome shutter and slewing dome to park position."
            )

        await self.disable_dome_following()

        if check.atmcs:
            self.log.debug("Slew telescope to Park position.")

            try:
                await self.point_azel(
                    target_name="Park position",
                    az=self.tel_park_az,
                    el=self.tel_park_el,
                    rot_tel=self.tel_park_rot,
                    wait_dome=False,
                )
                await self.stop_tracking()
            except Exception:
                self.log.exception(
                    "Failed to slew telescope to park position. Continuing..."
                )
        else:
            self.log.info("Skip slewing telescope to park position.")

        # restore check
        self.check = copy.copy(check)

        self.log.info("Put CSCs in standby")

        await self.standby()

    async def open_dome_shutter(self) -> None:
        """Task to open dome shutter and return when it is done."""

        shutter_pos = await self.rem.atdome.evt_mainDoorState.aget(
            timeout=self.fast_timeout
        )

        if shutter_pos.state in {
            ATDome.ShutterDoorState.CLOSED,
            ATDome.ShutterDoorState.PARTIALLYOPENED,
        }:
            self.log.debug("Opening dome shutter...")

            self.rem.atdome.evt_mainDoorState.flush()

            # FIXME: DM-28723: Remove workaround in ATCS class for opening/
            # closing the dome.
            # Work around for a problem with moveShutterMainDoor in ATDome
            # v1.3.3. The CSC is not able to determine reliably when the slit
            # is opened or closed. See DM-28512.

            open_shutter_task = asyncio.create_task(
                self.rem.atdome.cmd_moveShutterMainDoor.set_start(
                    open=True, timeout=self.open_dome_shutter_time
                )
            )

            self.rem.atdome.evt_summaryState.flush()
            task_list = [
                asyncio.create_task(self.check_component_state("atdome")),
                asyncio.create_task(
                    self._wait_for_shutter_door_state(
                        state=ATDome.ShutterDoorState.OPENED,
                        cmd_task=open_shutter_task,
                        timeout=self.open_dome_shutter_time,
                    )
                ),
            ]

            await self.process_as_completed(task_list)

        elif shutter_pos.state == ATDome.ShutterDoorState.OPENED:
            self.log.info("ATDome Shutter Door is already opened. Ignoring.")
        else:
            raise RuntimeError(
                f"Shutter Door state is "
                f"{ATDome.ShutterDoorState(shutter_pos.state)!r}. "
                f"expected either {ATDome.ShutterDoorState.CLOSED!r}, "
                f"{ATDome.ShutterDoorState.PARTIALLYOPENED!r} or "
                f"{ATDome.ShutterDoorState.OPENED!r}"
            )

    async def home_dome(self, force: bool = False) -> None:
        """Task to execute dome home command and wait for it to complete.

        Parameters
        ----------
        force : `bool`, optional
            Force dome to be homed even if it is already homed (default=False).
        """

        if await self.is_dome_homed() and not force:
            self.log.warning("Dome already homed. Nothing do to.")
            return
        elif force:
            self.log.info("Dome already homed. Running in force mode, homing it...")
        else:
            self.log.info("Homing dome.")

        self.rem.atdome.evt_azimuthState.flush()

        await self.rem.atdome.cmd_homeAzimuth.start()

        await asyncio.sleep(self.fast_timeout)  # Give the dome time to start moving

        # Work around for when the atdome is pressing the limit switch when
        # we issue a home command.
        # See DM-29202 for a more permanent fix.

        # Check if the dome is in zero. If it is, assume dome is homed and
        # move forward.
        dome_pos = await self.rem.atdome.tel_position.next(
            flush=True, timeout=self.fast_timeout
        )

        az_position = Angle(dome_pos.azimuthPosition * u.deg).wrap_at("180d")
        if az_position < 1.0e-3 * u.deg:
            # If we get here it means the dome may potentially be perssing the
            # limit switch, but it may also be that it was close to homing and
            # manage to finish really quick. So, better make sure.
            try:
                # If dome was pressing the limit switch this event will not
                # be published, but if it homed, it will get published.
                # So treat a timeout as an indication that it was pressing the
                # home switch.
                az_state = await self.rem.atdome.evt_azimuthState.next(
                    flush=False, timeout=self.fast_timeout
                )
            except asyncio.TimeoutError:
                # The event timedout, this probably means the switch was
                # pressed. Log a warning and move on.
                self.log.warning(
                    "Timeout waiting for ATDome azimuthState event. This may "
                    "indicate that the dome is already homed and resting exactly on the home switch."
                )
                return
            else:
                # If we got here it means we received the event.
                # Log the condition and move forward, not that it will skip to
                # the "while" statement bellow and check whether the dome was
                # homing or not.
                self.log.debug(
                    f"ATDome azimuth position ({az_position}) too close to zero. "
                    "Received azimuthState event. Waiting for homing to finish."
                )
        else:
            az_state = await self.rem.atdome.evt_azimuthState.next(
                flush=False, timeout=self.open_dome_shutter_time
            )
        while az_state.homing:
            self.log.info("Dome azimuth still homing.")
            az_state = await self.rem.atdome.evt_azimuthState.next(
                flush=False, timeout=self.open_dome_shutter_time
            )
        else:
            self.log.info("Dome azimuth homed successfully.")

    async def close_dome(self, force: bool = True) -> None:
        """Task to close ATDome.

        Parameters
        ----------
        force : `bool`
            Close the dome shutter even if the method is unable to determine
            the state of m1 cover and/or the mirror is open.
        """

        # Before closing the dome, need to make sure mirror is closed.
        try:
            cover_state = await self.rem.atpneumatics.evt_m1CoverState.aget(
                timeout=self.fast_timeout
            )
        except asyncio.TimeoutError:
            if not force:
                raise RuntimeError(
                    "Can not determine m1 cover state. It is not safe to close "
                    "the dome shutter with the mirror cover opened. If you want "
                    "to force this operation, run close_dome(force=True)."
                )
            else:
                self.log.warning(
                    "Forcing to close the dome shutter without information on m1 cover state."
                )

        if cover_state.state != ATPneumatics.MirrorCoverState.CLOSED and not force:
            raise RuntimeError(
                "M1 cover state open. Close the mirror before closing the dome shutter."
            )
        elif force:
            self.log.warning(
                f"Current M1 cover state is {ATPneumatics.MirrorCoverState(cover_state.state)!r}. "
                "Force-closing the dome shutter anyway."
            )

        shutter_pos = await self.rem.atdome.evt_mainDoorState.aget(
            timeout=self.fast_timeout
        )

        if shutter_pos.state == ATDome.ShutterDoorState.OPENED or force:
            self.log.debug("Closing dome shutter...")

            await self.rem.atdome.cmd_closeShutter.set_start(
                timeout=self.open_dome_shutter_time
            )

        elif shutter_pos.state == ATDome.ShutterDoorState.CLOSED:
            self.log.info("ATDome Shutter Door is already closed. Ignoring.")
        else:
            raise RuntimeError(
                f"Shutter Door state is "
                f"{ATDome.ShutterDoorState(shutter_pos.state)}. "
                f"expected either {ATDome.ShutterDoorState.OPENED} or "
                f"{ATDome.ShutterDoorState.CLOSED}"
            )

    async def open_dropout_door(self) -> None:
        """Open ATdome dropout door."""

        dropout_door_state = await self.rem.atdome.evt_dropoutDoorState.aget(
            timeout=self.fast_timeout
        )

        if dropout_door_state.state in {
            ATDome.ShutterDoorState.CLOSED,
            ATDome.ShutterDoorState.PARTIALLYOPENED,
        }:
            self.log.debug("Opening dome dropout door...")

            # flush state
            self.rem.atdome.evt_dropoutDoorState.flush()

            open_dropout_door_task = asyncio.create_task(
                self.rem.atdome.cmd_moveShutterDropoutDoor.set_start(
                    open=True, timeout=self.open_dropout_door_time
                )
            )

            self.rem.atdome.evt_summaryState.flush()
            task_list = [
                asyncio.create_task(self.check_component_state("atdome")),
                asyncio.create_task(
                    self._wait_for_dropout_door_state(
                        state=ATDome.ShutterDoorState.OPENED,
                        cmd_task=open_dropout_door_task,
                        timeout=self.open_dropout_door_time,
                    )
                ),
            ]

            await self.process_as_completed(task_list)

        elif dropout_door_state.state == ATDome.ShutterDoorState.OPENED:
            self.log.info("ATDome Dropout Door is already opened. Ignoring.")
        else:
            raise RuntimeError(
                f"Dropout Door state is "
                f"{ATDome.ShutterDoorState(dropout_door_state.state)!r}. "
                f"Expected either {ATDome.ShutterDoorState.CLOSED!r}, "
                f"{ATDome.ShutterDoorState.PARTIALLYOPENED!r} or"
                f"{ATDome.ShutterDoorState.OPENED}"
            )

    async def close_dropout_door(self) -> None:
        """Close ATDome dropout door"""

        dropout_door_state = await self.rem.atdome.evt_dropoutDoorState.aget(
            timeout=self.fast_timeout
        )
        if dropout_door_state.state in {
            ATDome.ShutterDoorState.OPENED,
            ATDome.ShutterDoorState.PARTIALLYOPENED,
        }:
            self.log.debug("Closing dome dropout door...")

            close_dropout_door_task = asyncio.create_task(
                self.rem.atdome.cmd_moveShutterDropoutDoor.set_start(
                    open=False, timeout=self.open_dropout_door_time
                )
            )

            self.rem.atdome.evt_summaryState.flush()

            task_list = [
                asyncio.create_task(self.check_component_state("atdome")),
                asyncio.create_task(
                    self._wait_for_dropout_door_state(
                        state=ATDome.ShutterDoorState.CLOSED,
                        cmd_task=close_dropout_door_task,
                        timeout=self.open_dropout_door_time,
                    )
                ),
            ]

            await self.process_as_completed(task_list)

        elif dropout_door_state.state == ATDome.ShutterDoorState.CLOSED:
            self.log.info("ATDome Dropout Door is already closed. Ignoring.")
        else:
            raise RuntimeError(
                f"Dropout Door state is "
                f"{ATDome.ShutterDoorState(dropout_door_state.state)!r}. "
                f"Expected either {ATDome.ShutterDoorState.OPENED!r} or "
                f"{ATDome.ShutterDoorState.CLOSED!r}"
            )

    async def _wait_for_dropout_door_state(
        self,
        state: enum.IntEnum,
        cmd_task: typing.Optional[asyncio.Task] = None,
        timeout: typing.Optional[float] = None,
    ) -> None:
        """Wait for `ATDome.ShutterDoorState.state` to match a required value.

        Parameters:
        -----------
        state : `ATDome.ShutterDoorState`
            The expected shutter door state enumeration value.
        cmd_task : `asyncio.Task` or `None`
            Task with the command to open or close the dome.
        timeout : `float` or `None`
            How long to wait for state (seconds). If `None`, wait for ever.

        Raises:
        -------
        asyncio.TimeoutError
            If `evt_dropoutDoorState` does not reach the expected state in the
            expected time.
        """

        dropout_door_state = ATDome.ShutterDoorState(
            (await self.rem.atdome.evt_dropoutDoorState.aget(timeout=timeout)).state
        )

        self.log.debug(
            f"Waiting for ATDome dropoutDoorState to reach state: "
            f" {state!r}. Current state: {dropout_door_state!r}."
        )

        try:
            while dropout_door_state != state:
                dropout_door_state = ATDome.ShutterDoorState(
                    (
                        await self.rem.atdome.evt_dropoutDoorState.next(
                            flush=False, timeout=timeout
                        )
                    ).state
                )

                self.log.info(f"dropoutDoorState: {dropout_door_state!r}")
        finally:
            if cmd_task is None:
                self.log.debug(
                    f"No dropout door command task. Finished with "
                    f"dropoutDoorState: {dropout_door_state!r}."
                )
            else:
                self.log.debug("Finishing ATDome dropout door command task.")
                if not cmd_task.done():
                    self.log.debug(
                        "ATDome dropout door command task not done. Cancelling."
                    )
                    cmd_task.cancel()

                try:
                    await cmd_task
                except asyncio.CancelledError:
                    self.log.warning("ATDome dropout door command task cancelled.")
                except asyncio.TimeoutError:
                    self.log.warning("ATDome dropout door command task timedout.")

    async def _wait_for_shutter_door_state(
        self,
        state: enum.IntEnum,
        cmd_task: typing.Optional[asyncio.Task] = None,
        timeout: typing.Optional[float] = None,
    ) -> None:
        """Wait for `ATDome.ShutterDoorState.state` to match a required value.

        Parameters
        ----------
        state : `ATDome.ShutterDoorState`
            The expected shutter door state enumeration value.
        cmd_task : `asyncio.Task` or `None`
            Task with the command to open or close the dome.
        timeout : `float` or `None`
            How long to wait for state (seconds). If `None`, wait for ever.

        Raises
        ------
        asyncio.TimeoutError
            If `evt_mainDoorState` does not reach the expected state in the
            expected time.
        """
        # FIXME: DM-28723: Remove workaround in ATCS class for opening/
        # closing the dome.

        shutter_state = ATDome.ShutterDoorState(
            (await self.rem.atdome.evt_mainDoorState.aget(timeout=timeout)).state
        )

        self.log.debug(
            f"Waiting for ATDome mainDoorState: {state!r}. "
            f"Current state: {shutter_state!r}."
        )

        try:
            while shutter_state != state:
                shutter_state = ATDome.ShutterDoorState(
                    (
                        await self.rem.atdome.evt_mainDoorState.next(
                            flush=False, timeout=timeout
                        )
                    ).state
                )

                self.log.info(f"mainDoorState: {shutter_state!r}")
        finally:
            if cmd_task is None:
                self.log.debug(
                    f"No shutter command task. Finished with mainDoorState: {shutter_state!r}."
                )
            else:
                self.log.debug("Finishing ATDome shutter command task.")
                if not cmd_task.done():
                    self.log.debug("ATDome shutter command task not done. Cancelling.")
                    cmd_task.cancel()

                try:
                    await cmd_task
                except asyncio.CancelledError:
                    self.log.warning("ATDome shutter command task cancelled.")
                except asyncio.TimeoutError:
                    self.log.warning("ATDome shutter command task timedout.")

    async def open_m1_cover(self) -> None:
        """Task to open m1 cover.

        Warnings
        --------
        The Mirror cover can only be opened if the telescope is pointing
        above `self.tel_el_operate_pneumatics` (=70 degrees). The method will
        check if the telescope is in an operational range and, if not, will
        move the telescope to an operational elevation, maintaining the same
        azimuth before opening the mirror cover. The telescope will be left
        in that same position in the end.
        """

        await self.assert_m1_correction_disabled(
            "Cannot open m1 cover. Disable ATAOS m1 correction and try again."
        )

        try:
            await self.open_valve_main()
        except Exception:
            self.log.warning("Failed to open main valve, may fail to open m1 cover.")

        cover_state = await self.rem.atpneumatics.evt_m1CoverState.aget(
            timeout=self.fast_timeout
        )

        self.log.debug(
            f"Cover state {ATPneumatics.MirrorCoverState(cover_state.state)!r}"
        )

        if cover_state.state == ATPneumatics.MirrorCoverState.CLOSED:
            self.log.debug("Opening M1 cover.")

            if not await self.in_pneumatics_operational_range():
                await self.slew_to_pneumatics_operational_range()

            await self.rem.atpneumatics.cmd_openM1Cover.start(timeout=self.long_timeout)

            while cover_state.state != ATPneumatics.MirrorCoverState.OPENED:
                cover_state = await self.rem.atpneumatics.evt_m1CoverState.next(
                    flush=False, timeout=self.long_long_timeout
                )
                self.log.debug(
                    f"Cover state {ATPneumatics.MirrorCoverState(cover_state.state)!r}"
                )
                if cover_state.state == ATPneumatics.MirrorCoverState.FAULT:
                    raise RuntimeError(
                        f"Open cover failed. Cover state "
                        f"{ATPneumatics.MirrorCoverState(cover_state.state)!r}"
                    )
        elif cover_state.state == ATPneumatics.MirrorCoverState.OPENED:
            self.log.info("M1 cover already opened.")
        else:
            raise RuntimeError(
                f"M1 cover in {ATPneumatics.MirrorCoverState(cover_state.state)!r} "
                f"state. Expected {ATPneumatics.MirrorCoverState.OPENED!r} or "
                f"{ATPneumatics.MirrorCoverState.CLOSED!r}"
            )

    async def close_m1_cover(self) -> None:
        """Task to close m1 cover.

        Warnings
        --------
        The Mirror cover can only be closed if the telescope is pointing
        above `self.tel_el_operate_pneumatics` (=70 degrees). The method will
        check if the telescope is in an operational range and, if not, will
        move the telescope to an operational elevation, maintaining the same
        azimuth before closing the mirror cover. The telescope will be left
        in that same position in the end.
        """

        await self.assert_m1_correction_disabled(
            "Cannot close m1 cover. Disable ATAOS m1 correction and try again."
        )

        cover_state = await self.rem.atpneumatics.evt_m1CoverState.aget(
            timeout=self.long_long_timeout
        )

        self.log.debug(
            f"Cover state {ATPneumatics.MirrorCoverState(cover_state.state)!r}"
        )

        if cover_state.state == ATPneumatics.MirrorCoverState.OPENED:
            self.log.debug("Closing M1 cover.")

            if not await self.in_pneumatics_operational_range():
                await self.slew_to_pneumatics_operational_range()

            self.rem.atpneumatics.evt_m1CoverState.flush()

            await self.rem.atpneumatics.cmd_closeM1Cover.start(
                timeout=self.long_timeout
            )

            while cover_state.state != ATPneumatics.MirrorCoverState.CLOSED:
                cover_state = await self.rem.atpneumatics.evt_m1CoverState.next(
                    flush=False, timeout=self.long_long_timeout
                )
                self.log.debug(
                    f"Cover state {ATPneumatics.MirrorCoverState(cover_state.state)!r}"
                )

                if cover_state.state == ATPneumatics.MirrorCoverState.FAULT:
                    raise RuntimeError(
                        f"Open cover failed. Cover state "
                        f"{ATPneumatics.MirrorCoverState(cover_state.state)!r}"
                    )

        elif cover_state.state == ATPneumatics.MirrorCoverState.CLOSED:
            self.log.info("M1 cover already closed.")
        else:
            raise RuntimeError(
                f"M1 cover in {ATPneumatics.MirrorCoverState(cover_state.state)!r} "
                f"state. Expected {ATPneumatics.MirrorCoverState.OPENED!r} or "
                f"{ATPneumatics.MirrorCoverState.CLOSED!r}"
            )

    async def open_m1_vent(self) -> None:
        """Task to open m1 vents."""

        await self.assert_m1_correction_disabled(
            "Cannot open m1 vents. Disable ATAOS m1 correction and try again."
        )

        await self.open_valves()

        vent_state = await self.rem.atpneumatics.evt_m1VentsPosition.aget(
            timeout=self.long_long_timeout
        )

        self.log.debug(
            f"M1 vent state {ATPneumatics.VentsPosition(vent_state.position)!r}"
        )

        if vent_state.position == ATPneumatics.VentsPosition.CLOSED:
            self.log.debug("Opening M1 vents.")

            try:
                await self.rem.atpneumatics.cmd_openM1CellVents.start(
                    timeout=self.long_timeout
                )
            except Exception:
                return

            vent_state = await self.rem.atpneumatics.evt_m1VentsPosition.aget()
            self.rem.atpneumatics.evt_m1VentsPosition.flush()
            while vent_state.position != ATPneumatics.VentsPosition.OPENED:
                vent_state = await self.rem.atpneumatics.evt_m1VentsPosition.next(
                    flush=False, timeout=self.long_long_timeout
                )
                self.log.debug(
                    f"M1 vent state {ATPneumatics.VentsPosition(vent_state.position)!r}"
                )
        elif vent_state.position == ATPneumatics.VentsPosition.OPENED:
            self.log.info("M1 vents already opened.")
        else:
            raise RuntimeError(
                f"Unrecognized M1 vent position: {vent_state.position!r}"
            )

    async def close_m1_vent(self) -> None:
        """Task to open m1 vents."""

        await self.assert_m1_correction_disabled(
            "Cannot close m1 vents. Disable ATAOS m1 correction and try again."
        )

        vent_state = await self.rem.atpneumatics.evt_m1VentsPosition.aget(
            timeout=self.fast_timeout
        )

        self.log.debug(
            f"M1 vent state {ATPneumatics.VentsPosition(vent_state.position)!r}"
        )

        if vent_state.position == ATPneumatics.VentsPosition.OPENED:
            self.log.debug("Closing M1 vents.")

            try:
                await self.rem.atpneumatics.cmd_closeM1CellVents.start(
                    timeout=self.long_timeout
                )
            except Exception:
                return

            vent_state = await self.rem.atpneumatics.evt_m1VentsPosition.next(
                flush=False, timeout=self.long_long_timeout
            )

            while vent_state.position != ATPneumatics.VentsPosition.CLOSED:
                vent_state = await self.rem.atpneumatics.evt_m1VentsPosition.next(
                    flush=True, timeout=self.long_long_timeout
                )
                self.log.debug(
                    f"M1 vent state {ATPneumatics.VentsPosition(vent_state.position)!r}"
                )
        elif vent_state.position == ATPneumatics.VentsPosition.CLOSED:
            self.log.info("M1 vents already closed.")
        else:
            raise RuntimeError(
                f"Unrecognized M1 vent position: {vent_state.position!r}"
            )

    async def open_valves(self) -> None:
        """Open the air valve system on ATPneumatics."""

        atpneumatics_state = await self.get_state("atpneumatics", ignore_timeout=True)

        if atpneumatics_state != salobj.State.ENABLED:
            raise RuntimeError(
                f"Current ATPneumatics state is {atpneumatics_state!r}. "
                "Need to be ENABLED to open air valves."
            )

        try:
            await self.open_valve_main()
        except salobj.AckError:
            self.log.warning("Failed to open main valve.")

        try:
            await self.open_valve_instrument()
        except salobj.AckError:
            self.log.warning("Failed to open instrument valve.")

    async def open_valve_main(self) -> None:
        """Open ATPneumatics main valve."""

        pneumatics_main_valve_state = (
            await self.rem.atpneumatics.evt_mainValveState.aget(
                timeout=self.fast_timeout
            )
        ).state

        if pneumatics_main_valve_state == ATPneumatics.AirValveState.CLOSED:
            self.log.debug("Main valve closed, opening.")

            self.rem.atpneumatics.evt_mainValveState.flush()

            await self.rem.atpneumatics.cmd_openMasterAirSupply.start(
                timeout=self.long_timeout
            )

            while pneumatics_main_valve_state != ATPneumatics.AirValveState.OPENED:
                try:
                    pneumatics_main_valve_state = ATPneumatics.AirValveState(
                        (
                            await self.rem.atpneumatics.evt_mainValveState.next(
                                flush=False, timeout=self.long_timeout
                            )
                        ).state
                    )
                except asyncio.TimeoutError:
                    raise RuntimeError("Timeout waiting for main valve to open.")
                self.log.debug(f"Main valve state: {pneumatics_main_valve_state!r}")

        elif pneumatics_main_valve_state == ATPneumatics.AirValveState.OPENED:
            self.log.debug("Main valve opened.")
        else:
            raise RuntimeError(
                f"Main valve state is {pneumatics_main_valve_state!r}, expected "
                f" {ATPneumatics.AirValveState.CLOSED!r} or {ATPneumatics.AirValveState.OPENED!r}."
            )

    async def open_valve_instrument(self) -> None:
        """Open ATPneumatics instrument valve."""
        pneumatics_instrument_valve_state = (
            await self.rem.atpneumatics.evt_instrumentState.aget(
                timeout=self.fast_timeout
            )
        ).state

        if pneumatics_instrument_valve_state == ATPneumatics.AirValveState.CLOSED:
            self.log.debug("Instrument valve closed, opening.")

            self.rem.atpneumatics.evt_instrumentState.flush()

            await self.rem.atpneumatics.cmd_openInstrumentAirValve.start(
                timeout=self.long_timeout
            )

            while (
                pneumatics_instrument_valve_state != ATPneumatics.AirValveState.OPENED
            ):
                try:
                    pneumatics_instrument_valve_state = ATPneumatics.AirValveState(
                        (
                            await self.rem.atpneumatics.evt_instrumentState.next(
                                flush=False, timeout=self.long_timeout
                            )
                        ).state
                    )
                except asyncio.TimeoutError:
                    raise RuntimeError("Timeout waiting for main valve to open.")
                self.log.debug(
                    f"Main valve state: {pneumatics_instrument_valve_state!r}"
                )
        elif pneumatics_instrument_valve_state == ATPneumatics.AirValveState.OPENED:
            self.log.debug("Main valve opened.")
        else:
            raise RuntimeError(
                f"Main valve state is {pneumatics_instrument_valve_state!r}, expected "
                f" {ATPneumatics.AirValveState.CLOSED!r} or {ATPneumatics.AirValveState.OPENED!r}."
            )

    async def _slew_to(
        self,
        slew_cmd: typing.Any,
        slew_timeout: float,
        offset_cmd: typing.Any = None,
        stop_before_slew: bool = False,
        wait_settle: bool = True,
        check: typing.Any = None,
    ) -> None:
        """Encapsulate "slew" activities.

        Parameters
        ----------
        slew_cmd: `coro`
            One of the slew commands from the ptg remote. Command need to be
            setup before calling this method.
        slew_time: `float`
            Expected slew time in seconds.
        offset_cmd: `coro`
            One of the offset commands from the ptg remote. Command need to be
            setup before calling this method.
        stop_before_slew: `bool`
            Stop tracking before slewing?
        wait_settle: `bool`
            After slew complets, add an addional settle wait before returning.
        check : `types.SimpleNamespace` or `None`, optional
            Override internal `check` attribute with a user-provided one.
            By default (`None`) use internal attribute.
        """

        assert self.dome_az_in_position is not None

        self.log.debug("Sending command")

        _check = self.check if check is None else check

        if stop_before_slew:
            try:
                await self.stop_tracking()
            except Exception:
                pass
        else:
            self.rem.atmcs.evt_allAxesInPosition.flush()

        track_id = next(self.track_id_gen)

        try:
            current_target = await self.next_telescope_target(self.fast_timeout)
            if track_id <= current_target.trackId:
                self.track_id_gen = utils.index_generator(current_target.trackId + 1)
                track_id = next(self.track_id_gen)

        except asyncio.TimeoutError:
            pass

        slew_cmd.data.trackId = track_id

        await slew_cmd.start(timeout=slew_timeout)
        self.dome_az_in_position.clear()
        if offset_cmd is not None:
            await offset_cmd.start(timeout=self.fast_timeout)

        self.log.debug("Scheduling check coroutines")

        self.scheduled_coro.append(
            asyncio.create_task(
                self.wait_for_inposition(
                    timeout=slew_timeout,
                    wait_settle=wait_settle,
                    check=_check,
                )
            )
        )

        asyncio.create_task(self.monitor_position(check=_check))

        try:
            for comp in self.components_attr:
                if getattr(_check, comp):
                    getattr(self.rem, comp).evt_summaryState.flush()
                    self.scheduled_coro.append(
                        asyncio.create_task(self.check_component_state(comp))
                    )

            await self.process_as_completed(self.scheduled_coro)
        finally:
            self.stop_monitor()

    async def get_bore_sight_angle(self) -> float:
        """Get the instrument bore sight angle with respect to the telescope
        axis.

        This method also determines the parity of the x-axis based on the
        currently selected focus.

        Returns
        -------
        angle : `float`
            Bore sight angle.
        """

        # Determines x-axis parity.
        try:
            focus_name = await self.rem.atptg.evt_focusNameSelected.aget(
                timeout=self.fast_timeout
            )
            self.parity_x = (
                -1.0 if ATPtg.Foci(focus_name.focus) == ATPtg.Foci.NASMYTH2 else 1.0
            )
        except asyncio.TimeoutError:
            self.log.error(
                "Could not determine current selected focus. Using current x-axis parity = {self.parity_x}."
            )

        # Determines bore_sight_angle angle
        azel = self.telescope_position
        try:
            nasmyth = await self.rem.atmcs.tel_mount_Nasmyth_Encoders.aget(
                timeout=self.fast_timeout
            )
        except asyncio.TimeoutError:
            raise RuntimeError("Cannot determine nasmyth position.")

        nasmyth_angle = (
            np.mean(nasmyth.nasmyth1CalculatedAngle)
            if self.parity_x > 0
            else -np.mean(nasmyth.nasmyth2CalculatedAngle)
        )

        angle = np.mean(azel.elevationCalculatedAngle) + nasmyth_angle + 90.0

        return angle

    async def get_selected_nasmyth_angle(self) -> float:
        """Get selected nasmyth angle.

        Check which nasmyth port is selected and return its current position.
        If it cannot determine the current nasmyth, issue a warning and uses
        port 2, if `self.parity_x == -1`, or port 1, otherwise.

        Returns
        -------
        nasmyth_angle : `float`
            Calculated angle of the current selected nasmyth port.

        Raises
        ------
        RuntimeError:
            If cannot get mount_Nasmyth_Encoders.
        """

        try:
            focus_name = ATPtg.Foci(
                (
                    await self.rem.atptg.evt_focusNameSelected.aget(
                        timeout=self.fast_timeout
                    )
                ).focus
            )
        except asyncio.TimeoutError:
            focus_name = (
                ATPtg.Foci.NASMYTH2 if self.parity_x < 0.0 else ATPtg.Foci.NASMYTH1
            )
            self.log.warning(
                "Could not determine current selected nasmyth port."
                "Using {focus_name!r}."
            )
        else:
            self.log.debug(f"Using nasmyth port {focus_name!r}")

        try:
            nasmyth = await self.rem.atmcs.tel_mount_Nasmyth_Encoders.aget(
                timeout=self.fast_timeout
            )
        except asyncio.TimeoutError:
            raise RuntimeError("Cannot determine nasmyth position.")

        return (
            np.mean(nasmyth.nasmyth2CalculatedAngle)
            if focus_name == ATPtg.Foci.NASMYTH2
            else np.mean(nasmyth.nasmyth1CalculatedAngle)
        )

    def flush_offset_events(self) -> None:
        """Implement abstract method to flush events before an offset is
        performed.

        See Also
        --------
        offset_done : Wait for events that mark an offset as completed.
        offset_azel : Offset in local AzEl coordinates.
        offset_xy : Offset in terms of boresight.
        offset_radec : Offset in sky coordinates.
        """
        self.rem.atmcs.evt_allAxesInPosition.flush()

    async def offset_done(self) -> None:
        """Wait for events specifying that an offset completed.

        Notes
        -----
        For ATMCS we expect the component to send
        `allAxesInPosition.inPosition=False` at the start of an offset and then
        `allAxesInPosition.inPosition=True` when it is done.

        If the ATMCS fails to send these events in more than
        `self.tel_settle_time` seconds, waiting for the event will timeout and
        raise an `asyncio.Timeout` exception.

        See Also
        --------
        flush_offset_events : Flush events before an offset.
        offset_azel : Offset in local AzEl coordinates.
        offset_xy : Offset in terms of boresight.
        offset_radec : Offset in sky coordinates.
        """

        self.rem.atmcs.evt_allAxesInPosition.flush()

        in_position = await self.rem.atmcs.evt_allAxesInPosition.aget(
            timeout=self.long_timeout
        )

        if in_position.inPosition:
            self.log.debug("ATMCS in position, handling potential race condition.")
            await asyncio.sleep(self.tel_settle_time)
            in_position = await self.rem.atmcs.evt_allAxesInPosition.aget(
                timeout=self.long_timeout
            )

        while not in_position.inPosition:
            self.log.debug("Telescope not in position.")
            in_position = await self.rem.atmcs.evt_allAxesInPosition.next(
                flush=False, timeout=self.long_timeout
            )
        self.log.debug("All axes in position.")

    async def wait_for_inposition(
        self,
        timeout: float,
        wait_settle: bool,
        check: typing.Optional[typing.Any] = None,
    ) -> typing.List[str]:
        """Wait for both the ATMCS and ATDome to be in position.

        Parameters
        ----------
        timeout: `float`
            How long should it wait before timing out.
        cmd_ack: `CmdAck` or `None`
            CmdAck from the command that started the slew process. This is an
            experimental feature to discard events that where sent before the
            slew starts.
        wait_settle: `bool`
            After slew completes, add an addional settle wait before returning.
        check : `types.SimpleNamespace` or `None`
            Override `self.check` for defining which resources are used.

        Returns
        -------
        status: `list` of `str`
            String with final status.

        Raises
        ------
        RuntimeError:
            If tasks times out.
        """

        # Creates a copy of check so it can be freely modified to control what
        # needs to be verified at each stage of the process.
        _check = copy.copy(self.check) if check is None else copy.copy(check)

        tasks = list()

        if _check.atmcs:
            tasks.append(
                asyncio.create_task(
                    self.wait_for_atmcs_inposition(timeout=timeout),
                    name="Telescope",
                )
            )

        if _check.atdome:
            tasks.append(
                asyncio.create_task(
                    self.wait_for_atdome_inposition(timeout),
                    name="Dome",
                )
            )

        try:
            status = await asyncio.gather(*tasks)
        except (TimeoutError, asyncio.exceptions.TimeoutError):
            error_message = ""
            for task in tasks:
                if task.done() and task.exception():
                    error_message += (
                        f"{task.get_name()} timed out getting in position.\n"
                    )
            await self.cancel_not_done(tasks=tasks)
            raise RuntimeError(error_message)

        if wait_settle:
            self.log.debug(
                f"Wait additional {self.tel_settle_time}s for telescope to settle."
            )
            await asyncio.sleep(self.tel_settle_time)

        return status

    async def wait_for_atmcs_inposition(self, timeout: float) -> str:
        """Wait for inPosition of atmcs to be ready.

        Parameters
        ----------
        timeout: `float`
            How long should it wait before timing out.

        Returns
        -------
        status: `str`
            String with final status.

        Raises
        ------
        asyncio.TimeoutError
            If does not get a status update in less then `timeout` seconds.
        """
        return await self._handle_in_position(
            in_position_event=self.rem.atmcs.evt_allAxesInPosition,
            timeout=timeout,
            settle_time=self.tel_settle_time,
            component_name="ATMCS",
        )

    async def wait_for_atdome_inposition(self, timeout: float) -> str:
        """Wait until the telescope is cleared by the dome.

        Instead of waiting until the dome finishes moving. This method will
        wait until the telescope is not vigneted by the dome. This is
        monitored in `monitor_position` and broadcasted as an `asyncio.Event`.

        Parameters
        ----------
        timeout: `float`
            How long should it wait before timing out.

        Returns
        -------
        status: `str`
            String with final status.

        Raises
        ------
        asyncio.TimeoutError
            If does not get a status update in less then `timeout` seconds.
        """
        assert self.dome_az_in_position is not None

        if not await self.check_dome_following():
            self.log.debug("Dome following disabled. Ignoring dome position.")
            self.dome_az_in_position.set()
        else:
            self.log.debug(
                "Dome following enabled. Waiting for dome to get in position."
            )
            await asyncio.wait_for(self.dome_az_in_position.wait(), timeout=timeout)
        self.log.info("ATDome in position.")
        return "ATDome in position."

    async def wait_for_atdome_shutter_inposition(self) -> str:
        """Wait for the atdome shutter to be in position.

        Returns
        -------
        status: `str`
            String with final status.

        Raises
        ------
        asyncio.TimeoutError
            If does not get in position before `self.open_dome_shutter_time`
        """
        timeout = self.open_dome_shutter_time

        while True:
            in_position = await self.rem.atdome.evt_shutterInPosition.next(
                flush=False, timeout=timeout
            )

            self.log.debug(f"Got: {in_position}")

            if in_position.inPosition:
                self.log.info("ATDome shutter in position.")
                return "ATDome shutter in position."
            else:
                self.log.debug("ATDome shutter not in position.")

    async def monitor_position(self, check: typing.Optional[typing.Any] = None) -> None:
        """Monitor and log the position of the telescope and the dome.

        Parameters
        ----------
        check : `types.SimpleNamespace` or `None`
            Override `self.check` for defining which resources are used.
        """
        # Creates a copy of check so it can modify it freely to control what
        # needs to be verified at each stage of the process.
        _check = copy.copy(self.check) if check is None else copy.copy(check)

        assert self.dome_az_in_position is not None
        # Wait for target events to be published before entering the loop.

        if _check.atmcs:
            try:
                await self.next_telescope_target(timeout=self.long_timeout)
            except asyncio.TimeoutError:
                raise RuntimeError(
                    "Not receiving target events from the ATMCS. "
                    "Check component for errors."
                )

        dome_following = await self.check_dome_following()

        if not dome_following and _check.atdome:
            self.log.warning(
                "Dome following disabled and check dome enabled. "
                "Disabling dome check."
            )
            _check.atdome = False

        in_position = False

        if not self.is_monitor_enabled():
            self.log.debug("Monitor disabled. Enabling and starting monitoring loop.")
            self.enable_monitor()

        while self.is_monitor_enabled():
            status = ""
            if _check.atmcs:
                comm_pos = await self.next_telescope_target(timeout=self.long_timeout)
                tel_pos = await self.next_telescope_position(timeout=self.fast_timeout)
                nasm_pos = await self.rem.atmcs.tel_mount_Nasmyth_Encoders.next(
                    flush=True, timeout=self.fast_timeout
                )

                alt_dif = angle_diff(
                    comm_pos.elevation, tel_pos.elevationCalculatedAngle[-1]
                )
                az_dif = angle_diff(
                    comm_pos.azimuth, tel_pos.azimuthCalculatedAngle[-1]
                )
                nasm1_dif = angle_diff(
                    comm_pos.nasmyth1RotatorAngle, nasm_pos.nasmyth1CalculatedAngle[-1]
                )
                nasm2_dif = angle_diff(
                    comm_pos.nasmyth2RotatorAngle, nasm_pos.nasmyth2CalculatedAngle[-1]
                )
                alt_in_position = np.abs(alt_dif) < self.tel_el_slew_tolerance
                az_in_position = np.abs(az_dif) < self.tel_az_slew_tolerance
                na1_in_position = np.abs(nasm1_dif) < self.tel_nasm_slew_tolerance
                na2_in_position = np.abs(nasm2_dif) < self.tel_nasm_slew_tolerance
                status += (
                    f"[Tel]: Az = {tel_pos.azimuthCalculatedAngle[-1]:+08.3f}[{az_dif.deg:+6.1f}]; "
                    f"El = {tel_pos.elevationCalculatedAngle[-1]:+08.3f}[{alt_dif.deg:+6.1f}] "
                    f"[Nas1]: {nasm_pos.nasmyth1CalculatedAngle[-1]:+08.3f}[{nasm1_dif.deg:+6.1f}] "
                    f"[Nas2]: {nasm_pos.nasmyth2CalculatedAngle[-1]:+08.3f}[{nasm2_dif.deg:+6.1f}] "
                )

            if _check.atdome:
                dom_pos = await self.rem.atdome.tel_position.next(
                    flush=True, timeout=self.fast_timeout
                )
                dom_comm_pos = await self.rem.atdome.evt_azimuthCommandedState.aget(
                    timeout=self.fast_timeout
                )

                dom_az_dif = angle_diff(dom_comm_pos.azimuth, dom_pos.azimuthPosition)

                dom_in_position = np.abs(dom_az_dif) < self.dome_slew_tolerance
                status += f"[Dome] Az = {dom_pos.azimuthPosition:+08.3f}[{dom_az_dif.deg:+6.1f}]"

                if dom_in_position:
                    self.dome_az_in_position.set()

            if status:
                self.log.info(status)

            if _check.atmcs and _check.atdome:
                in_position = (
                    alt_in_position
                    and az_in_position
                    and na1_in_position
                    and na2_in_position
                    and dom_in_position
                )
            elif _check.atdome:
                in_position = dom_in_position
            elif _check.atmcs:
                in_position = (
                    alt_in_position
                    and az_in_position
                    and na1_in_position
                    and na2_in_position
                )
            else:
                break

            await asyncio.sleep(1.0)

        if in_position:
            self.log.debug("Axes in position.")
        else:
            self.log.warning("Nothing to check.")

    async def check_target_status(self) -> None:
        """Check the targeting status of the atmcs."""
        while True:
            in_position = await self.rem.atmcs.evt_allAxesInPosition.next(flush=False)
            self.log.debug(f"Got {in_position.inPosition}")
            if in_position.inPosition is False:
                raise RuntimeError("ATMCS is no longer tracking.")

    async def focus_offset(self, offset: float) -> None:
        """Apply focus offset.

        Returns after offset is aplied.

        Parameters
        ----------
        offset : `float`
            Offset in mm.
        """
        self.rem.athexapod.evt_positionUpdate.flush()
        await self.rem.ataos.cmd_applyFocusOffset.set_start(offset=offset)

        # TODO: Remove when DM-24491 is implemented.
        try:
            await self.rem.athexapod.evt_positionUpdate.next(
                flush=False, timeout=self.long_timeout
            )
        except asyncio.TimeoutError:
            self.log.warning("Did not received position update from ATHexapod.")
            pass

    def set_azel_slew_checks(self, wait_dome: bool) -> typing.Any:
        """Handle azEl slew to wait or not for the dome.

        Parameters
        ----------
        wait_dome : `bool`
            Should the slew wait for the dome?

        Returns
        -------
        check : `types.SimpleNamespace`
            Reformated check namespace.
        """
        check = copy.copy(self.check)
        check.atdome = wait_dome
        check.atdometrajectory = wait_dome
        return check

    async def _ready_to_take_data(self) -> None:
        """Wait until ATCS is ready to take data."""
        # Things to check
        # 1 - ATMCS evt_allAxesInPosition.inPosition == True
        # 2 - All ATAOS corrections are applied
        # 3 - ATMCS and ATDome positions are within specified range.
        ready = False
        assert self.dome_az_in_position is not None

        while not ready:
            # This loop will run until all conditions are met. Note that it
            # may happen that one condition will be met when we run it the
            # first time and then not when we run the second time.
            check = await asyncio.gather(
                self.atmcs_in_position(),
                self.ataos_corrections_completed(),
                self.dome_az_in_position.wait(),
            )
            self.log.debug(
                f"Ready to take data:: atmcs={check[0]}, ataos={check[1]}, atdome={check[2]}."
            )
            ready = all(check)

    async def ataos_corrections_completed(self) -> bool:
        """Check that all ATAOS corrections completed.

        Returns
        -------
        corrections_completed: `bool`
            Returns `True` when corrections are completed.

        Raise
        -----
        RuntimeError:
            If the last `atspectrographCorrectionCompleted` event was published
            before the last `atspectrographCorrectionStarted` and a timeout
            happens when waiting for a new `atspectrographCorrectionCompleted`.
        """

        ataos_enabled_corrections = await self.rem.ataos.evt_correctionEnabled.aget(
            timeout=self.fast_timeout
        )
        # If the atspectrograph correction is not enabled, then nothing to wait
        # for. Just return.
        if not ataos_enabled_corrections.atspectrograph:
            return True

        self.log.debug(
            "atspectrograph correction running. Trying to determine state of the corrections."
        )
        ret_val = await asyncio.gather(
            self.rem.ataos.evt_atspectrographCorrectionStarted.next(
                flush=True, timeout=self.fast_timeout
            ),
            self.rem.ataos.evt_atspectrographCorrectionCompleted.next(
                flush=True, timeout=self.fast_timeout
            ),
            return_exceptions=True,
        )
        # If they are both execeptions it probably means the ATAOS got into a
        # stable state and it is ready to take images. We need to verify now
        # that the last completed correction was issued after the last started
        # correction.
        if all([isinstance(val, asyncio.TimeoutError) for val in ret_val]):
            self.log.debug(
                f"No correction seen in the last {self.fast_timeout} seconds. "
                "Determining order of last corrections."
            )
            started, completed = await asyncio.gather(
                self.rem.ataos.evt_atspectrographCorrectionStarted.aget(
                    timeout=self.fast_timeout
                ),
                self.rem.ataos.evt_atspectrographCorrectionCompleted.aget(
                    timeout=self.fast_timeout
                ),
            )
            if started.private_sndStamp >= completed.private_sndStamp:
                self.log.debug("Last correction still pending.")
                # There is probably a correction going on. Still not ready.
                return False
            else:
                self.log.debug("Last correction completed.")
                # Correction completed was done after last started. It is
                # probably ready to take data.
                return True

        else:
            # This means we got some data. We are not in a stable state yet.
            correction_name = ["started", "completed"]
            correction_received = [
                name
                for name, corr in zip(correction_name, ret_val)
                if not isinstance(corr, asyncio.TimeoutError)
            ]

            self.log.debug(f"Received corrections: {correction_received}.")
            return False

    async def atmcs_in_position(self) -> bool:
        """Check if atmcs is in position.

        This method will try to get the next event published after the call. If
        it fails, it will return the last event seen. If no event was ever
        seen, it will fail with a `TimeoutError`.

        Returns
        -------
        in_position: `bool`
            In position flag value.
        """

        try:
            in_position = await self.rem.atmcs.evt_allAxesInPosition.next(
                flush=True, timeout=self.fast_timeout
            )
        except asyncio.TimeoutError:
            in_position = await self.rem.atmcs.evt_allAxesInPosition.aget(
                timeout=self.fast_timeout
            )

        return in_position.inPosition

    async def assert_ataos_corrections_enabled(self) -> None:
        """Assert that m1, hexapod and atspectrograph corrections are enabled.

        Raises
        ------
        AssertionError
            If ATAOS m1, hexapod, or atspectrograph corrections are disabled.

        """

        self.log.debug("Check ATAOS corrections are enabled.")
        ataos_corrections = await self.rem.ataos.evt_correctionEnabled.aget(
            timeout=self.fast_timeout
        )

        assert (
            ataos_corrections.hexapod
            and ataos_corrections.m1
            and ataos_corrections.atspectrograph
        ), (
            "Not all required ATAOS corrections are enabled. "
            "The following loops must all be closed (True), but are currently: "
            f"Hexapod: {ataos_corrections.hexapod}, "
            f"M1: {ataos_corrections.m1}, "
            f"ATSpectrograph: {ataos_corrections.atspectrograph}. "
            "Enable corrections with the ATAOS 'enableCorrection' command before proceeding.",
        )

    async def assert_m1_correction_disabled(self, message: str = "") -> None:
        """Assert that m1 corrections is disabled.

        Parameters
        ----------
        message : `str`
            Additional message to append to error.

        Raises
        ------
        AssertionError
            If ATAOS m1 corrections are enabled.
        """

        try:
            ataos_correction_enabled = await self.rem.ataos.evt_correctionEnabled.aget(
                timeout=self.fast_timeout
            )
        except asyncio.TimeoutError:
            self.log.debug(
                "No correctionEnabled event, assuming correction not enabled."
            )
            return
        else:
            assert (
                not ataos_correction_enabled.m1
            ), f"ATAOS m1 correction enabled. {message}"

    async def offset_aos_lut(
        self,
        z: float = 0.0,
        x: float = 0.0,
        y: float = 0.0,
        u: float = 0.0,
        v: float = 0.0,
        m1: float = 0.0,
        offset_telescope: bool = True,
    ) -> None:
        """Apply offsets to hexapod and optionally re-center telescope after
        hexapod offset.

        Parameters
        ----------
        z : `float`, optional
            Hexapod offset in z axis (mm)
        x : `float`, optional
            Hexapod offset in x axis (mm)
        y : `float`, optional
            Hexapod offset in y axis (mm)
        u : `float`, optional
            Hexapod Rx offset (deg)
        v : `float`, optional
            Hexapod Ry offset (deg)
        m1 : `float`, optional
            M1 pressure offset (Pa). Must be less than 0.
        offset_telescope : `bool`, optional
            Offset the telescope after the hexpod offset to compensate for
            chage in pointing.
        """

        if m1 > 0.0:
            raise RuntimeError(
                f"Invalied user-supplied m1 offset: {m1}; must be less than or equal to 0."
            )

        offset_applied = {
            "m1": m1,
            "m2": 0.0,
            "x": x,
            "y": y,
            "z": z,
            "u": u,
            "v": v,
        }

        self.log.info(
            f"Applying hexapod offset [m1, m2, x, y, z, u, v, w]: {offset_applied}."
        )

        self.rem.ataos.evt_detailedState.flush()

        await self.rem.ataos.cmd_offset.set_start(
            **offset_applied, timeout=self.long_timeout
        )

        if offset_telescope and (x != 0.0 or y != 0.0 or u != 0.0 or v != 0.0):
            tel_el_offset_xy, tel_az_offset_xy, _ = np.matmul(
                [x, y, z], atcs_constants.hexapod_offset_scale
            )

            tel_el_offset_uv, tel_az_offset_uv, _ = np.matmul(
                [u, v, z], atcs_constants.hexapod_uv_offset_scale
            )
            tel_az_offset, tel_el_offset = (
                tel_el_offset_xy + tel_el_offset_uv,
                tel_az_offset_xy + tel_az_offset_uv,
            )

            self.log.info(
                f"Applying telescope offset [az,el]: [{tel_az_offset:0.3f}, {tel_el_offset:0.3f}]."
            )

            await self.offset_azel(
                az=tel_az_offset,
                el=tel_el_offset,
                relative=True,
                persistent=True,
            )

    async def slew_to_pneumatics_operational_range(self) -> None:
        """Slew the telescope to safe range for pneumatics operation.

        This method  will slew the telescope to a safe elevation to perform
        atpneumatics operations. It should be used in combination with the
        in_pneumatics_operational_range method. Telescope will be left in
        pneumatics position with tracking disabled.

        """

        tel_pos = await self.next_telescope_position(timeout=self.fast_timeout)

        nasmyth_angle = await self.get_selected_nasmyth_angle()

        await self.point_azel(
            az=tel_pos.azimuthCalculatedAngle[-1],
            el=self.tel_el_operate_pneumatics,
            rot_tel=nasmyth_angle,
            wait_dome=False,
        )

    async def in_pneumatics_operational_range(self) -> bool:
        """Check if ATMCS is in operational range for pneumatics operation.

        Returns
        -------
        elevation_in_range: `bool`
            Returns `True` when telecsope elevation is in safe range for
            pneumatics operation.

        """

        tel_pos = await self.next_telescope_position(timeout=self.fast_timeout)

        return tel_pos.elevationCalculatedAngle[-1] > self.tel_el_operate_pneumatics

    @property
    def plate_scale(self) -> float:
        """Plate scale in mm/arcsec."""
        return atcs_constants.plate_scale

    @property
    def ptg_name(self) -> str:
        """Return name of the pointing component."""
        return "atptg"

    @property
    def dome_trajectory_name(self) -> str:
        """Return name of the DomeTrajectory component."""
        return "atdometrajectory"

    @property
    def CoordFrame(self) -> enum.IntEnum:
        """Return CoordFrame enumeration."""
        return ATPtg.CoordFrame

    @property
    def RotFrame(self) -> enum.IntEnum:
        """Return RotFrame enumeration."""
        return ATPtg.RotFrame

    @property
    def RotMode(self) -> enum.IntEnum:
        """Return RotMode enumeration."""
        return ATPtg.RotMode

    @property
    def WrapStrategy(self) -> enum.IntEnum:
        """Return WrapStrategy enumeration"""
        return ATPtg.WrapStrategy

    @property
    def valid_use_cases(self) -> ATCSUsages:
        """Returns valid usages.

        When subclassing, overwrite this method to return the proper enum.

        Returns
        -------
        usages: enum

        """
        return ATCSUsages()

    @property
    def usages(self) -> typing.Dict[int, UsagesResources]:
        if self._usages is None:
            usages = super().usages

            usages[self.valid_use_cases.All] = UsagesResources(
                components_attr=self.components_attr,
                readonly=False,
                generics=[
                    "start",
                    "enable",
                    "disable",
                    "standby",
                    "exitControl",
                    "enterControl",
                    "summaryState",
                    "configurationsAvailable",
                    "heartbeat",
                ],
                atmcs=[
                    "allAxesInPosition",
                    "atMountState",
                    "azimuthCommandedState",
                    "azimuthInPosition",
                    "azimuthState",
                    "target",
                    "mount_AzEl_Encoders",
                    "position",
                    "mount_Nasmyth_Encoders",
                ],
                atptg=[
                    "azElTarget",
                    "raDecTarget",
                    "planetTarget",
                    "stopTracking",
                    "offsetAzEl",
                    "offsetRADec",
                    "poriginOffset",
                    "pointAddData",
                    "pointNewFile",
                    "pointAddData",
                    "timeAndDate",
                    "focusNameSelected",
                ],
                ataos=[
                    "enableCorrection",
                    "disableCorrection",
                    "applyFocusOffset",
                    "correctionEnabled",
                    "atspectrographCorrectionStarted",
                    "atspectrographCorrectionCompleted",
                ],
                atpneumatics=[
                    "openM1Cover",
                    "closeM1Cover",
                    "openM1CellVents",
                    "closeM1CellVents",
                    "m1CoverState",
                    "m1VentsPosition",
                    "m1SetPressure",
                    "m2SetPressure",
                    "m1OpenAirValve",
                    "m2OpenAirValve",
                    "m1CloseAirValve",
                    "m2CloseAirValve",
                    "openMasterAirSupply",
                    "openInstrumentAirValve",
                    "m1State",
                    "m2State",
                    "instrumentState",
                    "mainValveState",
                    "m1AirPressure",
                    "m2AirPressure",
                ],
                athexapod=["positionUpdate"],
                atdome=[
                    "moveAzimuth",
                    "stopMotion",
                    "moveShutterMainDoor",
                    "homeAzimuth",
                    "closeShutter",
                    "mainDoorState",
                    "scbLink",
                ],
                atdometrajectory=["followingMode"],
            )

            usages[self.valid_use_cases.Slew] = UsagesResources(
                components_attr=self.components_attr,
                readonly=False,
                generics=["summaryState", "configurationsAvailable", "heartbeat"],
                atmcs=[
                    "allAxesInPosition",
                    "atMountState",
                    "azimuthCommandedState",
                    "azimuthInPosition",
                    "azimuthState",
                    "target",
                    "mount_AzEl_Encoders",
                    "position",
                    "mount_Nasmyth_Encoders",
                ],
                atptg=[
                    "azElTarget",
                    "raDecTarget",
                    "planetTarget",
                    "stopTracking",
                    "offsetAzEl",
                    "offsetRADec",
                    "poriginOffset",
                    "pointAddData",
                    "pointNewFile",
                    "pointAddData",
                    "timeAndDate",
                    "focusNameSelected",
                ],
                atdome=["stopMotion", "shutterInPosition"],
                athexapod=["positionUpdate"],
                atdometrajectory=["followingMode"],
                ataos=[
                    "applyFocusOffset",
                    "correctionEnabled",
                    "atspectrographCorrectionStarted",
                    "atspectrographCorrectionCompleted",
                ],
            )
            usages[self.valid_use_cases.StartUp] = UsagesResources(
                components_attr=self.components_attr,
                readonly=False,
                generics=[
                    "start",
                    "enable",
                    "disable",
                    "standby",
                    "exitControl",
                    "enterControl",
                    "summaryState",
                    "configurationsAvailable",
                    "heartbeat",
                ],
                atmcs=[
                    "allAxesInPosition",
                    "atMountState",
                    "azimuthCommandedState",
                    "azimuthInPosition",
                    "azimuthState",
                    "mount_AzEl_Encoders",
                    "position",
                    "mount_Nasmyth_Encoders",
                ],
                atptg=["azElTarget", "stopTracking", "target", "focusNameSelected"],
                atdome=[
                    "moveAzimuth",
                    "stopMotion",
                    "moveShutterMainDoor",
                    "homeAzimuth",
                    "shutterInPosition",
                    "scbLink",
                    "mainDoorState",
                ],
                ataos=["enableCorrection", "correctionEnabled"],
                atpneumatics=[
                    "openM1Cover",
                    "closeM1Cover",
                    "openM1CellVents",
                    "closeM1CellVents",
                    "m1CoverState",
                    "m1VentsPosition",
                    "m1SetPressure",
                    "m2SetPressure",
                    "m1OpenAirValve",
                    "m2OpenAirValve",
                    "m1CloseAirValve",
                    "m2CloseAirValve",
                    "openMasterAirSupply",
                    "openInstrumentAirValve",
                    "m1State",
                    "m2State",
                    "instrumentState",
                    "mainValveState",
                    "m1AirPressure",
                    "m2AirPressure",
                ],
                athexapod=["positionUpdate"],
                atdometrajectory=["followingMode"],
            )

            usages[self.valid_use_cases.Shutdown] = UsagesResources(
                components_attr=self.components_attr,
                readonly=False,
                generics=[
                    "start",
                    "enable",
                    "disable",
                    "standby",
                    "exitControl",
                    "enterControl",
                    "summaryState",
                    "configurationsAvailable",
                    "heartbeat",
                ],
                atmcs=[
                    "allAxesInPosition",
                    "atMountState",
                    "azimuthCommandedState",
                    "azimuthInPosition",
                    "azimuthState",
                    "target",
                    "mount_AzEl_Encoders",
                    "position",
                    "mount_Nasmyth_Encoders",
                ],
                atptg=[
                    "azElTarget",
                    "moveAzimuth",
                    "stopTracking",
                    "focusNameSelected",
                ],
                atdome=[
                    "stopMotion",
                    "moveShutterMainDoor",
                    "closeShutter",
                    "mainDoorState",
                    "scbLink",
                ],
                ataos=["disableCorrection", "correctionEnabled"],
                atpneumatics=[
                    "closeM1Cover",
                    "closeM1CellVents",
                    "m1CoverState",
                    "m1VentsPosition",
                ],
                athexapod=["positionUpdate"],
                atdometrajectory=["followingMode"],
            )

            usages[self.valid_use_cases.PrepareForFlatfield] = UsagesResources(
                components_attr=self.components_attr,
                readonly=False,
                generics=[
                    "start",
                    "enable",
                    "disable",
                    "standby",
                    "exitControl",
                    "enterControl",
                    "summaryState",
                    "configurationsAvailable",
                    "heartbeat",
                ],
                atmcs=[
                    "allAxesInPosition",
                    "atMountState",
                    "azimuthCommandedState",
                    "azimuthInPosition",
                    "azimuthState",
                    "target",
                    "mount_AzEl_Encoders",
                    "position",
                    "mount_Nasmyth_Encoders",
                ],
                atptg=[
                    "azElTarget",
                    "moveAzimuth",
                    "stopTracking",
                    "focusNameSelected",
                ],
                atdome=[
                    "stopMotion",
                    "homeAzimuth",
                    "mainDoorState",
                    "scbLink",
                ],
                ataos=["correctionEnabled"],
                atpneumatics=[
                    "openM1Cover",
                    "closeM1Cover",
                    "openM1CellVents",
                    "closeM1CellVents",
                    "m1CoverState",
                    "m1VentsPosition",
                    "m1SetPressure",
                    "m2SetPressure",
                    "m1OpenAirValve",
                    "m2OpenAirValve",
                    "m1CloseAirValve",
                    "m2CloseAirValve",
                    "openMasterAirSupply",
                    "openInstrumentAirValve",
                    "m1State",
                    "m2State",
                    "instrumentState",
                    "mainValveState",
                    "m1AirPressure",
                    "m2AirPressure",
                ],
                athexapod=["positionUpdate"],
                atdometrajectory=["followingMode"],
            )

            usages[self.valid_use_cases.OffsettingForATAOS] = UsagesResources(
                components_attr=["atmcs", "atptg", "atpneumatics", "athexapod"],
                readonly=False,
                generics=["summaryState"],
                atmcs=[
                    "allAxesInPosition",
                    "target",
                    "mount_AzEl_Encoders",
                    "position",
                    "mount_Nasmyth_Encoders",
                ],
                atptg=["timeAndDate", "poriginOffset", "focusNameSelected"],
                atpneumatics=[
                    "m1SetPressure",
                    "m2SetPressure",
                    "m1OpenAirValve",
                    "m2OpenAirValve",
                    "m1CloseAirValve",
                    "m2CloseAirValve",
                    "openMasterAirSupply",
                    "openInstrumentAirValve",
                    "m1State",
                    "m2State",
                    "instrumentState",
                    "mainValveState",
                    "m1AirPressure",
                    "m2AirPressure",
                ],
                athexapod=["positionUpdate", "moveToPosition"],
            )

            usages[self.valid_use_cases.DryTest] = UsagesResources(
                components_attr=(), readonly=True
            )

            self._usages = usages

        assert self._usages is not None
        return self._usages

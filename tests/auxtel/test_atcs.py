# This file is part of ts_observatory_control
#
# Developed for the Vera Rubin Observatory Data Management System.
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

import asyncio
import copy
import logging
import typing
import unittest
import unittest.mock
from contextlib import contextmanager

import astropy.units as u
import numpy as np
import pytest
from astropy.coordinates import Angle
from astroquery.simbad import Simbad
from lsst.ts import salobj
from lsst.ts.idl.enums import ATDome, ATPneumatics
from lsst.ts.observatory.control.mock.atcs_async_mock import ATCSAsyncMock
from lsst.ts.observatory.control.utils import RotType


class TestATTCS(ATCSAsyncMock):
    def test_object_list_get(self) -> None:
        name = "HD 185975"

        object_table = self.atcs.object_list_get(name)

        assert name in self.atcs._object_list
        assert object_table is not None

    def test_object_list_clear(self) -> None:
        name = "HD 185975"

        object_table = self.atcs.object_list_get(name)

        assert name in self.atcs._object_list
        assert object_table is not None

        self.atcs.object_list_clear()

        assert len(self.atcs._object_list) == 0

    def test_object_list_remove(self) -> None:
        name = "HD 185975"

        object_table = self.atcs.object_list_get(name)

        assert name in self.atcs._object_list
        assert object_table is not None

        self.atcs.object_list_remove(name)

        assert name not in self.atcs._object_list

    def test_object_list_add(self) -> None:
        name = "HD 185975"

        object_table = Simbad.query_object(name)

        self.atcs.object_list_add(name, object_table)

        assert name in self.atcs._object_list

    def test_object_list_get_from_catalog(self) -> None:
        self.atcs.load_catalog("hd_catalog_6th_mag")

        name = "HD  68601"

        with self.assertLogs(
            self.log.name, level=logging.DEBUG
        ) as log_messages_object_list_get:
            object_table = self.atcs.object_list_get(name)

        for message in log_messages_object_list_get.output:
            assert f"Found {name} in internal catalog." in message

        assert name in self.atcs._object_list
        assert object_table is not None

        self.atcs.object_list_clear()
        self.atcs.clear_catalog()

        assert len(self.atcs._object_list) == 0

    def test_list_available_catalogs(self) -> None:
        available_catalogs = self.atcs.list_available_catalogs()

        assert "hd_catalog_6th_mag" in available_catalogs

    def test_load_catalog_and_clear_catalog(self) -> None:
        # Need to clear the catalog in case it was loaded before by another
        # test
        self.atcs.clear_catalog()

        assert not self.atcs.is_catalog_loaded()

        self.atcs.load_catalog("hd_catalog_6th_mag")

        assert self.atcs.is_catalog_loaded()

        self.atcs.clear_catalog()

        assert not self.atcs.is_catalog_loaded()

    @pytest.mark.xfail(
        reason="Access to Simbad database is sometimes flaky.",
        raises=RuntimeError,
    )
    async def test_find_target(self) -> None:
        # Make sure it searches Simbad and not local catalog
        self.atcs.clear_catalog()

        name = await self.atcs.find_target(az=-180.0, el=30.0, mag_limit=9.0)

        assert name in self.atcs._object_list

        self.atcs.object_list_clear()

    async def test_find_target_with_internal_catalog(self) -> None:
        # Clear catalog to make sure it was not loaded
        self.atcs.clear_catalog()
        # Load catalog
        self.atcs.load_catalog("hd_catalog_6th_mag")

        with self.assertLogs(
            self.log.name, level=logging.DEBUG
        ) as log_messages_find_target:
            name = await self.atcs.find_target(
                az=-180.0, el=30.0, mag_limit=4.0, mag_range=2.0, radius=2.0
            )

        for message in log_messages_find_target.output:
            assert "Searching internal catalog." in message

        assert name in self.atcs._object_list

        self.atcs.object_list_clear()

    async def test_find_target_local_catalog_fail_not_loaded(self) -> None:
        # Clear catalog to make sure it was not loaded
        self.atcs.clear_catalog()

        with pytest.raises(AssertionError):
            await self.atcs.find_target_local_catalog(az=-180.0, el=30.0, mag_limit=9.0)

    async def test_find_target_local_catalog_fail_outside_mag_limit(self) -> None:
        # Clear catalog to make sure it was not loaded
        self.atcs.clear_catalog()
        # Load catalog
        self.atcs.load_catalog("hd_catalog_6th_mag")

        with pytest.raises(RuntimeError) as excinfo:
            # Test catalog only goes to magnitude 6, search for mag = 9-11
            await self.atcs.find_target_local_catalog(
                az=-180.0, el=30.0, mag_limit=9.0, mag_range=2.0
            )

        assert "No target in local catalog with magnitude between" in str(excinfo.value)

    async def test_find_target_local_catalog_fail_outside_radius(self) -> None:
        # Clear catalog to make sure it was not loaded
        self.atcs.clear_catalog()
        # Load catalog
        self.atcs.load_catalog("hd_catalog_6th_mag")

        with pytest.raises(RuntimeError) as excinfo:
            await self.atcs.find_target_local_catalog(
                az=-180.0, el=30.0, mag_limit=4.0, mag_range=2.0, radius=0.1
            )

        assert "Could not find a valid target in the specified radius." in str(
            excinfo.value
        )

    async def test_find_target_local_catalog_loaded(self) -> None:
        # Clear catalog to make sure it was not loaded
        self.atcs.clear_catalog()
        # Load catalog
        self.atcs.load_catalog("hd_catalog_6th_mag")

        # Search close to the south pole, where there are a handfull of
        # suitable targets all the time.
        # The test catalog only has targets brighther than 6th magnitude, so
        # will use the range 4 - 6.
        name = await self.atcs.find_target_local_catalog(
            az=-180.0, el=30.0, mag_limit=4.0, mag_range=2.0, radius=2.0
        )

        assert name in self.atcs._object_list

        self.atcs.object_list_clear()

    async def test_slew_dome_to_check_false(self) -> None:
        az = 45.0
        self.atcs.check.atdome = False

        with pytest.raises(RuntimeError):
            await self.atcs.slew_dome_to(az=az)

    async def test_slew_dome_to(self) -> None:
        az = 45.0
        check = self.get_all_checks()

        await self.atcs.slew_dome_to(az=az, check=check)

        self.atcs.rem.atdometrajectory.cmd_setFollowingMode.set_start.assert_awaited_with(
            enable=False, timeout=self.atcs.fast_timeout
        )
        self.atcs.rem.atdome.evt_azimuthInPosition.flush.assert_called()

        self.atcs.rem.atdome.cmd_moveAzimuth.set_start.assert_awaited_with(
            azimuth=az, timeout=self.atcs.long_long_timeout
        )

    async def test_disable_dome_following_passing_check(self) -> None:
        check = self.get_all_checks()

        await self.atcs.disable_dome_following(check)

        self.atcs.rem.atdometrajectory.cmd_setFollowingMode.set_start.assert_awaited_with(
            enable=False, timeout=self.atcs.fast_timeout
        )

    async def test_disable_dome_following_check_false(self) -> None:
        original_check = copy.copy(self.atcs.check)

        try:
            self.atcs.check.atdometrajectory = False

            await self.atcs.disable_dome_following()

            self.atcs.rem.atdometrajectory.cmd_setFollowingMode.set_start.assert_not_awaited()
        finally:
            self.atcs.check = original_check

    async def test_disable_dome_following_check_true(self) -> None:
        original_check = copy.copy(self.atcs.check)

        try:
            self.atcs.check.atdometrajectory = True

            await self.atcs.disable_dome_following()

            self.atcs.rem.atdometrajectory.cmd_setFollowingMode.set_start.assert_awaited_with(
                enable=False, timeout=self.atcs.fast_timeout
            )
        finally:
            self.atcs.check = original_check

    async def test_enable_dome_following_passing_check(self) -> None:
        check = self.get_all_checks()

        await self.atcs.enable_dome_following(check)

        self.atcs.rem.atdometrajectory.cmd_setFollowingMode.set_start.assert_awaited_with(
            enable=True, timeout=self.atcs.fast_timeout
        )

    async def test_enable_dome_following_check_false(self) -> None:
        self.atcs.check.atdometrajectory = False

        await self.atcs.enable_dome_following()

        self.atcs.rem.atdometrajectory.cmd_setFollowingMode.set_start.assert_not_awaited()

    async def test_enable_dome_following_check_true(self) -> None:
        self.atcs.check.atdometrajectory = True

        await self.atcs.enable_dome_following()

        self.atcs.rem.atdometrajectory.cmd_setFollowingMode.set_start.assert_awaited_with(
            enable=True, timeout=self.atcs.fast_timeout
        )

    async def test_open_dome_shutter_when_closed(self) -> None:
        await self.atcs.enable()
        await self.atcs.assert_all_enabled()

        self._atdome_evt_main_door_state.state = ATDome.ShutterDoorState.CLOSED

        await self.atcs.open_dome_shutter()

        self.atcs.rem.atdome.cmd_moveShutterMainDoor.set_start.assert_awaited_with(
            open=True, timeout=self.atcs.open_dome_shutter_time
        )

    async def test_open_dome_shutter_when_open(self) -> None:
        self._atdome_evt_main_door_state.state = ATDome.ShutterDoorState.OPENED

        await self.atcs.open_dome_shutter()

        self.atcs.rem.atdome.cmd_moveShutterMainDoor.set_start.assert_not_awaited()

    async def test_open_dome_shutter_when_opening(self) -> None:
        self._atdome_evt_main_door_state.state = ATDome.ShutterDoorState.OPENING

        with pytest.raises(RuntimeError):
            await self.atcs.open_dome_shutter()

    async def test_close_dome_when_open(self) -> None:
        await self.atcs.enable()
        await self.atcs.assert_all_enabled()

        self._atdome_evt_main_door_state.state = ATDome.ShutterDoorState.OPENED

        await self.atcs.close_dome()

        self.atcs.rem.atdome.cmd_closeShutter.set_start.assert_awaited_with(
            timeout=self.atcs.open_dome_shutter_time
        )

    async def test_close_dome_when_closed(self) -> None:
        self._atdome_evt_main_door_state.state = ATDome.ShutterDoorState.CLOSED

        await self.atcs.close_dome(force=False)

        self.atcs.rem.atdome.cmd_closeShutter.set_start.assert_not_awaited()

    async def test_close_dome_when_opening(self) -> None:
        self._atdome_evt_main_door_state.state = ATDome.ShutterDoorState.OPENING

        with pytest.raises(RuntimeError):
            await self.atcs.close_dome(force=False)

    async def test_assert_m1_correction_disable_when_off(self) -> None:
        self._ataos_evt_correction_enabled.m1 = False

        await self.atcs.assert_m1_correction_disabled()

    async def test_assert_m1_correction_disable_when_on(self) -> None:
        self._ataos_evt_correction_enabled.m1 = True

        with pytest.raises(AssertionError):
            await self.atcs.assert_m1_correction_disabled()

    async def test_open_m1_cover_when_cover_closed(self) -> None:
        # make sure cover is closed
        self._atpneumatics_evt_m1_cover_state.state = (
            ATPneumatics.MirrorCoverState.CLOSED
        )

        # make sure telescope is higher than pneumatics operation limit.
        self._telescope_position.elevationCalculatedAngle = (
            np.zeros_like(self._telescope_position.elevationCalculatedAngle)
            + self.atcs.tel_el_operate_pneumatics
            + 1.0
        )

        await self.atcs.open_m1_cover()

        assert (
            self._atpneumatics_evt_instrument_state.state
            == ATPneumatics.AirValveState.CLOSED
        )

        assert (
            self._atpneumatics_evt_main_valve_state.state
            == ATPneumatics.AirValveState.OPENED
        )

        self.atcs.rem.atpneumatics.cmd_openM1Cover.start.assert_awaited_with(
            timeout=self.atcs.long_timeout
        )

        self.atcs.rem.atptg.cmd_azElTarget.set.assert_not_called()

    async def test_open_m1_cover_when_cover_closed_bellow_el_limit(self) -> None:
        await self.atcs.enable()
        await self.atcs.assert_all_enabled()

        # make sure cover is closed
        self._atpneumatics_evt_m1_cover_state.state = (
            ATPneumatics.MirrorCoverState.CLOSED
        )

        # make sure telescope is higher than pneumatics operation limit.
        self._telescope_position.elevationCalculatedAngle = (
            np.zeros_like(self._telescope_position.elevationCalculatedAngle)
            + self.atcs.tel_el_operate_pneumatics
            - 1.0
        )

        await self.atcs.open_m1_cover()

        assert (
            self._atpneumatics_evt_instrument_state.state
            == ATPneumatics.AirValveState.CLOSED
        )

        assert (
            self._atpneumatics_evt_main_valve_state.state
            == ATPneumatics.AirValveState.OPENED
        )

        self.atcs.rem.atpneumatics.cmd_openM1Cover.start.assert_awaited_with(
            timeout=self.atcs.long_timeout
        )

        self.atcs.rem.atptg.cmd_azElTarget.set.assert_called_with(
            targetName="azel_target",
            azDegs=self._telescope_position.azimuthCalculatedAngle[-1],
            elDegs=self.atcs.tel_el_operate_pneumatics,
            rotPA=np.mean(
                self._atmcs_tel_mount_nasmyth_encoders.nasmyth2CalculatedAngle
            ),
        )

    async def test_open_m1_cover_when_cover_opened(self) -> None:
        # Make sure m1 cover is OPENED
        self._atpneumatics_evt_m1_cover_state.state = (
            ATPneumatics.MirrorCoverState.OPENED
        )

        await self.atcs.open_m1_cover()

        assert (
            self._atpneumatics_evt_instrument_state.state
            == ATPneumatics.AirValveState.CLOSED
        )

        assert (
            self._atpneumatics_evt_main_valve_state.state
            == ATPneumatics.AirValveState.OPENED
        )

        # Should not be called
        self.atcs.rem.atpneumatics.cmd_openM1Cover.start.assert_not_awaited()

    async def test_open_m1_cover_when_m1_correction_enabled(self) -> None:
        self._ataos_evt_correction_enabled.m1 = True

        with pytest.raises(AssertionError):
            await self.atcs.open_m1_cover()

    async def test_close_m1_cover_when_cover_opened(self) -> None:
        # make sure cover is opened
        self._atpneumatics_evt_m1_cover_state.state = (
            ATPneumatics.MirrorCoverState.OPENED
        )

        # make sure telescope is higher than pneumatics operation limit.
        self._telescope_position.elevationCalculatedAngle = (
            np.zeros_like(self._telescope_position.elevationCalculatedAngle)
            + self.atcs.tel_el_operate_pneumatics
            + 1.0
        )

        await self.atcs.close_m1_cover()

        self.atcs.rem.atpneumatics.cmd_closeM1Cover.start.assert_awaited_with(
            timeout=self.atcs.long_timeout
        )

        self.atcs.rem.atptg.cmd_azElTarget.set.assert_not_called()

    async def test_close_m1_cover_when_cover_opened_bellow_el_limit(self) -> None:
        await self.atcs.enable()
        await self.atcs.assert_all_enabled()

        # make sure cover is opened
        self._atpneumatics_evt_m1_cover_state.state = (
            ATPneumatics.MirrorCoverState.OPENED
        )

        # make sure telescope is lower than pneumatics operation limit.
        self._telescope_position.elevationCalculatedAngle = (
            np.zeros_like(self._telescope_position.elevationCalculatedAngle)
            + self.atcs.tel_el_operate_pneumatics
            - 1.0
        )

        await self.atcs.close_m1_cover()

        self.atcs.rem.atpneumatics.cmd_closeM1Cover.start.assert_awaited_with(
            timeout=self.atcs.long_timeout
        )

        self.atcs.rem.atptg.cmd_azElTarget.set.assert_called_with(
            targetName="azel_target",
            azDegs=self._telescope_position.azimuthCalculatedAngle[-1],
            elDegs=self.atcs.tel_el_operate_pneumatics,
            rotPA=np.mean(
                self._atmcs_tel_mount_nasmyth_encoders.nasmyth2CalculatedAngle
            ),
        )

    async def test_close_m1_cover_when_cover_closed(self) -> None:
        # Make sure m1 cover is CLOSED
        self._atpneumatics_evt_m1_cover_state.state = (
            ATPneumatics.MirrorCoverState.CLOSED
        )

        await self.atcs.close_m1_cover()

        # Should not be called
        self.atcs.rem.atpneumatics.cmd_closeM1Cover.start.assert_not_awaited()

    async def test_close_m1_cover_when_m1_correction_enabled(self) -> None:
        self._ataos_evt_correction_enabled.m1 = True

        with pytest.raises(AssertionError):
            await self.atcs.close_m1_cover()

    async def test_open_m1_vent_when_closed(self) -> None:
        await self.atcs.enable()
        await self.atcs.assert_all_enabled()

        await self.atcs.open_m1_vent()

        assert (
            self._atpneumatics_evt_instrument_state.state
            == ATPneumatics.AirValveState.OPENED
        )

        assert (
            self._atpneumatics_evt_main_valve_state.state
            == ATPneumatics.AirValveState.OPENED
        )

        self.atcs.rem.atpneumatics.cmd_openM1CellVents.start.assert_awaited_with(
            timeout=self.atcs.long_timeout
        )
        assert (
            self._atpneumatics_evt_m1_vents_position.position
            == ATPneumatics.VentsPosition.OPENED
        )

    async def test_open_m1_vent_when_opened(self) -> None:
        await self.atcs.enable()
        await self.atcs.assert_all_enabled()

        self._atpneumatics_evt_m1_vents_position.position = (
            ATPneumatics.VentsPosition.OPENED
        )

        await self.atcs.open_m1_vent()

        assert (
            self._atpneumatics_evt_instrument_state.state
            == ATPneumatics.AirValveState.OPENED
        )

        assert (
            self._atpneumatics_evt_main_valve_state.state
            == ATPneumatics.AirValveState.OPENED
        )

        self.atcs.rem.atpneumatics.cmd_openM1CellVents.start.assert_not_awaited()

        assert (
            self._atpneumatics_evt_m1_vents_position.position
            == ATPneumatics.VentsPosition.OPENED
        )

    async def test_open_m1_vent_when_partiallyopened(self) -> None:
        self._atpneumatics_evt_m1_vents_position.position = (
            ATPneumatics.VentsPosition.PARTIALLYOPENED
        )

        with pytest.raises(RuntimeError):
            await self.atcs.open_m1_vent()

    async def test_open_m1_vent_when_m1_correction_enabled(self) -> None:
        self._ataos_evt_correction_enabled.m1 = True

        with pytest.raises(AssertionError):
            await self.atcs.open_m1_vent()

    async def test_home_dome_pressing_home_switch(self) -> None:
        """This is a test for a special condition when the dome is pressing the
        home switch.
        """
        self._atdome_position.azimuthPosition = 0.0
        # Test that warning message is posted
        with self.assertLogs(self.log.name, level=logging.WARNING):
            await self.atcs.home_dome()

        self.atcs.rem.atdome.cmd_homeAzimuth.start.assert_awaited()

    async def test_home_dome_close_to_pressing_home_switch(self) -> None:
        """This is a test for a special condition when the dome is close
        to pressing the home switch, but not exactly.
        """
        self._atdome_position.azimuthPosition = 9.0e-4

        with self.assertLogs(
            self.log.name, level=logging.DEBUG
        ) as home_dome_log_messages:
            await self.atcs.home_dome()

        self.atcs.rem.atdome.cmd_homeAzimuth.start.assert_awaited()

        # Test that warning message was not posted
        for message in home_dome_log_messages.output:
            assert "WARNING" not in message

    async def test_home_dome(self) -> None:
        self._atdome_position.azimuthPosition = 45

        with self.assertLogs(
            self.log.name, level=logging.DEBUG
        ) as home_dome_log_messages:
            await self.atcs.home_dome()

        self.atcs.rem.atdome.cmd_homeAzimuth.start.assert_awaited()

        # Test that warning message was not posted
        for message in home_dome_log_messages.output:
            assert "WARNING" not in message

    async def test_is_dome_homed(self) -> None:
        self._atdome_evt_azimuth_state.homed = False
        assert not await self.atcs.is_dome_homed()

        self._atdome_evt_azimuth_state.homed = True
        assert await self.atcs.is_dome_homed()

    async def test_prepare_for_flatfield(self) -> None:
        await self.atcs.enable()
        await self.atcs.assert_all_enabled()

        check = self.get_all_checks()

        await self.atcs.prepare_for_flatfield(check)

        # make sure atdometrajectory following mode was disabled.
        self.atcs.rem.atdometrajectory.cmd_setFollowingMode.set_start.assert_awaited_with(
            enable=False, timeout=self.atcs.fast_timeout
        )

        # make sure m1 mirror cover was opened
        self.atcs.rem.atpneumatics.cmd_openM1Cover.start.assert_awaited_with(
            timeout=self.atcs.long_timeout
        )
        assert (
            self._atpneumatics_evt_m1_cover_state.state
            == ATPneumatics.MirrorCoverState.OPENED
        )

        # make sure telescope slew to the flat field position
        self.atcs.rem.atptg.cmd_azElTarget.set.assert_called_with(
            targetName="FlatField position",
            azDegs=self.atcs.tel_flat_az,
            elDegs=self.atcs.tel_flat_el,
            rotPA=self.atcs.tel_flat_rot,
        )

        self.atcs.rem.atdome.cmd_moveAzimuth.set_start.assert_awaited_with(
            azimuth=self.atcs.dome_flat_az, timeout=self.atcs.long_long_timeout
        )

    async def test_prepare_for_onsky(self) -> None:
        await self.atcs.enable()
        await self.atcs.assert_all_enabled()

        original_check = copy.copy(self.atcs.check)

        self.atcs.check = self.get_all_checks()

        try:
            await self.atcs.prepare_for_onsky()
        finally:
            self.atcs.check = original_check

        assert self._atdome_evt_main_door_state.state == ATDome.ShutterDoorState.OPENED
        assert (
            self._atpneumatics_evt_m1_cover_state.state
            == ATPneumatics.MirrorCoverState.OPENED
        )
        assert (
            self._atpneumatics_evt_m1_vents_position.position
            == ATPneumatics.VentsPosition.OPENED
        )
        self.atcs.rem.ataos.cmd_enableCorrection.set_start.assert_awaited_with(
            m1=True, hexapod=True, atspectrograph=True, timeout=self.atcs.long_timeout
        )

        atdometreajectory_cmd_set_following_mode_expected_calls = [
            unittest.mock.call(enable=False, timeout=self.atcs.fast_timeout),
            unittest.mock.call(enable=True, timeout=self.atcs.fast_timeout),
        ]

        self.atcs.rem.atdometrajectory.cmd_setFollowingMode.set_start.assert_has_awaits(
            atdometreajectory_cmd_set_following_mode_expected_calls
        )

    async def test_prepare_for_onsky_no_scb_link(self) -> None:
        await self.atcs.enable()
        await self.atcs.assert_all_enabled()

        original_check = copy.copy(self.atcs.check)

        self.atcs.check = self.get_all_checks()

        self._atdome_evt_scb_link.active = False
        try:
            with pytest.raises(RuntimeError):
                await self.atcs.prepare_for_onsky()
        finally:
            self.atcs.check = original_check

    async def test_prepare_for_vent_partially_open(self) -> None:
        await self.atcs.enable()
        self.dome_slit_positioning_time = 120.0
        self.atcs.dome_vent_open_shutter_time = 0.5
        (
            telescope_vent_position,
            dome_vent_position,
        ) = self.atcs.get_telescope_and_dome_vent_azimuth()

        await self.atcs.prepare_for_vent(partially_open_dome=True)

        assert (
            self._atdome_evt_main_door_state.state
            == ATDome.ShutterDoorState.PARTIALLYOPENED
        )
        assert (
            self._atpneumatics_evt_m1_cover_state.state
            == ATPneumatics.MirrorCoverState.CLOSED
        )
        self.atcs.rem.ataos.cmd_enableCorrection.set_start.assert_awaited_with(
            m1=True, hexapod=True, atspectrograph=True, timeout=self.atcs.long_timeout
        )
        self.atcs.rem.ataos.cmd_disableCorrection.set_start.assert_awaited_with(
            disableAll=True, timeout=self.atcs.long_timeout
        )

        atdometreajectory_cmd_set_following_mode_expected_calls = [
            unittest.mock.call(enable=False, timeout=self.atcs.fast_timeout),
        ]

        self.atcs.rem.atdometrajectory.cmd_setFollowingMode.set_start.assert_has_awaits(
            atdometreajectory_cmd_set_following_mode_expected_calls
        )
        self.atcs.rem.atdome.cmd_moveAzimuth.set_start.assert_awaited_with(
            azimuth=pytest.approx(dome_vent_position, abs=0.25),
            timeout=self.atcs.long_long_timeout,
        )
        self.atcs.rem.atdome.cmd_stopMotion.start.assert_awaited_with(
            timeout=self.atcs.fast_timeout
        )
        self.atcs.rem.atptg.cmd_azElTarget.set.assert_called_with(
            targetName="Vent Position",
            azDegs=telescope_vent_position,
            elDegs=self.atcs.tel_vent_el,
            rotPA=self.atcs.tel_park_rot,
        )

    async def test_prepare_for_vent_keep_dome_closed(self) -> None:
        await self.atcs.enable()
        self.dome_slit_positioning_time = 120.0
        self.atcs.dome_vent_open_shutter_time = 0.5
        (
            telescope_vent_position,
            dome_vent_position,
        ) = self.atcs.get_telescope_and_dome_vent_azimuth()

        await self.atcs.prepare_for_vent()

        assert self._atdome_evt_main_door_state.state == ATDome.ShutterDoorState.CLOSED
        assert (
            self._atpneumatics_evt_m1_cover_state.state
            == ATPneumatics.MirrorCoverState.CLOSED
        )
        self.atcs.rem.ataos.cmd_enableCorrection.set_start.assert_awaited_with(
            m1=True, hexapod=True, atspectrograph=True, timeout=self.atcs.long_timeout
        )
        self.atcs.rem.ataos.cmd_disableCorrection.set_start.assert_awaited_with(
            disableAll=True, timeout=self.atcs.long_timeout
        )

        atdometreajectory_cmd_set_following_mode_expected_calls = [
            unittest.mock.call(enable=False, timeout=self.atcs.fast_timeout),
        ]

        self.atcs.rem.atdometrajectory.cmd_setFollowingMode.set_start.assert_has_awaits(
            atdometreajectory_cmd_set_following_mode_expected_calls
        )
        self.atcs.rem.atdome.cmd_moveAzimuth.set_start.assert_awaited_with(
            azimuth=pytest.approx(dome_vent_position, abs=0.25),
            timeout=self.atcs.long_long_timeout,
        )
        self.atcs.rem.atdome.cmd_stopMotion.start.assert_not_awaited()
        self.atcs.rem.atptg.cmd_azElTarget.set.assert_called_with(
            targetName="Vent Position",
            azDegs=telescope_vent_position,
            elDegs=self.atcs.tel_vent_el,
            rotPA=self.atcs.tel_park_rot,
        )

    async def test_shutdown(self) -> None:
        await self.atcs.enable()
        await self.atcs.assert_all_enabled()

        original_check = copy.copy(self.atcs.check)

        self.atcs.check = self.get_all_checks()

        try:
            # Make sure everything is opened
            self._atpneumatics_evt_m1_vents_position.position = (
                ATPneumatics.VentsPosition.OPENED
            )
            self._atpneumatics_evt_m1_cover_state.state = (
                ATPneumatics.MirrorCoverState.OPENED
            )
            self._atdome_evt_main_door_state.state = ATDome.ShutterDoorState.OPENED

            await self.atcs.shutdown()
        finally:
            self.atcs.check = original_check

        assert (
            self._atpneumatics_evt_m1_vents_position.position
            == ATPneumatics.VentsPosition.CLOSED
        )
        assert (
            self._atpneumatics_evt_m1_cover_state.state
            == ATPneumatics.MirrorCoverState.CLOSED
        )
        assert self._atdome_evt_main_door_state.state == ATDome.ShutterDoorState.CLOSED

    async def test_set_azel_slew_checks(self) -> None:
        original_check = copy.copy(self.atcs.check)

        check = self.atcs.set_azel_slew_checks(True)

        for comp in self.atcs.components_attr:
            assert getattr(self.atcs.check, comp) == getattr(original_check, comp)

        for comp in {"atdome", "atdometrajectory"}:
            assert getattr(check, comp)

        check = self.atcs.set_azel_slew_checks(False)

        for comp in {"atdome", "atdometrajectory"}:
            assert not getattr(check, comp)

    async def test_enable(self) -> None:
        original_check = copy.copy(self.atcs.check)

        check = self.get_all_checks()
        self.atcs.check = check
        try:
            await self.atcs.enable()
        finally:
            self.atcs.check = original_check

    async def test_enable_with_settings(self) -> None:
        original_check = copy.copy(self.atcs.check)

        check = self.get_all_checks()
        self.atcs.check = check
        try:
            await self.atcs.enable(
                dict([(component, "config") for component in self.atcs.components_attr])
            )
        finally:
            self.atcs.check = original_check

    async def test_standby(self) -> None:
        original_check = copy.copy(self.atcs.check)

        check = self.get_all_checks()
        self.atcs.check = check
        try:
            await self.atcs.standby()
        finally:
            self.atcs.check = original_check

    async def test_stop_tracking(self) -> None:
        await self.atcs.stop_tracking()

        self.atcs.rem.atptg.cmd_stopTracking.start.assert_called_with(
            timeout=self.atcs.fast_timeout
        )

        self.atcs.rem.atmcs.evt_atMountState.flush.assert_called()
        self.atcs.rem.atmcs.evt_atMountState.aget.assert_called_with(
            timeout=self.atcs.long_timeout
        )

        self.atcs.rem.atmcs.evt_allAxesInPosition.flush.assert_called()
        self.atcs.rem.atmcs.evt_allAxesInPosition.aget.assert_called_with(
            timeout=self.atcs.fast_timeout
        )

    async def test_monitor_position_dome_following_enabled(self) -> None:
        original_check = copy.copy(self.atcs.check)

        self.atcs.check = self.get_all_checks()

        try:
            start_az = 1.0
            end_az = 0.9

            self._telescope_position.azimuthCalculatedAngle = np.linspace(
                start_az,
                end_az,
                len(self._telescope_position.azimuthCalculatedAngle),
            )

            self._atdometrajectory_dome_following.enabled = True

            task = asyncio.create_task(self.atcs.monitor_position())

            await asyncio.sleep(2.0)

            assert not task.done()

            start_az = 0.1
            end_az = 0.0

            self._telescope_position.azimuthCalculatedAngle = np.linspace(
                start_az,
                end_az,
                len(self._telescope_position.azimuthCalculatedAngle),
            )

            await asyncio.sleep(2.0)

            assert not task.done()

            self.atcs.stop_monitor()

            await asyncio.wait_for(task, timeout=self.atcs.fast_timeout)

            assert task.exception() is None
        finally:
            self.atcs.check = original_check

        self.atcs.next_telescope_target.assert_called_with(
            timeout=self.atcs.long_timeout
        )
        self.atcs.next_telescope_position.assert_called_with(
            timeout=self.atcs.fast_timeout
        )
        self.atcs.rem.atmcs.tel_mount_Nasmyth_Encoders.next.assert_called_with(
            flush=True, timeout=self.atcs.fast_timeout
        )

        self.atcs.rem.atdome.tel_position.next.assert_called_with(
            flush=True, timeout=self.atcs.fast_timeout
        )
        self.atcs.rem.atdome.evt_azimuthCommandedState.aget.assert_called_with(
            timeout=self.atcs.fast_timeout
        )

    async def test_monitor_position_dome_following_disabled(self) -> None:
        original_check = copy.copy(self.atcs.check)

        self.atcs.check = self.get_all_checks()

        try:
            start_az = 1.0
            end_az = 0.9

            self._telescope_position.azimuthCalculatedAngle = np.linspace(
                start_az,
                end_az,
                len(self._telescope_position.azimuthCalculatedAngle),
            )

            self._atdometrajectory_dome_following.enabled = False

            task = asyncio.create_task(self.atcs.monitor_position())

            await asyncio.sleep(2.0)

            assert not task.done()

            start_az = 0.1
            end_az = 0.0

            self._telescope_position.azimuthCalculatedAngle = np.linspace(
                start_az,
                end_az,
                len(self._telescope_position.azimuthCalculatedAngle),
            )

            await asyncio.sleep(2.0)

            assert not task.done()

            self.atcs.stop_monitor()

            await asyncio.wait_for(task, timeout=self.atcs.fast_timeout)

            assert task.exception() is None
        finally:
            self.atcs.check = original_check

        self.atcs.next_telescope_target.assert_called_with(
            timeout=self.atcs.long_timeout
        )
        self.atcs.next_telescope_position.assert_called_with(
            timeout=self.atcs.fast_timeout
        )
        self.atcs.rem.atmcs.tel_mount_Nasmyth_Encoders.next.assert_called_with(
            flush=True, timeout=self.atcs.fast_timeout
        )

        self.atcs.rem.atdome.tel_position.next.assert_not_called()
        self.atcs.rem.atdome.evt_azimuthCommandedState.aget.assert_not_called()

    async def test_slew_icrs(self) -> None:
        await self.atcs.enable()
        await self.atcs.assert_all_enabled()

        name = "HD 185975"
        ra = "20 28 18.7402"
        dec = "-87 28 19.938"

        await self.atcs.slew_icrs(ra=ra, dec=dec, target_name=name)

        self.atcs.rem.atptg.cmd_raDecTarget.set.assert_called_with(
            ra=Angle(ra, unit=u.hourangle).hour,
            declination=Angle(dec, unit=u.deg).deg,
            targetName=name,
            frame=self.atcs.CoordFrame.ICRS,
            rotAngle=0.0,
            rotStartFrame=self.atcs.RotFrame.TARGET,
            rotTrackFrame=self.atcs.RotFrame.TARGET,
            azWrapStrategy=self.atcs.WrapStrategy.MAXTIMEONTARGET,
            timeOnTarget=0.0,
            epoch=2000,
            equinox=2000,
            parallax=0,
            pmRA=0,
            pmDec=0,
            rv=0,
            dRA=0.0,
            dDec=0.0,
            rotMode=self.atcs.RotMode.FIELD,
        )

        self.atcs.rem.atptg.cmd_poriginOffset.set.assert_called_with(dx=0, dy=0, num=0)

        self.atcs.rem.atptg.cmd_stopTracking.start.assert_not_awaited()

    async def test_slew_object(self) -> None:
        await self.atcs.enable()
        await self.atcs.assert_all_enabled()

        name = "HD 185975"

        radec_icrs = self.atcs.object_list_get(name)

        await self.atcs.slew_object(name=name)

        self.atcs.rem.atptg.cmd_stopTracking.start.assert_not_awaited()

        self.atcs.rem.atptg.cmd_raDecTarget.set.assert_called_with(
            ra=radec_icrs.ra.hour,
            declination=radec_icrs.dec.deg,
            targetName=name,
            frame=self.atcs.CoordFrame.ICRS,
            rotAngle=0.0,
            rotStartFrame=self.atcs.RotFrame.TARGET,
            rotTrackFrame=self.atcs.RotFrame.TARGET,
            azWrapStrategy=self.atcs.WrapStrategy.MAXTIMEONTARGET,
            timeOnTarget=0.0,
            epoch=2000,
            equinox=2000,
            parallax=0,
            pmRA=0,
            pmDec=0,
            rv=0,
            dRA=0.0,
            dDec=0.0,
            rotMode=self.atcs.RotMode.FIELD,
        )

        self.atcs.rem.atptg.cmd_poriginOffset.set.assert_called_with(dx=0, dy=0, num=0)

    async def test_slew_icrs_no_stop(self) -> None:
        await self.atcs.enable()
        await self.atcs.assert_all_enabled()

        name = "HD 185975"
        ra = "20:28:18.74"
        dec = "-87:28:19.9"

        await self.atcs.slew_icrs(
            ra=ra, dec=dec, target_name=name, stop_before_slew=False
        )

        self.atcs.rem.atptg.cmd_raDecTarget.set.assert_called_with(
            ra=Angle(ra, unit=u.hourangle).hour,
            declination=Angle(dec, unit=u.deg).deg,
            targetName=name,
            frame=self.atcs.CoordFrame.ICRS,
            rotAngle=0.0,
            rotStartFrame=self.atcs.RotFrame.TARGET,
            rotTrackFrame=self.atcs.RotFrame.TARGET,
            azWrapStrategy=self.atcs.WrapStrategy.MAXTIMEONTARGET,
            timeOnTarget=0.0,
            epoch=2000,
            equinox=2000,
            parallax=0,
            pmRA=0,
            pmDec=0,
            rv=0,
            dRA=0.0,
            dDec=0.0,
            rotMode=self.atcs.RotMode.FIELD,
        )

        self.atcs.rem.atptg.cmd_poriginOffset.set.assert_called_with(dx=0, dy=0, num=0)

        self.atcs.rem.atptg.cmd_stopTracking.start.assert_not_called()

        self.atcs.rem.atptg.cmd_raDecTarget.start.assert_called()
        self.atcs.rem.atptg.cmd_poriginOffset.start.assert_called_with(
            timeout=self.atcs.fast_timeout
        )

    async def test_slew_icrs_rot(self) -> None:
        await self.atcs.enable()
        await self.atcs.assert_all_enabled()

        name = "HD 185975"
        ra = "20:28:18.74"
        dec = "-87:28:19.9"
        rot = 45.0

        await self.atcs.slew_icrs(
            ra=ra, dec=dec, rot=rot, rot_type=RotType.Sky, target_name=name
        )

        self.atcs.rem.atptg.cmd_raDecTarget.set.assert_called_with(
            ra=Angle(ra, unit=u.hourangle).hour,
            declination=Angle(dec, unit=u.deg).deg,
            targetName=name,
            frame=self.atcs.CoordFrame.ICRS,
            rotAngle=rot,
            rotStartFrame=self.atcs.RotFrame.TARGET,
            rotTrackFrame=self.atcs.RotFrame.TARGET,
            azWrapStrategy=self.atcs.WrapStrategy.MAXTIMEONTARGET,
            timeOnTarget=0.0,
            epoch=2000,
            equinox=2000,
            parallax=0,
            pmRA=0,
            pmDec=0,
            rv=0,
            dRA=0.0,
            dDec=0.0,
            rotMode=self.atcs.RotMode.FIELD,
        )

        self.atcs.rem.atptg.cmd_poriginOffset.set.assert_called_with(dx=0, dy=0, num=0)

        self.atcs.rem.atptg.cmd_stopTracking.start.assert_not_awaited()

        self.atcs.rem.atptg.cmd_raDecTarget.start.assert_awaited()
        self.atcs.rem.atptg.cmd_poriginOffset.start.assert_awaited_with(
            timeout=self.atcs.fast_timeout
        )

    async def test_slew_icrs_rot_physical(self) -> None:
        await self.atcs.enable()
        await self.atcs.assert_all_enabled()

        name = "HD 185975"
        ra = "20:28:18.74"
        dec = "-87:28:19.9"
        rot = 45.0

        await self.atcs.slew_icrs(
            ra=ra, dec=dec, rot=rot, rot_type=RotType.Physical, target_name=name
        )

        self.atcs.rem.atptg.cmd_raDecTarget.set.assert_called_with(
            ra=Angle(ra, unit=u.hourangle).hour,
            declination=Angle(dec, unit=u.deg).deg,
            targetName=name,
            frame=self.atcs.CoordFrame.ICRS,
            rotAngle=rot,
            rotStartFrame=self.atcs.RotFrame.FIXED,
            rotTrackFrame=self.atcs.RotFrame.FIXED,
            azWrapStrategy=self.atcs.WrapStrategy.MAXTIMEONTARGET,
            timeOnTarget=0.0,
            epoch=2000,
            equinox=2000,
            parallax=0,
            pmRA=0,
            pmDec=0,
            rv=0,
            dRA=0.0,
            dDec=0.0,
            rotMode=self.atcs.RotMode.FIELD,
        )

        self.atcs.rem.atptg.cmd_poriginOffset.set.assert_called_with(dx=0, dy=0, num=0)

        self.atcs.rem.atptg.cmd_raDecTarget.start.assert_awaited()
        self.atcs.rem.atptg.cmd_poriginOffset.start.assert_awaited_with(
            timeout=self.atcs.fast_timeout
        )

    async def test_slew_icrs_rot_physical_sky(self) -> None:
        await self.atcs.enable()
        await self.atcs.assert_all_enabled()

        name = "HD 185975"
        ra = "20:28:18.74"
        dec = "-87:28:19.9"
        rot = 45.0

        await self.atcs.slew_icrs(
            ra=ra, dec=dec, rot=rot, rot_type=RotType.PhysicalSky, target_name=name
        )

        self.atcs.rem.atptg.cmd_raDecTarget.set.assert_called_with(
            ra=Angle(ra, unit=u.hourangle).hour,
            declination=Angle(dec, unit=u.deg).deg,
            targetName=name,
            frame=self.atcs.CoordFrame.ICRS,
            rotAngle=rot,
            rotStartFrame=self.atcs.RotFrame.FIXED,
            rotTrackFrame=self.atcs.RotFrame.TARGET,
            azWrapStrategy=self.atcs.WrapStrategy.MAXTIMEONTARGET,
            timeOnTarget=0.0,
            epoch=2000,
            equinox=2000,
            parallax=0,
            pmRA=0,
            pmDec=0,
            rv=0,
            dRA=0.0,
            dDec=0.0,
            rotMode=self.atcs.RotMode.FIELD,
        )

        self.atcs.rem.atptg.cmd_poriginOffset.set.assert_called_with(dx=0, dy=0, num=0)

        self.atcs.rem.atptg.cmd_stopTracking.start.assert_not_awaited()

        self.atcs.rem.atptg.cmd_raDecTarget.start.assert_awaited()
        self.atcs.rem.atptg.cmd_poriginOffset.start.assert_awaited_with(
            timeout=self.atcs.fast_timeout
        )

    async def test_slew_icrs_rot_sky_init_angle_out_of_range(self) -> None:
        await self.atcs.enable()
        await self.atcs.assert_all_enabled()

        name = "HD 185975"
        ra = "20:28:18.74"
        dec = "-87:28:19.9"
        rot = 45.0

        with self.fail_ra_dec_target("angle_out_of_range"):
            await self.atcs.slew_icrs(
                ra=ra, dec=dec, rot=rot, rot_type=RotType.Sky, target_name=name
            )

        atptg_cmd_ra_dec_target_expected_calls = [
            unittest.mock.call(
                ra=Angle(ra, unit=u.hourangle).hour,
                declination=Angle(dec, unit=u.deg).deg,
                targetName=name,
                frame=self.atcs.CoordFrame.ICRS,
                rotAngle=rot,
                rotStartFrame=self.atcs.RotFrame.TARGET,
                rotTrackFrame=self.atcs.RotFrame.TARGET,
                azWrapStrategy=self.atcs.WrapStrategy.MAXTIMEONTARGET,
                timeOnTarget=0.0,
                epoch=2000,
                equinox=2000,
                parallax=0,
                pmRA=0,
                pmDec=0,
                rv=0,
                dRA=0.0,
                dDec=0.0,
                rotMode=self.atcs.RotMode.FIELD,
            ),
            unittest.mock.call(
                ra=Angle(ra, unit=u.hourangle).hour,
                declination=Angle(dec, unit=u.deg).deg,
                targetName=name,
                frame=self.atcs.CoordFrame.ICRS,
                rotAngle=rot + 180.0,
                rotStartFrame=self.atcs.RotFrame.TARGET,
                rotTrackFrame=self.atcs.RotFrame.TARGET,
                azWrapStrategy=self.atcs.WrapStrategy.MAXTIMEONTARGET,
                timeOnTarget=0.0,
                epoch=2000,
                equinox=2000,
                parallax=0,
                pmRA=0,
                pmDec=0,
                rv=0,
                dRA=0.0,
                dDec=0.0,
                rotMode=self.atcs.RotMode.FIELD,
            ),
        ]

        self.atcs.rem.atptg.cmd_raDecTarget.set.assert_has_calls(
            atptg_cmd_ra_dec_target_expected_calls
        )

        self.atcs.rem.atptg.cmd_poriginOffset.set.assert_called_with(dx=0, dy=0, num=0)

        self.atcs.rem.atptg.cmd_stopTracking.start.assert_not_awaited()

        self.atcs.rem.atptg.cmd_raDecTarget.start.assert_awaited()
        self.atcs.rem.atptg.cmd_poriginOffset.start.assert_awaited_with(
            timeout=self.atcs.fast_timeout
        )

    async def test_slew_icrs_fail_runtimeerror(self) -> None:
        await self.atcs.enable()
        await self.atcs.assert_all_enabled()

        name = "HD 185975"
        ra = "20:28:18.74"
        dec = "-87:28:19.9"
        rot = 45.0

        with self.fail_ra_dec_target("Test fail"), self.assertRaisesRegex(
            RuntimeError, "Test fail"
        ):
            await self.atcs.slew_icrs(
                ra=ra, dec=dec, rot=rot, rot_type=RotType.Sky, target_name=name
            )

        self.atcs.rem.atptg.cmd_raDecTarget.start.assert_awaited_once()

    async def test_slew_icrs_with_offset(self) -> None:
        await self.atcs.enable()
        await self.atcs.assert_all_enabled()

        name = "HD 185975"
        ra = "20:28:18.74"
        dec = "-87:28:19.9"
        offset_x = 10.0
        offset_y = -10.0

        await self.atcs.slew_icrs(
            ra=ra, dec=dec, offset_x=offset_x, offset_y=offset_y, target_name=name
        )

        self.atcs.rem.atptg.cmd_raDecTarget.set.assert_called_with(
            ra=Angle(ra, unit=u.hourangle).hour,
            declination=Angle(dec, unit=u.deg).deg,
            targetName=name,
            frame=self.atcs.CoordFrame.ICRS,
            rotAngle=0.0,
            rotStartFrame=self.atcs.RotFrame.TARGET,
            rotTrackFrame=self.atcs.RotFrame.TARGET,
            azWrapStrategy=self.atcs.WrapStrategy.MAXTIMEONTARGET,
            timeOnTarget=0.0,
            epoch=2000,
            equinox=2000,
            parallax=0,
            pmRA=0,
            pmDec=0,
            rv=0,
            dRA=0.0,
            dDec=0.0,
            rotMode=self.atcs.RotMode.FIELD,
        )

        self.atcs.rem.atptg.cmd_poriginOffset.set.assert_called_with(
            dx=offset_x * self.atcs.plate_scale,
            dy=offset_y * self.atcs.plate_scale,
            num=0,
        )

        self.atcs.rem.atptg.cmd_stopTracking.start.assert_not_awaited()

        self.atcs.rem.atptg.cmd_raDecTarget.start.assert_awaited()
        self.atcs.rem.atptg.cmd_poriginOffset.start.assert_awaited_with(
            timeout=self.atcs.fast_timeout
        )

    async def test_point_azel(self) -> None:
        await self.atcs.enable()
        await self.atcs.assert_all_enabled()

        az = 180.0
        el = 45.0
        rot_tel = 45
        target_name = "test_position"

        await self.atcs.point_azel(
            az=az, el=el, rot_tel=rot_tel, target_name=target_name
        )

        self.atcs.rem.atptg.cmd_azElTarget.set.assert_called_with(
            targetName=target_name,
            azDegs=az,
            elDegs=el,
            rotPA=rot_tel,
        )

        self.atcs.rem.atptg.cmd_poriginOffset.set.assert_not_called()

        self.atcs.rem.atptg.cmd_stopTracking.start.assert_not_called()

    async def test_offset_radec(self) -> None:
        # Test offset_radec
        ra_offset, dec_offset = 10.0, -10.0
        await self.atcs.offset_radec(ra=ra_offset, dec=dec_offset)

        self.atcs.rem.atptg.cmd_offsetRADec.set_start.assert_called_with(
            type=0, off1=ra_offset, off2=dec_offset, num=0
        )

    async def test_offset_azel(self) -> None:
        az_offset, el_offset = 10.0, -10.0

        # Default call should yield relative=True, absorb=False
        await self.atcs.offset_azel(az=az_offset, el=el_offset)

        self.atcs.rem.atptg.cmd_offsetAzEl.set_start.assert_called_with(
            az=az_offset, el=el_offset, num=1
        )

    async def test_offset_azel_with_defaults(self) -> None:
        az_offset, el_offset = 10.0, -10.0

        # Same as default but now pass the parameters
        await self.atcs.offset_azel(
            az=az_offset, el=el_offset, relative=True, absorb=False
        )

        self.atcs.rem.atptg.cmd_offsetAzEl.set_start.assert_called_with(
            az=az_offset, el=el_offset, num=1
        )

    async def test_offset_azel_not_relative(self) -> None:
        az_offset, el_offset = 10.0, -10.0

        # Call with relative=False
        await self.atcs.offset_azel(
            az=az_offset, el=el_offset, relative=False, absorb=False
        )

        self.atcs.rem.atptg.cmd_offsetAzEl.set_start.assert_called_with(
            az=az_offset, el=el_offset, num=0
        )

    async def test_offset_azel_relative_absorb(self) -> None:
        az_offset, el_offset = 10.0, -10.0

        # Call with relative=True and absorb=True
        await self.atcs.offset_azel(
            az=az_offset, el=el_offset, relative=True, absorb=True
        )

        bore_sight_angle = (
            np.mean(self._telescope_position.elevationCalculatedAngle)
            - np.mean(self._atmcs_tel_mount_nasmyth_encoders.nasmyth2CalculatedAngle)
            + 90.0
        )

        x, y, _ = np.matmul(
            [self.atcs.parity_x * el_offset, self.atcs.parity_y * az_offset, 0.0],
            self.atcs.rotation_matrix(bore_sight_angle),
        )

        self.atcs.rem.atptg.cmd_poriginOffset.set_start.assert_called_with(
            dx=x * self.atcs.plate_scale, dy=y * self.atcs.plate_scale, num=1
        )

    async def test_offset_azel_absorb(self) -> None:
        az_offset, el_offset = 10.0, -10.0

        # Call with relative=False and absorb=True
        await self.atcs.offset_azel(
            az=az_offset, el=el_offset, relative=False, absorb=True
        )

        bore_sight_angle = (
            np.mean(self._telescope_position.elevationCalculatedAngle)
            - np.mean(self._atmcs_tel_mount_nasmyth_encoders.nasmyth2CalculatedAngle)
            + 90.0
        )

        x, y, _ = np.matmul(
            [self.atcs.parity_x * el_offset, self.atcs.parity_y * az_offset, 0.0],
            self.atcs.rotation_matrix(bore_sight_angle),
        )
        self.atcs.rem.atptg.cmd_poriginOffset.set_start.assert_called_with(
            dx=x * self.atcs.plate_scale,
            dy=y * self.atcs.plate_scale,
            num=0,
        )

    async def test_reset_offsets(self) -> None:
        await self.atcs.reset_offsets()

        self.atcs.rem.atptg.cmd_poriginClear.set_start.assert_any_call(
            num=0, timeout=self.atcs.fast_timeout
        )

        self.atcs.rem.atptg.cmd_poriginClear.set_start.assert_any_call(
            num=1, timeout=self.atcs.fast_timeout
        )

        self.atcs.rem.atptg.cmd_offsetClear.set_start.assert_any_call(
            num=0, timeout=self.atcs.fast_timeout
        )

        self.atcs.rem.atptg.cmd_offsetClear.set_start.assert_any_call(
            num=1, timeout=self.atcs.fast_timeout
        )

    async def test_reset_offsets_absorbed(self) -> None:
        await self.atcs.reset_offsets(absorbed=True, non_absorbed=False)

        self.atcs.rem.atptg.cmd_poriginClear.set_start.assert_any_call(
            num=0, timeout=self.atcs.fast_timeout
        )

        self.atcs.rem.atptg.cmd_poriginClear.set_start.assert_any_call(
            num=1, timeout=self.atcs.fast_timeout
        )

        self.atcs.rem.atptg.cmd_offsetClear.set_start.assert_not_called()

    async def test_reset_offsets_non_absorbed(self) -> None:
        await self.atcs.reset_offsets(absorbed=False, non_absorbed=True)

        self.atcs.rem.atptg.cmd_poriginClear.set_start.assert_not_called()

        self.atcs.rem.atptg.cmd_offsetClear.set_start.assert_any_call(
            num=0, timeout=self.atcs.fast_timeout
        )

        self.atcs.rem.atptg.cmd_offsetClear.set_start.assert_any_call(
            num=1, timeout=self.atcs.fast_timeout
        )

    async def test_offset_xy(self) -> None:
        x_offset, y_offset = 10.0, -10.0

        # Default call should yield relative=True, absorb=False
        await self.atcs.offset_xy(x=x_offset, y=y_offset)

        bore_sight_angle = (
            np.mean(self._telescope_position.elevationCalculatedAngle)
            - np.mean(self._atmcs_tel_mount_nasmyth_encoders.nasmyth2CalculatedAngle)
            + 90.0
        )

        el, az, _ = np.matmul(
            [self.atcs.parity_x * x_offset, self.atcs.parity_y * y_offset, 0.0],
            self.atcs.rotation_matrix(bore_sight_angle),
        )

        self.atcs.rem.atptg.cmd_offsetAzEl.set_start.assert_called_with(
            az=az, el=el, num=1
        )

    async def test_offset_xy_with_defaults(self) -> None:
        x_offset, y_offset = 10.0, -10.0

        # Same as default but now pass the parameters
        await self.atcs.offset_xy(x=x_offset, y=y_offset, relative=True, absorb=False)

        bore_sight_angle = (
            np.mean(self._telescope_position.elevationCalculatedAngle)
            - np.mean(self._atmcs_tel_mount_nasmyth_encoders.nasmyth2CalculatedAngle)
            + 90.0
        )

        el, az, _ = np.matmul(
            [self.atcs.parity_x * x_offset, self.atcs.parity_y * y_offset, 0.0],
            self.atcs.rotation_matrix(bore_sight_angle),
        )

        self.atcs.rem.atptg.cmd_offsetAzEl.set_start.assert_called_with(
            az=az, el=el, num=1
        )

    async def test_offset_xy_not_relative(self) -> None:
        x_offset, y_offset = 10.0, -10.0

        # Call with relative=False
        await self.atcs.offset_xy(x=x_offset, y=y_offset, relative=False, absorb=False)

        bore_sight_angle = (
            np.mean(self._telescope_position.elevationCalculatedAngle)
            - np.mean(self._atmcs_tel_mount_nasmyth_encoders.nasmyth2CalculatedAngle)
            + 90.0
        )

        el, az, _ = np.matmul(
            [self.atcs.parity_x * x_offset, self.atcs.parity_y * y_offset, 0.0],
            self.atcs.rotation_matrix(bore_sight_angle),
        )

        self.atcs.rem.atptg.cmd_offsetAzEl.set_start.assert_called_with(
            az=az, el=el, num=0
        )

    async def test_offset_xy_relative_absorb(self) -> None:
        x_offset, y_offset = 10.0, -10.0

        # Call with relative=True and absorb=True
        await self.atcs.offset_xy(x=x_offset, y=y_offset, relative=True, absorb=True)

        self.atcs.rem.atptg.cmd_poriginOffset.set_start.assert_called_with(
            dx=x_offset * self.atcs.plate_scale,
            dy=y_offset * self.atcs.plate_scale,
            num=1,
        )

    async def test_offset_xy_absorb(self) -> None:
        x_offset, y_offset = 10.0, -10.0

        # Call with relative=False and absorb=True
        await self.atcs.offset_xy(x=x_offset, y=y_offset, relative=False, absorb=True)

        self.atcs.rem.atptg.cmd_poriginOffset.set_start.assert_called_with(
            dx=x_offset * self.atcs.plate_scale,
            dy=y_offset * self.atcs.plate_scale,
            num=0,
        )

    async def test_open_valves(self) -> None:
        await self.atcs.enable()
        await self.atcs.assert_all_enabled()

        await self.atcs.open_valves()

        self.atcs.rem.atpneumatics.evt_instrumentState.aget.assert_awaited_with(
            timeout=self.atcs.fast_timeout
        )

        self.atcs.rem.atpneumatics.evt_instrumentState.flush.assert_called()

        self.atcs.rem.atpneumatics.cmd_openInstrumentAirValve.start.assert_awaited_with(
            timeout=self.atcs.long_timeout
        )

        self.atcs.rem.atpneumatics.evt_instrumentState.next.assert_awaited_with(
            flush=False, timeout=self.atcs.long_timeout
        )

        assert (
            self._atpneumatics_evt_instrument_state.state
            == ATPneumatics.AirValveState.OPENED
        )

        self.atcs.rem.atpneumatics.evt_mainValveState.aget.assert_awaited_with(
            timeout=self.atcs.fast_timeout
        )

        self.atcs.rem.atpneumatics.evt_mainValveState.flush.assert_called()

        self.atcs.rem.atpneumatics.cmd_openMasterAirSupply.start.assert_awaited_with(
            timeout=self.atcs.long_timeout
        )

        self.atcs.rem.atpneumatics.evt_mainValveState.next.assert_awaited_with(
            flush=False, timeout=self.atcs.long_timeout
        )

        assert (
            self._atpneumatics_evt_main_valve_state.state
            == ATPneumatics.AirValveState.OPENED
        )

    async def test_open_valve_instrument(self) -> None:
        await self.atcs.open_valve_instrument()

        self.atcs.rem.atpneumatics.evt_instrumentState.aget.assert_awaited_with(
            timeout=self.atcs.fast_timeout
        )

        self.atcs.rem.atpneumatics.evt_instrumentState.flush.assert_called()

        self.atcs.rem.atpneumatics.cmd_openInstrumentAirValve.start.assert_awaited_with(
            timeout=self.atcs.long_timeout
        )

        self.atcs.rem.atpneumatics.evt_instrumentState.next.assert_awaited_with(
            flush=False, timeout=self.atcs.long_timeout
        )

        assert (
            self._atpneumatics_evt_instrument_state.state
            == ATPneumatics.AirValveState.OPENED
        )

    async def test_open_valve_main(self) -> None:
        await self.atcs.open_valve_main()

        self.atcs.rem.atpneumatics.evt_mainValveState.aget.assert_awaited_with(
            timeout=self.atcs.fast_timeout
        )

        self.atcs.rem.atpneumatics.evt_mainValveState.flush.assert_called()

        self.atcs.rem.atpneumatics.cmd_openMasterAirSupply.start.assert_awaited_with(
            timeout=self.atcs.long_timeout
        )

        self.atcs.rem.atpneumatics.evt_mainValveState.next.assert_awaited_with(
            flush=False, timeout=self.atcs.long_timeout
        )

        assert (
            self._atpneumatics_evt_main_valve_state.state
            == ATPneumatics.AirValveState.OPENED
        )

    def test_get_rot_angle_alternatives_default(self) -> None:
        expected_rot_angle_alternatives = [0.0, 180.0, -180.0, 90.0, -90.0]

        count_alternatives = 0

        for rot_angle_alternative in self.atcs.get_rot_angle_alternatives(0.0):
            assert rot_angle_alternative in expected_rot_angle_alternatives
            count_alternatives += 1
        assert count_alternatives == len(expected_rot_angle_alternatives)

    def test_set_get_rot_angle_alternatives_empty(self) -> None:
        self.atcs.set_rot_angle_alternatives([])

        expected_rot_angle_alternatives = [0.0]

        count_alternatives = 0

        for rot_angle_alternative in self.atcs.get_rot_angle_alternatives(0.0):
            assert rot_angle_alternative in expected_rot_angle_alternatives
            count_alternatives += 1

        assert count_alternatives == len(expected_rot_angle_alternatives)

    def test_set_rot_angle_alternatives_zero(self) -> None:
        self.atcs.set_rot_angle_alternatives([0, 0.0, 180.0, -180.0])

        expected_rot_angle_alternatives = [0.0, 180.0, -180.0]

        count_alternatives = 0

        for rot_angle_alternative in self.atcs.get_rot_angle_alternatives(0.0):
            assert rot_angle_alternative in expected_rot_angle_alternatives
            count_alternatives += 1

        assert count_alternatives == len(expected_rot_angle_alternatives)

    def test_set_rot_angle_alternatives_duplicated_entries(self) -> None:
        self.atcs.set_rot_angle_alternatives(
            [0, 0.0, 180.0, -180.0, 180.0, -180.0, 180, -180]
        )

        expected_rot_angle_alternatives = [0.0, 180.0, -180.0]

        count_alternatives = 0

        for rot_angle_alternative in self.atcs.get_rot_angle_alternatives(0.0):
            assert rot_angle_alternative in expected_rot_angle_alternatives
            count_alternatives += 1

        assert count_alternatives == len(expected_rot_angle_alternatives)

    def _handle_fail_angle_out_of_range(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> None:
        if self.atcs.rem.atptg.cmd_raDecTarget.start.await_count < 2:
            raise salobj.AckError(
                "Target out of rotator limit",
                ackcmd=salobj.AckCmdDataType(
                    private_seqNum="",
                    ack=salobj.sal_enums.SalRetCode.CMD_FAILED,
                    error=101,
                    result="Target out of rotator limit",
                ),
            )

    @contextmanager
    def fail_ra_dec_target(self, fail_type: str) -> typing.Generator[None, None, None]:
        if fail_type == "angle_out_of_range":
            self.atcs.rem.atptg.cmd_raDecTarget.start.side_effect = (
                self._handle_fail_angle_out_of_range
            )
        else:
            self.atcs.rem.atptg.cmd_raDecTarget.start.side_effect = RuntimeError(
                fail_type
            )

        yield
        self.atcs.rem.atptg.cmd_raDecTarget.start.side_effect = None

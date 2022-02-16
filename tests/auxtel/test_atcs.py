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
import copy
import types
import asyncio
import logging
import unittest

import numpy as np
import pytest

import astropy.units as u
from astropy.coordinates import ICRS, Angle

from astroquery.simbad import Simbad

from lsst.ts import idl
from lsst.ts.idl.enums import ATMCS, ATPtg, ATPneumatics, ATDome
from lsst.ts import salobj

from lsst.ts.observatory.control.auxtel.atcs import ATCS, ATCSUsages
from lsst.ts.observatory.control.utils import RotType


class TestATTCS(unittest.IsolatedAsyncioTestCase):
    def get_all_checks(self):
        check = copy.copy(self.atcs.check)
        for comp in self.atcs.components_attr:
            setattr(check, comp, True)

        return check

    def test_object_list_get(self):

        name = "HD 185975"

        object_table = self.atcs.object_list_get(name)

        assert name in self.atcs._object_list
        assert object_table is not None

    def test_object_list_clear(self):

        name = "HD 185975"

        object_table = self.atcs.object_list_get(name)

        assert name in self.atcs._object_list
        assert object_table is not None

        self.atcs.object_list_clear()

        assert len(self.atcs._object_list) == 0

    def test_object_list_remove(self):

        name = "HD 185975"

        object_table = self.atcs.object_list_get(name)

        assert name in self.atcs._object_list
        assert object_table is not None

        self.atcs.object_list_remove(name)

        assert name not in self.atcs._object_list

    def test_object_list_add(self):

        name = "HD 185975"

        object_table = Simbad.query_object(name)

        self.atcs.object_list_add(name, object_table)

        assert name in self.atcs._object_list

    def test_object_list_get_from_catalog(self):

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

    def test_list_available_catalogs(self):

        available_catalogs = self.atcs.list_available_catalogs()

        assert "hd_catalog_6th_mag" in available_catalogs

    def test_load_catalog_and_clear_catalog(self):

        # Need to clear the catalog in case it was loaded before by another
        # test
        self.atcs.clear_catalog()

        assert not self.atcs.is_catalog_loaded()

        self.atcs.load_catalog("hd_catalog_6th_mag")

        assert self.atcs.is_catalog_loaded()

        self.atcs.clear_catalog()

        assert not self.atcs.is_catalog_loaded()

    async def test_find_target(self):

        # Make sure it searches Simbad and not local catalog
        self.atcs.clear_catalog()

        name = await self.atcs.find_target(az=-180.0, el=30.0, mag_limit=9.0)

        assert name in self.atcs._object_list

        self.atcs.object_list_clear()

    async def test_find_target_with_internal_catalog(self):
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

    async def test_find_target_local_catalog_fail_not_loaded(self):

        # Clear catalog to make sure it was not loaded
        self.atcs.clear_catalog()

        with pytest.raises(RuntimeError):
            await self.atcs.find_target_local_catalog(az=-180.0, el=30.0, mag_limit=9.0)

    async def test_find_target_local_catalog_fail_outside_mag_limit(self):

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

    async def test_find_target_local_catalog_fail_outside_radius(self):

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

    async def test_find_target_local_catalog_loaded(self):

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

    async def test_slew_dome_to_check_false(self):

        az = 45.0
        self.atcs.check.atdome = False

        with pytest.raises(RuntimeError):
            await self.atcs.slew_dome_to(az=az)

    async def test_slew_dome_to(self):
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

    async def test_disable_dome_following_passing_check(self):

        check = self.get_all_checks()

        await self.atcs.disable_dome_following(check)

        self.atcs.rem.atdometrajectory.cmd_setFollowingMode.set_start.assert_awaited_with(
            enable=False, timeout=self.atcs.fast_timeout
        )

    async def test_disable_dome_following_check_false(self):

        original_check = copy.copy(self.atcs.check)

        try:
            self.atcs.check.atdometrajectory = False

            await self.atcs.disable_dome_following()

            self.atcs.rem.atdometrajectory.cmd_setFollowingMode.set_start.assert_not_awaited()
        finally:
            self.atcs.check = original_check

    async def test_disable_dome_following_check_true(self):

        original_check = copy.copy(self.atcs.check)

        try:
            self.atcs.check.atdometrajectory = True

            await self.atcs.disable_dome_following()

            self.atcs.rem.atdometrajectory.cmd_setFollowingMode.set_start.assert_awaited_with(
                enable=False, timeout=self.atcs.fast_timeout
            )
        finally:
            self.atcs.check = original_check

    async def test_enable_dome_following_passing_check(self):

        check = self.get_all_checks()

        await self.atcs.enable_dome_following(check)

        self.atcs.rem.atdometrajectory.cmd_setFollowingMode.set_start.assert_awaited_with(
            enable=True, timeout=self.atcs.fast_timeout
        )

    async def test_enable_dome_following_check_false(self):

        self.atcs.check.atdometrajectory = False

        await self.atcs.enable_dome_following()

        self.atcs.rem.atdometrajectory.cmd_setFollowingMode.set_start.assert_not_awaited()

    async def test_enable_dome_following_check_true(self):

        self.atcs.check.atdometrajectory = True

        await self.atcs.enable_dome_following()

        self.atcs.rem.atdometrajectory.cmd_setFollowingMode.set_start.assert_awaited_with(
            enable=True, timeout=self.atcs.fast_timeout
        )

    async def test_open_dome_shutter_when_closed(self):

        self._atdome_evt_main_door_state.state = ATDome.ShutterDoorState.CLOSED

        await self.atcs.open_dome_shutter()

        self.atcs.rem.atdome.cmd_moveShutterMainDoor.set_start.assert_awaited_with(
            open=True, timeout=self.atcs.open_dome_shutter_time
        )

    async def test_open_dome_shutter_when_open(self):

        self._atdome_evt_main_door_state.state = ATDome.ShutterDoorState.OPENED

        await self.atcs.open_dome_shutter()

        self.atcs.rem.atdome.cmd_moveShutterMainDoor.set_start.assert_not_awaited()

    async def test_open_dome_shutter_when_opening(self):

        self._atdome_evt_main_door_state.state = ATDome.ShutterDoorState.OPENING

        with pytest.raises(RuntimeError):
            await self.atcs.open_dome_shutter()

    async def test_close_dome_when_open(self):

        self._atdome_evt_main_door_state.state = ATDome.ShutterDoorState.OPENED

        await self.atcs.close_dome()

        self.atcs.rem.atdome.cmd_closeShutter.set_start.assert_awaited_with(
            timeout=self.atcs.open_dome_shutter_time
        )

    async def test_close_dome_when_closed(self):

        self._atdome_evt_main_door_state.state = ATDome.ShutterDoorState.CLOSED

        await self.atcs.close_dome()

        self.atcs.rem.atdome.cmd_closeShutter.set_start.assert_not_awaited()

    async def test_close_dome_when_opening(self):

        self._atdome_evt_main_door_state.state = ATDome.ShutterDoorState.OPENING

        with pytest.raises(RuntimeError):
            await self.atcs.close_dome()

    async def test_assert_m1_correction_disable_when_off(self):

        self._ataos_evt_correction_enabled.m1 = False

        await self.atcs.assert_m1_correction_disabled()

    async def test_assert_m1_correction_disable_when_on(self):

        self._ataos_evt_correction_enabled.m1 = True

        with pytest.raises(AssertionError):
            await self.atcs.assert_m1_correction_disabled()

    async def test_open_m1_cover_when_cover_closed(self):

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

    async def test_open_m1_cover_when_cover_closed_bellow_el_limit(self):

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

    async def test_open_m1_cover_when_cover_opened(self):

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

    async def test_open_m1_cover_when_m1_correction_enabled(self):

        self._ataos_evt_correction_enabled.m1 = True

        with pytest.raises(AssertionError):
            await self.atcs.open_m1_cover()

    async def test_close_m1_cover_when_cover_opened(self):

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

    async def test_close_m1_cover_when_cover_opened_bellow_el_limit(self):

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

    async def test_close_m1_cover_when_cover_closed(self):

        # Make sure m1 cover is CLOSED
        self._atpneumatics_evt_m1_cover_state.state = (
            ATPneumatics.MirrorCoverState.CLOSED
        )

        await self.atcs.close_m1_cover()

        # Should not be called
        self.atcs.rem.atpneumatics.cmd_closeM1Cover.start.assert_not_awaited()

    async def test_close_m1_cover_when_m1_correction_enabled(self):

        self._ataos_evt_correction_enabled.m1 = True

        with pytest.raises(AssertionError):
            await self.atcs.close_m1_cover()

    async def test_open_m1_vent_when_closed(self):

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

    async def test_open_m1_vent_when_opened(self):

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

    async def test_open_m1_vent_when_partiallyopened(self):

        self._atpneumatics_evt_m1_vents_position.position = (
            ATPneumatics.VentsPosition.PARTIALLYOPENED
        )

        with pytest.raises(RuntimeError):
            await self.atcs.open_m1_vent()

    async def test_open_m1_vent_when_m1_correction_enabled(self):

        self._ataos_evt_correction_enabled.m1 = True

        with pytest.raises(AssertionError):
            await self.atcs.open_m1_vent()

    async def test_home_dome_pressing_home_switch(self):
        """This is a test for a special condition when the dome is pressing the
        home switch.
        """
        self._atdome_position.azimuthPosition = 0.0
        # Test that warning message is posted
        with self.assertLogs(self.log.name, level=logging.WARNING):
            await self.atcs.home_dome()

        self.atcs.rem.atdome.cmd_homeAzimuth.start.assert_awaited()

    async def test_home_dome_close_to_pressing_home_switch(self):
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

    async def test_home_dome(self):

        self._atdome_position.azimuthPosition = 45

        with self.assertLogs(
            self.log.name, level=logging.DEBUG
        ) as home_dome_log_messages:
            await self.atcs.home_dome()

        self.atcs.rem.atdome.cmd_homeAzimuth.start.assert_awaited()

        # Test that warning message was not posted
        for message in home_dome_log_messages.output:
            assert "WARNING" not in message

    async def test_prepare_for_flatfield(self):

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

    async def test_prepare_for_onsky(self):

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

    async def test_prepare_for_onsky_no_scb_link(self):

        original_check = copy.copy(self.atcs.check)

        self.atcs.check = self.get_all_checks()

        self._atdome_evt_scb_link.active = False
        try:
            with pytest.raises(RuntimeError):
                await self.atcs.prepare_for_onsky()
        finally:
            self.atcs.check = original_check

    async def test_shutdown(self):

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

    async def test_set_azel_slew_checks(self):

        original_check = copy.copy(self.atcs.check)

        check = self.atcs.set_azel_slew_checks(True)

        for comp in self.atcs.components_attr:
            assert getattr(self.atcs.check, comp) == getattr(original_check, comp)

        for comp in {"atdome", "atdometrajectory"}:
            assert getattr(check, comp)

        check = self.atcs.set_azel_slew_checks(False)

        for comp in {"atdome", "atdometrajectory"}:
            assert not getattr(check, comp)

    async def test_enable(self):
        original_check = copy.copy(self.atcs.check)

        check = self.get_all_checks()
        self.atcs.check = check
        try:
            await self.atcs.enable()
        finally:
            self.atcs.check = original_check

    async def test_enable_with_settings(self):
        original_check = copy.copy(self.atcs.check)

        check = self.get_all_checks()
        self.atcs.check = check
        try:
            await self.atcs.enable(
                dict([(component, "config") for component in self.atcs.components_attr])
            )
        finally:
            self.atcs.check = original_check

    async def test_standby(self):
        original_check = copy.copy(self.atcs.check)

        check = self.get_all_checks()
        self.atcs.check = check
        try:
            await self.atcs.standby()
        finally:
            self.atcs.check = original_check

    async def test_stop_tracking(self):

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

    async def test_monitor_position(self):

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

            assert task.done()
            assert task.exception() is None
            await task
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

    async def test_slew_icrs(self):

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

    async def test_slew_object(self):

        name = "HD 185975"

        object_table = self.atcs.object_list_get(name)

        radec_icrs = ICRS(
            Angle(object_table["RA"], unit=u.hourangle),
            Angle(object_table["DEC"], unit=u.deg),
        )

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

    async def test_slew_icrs_no_stop(self):

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

    async def test_slew_icrs_rot(self):

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

    async def test_slew_icrs_rot_physical(self):

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

    async def test_slew_icrs_rot_physical_sky(self):

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

    async def test_slew_icrs_with_offset(self):

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

    async def test_point_azel(self):

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

    async def test_offset_radec(self):

        # Test offset_radec
        ra_offset, dec_offset = 10.0, -10.0
        await self.atcs.offset_radec(ra=ra_offset, dec=dec_offset)

        self.atcs.rem.atptg.cmd_offsetRADec.set_start.assert_called_with(
            type=0, off1=ra_offset, off2=dec_offset, num=0
        )

    async def test_offset_azel(self):

        az_offset, el_offset = 10.0, -10.0

        # Default call should yield relative=True, absorb=False
        await self.atcs.offset_azel(az=az_offset, el=el_offset)

        self.atcs.rem.atptg.cmd_offsetAzEl.set_start.assert_called_with(
            az=az_offset, el=el_offset, num=1
        )

    async def test_offset_azel_with_defaults(self):

        az_offset, el_offset = 10.0, -10.0

        # Same as default but now pass the parameters
        await self.atcs.offset_azel(
            az=az_offset, el=el_offset, relative=True, absorb=False
        )

        self.atcs.rem.atptg.cmd_offsetAzEl.set_start.assert_called_with(
            az=az_offset, el=el_offset, num=1
        )

    async def test_offset_azel_not_relative(self):

        az_offset, el_offset = 10.0, -10.0

        # Call with relative=False
        await self.atcs.offset_azel(
            az=az_offset, el=el_offset, relative=False, absorb=False
        )

        self.atcs.rem.atptg.cmd_offsetAzEl.set_start.assert_called_with(
            az=az_offset, el=el_offset, num=0
        )

    async def test_offset_azel_relative_absorb(self):

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

    async def test_offset_azel_absorb(self):

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

    async def test_reset_offsets(self):

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

    async def test_reset_offsets_absorbed(self):

        await self.atcs.reset_offsets(absorbed=True, non_absorbed=False)

        self.atcs.rem.atptg.cmd_poriginClear.set_start.assert_any_call(
            num=0, timeout=self.atcs.fast_timeout
        )

        self.atcs.rem.atptg.cmd_poriginClear.set_start.assert_any_call(
            num=1, timeout=self.atcs.fast_timeout
        )

        self.atcs.rem.atptg.cmd_offsetClear.set_start.assert_not_called()

    async def test_reset_offsets_non_absorbed(self):

        await self.atcs.reset_offsets(absorbed=False, non_absorbed=True)

        self.atcs.rem.atptg.cmd_poriginClear.set_start.assert_not_called()

        self.atcs.rem.atptg.cmd_offsetClear.set_start.assert_any_call(
            num=0, timeout=self.atcs.fast_timeout
        )

        self.atcs.rem.atptg.cmd_offsetClear.set_start.assert_any_call(
            num=1, timeout=self.atcs.fast_timeout
        )

    async def test_offset_xy(self):

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

    async def test_offset_xy_with_defaults(self):

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

    async def test_offset_xy_not_relative(self):

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

    async def test_offset_xy_relative_absorb(self):

        x_offset, y_offset = 10.0, -10.0

        # Call with relative=True and absorb=True
        await self.atcs.offset_xy(x=x_offset, y=y_offset, relative=True, absorb=True)

        self.atcs.rem.atptg.cmd_poriginOffset.set_start.assert_called_with(
            dx=x_offset * self.atcs.plate_scale,
            dy=y_offset * self.atcs.plate_scale,
            num=1,
        )

    async def test_offset_xy_absorb(self):

        x_offset, y_offset = 10.0, -10.0

        # Call with relative=False and absorb=True
        await self.atcs.offset_xy(x=x_offset, y=y_offset, relative=False, absorb=True)

        self.atcs.rem.atptg.cmd_poriginOffset.set_start.assert_called_with(
            dx=x_offset * self.atcs.plate_scale,
            dy=y_offset * self.atcs.plate_scale,
            num=0,
        )

    async def test_open_valves(self):

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

    async def test_open_valve_instrument(self):

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

    async def test_open_valve_main(self):

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

    def test_check_interface_atmcs(self):
        self.check_topic_attribute(
            attributes={"elevationCalculatedAngle", "azimuthCalculatedAngle"},
            topic="mount_AzEl_Encoders",
            component="ATMCS",
        )

        self.check_topic_attribute(
            attributes={
                "trackId",
                "elevation",
                "azimuth",
                "nasmyth1RotatorAngle",
                "nasmyth2RotatorAngle",
            },
            topic="logevent_target",
            component="ATMCS",
        )

        self.check_topic_attribute(
            attributes={"inPosition"},
            topic="logevent_allAxesInPosition",
            component="ATMCS",
        )

        self.check_topic_attribute(
            attributes={"state"},
            topic="logevent_atMountState",
            component="ATMCS",
        )

        self.check_topic_attribute(
            attributes={"private_sndStamp"},
            topic="command_stopTracking",
            component="ATMCS",
        )

        self.check_topic_attribute(
            attributes={"nasmyth1CalculatedAngle", "nasmyth2CalculatedAngle"},
            topic="mount_Nasmyth_Encoders",
            component="ATMCS",
        )

    def test_check_interface_athexapod(self):

        self.check_topic_attribute(
            attributes={"private_sndStamp"},
            topic="logevent_positionUpdate",
            component="ATHexapod",
        )

    def test_check_interface_ataos(self):

        self.check_topic_attribute(
            attributes={"private_sndStamp"},
            topic="command_applyFocusOffset",
            component="ATAOS",
        )

        self.check_topic_attribute(
            attributes={"m1", "m2", "atspectrograph"},
            topic="command_enableCorrection",
            component="ATAOS",
        )

        self.check_topic_attribute(
            attributes={"disableAll"},
            topic="command_disableCorrection",
            component="ATAOS",
        )

        self.check_topic_attribute(
            attributes={"private_sndStamp"},
            topic="logevent_atspectrographCorrectionStarted",
            component="ATAOS",
        )

        self.check_topic_attribute(
            attributes={"private_sndStamp"},
            topic="logevent_atspectrographCorrectionCompleted",
            component="ATAOS",
        )

    def test_check_interface_atdometrajectory(self):

        self.check_topic_attribute(
            attributes={"enable"},
            topic="command_setFollowingMode",
            component="ATDomeTrajectory",
        )

    def test_check_interface_atdome(self):

        self.check_topic_attribute(
            attributes={"private_sndStamp"},
            topic="logevent_azimuthInPosition",
            component="ATDome",
        )

        self.check_topic_attribute(
            attributes={"azimuth"},
            topic="command_moveAzimuth",
            component="ATDome",
        )

        self.check_topic_attribute(
            attributes={"private_sndStamp"},
            topic="command_stopMotion",
            component="ATDome",
        )

        self.check_topic_attribute(
            attributes={"active"},
            topic="logevent_scbLink",
            component="ATDome",
        )

        self.check_topic_attribute(
            attributes={"state"},
            topic="logevent_mainDoorState",
            component="ATDome",
        )

        self.check_topic_attribute(
            attributes={"open"},
            topic="command_moveShutterMainDoor",
            component="ATDome",
        )

        self.check_topic_attribute(
            attributes={"homing"},
            topic="logevent_azimuthState",
            component="ATDome",
        )

        self.check_topic_attribute(
            attributes={"private_sndStamp"},
            topic="command_closeShutter",
            component="ATDome",
        )

        self.check_topic_attribute(
            attributes={"inPosition"},
            topic="logevent_shutterInPosition",
            component="ATDome",
        )

    def test_check_interface_atptg(self):

        self.check_topic_attribute(
            attributes={
                "ra",
                "declination",
                "targetName",
                "frame",
                "rotAngle",
                "rotStartFrame",
                "rotTrackFrame",
                "azWrapStrategy",
                "timeOnTarget",
                "epoch",
                "equinox",
                "parallax",
                "pmRA",
                "pmDec",
                "rv",
                "dRA",
                "dDec",
                "rotMode",
            },
            topic="command_raDecTarget",
            component="ATPtg",
        )

        self.check_topic_attribute(
            attributes={
                "targetName",
                "azDegs",
                "elDegs",
                "rotPA",
            },
            topic="command_azElTarget",
            component="ATPtg",
        )

        self.check_topic_attribute(
            attributes={
                "dx",
                "dy",
                "num",
            },
            topic="command_poriginOffset",
            component="ATPtg",
        )

        self.check_topic_attribute(
            attributes={"type", "off1", "off2", "num"},
            topic="command_offsetRADec",
            component="ATPtg",
        )

        self.check_topic_attribute(
            attributes={"az", "el", "num"},
            topic="command_offsetAzEl",
            component="ATPtg",
        )

    def test_check_interface_atpneumatics(self):
        component = "ATPneumatics"

        self.check_topic_attribute(
            attributes={"state"},
            topic="logevent_m1CoverState",
            component=component,
        )

        self.check_topic_attribute(
            attributes={"position"},
            topic="logevent_m1VentsPosition",
            component=component,
        )

        self.check_topic_attribute(
            attributes={"state"},
            topic="logevent_mainValveState",
            component=component,
        )

        self.check_topic_attribute(
            attributes={"state"},
            topic="logevent_instrumentState",
            component=component,
        )

        self.check_topic_attribute(
            attributes={"private_sndStamp"},
            topic="command_openM1Cover",
            component=component,
        )

        self.check_topic_attribute(
            attributes={"private_sndStamp"},
            topic="command_closeM1Cover",
            component=component,
        )

        self.check_topic_attribute(
            attributes={"private_sndStamp"},
            topic="command_openM1CellVents",
            component=component,
        )

        self.check_topic_attribute(
            attributes={"private_sndStamp"},
            topic="command_closeM1CellVents",
            component=component,
        )

        self.check_topic_attribute(
            attributes={"private_sndStamp"},
            topic="command_openMasterAirSupply",
            component=component,
        )

        self.check_topic_attribute(
            attributes={"private_sndStamp"},
            topic="command_closeMasterAirSupply",
            component=component,
        )

        self.check_topic_attribute(
            attributes={"private_sndStamp"},
            topic="command_openInstrumentAirValve",
            component=component,
        )

        self.check_topic_attribute(
            attributes={"private_sndStamp"},
            topic="command_m1CloseAirValve",
            component=component,
        )

    def check_topic_attribute(self, attributes, topic, component):
        for attribute in attributes:
            assert (
                attribute
                in self.components_metadata[component].topic_info[topic].field_info
            )

    @classmethod
    def setUpClass(cls):
        """This classmethod is only called once, when preparing the unit
        test.
        """

        cls.log = logging.getLogger(__name__)

        # Pass in a string as domain to prevent ATCS from trying to create a
        # domain by itself. When using DryTest usage, the class won't create
        # any remote. When this method is called there is no event loop
        # running so all asyncio facilities will fail to create. This is later
        # rectified in the asyncSetUp.
        cls.atcs = ATCS(
            domain="FakeDomain", log=cls.log, intended_usage=ATCSUsages.DryTest
        )

        # Decrease telescope settle time to speed up unit test
        cls.atcs.tel_settle_time = 0.25

        # Gather metadada information, needed to validate topics versions
        cls.components_metadata = dict(
            [
                (
                    component,
                    salobj.parse_idl(
                        component,
                        idl.get_idl_dir()
                        / f"sal_revCoded_{component.split(':')[0]}.idl",
                    ),
                )
                for component in cls.atcs.components
            ]
        )

        cls.track_id_gen = salobj.index_generator(1)

    async def asyncSetUp(self):

        # Setup asyncio facilities that probably failed while setting up class
        self.atcs._create_asyncio_events()

        # Setup required ATAOS data
        self._ataos_evt_correction_enabled = types.SimpleNamespace(
            m1=False,
            hexapod=False,
            m2=False,
            focus=False,
            atspectrograph=False,
            moveWhileExposing=False,
        )

        # Setup required ATPtg data
        self._atptg_evt_focus_name_selected = types.SimpleNamespace(
            focus=ATPtg.Foci.NASMYTH2
        )

        # Setup required ATMCS data
        self._telescope_position = types.SimpleNamespace(
            elevationCalculatedAngle=np.zeros(100) + 80.0,
            azimuthCalculatedAngle=np.zeros(100),
        )

        self._atmcs_tel_mount_nasmyth_encoders = types.SimpleNamespace(
            nasmyth1CalculatedAngle=np.zeros(100), nasmyth2CalculatedAngle=np.zeros(100)
        )

        self._telescope_target_position = types.SimpleNamespace(
            trackId=next(self.track_id_gen),
            elevation=80.0,
            azimuth=0.0,
            nasmyth1RotatorAngle=0.0,
            nasmyth2RotatorAngle=0.0,
        )

        self._atmcs_all_axes_in_position = types.SimpleNamespace(inPosition=True)

        self._atmcs_evt_at_mount_state = types.SimpleNamespace(
            state=int(ATMCS.AtMountState.TRACKINGDISABLED)
        )

        # Setup required ATDome data
        self._atdome_position = types.SimpleNamespace(azimuthPosition=0.0)

        self._atdome_azimth_commanded_state = types.SimpleNamespace(azimuth=0.0)

        self._atdome_evt_azimuth_state = types.SimpleNamespace(
            homing=False, _taken=False
        )

        self._atdome_evt_scb_link = types.SimpleNamespace(active=True)

        self._atdome_evt_main_door_state = types.SimpleNamespace(
            state=ATDome.ShutterDoorState.CLOSED
        )

        # Setup required ATPneumatics data
        self._atpneumatics_evt_m1_cover_state = types.SimpleNamespace(
            state=ATPneumatics.MirrorCoverState.CLOSED
        )

        self._atpneumatics_evt_m1_vents_position = types.SimpleNamespace(
            position=ATPneumatics.VentsPosition.CLOSED
        )

        self._atpneumatics_evt_instrument_state = types.SimpleNamespace(
            state=ATPneumatics.AirValveState.CLOSED
        )

        self._atpneumatics_evt_main_valve_state = types.SimpleNamespace(
            state=ATPneumatics.AirValveState.CLOSED
        )

        # Setup data to support summary state manipulation
        self.summary_state = dict(
            [
                (comp, types.SimpleNamespace(summaryState=int(salobj.State.ENABLED)))
                for comp in self.atcs.components_attr
            ]
        )

        self.summary_state_queue = dict(
            [
                (comp, [types.SimpleNamespace(summaryState=int(salobj.State.ENABLED))])
                for comp in self.atcs.components_attr
            ]
        )

        self.summary_state_queue_event = dict(
            [(comp, asyncio.Event()) for comp in self.atcs.components_attr]
        )

        # Setup AsyncMock. The idea is to replace the placeholder for the
        # remotes (in atcs.rem) by AsyncMock. The remote for each component is
        # replaced by an AsyncMock and later augmented to emulate the behavior
        # of the Remote->Controller interaction with side_effect and
        # return_value.
        # By default all mocks are augmented to handle summary state setting.
        for component in self.atcs.components_attr:
            setattr(
                self.atcs.rem,
                component,
                unittest.mock.AsyncMock(
                    **{
                        "cmd_start.set_start.side_effect": self.set_summary_state_for(
                            component, salobj.State.DISABLED
                        ),
                        "cmd_enable.start.side_effect": self.set_summary_state_for(
                            component, salobj.State.ENABLED
                        ),
                        "cmd_disable.start.side_effect": self.set_summary_state_for(
                            component, salobj.State.DISABLED
                        ),
                        "cmd_standby.start.side_effect": self.set_summary_state_for(
                            component, salobj.State.STANDBY
                        ),
                        "evt_summaryState.next.side_effect": self.next_summary_state_for(
                            component
                        ),
                        "evt_summaryState.aget.side_effect": self.get_summary_state_for(
                            component
                        ),
                        "evt_heartbeat.next.side_effect": self.get_heartbeat,
                        "evt_heartbeat.aget.side_effect": self.get_heartbeat,
                        "evt_settingVersions.aget.return_value": None,
                    }
                ),
            )
            # A trick to support calling a regular method (flush) from an
            # AsyncMock. Basically, attach a regular Mock.
            getattr(self.atcs.rem, f"{component}").evt_summaryState.attach_mock(
                unittest.mock.Mock(),
                "flush",
            )

        # Augment ataos mock.
        self.atcs.rem.ataos.configure_mock(
            **{
                "evt_correctionEnabled.aget.side_effect": self.ataos_evt_correction_enabled
            }
        )
        # Augment atptg mock.
        self.atcs.rem.atptg.configure_mock(
            **{
                "evt_focusNameSelected.aget.side_effect": self.atptg_evt_focus_name_selected,
                "cmd_stopTracking.start.side_effect": self.atmcs_stop_tracking,
            }
        )

        self.atcs.rem.atptg.attach_mock(
            unittest.mock.AsyncMock(),
            "cmd_raDecTarget",
        )

        self.atcs.rem.atptg.cmd_raDecTarget.attach_mock(
            unittest.mock.Mock(
                **{
                    "return_value": types.SimpleNamespace(
                        **self.components_metadata["ATPtg"]
                        .topic_info["command_raDecTarget"]
                        .field_info
                    )
                }
            ),
            "DataType",
        )

        self.atcs.rem.atptg.cmd_poriginOffset.attach_mock(
            unittest.mock.Mock(),
            "set",
        )

        self.atcs.rem.atptg.cmd_raDecTarget.attach_mock(
            unittest.mock.Mock(),
            "set",
        )

        self.atcs.rem.atptg.cmd_azElTarget.attach_mock(
            unittest.mock.Mock(),
            "set",
        )

        # Augment atmcs mock
        self.atcs.rem.atmcs.configure_mock(
            **{
                "tel_mount_Nasmyth_Encoders.aget.side_effect": self.atmcs_tel_mount_nasmyth_encoders,
                "tel_mount_Nasmyth_Encoders.next.side_effect": self.atmcs_tel_mount_nasmyth_encoders,
                "evt_allAxesInPosition.next.side_effect": self.atmcs_all_axes_in_position,
                "evt_allAxesInPosition.aget.side_effect": self.atmcs_all_axes_in_position,
                "evt_atMountState.aget.side_effect": self.atmcs_evt_at_mount_state,
            }
        )

        self.atcs.rem.atmcs.evt_allAxesInPosition.attach_mock(
            unittest.mock.Mock(),
            "flush",
        )

        self.atcs.rem.atmcs.evt_atMountState.attach_mock(
            unittest.mock.Mock(),
            "flush",
        )

        self.atcs._tel_position = self._telescope_position
        self.atcs._tel_target = self._telescope_target_position

        self.atcs.next_telescope_position = unittest.mock.AsyncMock(
            side_effect=self.next_telescope_position
        )

        self.atcs.next_telescope_target = unittest.mock.AsyncMock(
            side_effect=self.next_telescope_target
        )

        # Augment atdome mock
        self.atcs.rem.atdome.configure_mock(
            **{
                "tel_position.next.side_effect": self.atdome_tel_position,
                "tel_position.aget.side_effect": self.atdome_tel_position,
                "evt_azimuthCommandedState.aget.side_effect": self.atdome_evt_azimuth_commanded_state,
                "evt_azimuthCommandedState.next.side_effect": self.atdome_evt_azimuth_commanded_state,
                "evt_azimuthState.next.side_effect": self.atdome_evt_azimuth_state,
                "evt_scbLink.aget.side_effect": self.atdome_evt_scb_link,
                "evt_mainDoorState.aget.side_effect": self.atdome_evt_main_door_state,
                "evt_mainDoorState.next.side_effect": self.atdome_evt_main_door_state,
                "cmd_homeAzimuth.start.side_effect": self.atdome_cmd_home_azimuth,
                "cmd_moveShutterMainDoor.set_start.side_effect": self.atdome_cmd_move_shutter_main_door,
                "cmd_closeShutter.set_start.side_effect": self.atdome_cmd_close_shutter,
            }
        )

        self.atcs.rem.atdome.evt_azimuthInPosition.attach_mock(
            unittest.mock.Mock(),
            "flush",
        )

        self.atcs.rem.atdome.evt_azimuthState.attach_mock(
            unittest.mock.Mock(side_effect=self.atdome_evt_azimuth_state_flush),
            "flush",
        )

        self.atcs.rem.atdome.evt_mainDoorState.attach_mock(
            unittest.mock.Mock(),
            "flush",
        )

        # Augment atpneumatics mock
        self.atcs.rem.atpneumatics.configure_mock(
            **{
                "evt_m1CoverState.aget.side_effect": self.atpneumatics_evt_m1_cover_state,
                "evt_m1CoverState.next.side_effect": self.atpneumatics_evt_m1_cover_state,
                "evt_m1VentsPosition.aget.side_effect": self.atpneumatics_evt_m1_vents_position,
                "evt_m1VentsPosition.next.side_effect": self.atpneumatics_evt_m1_vents_position,
                "evt_instrumentState.aget.side_effect": self.atpneumatics_evt_instrument_state,
                "evt_instrumentState.next.side_effect": self.atpneumatics_evt_instrument_state,
                "evt_mainValveState.aget.side_effect": self.atpneumatics_evt_main_valve_state,
                "evt_mainValveState.next.side_effect": self.atpneumatics_evt_main_valve_state,
                "cmd_openInstrumentAirValve.start.side_effect": self.atpneumatics_open_air_valve,
                "cmd_openMasterAirSupply.start.side_effect": self.atpneumatics_open_main_valve,
                "cmd_closeM1Cover.start.side_effect": self.atpneumatics_close_m1_cover,
                "cmd_openM1Cover.start.side_effect": self.atpneumatics_open_m1_cover,
                "cmd_openM1CellVents.start.side_effect": self.atpneumatics_open_m1_cell_vents,
                "cmd_closeM1CellVents.start.side_effect": self.atpneumatics_close_m1_cell_vents,
            }
        )

        self.atcs.rem.atpneumatics.evt_m1CoverState.attach_mock(
            unittest.mock.Mock(),
            "flush",
        )

        self.atcs.rem.atpneumatics.evt_m1VentsPosition.attach_mock(
            unittest.mock.Mock(),
            "flush",
        )

        self.atcs.rem.atpneumatics.evt_instrumentState.attach_mock(
            unittest.mock.Mock(),
            "flush",
        )

        self.atcs.rem.atpneumatics.evt_mainValveState.attach_mock(
            unittest.mock.Mock(),
            "flush",
        )

    async def get_heartbeat(self, *args, **kwargs):
        """Emulate heartbeat functionality."""
        await asyncio.sleep(1.0)
        return types.SimpleNamespace()

    async def ataos_evt_correction_enabled(self, *args, **kwargs):
        return self._ataos_evt_correction_enabled

    async def atptg_evt_focus_name_selected(self, *args, **kwargs):
        return self._atptg_evt_focus_name_selected

    async def atmcs_tel_mount_nasmyth_encoders(self, *args, **kwargs):
        return self._atmcs_tel_mount_nasmyth_encoders

    async def next_telescope_position(self, *args, **kwargs):
        return self._telescope_position

    async def next_telescope_target(self, *args, **kwargs):
        return self._telescope_target_position

    async def atdome_tel_position(self, *args, **kwargs):
        return self._atdome_position

    async def atdome_evt_azimuth_commanded_state(self, *args, **kwargs):
        return self._atdome_azimth_commanded_state

    async def atdome_evt_azimuth_state(self, *args, **kwargs):
        if self._atdome_evt_azimuth_state._taken:
            raise asyncio.TimeoutError("Timeout waiting for azimuthState")
        else:
            await asyncio.sleep(0.1)
            return self._atdome_evt_azimuth_state

    def atdome_evt_azimuth_state_flush(self, *args, **kwargs):
        self._atdome_evt_azimuth_state._taken = True

    async def atdome_evt_scb_link(self, *args, **kwargs):
        return self._atdome_evt_scb_link

    async def atdome_evt_main_door_state(self, *args, **kwargs):
        await asyncio.sleep(0.2)
        return self._atdome_evt_main_door_state

    async def atdome_cmd_home_azimuth(self, *args, **kwargs):
        if self._atdome_position.azimuthPosition == 0.0:
            return
        else:
            self._atdome_evt_azimuth_state._taken = False
            self._atdome_evt_azimuth_state.homing = True
            asyncio.create_task(self._atdome_cmd_home_azimuth())

    async def atdome_cmd_move_shutter_main_door(self, *args, **kwargs):
        asyncio.create_task(
            self._atdome_cmd_move_shutter_main_door(open=kwargs["open"])
        )

    async def atdome_cmd_close_shutter(self, *args, **kwargs):
        asyncio.create_task(self._atdome_cmd_move_shutter_main_door(open=False))

    async def _atdome_cmd_home_azimuth(self):
        await asyncio.sleep(0.2)
        self._atdome_evt_azimuth_state.homing = False

    async def _atdome_cmd_move_shutter_main_door(self, open):
        if (
            open
            and self._atdome_evt_main_door_state.state != ATDome.ShutterDoorState.OPENED
        ):
            self._atdome_evt_main_door_state.state = ATDome.ShutterDoorState.OPENING
            await asyncio.sleep(0.5)
            self._atdome_evt_main_door_state.state = ATDome.ShutterDoorState.OPENED
        elif (
            not open
            and self._atdome_evt_main_door_state.state != ATDome.ShutterDoorState.CLOSED
        ):
            self._atdome_evt_main_door_state.state = ATDome.ShutterDoorState.CLOSING
            await asyncio.sleep(0.5)
            self._atdome_evt_main_door_state.state = ATDome.ShutterDoorState.CLOSED

    async def atmcs_all_axes_in_position(self, *args, **kwargs):
        await asyncio.sleep(0.1)
        return self._atmcs_all_axes_in_position

    async def atmcs_evt_at_mount_state(self, *args, **kwargs):
        return self._atmcs_evt_at_mount_state

    async def start_tracking(self, data, *args, **kwargs):

        self._atmcs_all_axes_in_position.inPosition = True

        self._atmcs_evt_at_mount_state.state = int(ATMCS.AtMountState.TRACKINGENABLED)

    async def atmcs_stop_tracking(self, *args, **kwargs):

        self._atmcs_all_axes_in_position.inPosition = False
        self._atmcs_evt_at_mount_state.state = int(ATMCS.AtMountState.TRACKINGDISABLED)

    async def atpneumatics_evt_m1_cover_state(self, *args, **kwargs):
        await asyncio.sleep(0.1)
        return self._atpneumatics_evt_m1_cover_state

    async def atpneumatics_evt_m1_vents_position(self, *args, **kwargs):
        await asyncio.sleep(0.1)
        return self._atpneumatics_evt_m1_vents_position

    async def atpneumatics_evt_instrument_state(self, *args, **kwargs):
        await asyncio.sleep(0.1)
        return self._atpneumatics_evt_instrument_state

    async def atpneumatics_evt_main_valve_state(self, *args, **kwargs):
        await asyncio.sleep(0.1)
        return self._atpneumatics_evt_main_valve_state

    async def atpneumatics_close_m1_cover(self, *args, **kwargs):
        asyncio.create_task(self._atpneumatics_close_m1_cover())

    async def atpneumatics_open_m1_cover(self, *args, **kwargs):
        if (
            self._atpneumatics_evt_main_valve_state.state
            != ATPneumatics.AirValveState.OPENED
        ):
            raise RuntimeError("Valves not opened.")
        asyncio.create_task(self._atpneumatics_open_m1_cover())

    async def atpneumatics_open_m1_cell_vents(self, *args, **kwargs):
        if (
            self._atpneumatics_evt_main_valve_state.state
            != ATPneumatics.AirValveState.OPENED
            or self._atpneumatics_evt_instrument_state.state
            != ATPneumatics.AirValveState.OPENED
        ):
            raise RuntimeError("Valves not opened.")
        asyncio.create_task(self._atpneumatics_open_m1_cell_vents())

    async def atpneumatics_close_m1_cell_vents(self, *args, **kwargs):
        asyncio.create_task(self._atpneumatics_close_m1_cell_vents())

    async def atpneumatics_open_air_valve(self, *args, **kwargs):
        asyncio.create_task(self._atpneumatics_open_air_valve())

    async def atpneumatics_open_main_valve(self, *args, **kwargs):
        asyncio.create_task(self._atpneumatics_open_main_valve())

    async def _atpneumatics_close_m1_cover(self):
        if (
            self._atpneumatics_evt_m1_cover_state.state
            == ATPneumatics.MirrorCoverState.CLOSED
        ):
            return
        else:
            self._atpneumatics_evt_m1_cover_state.state = (
                ATPneumatics.MirrorCoverState.INMOTION
            )
            await asyncio.sleep(0.5)
            self._atpneumatics_evt_m1_cover_state.state = (
                ATPneumatics.MirrorCoverState.CLOSED
            )

    async def _atpneumatics_open_m1_cover(self):
        if (
            self._atpneumatics_evt_m1_cover_state.state
            == ATPneumatics.MirrorCoverState.OPENED
        ):
            return
        else:
            self._atpneumatics_evt_m1_cover_state.state = (
                ATPneumatics.MirrorCoverState.INMOTION
            )
            await asyncio.sleep(0.5)
            self._atpneumatics_evt_m1_cover_state.state = (
                ATPneumatics.MirrorCoverState.OPENED
            )

    async def _atpneumatics_close_m1_cell_vents(self):
        if (
            self._atpneumatics_evt_m1_vents_position.position
            == ATPneumatics.VentsPosition.CLOSED
        ):
            return
        else:
            self._atpneumatics_evt_m1_vents_position.position = (
                ATPneumatics.VentsPosition.PARTIALLYOPENED
            )
            await asyncio.sleep(0.5)
            self._atpneumatics_evt_m1_vents_position.position = (
                ATPneumatics.VentsPosition.CLOSED
            )

    async def _atpneumatics_open_m1_cell_vents(self):
        self.log.debug("Open m1 cell vents")
        if (
            self._atpneumatics_evt_m1_vents_position.position
            == ATPneumatics.VentsPosition.OPENED
        ):
            return
        else:
            self._atpneumatics_evt_m1_vents_position.position = (
                ATPneumatics.VentsPosition.PARTIALLYOPENED
            )
            await asyncio.sleep(0.5)
            self._atpneumatics_evt_m1_vents_position.position = (
                ATPneumatics.VentsPosition.OPENED
            )

    async def _atpneumatics_open_air_valve(self):
        if (
            self._atpneumatics_evt_instrument_state.state
            == ATPneumatics.AirValveState.OPENED
        ):
            return
        else:

            await asyncio.sleep(0.5)

            self._atpneumatics_evt_instrument_state.state = (
                ATPneumatics.AirValveState.OPENED
            )

    async def _atpneumatics_open_main_valve(self):
        if (
            self._atpneumatics_evt_main_valve_state.state
            == ATPneumatics.AirValveState.OPENED
        ):
            return
        else:

            await asyncio.sleep(0.5)

            self._atpneumatics_evt_main_valve_state.state = (
                ATPneumatics.AirValveState.OPENED
            )

    def get_summary_state_for(self, comp):
        async def get_summary_state(timeout=None):
            return self.summary_state[comp]

        return get_summary_state

    def next_summary_state_for(self, comp):
        async def next_summary_state(flush, timeout=None):
            if flush or len(self.summary_state_queue[comp]) == 0:
                self.summary_state_queue_event[comp].clear()
                self.summary_state_queue[comp] = []
            await asyncio.wait_for(
                self.summary_state_queue_event[comp].wait(), timeout=timeout
            )
            return self.summary_state_queue[comp].pop(0)

        return next_summary_state

    def set_summary_state_for(self, comp, state):
        async def set_summary_state(*args, **kwargs):
            self.summary_state[comp].summaryState = int(state)
            self.summary_state_queue[comp].append(
                copy.copy(self.summary_state[comp].summaryState)
            )
            self.summary_state_queue_event[comp].set()

        return set_summary_state

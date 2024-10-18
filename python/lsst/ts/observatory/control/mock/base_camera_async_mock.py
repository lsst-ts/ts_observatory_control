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

import asyncio
import contextlib
import logging
import types
import typing

import astropy
import pytest
from lsst.ts import utils
from lsst.ts.observatory.control import CameraExposure
from lsst.ts.observatory.control.mock import RemoteGroupAsyncMock

HB_TIMEOUT = 5  # Heartbeat timeout (sec)
MAKE_TIMEOUT = 60  # Timeout for make_script (sec)

index_gen = utils.index_generator()


class FakeTCS:
    """This class is used to test the the synchronization between the TCS and
    GenericCamera.
    """

    def __init__(self, log: logging.Logger) -> None:
        self.log = log.getChild("FakeTCS")
        self._future = utils.make_done_future()
        self._future_task: typing.Union[None, asyncio.Task] = None
        self.fail = False
        self.called = 0

    def ready_to_take_data(self) -> None:
        self.log.debug("Ready to take data?")
        if self._future.done():
            self.called += 1
            self._future = asyncio.Future()
            if self.fail:
                self._future_task = asyncio.create_task(self.wait_and_fail_future())
            else:
                self._future_task = asyncio.create_task(self.wait_and_set_future())

        return self._future

    async def wait_and_set_future(self) -> None:
        self.log.debug("Waint and set future...")
        await asyncio.sleep(0.5)
        self.log.debug("done")
        if not self._future.done():
            self._future.set_result(True)

    async def wait_and_fail_future(self) -> None:
        self.log.debug("Waint and fail future...")
        await asyncio.sleep(0.5)
        self.log.debug("done")
        if not self._future.done():
            self._future.set_exception(RuntimeError("Failed."))


class BaseCameraAsyncMock(RemoteGroupAsyncMock):
    """Implement generic BaseCamera support for RemoteGroupAsyncMock unit test
    helper class to.

    This class is intended to be used for developing unit tests for BaseCamera
    class children. It contains some additions to RemoteGroupAsyncMock
    designed for testing the camera interface, like pre-defined method to
    execute unit tests for take_* commands and verify the results.
    """

    async def setup_mocks(self) -> None:
        self.remote_group.camera.evt_endReadout.next.configure_mock(
            side_effect=self.next_end_readout
        )

    async def next_end_readout(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> types.SimpleNamespace:
        date_id = astropy.time.Time.now().tai.isot.split("T")[0].replace("-", "")
        self.end_readout.imageName = f"test_genericcamera_{date_id}_{next(index_gen)}"
        return self.end_readout

    async def assert_take_bias(
        self,
        nbias: int,
        group_id: typing.Optional[str] = None,
        test_type: typing.Optional[str] = None,
        reason: typing.Optional[str] = None,
        program: typing.Optional[str] = None,
        sensors: typing.Optional[str] = None,
        note: typing.Optional[str] = None,
    ) -> None:
        """Run take_bias command and assert take images was executed with the
        expected values.

        Parameters
        ----------
        nbias : `int`
            Number of bias frames to take.
        group_id : `str`
            Optional group id for the data sequence. Will generate a common
            one for all the data if none is given.
        test_type : `str`
            Optional string to be added to the keyword testType image header.
        reason : `str`, optional
            Reason for the data being taken. This must be a short tag-like
            string that can be used to disambiguate a set of observations.
        program : `str`, optional
            Name of the program this data belongs to, e.g. WFD, DD, etc.
        sensors : `str`
            A colon delimited list of sensor names to use for the image.
        note : `str`
            Optional observer note to be added to the image header.
        """

        group_id = self.remote_group.next_group_id()

        await self.remote_group.take_bias(
            nbias=nbias,
            group_id=group_id,
            test_type=test_type,
            reason=reason,
            program=program,
            sensors=sensors,
            note=note,
        )

        expected_camera_exposure = CameraExposure(
            exp_time=0.0,
            shutter=False,
            image_type="BIAS",
            group_id=group_id,
            n=nbias,
            n_snaps=1,
            n_shift=0,
            row_shift=0,
            test_type="BIAS" if test_type is None else test_type,
            reason=reason,
            program=program,
            sensors=sensors if sensors is not None else "",
            note=note if note is not None else "",
        )

        self.assert_take_images(expected_camera_exposure=expected_camera_exposure)

    async def assert_take_darks(
        self,
        exptime: float,
        ndarks: int,
        group_id: typing.Optional[str] = None,
        test_type: typing.Optional[str] = None,
        reason: typing.Optional[str] = None,
        program: typing.Optional[str] = None,
        sensors: typing.Optional[str] = None,
        note: typing.Optional[str] = None,
    ) -> None:
        """Run take_darks and assert take images command was executed with
        expected values.

        Parameters
        ----------
        exptime : `float`
            Darks exposure times.
        ndarks : `int`
            Number of darks.
                test_type : `str`
            Optional string to be added to the keyword testType image header.
        reason : `str`, optional
            Reason for the data being taken. This must be a short tag-like
            string that can be used to disambiguate a set of observations.
        program : `str`, optional
            Name of the program this data belongs to, e.g. WFD, DD, etc.
        sensors : `str`
            A colon delimited list of sensor names to use for the image.
        note : `str`
            Optional observer note to be added to the image header.
        """

        group_id = self.remote_group.next_group_id()

        await self.remote_group.take_darks(
            exptime=exptime,
            ndarks=ndarks,
            group_id=group_id,
            test_type=test_type,
            reason=reason,
            program=program,
            sensors=sensors,
            note=note,
        )

        expected_camera_exposure = CameraExposure(
            exp_time=exptime,
            shutter=False,
            image_type="DARK",
            group_id=group_id,
            n=ndarks,
            n_snaps=1,
            n_shift=0,
            row_shift=0,
            test_type="DARK" if test_type is None else test_type,
            reason=reason,
            program=program,
            sensors=sensors if sensors is not None else "",
            note=note if note is not None else "",
        )

        self.assert_take_images(expected_camera_exposure=expected_camera_exposure)

    async def assert_take_flats(
        self,
        exptime: float,
        nflats: int,
        group_id: typing.Optional[str] = None,
        test_type: typing.Optional[str] = None,
        reason: typing.Optional[str] = None,
        program: typing.Optional[str] = None,
        sensors: typing.Optional[str] = None,
        note: typing.Optional[str] = None,
        **kwargs: typing.Any,
    ) -> None:
        """Run take_flats and assert take images command was executed with
        expected values.

        Parameters
        ----------
        exptime : `float`
            Exposure time.
        nflats : `int`
            Number of flats.
                test_type : `str`
            Optional string to be added to the keyword testType image header.
        reason : `str`, optional
            Reason for the data being taken. This must be a short tag-like
            string that can be used to disambiguate a set of observations.
        program : `str`, optional
            Name of the program this data belongs to, e.g. WFD, DD, etc.
        sensors : `str`
            A colon delimited list of sensor names to use for the image.
        note : `str`
            Optional observer note to be added to the image header.
        """

        exptime = 15.0
        nflats = 10
        group_id = self.remote_group.next_group_id()

        await self.remote_group.take_flats(
            exptime=exptime,
            nflats=nflats,
            group_id=group_id,
            test_type=test_type,
            reason=reason,
            program=program,
            sensors=sensors,
            note=note,
            **kwargs,
        )

        expected_camera_exposure = CameraExposure(
            exp_time=exptime,
            shutter=True,
            image_type="FLAT",
            group_id=group_id,
            n=nflats,
            n_snaps=1,
            n_shift=0,
            row_shift=0,
            test_type="FLAT" if test_type is None else test_type,
            reason=reason,
            program=program,
            sensors=sensors if sensors is not None else "",
            note=note if note is not None else "",
        )

        self.assert_take_images(expected_camera_exposure=expected_camera_exposure)

    async def assert_take_object(
        self,
        exptime: float,
        n: int,
        n_snaps: int = 1,
        group_id: typing.Optional[str] = None,
        test_type: typing.Optional[str] = None,
        reason: typing.Optional[str] = None,
        program: typing.Optional[str] = None,
        sensors: typing.Optional[str] = None,
        note: typing.Optional[str] = None,
        **kwargs: typing.Any,
    ) -> None:
        """Run take_objects and assert take images command was executed with
        expected values.

        Parameters
        ----------
        exptime : `float`
            Exposure time.
        n : `int`
            Number of exposures.
        n_snaps : `int`, optinal
            Number of snaps (default =1).
                test_type : `str`
            Optional string to be added to the keyword testType image header.
        reason : `str`, optional
            Reason for the data being taken. This must be a short tag-like
            string that can be used to disambiguate a set of observations.
        program : `str`, optional
            Name of the program this data belongs to, e.g. WFD, DD, etc.
        sensors : `str`
            A colon delimited list of sensor names to use for the image.
        note : `str`
            Optional observer note to be added to the image header.
        """

        exptime = 15.0
        n = 10
        group_id = self.remote_group.next_group_id()

        await self.remote_group.take_object(
            exptime=exptime,
            n=n,
            n_snaps=n_snaps,
            group_id=group_id,
            test_type=test_type,
            reason=reason,
            program=program,
            sensors=sensors,
            note=note,
            **kwargs,
        )

        expected_camera_exposure = CameraExposure(
            exp_time=exptime,
            shutter=True,
            image_type="OBJECT",
            group_id=group_id,
            n=n,
            n_snaps=n_snaps,
            n_shift=0,
            row_shift=0,
            test_type="OBJECT" if test_type is None else test_type,
            reason=reason,
            program=program,
            sensors=sensors if sensors is not None else "",
            note=note if note is not None else "",
        )

        self.assert_take_images(expected_camera_exposure=expected_camera_exposure)

    async def assert_take_engtest(
        self,
        exptime: float,
        n: int,
        group_id: typing.Optional[str] = None,
        test_type: typing.Optional[str] = None,
        reason: typing.Optional[str] = None,
        program: typing.Optional[str] = None,
        sensors: typing.Optional[str] = None,
        note: typing.Optional[str] = None,
        **kwargs: typing.Any,
    ) -> None:
        """Run take_engtest and assert take images command was executed with
        expected values.

        Parameters
        ----------
        exptime : `float`
            Exposure time.
        n : `int`
            Number of exposures.
                test_type : `str`
            Optional string to be added to the keyword testType image header.
        reason : `str`, optional
            Reason for the data being taken. This must be a short tag-like
            string that can be used to disambiguate a set of observations.
        program : `str`, optional
            Name of the program this data belongs to, e.g. WFD, DD, etc.
        sensors : `str`
            A colon delimited list of sensor names to use for the image.
        note : `str`
            Optional observer note to be added to the image header.
        """

        group_id = self.remote_group.next_group_id()

        await self.remote_group.take_engtest(
            exptime=exptime,
            n=n,
            group_id=group_id,
            test_type=test_type,
            reason=reason,
            program=program,
            sensors=sensors,
            note=note,
            **kwargs,
        )

        expected_camera_exposure = CameraExposure(
            exp_time=exptime,
            shutter=True,
            image_type="ENGTEST",
            group_id=group_id,
            n=n,
            n_snaps=1,
            n_shift=0,
            row_shift=0,
            test_type="ENGTEST" if test_type is None else test_type,
            reason=reason,
            program=program,
            sensors=sensors if sensors is not None else "",
            note=note if note is not None else "",
        )

        self.assert_take_images(expected_camera_exposure=expected_camera_exposure)

    async def assert_take_focus(
        self,
        exptime: float,
        n: int,
        group_id: typing.Optional[str] = None,
        test_type: typing.Optional[str] = None,
        reason: typing.Optional[str] = None,
        program: typing.Optional[str] = None,
        sensors: typing.Optional[str] = None,
        note: typing.Optional[str] = None,
        **kwargs: typing.Any,
    ) -> None:
        """Run take_focus and assert take images command was executed with
        expected values.

        Parameters
        ----------
        exptime : `float`
            Exposure time.
        n : `int`
            Number of exposures.
                test_type : `str`
            Optional string to be added to the keyword testType image header.
        reason : `str`, optional
            Reason for the data being taken. This must be a short tag-like
            string that can be used to disambiguate a set of observations.
        program : `str`, optional
            Name of the program this data belongs to, e.g. WFD, DD, etc.
        sensors : `str`
            A colon delimited list of sensor names to use for the image.
        note : `str`
            Optional observer note to be added to the image header.
        """

        group_id = self.remote_group.next_group_id()

        await self.remote_group.take_focus(
            exptime=exptime,
            n=n,
            group_id=group_id,
            test_type=test_type,
            reason=reason,
            program=program,
            sensors=sensors,
            note=note,
            **kwargs,
        )

        expected_camera_exposure = CameraExposure(
            exp_time=exptime,
            shutter=True,
            image_type="FOCUS",
            group_id=group_id,
            n=n,
            n_snaps=1,
            n_shift=0,
            row_shift=0,
            test_type="FOCUS" if test_type is None else test_type,
            reason=reason,
            program=program,
            sensors=sensors if sensors is not None else "",
            note=note if note is not None else "",
        )

        self.assert_take_images(expected_camera_exposure=expected_camera_exposure)

    async def assert_take_cwfs(
        self,
        exptime: float,
        n: int,
        group_id: typing.Optional[str] = None,
        test_type: typing.Optional[str] = None,
        reason: typing.Optional[str] = None,
        program: typing.Optional[str] = None,
        sensors: typing.Optional[str] = None,
        note: typing.Optional[str] = None,
        **kwargs: typing.Any,
    ) -> None:
        """Run take_cwfs and assert take images command was executed with
        expected values.

        Parameters
        ----------
        exptime : `float`
            Exposure time.
        n : `int`
            Number of exposures.
                test_type : `str`
            Optional string to be added to the keyword testType image header.
        reason : `str`, optional
            Reason for the data being taken. This must be a short tag-like
            string that can be used to disambiguate a set of observations.
        program : `str`, optional
            Name of the program this data belongs to, e.g. WFD, DD, etc.
        sensors : `str`
            A colon delimited list of sensor names to use for the image.
        note : `str`
            Optional observer note to be added to the image header.
        """

        group_id = self.remote_group.next_group_id()

        await self.remote_group.take_cwfs(
            exptime=exptime,
            n=n,
            group_id=group_id,
            test_type=test_type,
            reason=reason,
            program=program,
            sensors=sensors,
            note=note,
            **kwargs,
        )

        expected_camera_exposure = CameraExposure(
            exp_time=exptime,
            shutter=True,
            image_type="CWFS",
            group_id=group_id,
            n=n,
            n_snaps=1,
            n_shift=0,
            row_shift=0,
            test_type="CWFS" if test_type is None else test_type,
            reason=reason,
            program=program,
            sensors=sensors if sensors is not None else "",
            note=note if note is not None else "",
        )

        self.assert_take_images(expected_camera_exposure=expected_camera_exposure)

    async def assert_take_acq(
        self,
        group_id: typing.Optional[str] = None,
        test_type: typing.Optional[str] = None,
        reason: typing.Optional[str] = None,
        program: typing.Optional[str] = None,
        sensors: typing.Optional[str] = None,
        note: typing.Optional[str] = None,
        **kwargs: typing.Any,
    ) -> None:
        """Run take_acq and assert take images command was executed with
        expected values.

        Parameters
        ----------
        test_type : `str`
            Optional string to be added to the keyword testType image header.
        reason : `str`, optional
            Reason for the data being taken. This must be a short tag-like
            string that can be used to disambiguate a set of observations.
        program : `str`, optional
            Name of the program this data belongs to, e.g. WFD, DD, etc.
        sensors : `str`
            A colon delimited list of sensor names to use for the image.
        note : `str`
            Optional observer note to be added to the image header.
        """

        group_id = self.remote_group.next_group_id()

        await self.remote_group.take_acq(
            group_id=group_id,
            **kwargs,
        )

        expected_camera_exposure = CameraExposure(
            exp_time=1.0,
            shutter=True,
            image_type="ACQ",
            group_id=group_id,
            n=1,
            n_snaps=1,
            n_shift=0,
            row_shift=0,
            test_type="ACQ" if test_type is None else test_type,
            reason=reason,
            program=program,
            sensors=sensors if sensors is not None else "",
            note=note if note is not None else "",
        )

        self.assert_take_images(expected_camera_exposure=expected_camera_exposure)

    async def assert_take_stuttered(
        self,
        exptime: float,
        n_shift: int,
        row_shift: int,
        n: int = 1,
        group_id: typing.Optional[str] = None,
        test_type: typing.Optional[str] = None,
        reason: typing.Optional[str] = None,
        program: typing.Optional[str] = None,
        sensors: typing.Optional[str] = None,
        note: typing.Optional[str] = None,
        **kwargs: typing.Any,
    ) -> None:
        """Run take_stuttered and assert the await and calls were made with
        the expected values.

        Parameters
        ----------
        exptime : `float`
            Exposure time (in seconds).
        n_shift : `int`
            Number of shift-expose sequences.
        row_shift : `int`
            How many rows to shift at each sequence.
        n : `int`, optional
            Number of frames to take.
        test_type : `str`
            Optional string to be added to the keyword testType image header.
        reason : `str`, optional
            Reason for the data being taken. This must be a short tag-like
            string that can be used to disambiguate a set of observations.
        program : `str`, optional
            Name of the program this data belongs to, e.g. WFD, DD, etc.
        sensors : `str`
            A colon delimited list of sensor names to use for the image.
        note : `str`
            Optional observer note to be added to the image header.
        """

        group_id = self.remote_group.next_group_id()

        await self.remote_group.take_stuttered(
            n=n,
            exptime=exptime,
            n_shift=n_shift,
            row_shift=row_shift,
            group_id=group_id,
            test_type=test_type,
            reason=reason,
            program=program,
            sensors=sensors,
            note=note,
            **kwargs,
        )

        expected_camera_exposure = CameraExposure(
            exp_time=exptime,
            shutter=True,
            image_type="STUTTERED",
            group_id=group_id,
            n=n,
            n_snaps=1,
            n_shift=n_shift,
            row_shift=row_shift,
            test_type="STUTTERED" if test_type is None else test_type,
            reason=reason,
            program=program,
            sensors=sensors,
            note=note,
        )

        self.assert_take_calibration(expected_camera_exposure=expected_camera_exposure)

    def assert_take_images(self, expected_camera_exposure: CameraExposure) -> None:
        """Assert that a take image operation was executed with the expected
        values for the input parameters.

        Parameters
        ----------
        expected_camera_exposure : `CameraExposure`
            Expected camera exposure paramaters.
        """
        self.remote_group.camera.cmd_takeImages.set.assert_called_with(
            numImages=expected_camera_exposure.n_snaps,
            expTime=expected_camera_exposure.exp_time,
            shutter=expected_camera_exposure.shutter,
            keyValueMap=expected_camera_exposure.get_key_value_map(),
            sensors=expected_camera_exposure.sensors,
            obsNote=expected_camera_exposure.note,
        )
        self.remote_group.camera.evt_endReadout.flush.assert_called()
        expected_timeout = (
            self.remote_group.read_out_time + expected_camera_exposure.exp_time
        ) * expected_camera_exposure.n + self.remote_group.long_long_timeout
        self.remote_group.camera.cmd_takeImages.start.assert_awaited_with(
            timeout=expected_timeout
        )
        assert (
            self.remote_group.camera.cmd_takeImages.start.await_count
            == expected_camera_exposure.n
        )

    def assert_take_calibration(self, expected_camera_exposure: CameraExposure) -> None:
        """Assert the take calibration operation was executed with the
        expected values for the input parameters.

        This assertion is used in conjuntion with take_stuttered method.

        Parameters
        ----------
        expected_camera_exposure : `CameraExposure`
            Expected camera exposure parameters.
        """
        self.remote_group.camera.cmd_enableCalibration.start.assert_awaited_with(
            timeout=self.remote_group.long_timeout
        )
        self.remote_group.camera.evt_endReadout.flush.assert_called()

        self.remote_group.camera.cmd_startImage.set.assert_called_with(
            shutter=expected_camera_exposure.shutter,
            keyValueMap=expected_camera_exposure.get_key_value_map(),
            timeout=(
                self.remote_group.fast_timeout
                + expected_camera_exposure.exp_time
                * (expected_camera_exposure.n_shift + 1)
            ),
        )
        self.remote_group.camera.cmd_startImage.start.assert_awaited_with(
            timeout=self.remote_group.fast_timeout
        )
        self.remote_group.camera.cmd_endImage.start.assert_awaited_with(
            timeout=self.remote_group.long_timeout
        )
        self.remote_group.camera.cmd_disableCalibration.start.assert_awaited_with(
            timeout=self.remote_group.long_timeout
        )
        enable_calibrations_await_count = (
            self.remote_group.camera.cmd_enableCalibration.start.await_count
        )
        assert (
            enable_calibrations_await_count == 1
        ), f"Expected 1 got {enable_calibrations_await_count} for cmd_enableCalibration.start."
        disable_calibrations_await_count = (
            self.remote_group.camera.cmd_disableCalibration.start.await_count
        )
        assert (
            disable_calibrations_await_count == 1
        ), f"Expected 1 got {enable_calibrations_await_count} for cmd_disableCalibration.start."

        assert (
            self.remote_group.camera.cmd_startImage.start.await_count
            == expected_camera_exposure.n
        )
        assert (
            self.remote_group.camera.cmd_endImage.start.await_count
            == expected_camera_exposure.n
        )

        discard_rows_await_count = (
            self.remote_group.camera.cmd_discardRows.set_start.await_count
        )
        expected_discard_rows_await_count = (
            expected_camera_exposure.n * expected_camera_exposure.n_shift - 1
        )
        assert discard_rows_await_count == expected_discard_rows_await_count, (
            f"Expected {expected_discard_rows_await_count} got {discard_rows_await_count} "
            "await counts for cmd_discardRows.set_start."
        )

    async def assert_take_image_tcs_sync(
        self,
        image_type: str,
        exptime: float = 1.0,
        n: int = 1,
        should_fail: bool = False,
        **kwargs: typing.Any,
    ) -> None:
        """Test that taking an image of a given type waits for TCS readiness
        and asserts the camera commands.

        Parameters
        ----------
        image_type : str
            The image type to test (e.g., "OBJECT", "ENGTEST", "ACQ","CWFS").
        exptime : float
            Exposure time.
        n : int
            Number of images to take.
        should_fail : bool
            If True, simulate TCS failure and expect a RuntimeError.
        **kwargs
            Additional arguments to pass to the `assert_take_<type>` method.
        """
        image_type_lower = image_type.lower()

        assert_method_name = f"assert_take_{image_type_lower}"

        assert_take_method = getattr(self, assert_method_name, None)

        if assert_take_method is None:
            raise AttributeError(
                f"No method found for image type '{image_type}'. "
                f"Ensure that '{assert_method_name}' exist."
            )

        with self.get_fake_tcs() as fake_tcs:
            fake_tcs.fail = should_fail

            if should_fail:
                with pytest.raises(RuntimeError):
                    await assert_take_method(
                        exptime=exptime,
                        n=n,
                        **kwargs,
                    )
            else:
                await assert_take_method(
                    exptime=exptime,
                    n=n,
                    **kwargs,
                )
                assert fake_tcs.called == 1

    @contextlib.contextmanager
    def get_fake_tcs(self) -> typing.Generator[FakeTCS, None, None]:
        fake_tcs = FakeTCS(self.log)
        self.remote_group.ready_to_take_data = fake_tcs.ready_to_take_data
        yield fake_tcs
        self.remote_group.ready_to_take_data = None

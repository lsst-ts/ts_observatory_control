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
# You should have received a copy of the GNU General Public License.
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import logging
import unittest.mock
from typing import TYPE_CHECKING

import numpy as np
import pytest
from lsst.ts.observatory.control.utils.extras import (
    BEST_EFFORT_ISR_AVAILABLE,
    DM_STACK_AVAILABLE,
    GuiderROIs,
    get_vignetting_correction_from_butler,
)

if TYPE_CHECKING:
    from lsst.ts.observatory.control.utils.extras.vignetting_correction import (
        VignettingCorrection,
    )


def _create_mock_vignetting_correction() -> "VignettingCorrection":
    """Create a VignettingCorrection object for testing.

    Raises
    ------
    ImportError
        If VignettingCorrection class is not available - this is intentional
        as tests should fail if the required class is missing.
    """
    from lsst.ts.observatory.control.utils.extras.vignetting_correction import (
        VignettingCorrection,
    )

    theta = np.array([0.0, 0.5, 1.0, 1.5])
    vignetting = np.array([1.0, 0.95, 0.9, 0.85])
    metadata = {"description": "Test vignetting data", "version": "test"}

    return VignettingCorrection(theta, vignetting, metadata)


class TestGuiderROIs:
    """Test GuiderROIs class functionality."""

    @pytest.mark.skipif(not DM_STACK_AVAILABLE, reason="DM stack not available.")
    def test_init_without_dm_stack(self) -> None:
        """Test that GuiderROIs fails when DM stack is not available."""
        with unittest.mock.patch(
            "lsst.ts.observatory.control.utils.extras.guider_roi.DM_STACK_AVAILABLE",
            False,
        ):
            with pytest.raises(
                RuntimeError,
                match="DM Stack not available. BestEffortIsr mode is required",
            ):
                GuiderROIs()

    @pytest.mark.skipif(not DM_STACK_AVAILABLE, reason="DM stack not available.")
    def test_init_without_best_effort_isr(self) -> None:
        """Test that GuiderROIs fails when BestEffortIsr is not available."""
        with unittest.mock.patch(
            "lsst.ts.observatory.control.utils.extras.guider_roi.BEST_EFFORT_ISR_AVAILABLE",
            False,
        ):
            with pytest.raises(
                RuntimeError, match="BestEffortIsr is required but not available"
            ):
                GuiderROIs()

    @pytest.mark.skipif(not DM_STACK_AVAILABLE, reason="DM stack not available.")
    def test_init_with_failed_best_effort_isr(self) -> None:
        """Test that GuiderROIs fails when BestEffortIsr returns None
        butler."""
        mock_best_effort = unittest.mock.Mock()
        mock_best_effort.butler = None

        with unittest.mock.patch(
            "lsst.ts.observatory.control.utils.extras.guider_roi.BEST_EFFORT_ISR_AVAILABLE",
            True,
        ), unittest.mock.patch(
            "lsst.ts.observatory.control.utils.extras.guider_roi.BestEffortIsr",
            return_value=mock_best_effort,
        ):
            with pytest.raises(
                RuntimeError, match="Failed to obtain Butler from BestEffortIsr"
            ):
                GuiderROIs()

    @pytest.mark.skipif(not DM_STACK_AVAILABLE, reason="DM stack not available.")
    def test_init_success(self) -> None:
        """Test successful initialization with BestEffortIsr."""
        mock_best_effort = unittest.mock.Mock()
        mock_butler = unittest.mock.Mock()
        mock_best_effort.butler = mock_butler

        mock_dataset_type = unittest.mock.Mock()
        mock_dataset_type.dimensions.required = {"healpix5"}
        mock_butler.registry.getDatasetType.return_value = mock_dataset_type

        vignetting_correction = _create_mock_vignetting_correction()

        with unittest.mock.patch(
            "lsst.ts.observatory.control.utils.extras.guider_roi.BEST_EFFORT_ISR_AVAILABLE",
            True,
        ), unittest.mock.patch(
            "lsst.ts.observatory.control.utils.extras.guider_roi.BestEffortIsr",
            return_value=mock_best_effort,
        ), unittest.mock.patch(
            "lsst.ts.observatory.control.utils.extras.guider_roi.get_vignetting_correction_from_butler",
            return_value=vignetting_correction,
        ):
            roi = GuiderROIs()

            assert roi.butler is mock_butler
            assert roi.best_effort_isr is mock_best_effort
            assert roi.catalog_name == "guider_roi_monster_guide_catalog"
            assert roi.vignetting_dataset == "guider_roi_vignetting_correction"
            assert roi.collection == "guider_roi_data"
            assert roi.nside == 32  # 2^5
            assert roi.healpix_dim == "healpix5"
            assert roi.healpix_level == 5
            assert roi.ccd_diag == 0.15852
            assert roi.bad_guideramps == {193: ["C1"], 198: ["C1"], 201: ["C0"]}
            assert roi.camera is not None

    @pytest.mark.skipif(not DM_STACK_AVAILABLE, reason="DM stack not available.")
    def test_init_custom_parameters(self) -> None:
        """Test initialization with custom parameters."""
        mock_best_effort = unittest.mock.Mock()
        mock_butler = unittest.mock.Mock()
        mock_best_effort.butler = mock_butler

        mock_dataset_type = unittest.mock.Mock()
        mock_dataset_type.dimensions.required = {"healpix4"}
        mock_butler.registry.getDatasetType.return_value = mock_dataset_type

        vignetting_correction = _create_mock_vignetting_correction()

        mock_logger = unittest.mock.Mock(spec=logging.Logger)

        with unittest.mock.patch(
            "lsst.ts.observatory.control.utils.extras.guider_roi.BEST_EFFORT_ISR_AVAILABLE",
            True,
        ), unittest.mock.patch(
            "lsst.ts.observatory.control.utils.extras.guider_roi.BestEffortIsr",
            return_value=mock_best_effort,
        ), unittest.mock.patch(
            "lsst.ts.observatory.control.utils.extras.guider_roi.get_vignetting_correction_from_butler",
            return_value=vignetting_correction,
        ):
            roi = GuiderROIs(
                catalog_name="custom_catalog",
                vignetting_dataset="custom_vignetting",
                collection="custom_collection",
                log=mock_logger,
            )

            assert roi.catalog_name == "custom_catalog"
            assert roi.vignetting_dataset == "custom_vignetting"
            assert roi.collection == "custom_collection"
            assert roi.nside == 16  # 2^4
            assert roi.healpix_dim == "healpix4"
            assert roi.healpix_level == 4

    @pytest.mark.skipif(not DM_STACK_AVAILABLE, reason="DM stack not available.")
    def test_init_no_healpix_dimension(self) -> None:
        """Test that initialization fails when dataset has no HEALPix
        dimension."""
        mock_best_effort = unittest.mock.Mock()
        mock_butler = unittest.mock.Mock()
        mock_best_effort.butler = mock_butler

        mock_dataset_type = unittest.mock.Mock()
        mock_dataset_type.dimensions.required = {"visit", "detector"}
        mock_butler.registry.getDatasetType.return_value = mock_dataset_type

        with unittest.mock.patch(
            "lsst.ts.observatory.control.utils.extras.guider_roi.BEST_EFFORT_ISR_AVAILABLE",
            True,
        ), unittest.mock.patch(
            "lsst.ts.observatory.control.utils.extras.guider_roi.BestEffortIsr",
            return_value=mock_best_effort,
        ):
            with pytest.raises(
                RuntimeError, match="DatasetType.*has no HEALPix dimension"
            ):
                GuiderROIs()

    @pytest.mark.skipif(not DM_STACK_AVAILABLE, reason="DM stack not available.")
    def test_init_vignetting_data_error(self) -> None:
        """Test that initialization fails when vignetting data is not
        available."""
        mock_best_effort = unittest.mock.Mock()
        mock_butler = unittest.mock.Mock()
        mock_best_effort.butler = mock_butler

        mock_dataset_type = unittest.mock.Mock()
        mock_dataset_type.dimensions.required = {"healpix5"}
        mock_butler.registry.getDatasetType.return_value = mock_dataset_type

        with unittest.mock.patch(
            "lsst.ts.observatory.control.utils.extras.guider_roi.BEST_EFFORT_ISR_AVAILABLE",
            True,
        ), unittest.mock.patch(
            "lsst.ts.observatory.control.utils.extras.guider_roi.BestEffortIsr",
            return_value=mock_best_effort,
        ), unittest.mock.patch(
            "lsst.ts.observatory.control.utils.extras.guider_roi.get_vignetting_correction_from_butler",
            side_effect=RuntimeError("No vignetting dataset"),
        ):
            with pytest.raises(RuntimeError, match="No vignetting dataset"):
                GuiderROIs()

    @pytest.mark.skipif(not DM_STACK_AVAILABLE, reason="DM stack not available.")
    def test_vignetting_correction(self) -> None:
        """Test vignetting correction calculation."""
        mock_best_effort = unittest.mock.Mock()
        mock_butler = unittest.mock.Mock()
        mock_best_effort.butler = mock_butler

        mock_dataset_type = unittest.mock.Mock()
        mock_dataset_type.dimensions.required = {"healpix5"}
        mock_butler.registry.getDatasetType.return_value = mock_dataset_type

        vignetting_correction = _create_mock_vignetting_correction()

        with unittest.mock.patch(
            "lsst.ts.observatory.control.utils.extras.guider_roi.BEST_EFFORT_ISR_AVAILABLE",
            True,
        ), unittest.mock.patch(
            "lsst.ts.observatory.control.utils.extras.guider_roi.BestEffortIsr",
            return_value=mock_best_effort,
        ), unittest.mock.patch(
            "lsst.ts.observatory.control.utils.extras.guider_roi.get_vignetting_correction_from_butler",
            return_value=vignetting_correction,
        ):
            roi = GuiderROIs()

            correction = roi.vignetting_correction(0.0)
            assert isinstance(correction, float)
            assert correction >= 0.0

            correction = roi.vignetting_correction(1.0)
            assert isinstance(correction, float)
            assert correction >= 0.0

    @pytest.mark.skipif(not DM_STACK_AVAILABLE, reason="DM stack not available.")
    def test_get_catalog_data_from_butler(self) -> None:
        """Test catalog data retrieval from Butler."""
        mock_best_effort = unittest.mock.Mock()
        mock_butler = unittest.mock.Mock()
        mock_best_effort.butler = mock_butler

        mock_dataset_type = unittest.mock.Mock()
        mock_dataset_type.dimensions.required = {"healpix5"}
        mock_butler.registry.getDatasetType.return_value = mock_dataset_type

        vignetting_correction = _create_mock_vignetting_correction()

        with unittest.mock.patch(
            "lsst.ts.observatory.control.utils.extras.guider_roi.BEST_EFFORT_ISR_AVAILABLE",
            True,
        ), unittest.mock.patch(
            "lsst.ts.observatory.control.utils.extras.guider_roi.BestEffortIsr",
            return_value=mock_best_effort,
        ), unittest.mock.patch(
            "lsst.ts.observatory.control.utils.extras.guider_roi.get_vignetting_correction_from_butler",
            return_value=vignetting_correction,
        ):
            roi = GuiderROIs()

            # Test with no data available
            tables = roi._get_catalog_data_from_butler([12000, 12001])
            assert tables == []

    @pytest.mark.skipif(not DM_STACK_AVAILABLE, reason="DM stack not available.")
    def test_get_guider_rois_parameter_names(self) -> None:
        """Test that get_guider_rois uses the new parameter names."""
        mock_best_effort = unittest.mock.Mock()
        mock_butler = unittest.mock.Mock()
        mock_best_effort.butler = mock_butler

        mock_dataset_type = unittest.mock.Mock()
        mock_dataset_type.dimensions.required = {"healpix5"}
        mock_butler.registry.getDatasetType.return_value = mock_dataset_type

        vignetting_correction = _create_mock_vignetting_correction()

        with unittest.mock.patch(
            "lsst.ts.observatory.control.utils.extras.guider_roi.BEST_EFFORT_ISR_AVAILABLE",
            True,
        ), unittest.mock.patch(
            "lsst.ts.observatory.control.utils.extras.guider_roi.BestEffortIsr",
            return_value=mock_best_effort,
        ), unittest.mock.patch(
            "lsst.ts.observatory.control.utils.extras.guider_roi.get_vignetting_correction_from_butler",
            return_value=vignetting_correction,
        ):
            roi = GuiderROIs()

            # Test that the method accepts the new parameter names
            # This will fail due to no catalog data, but we can test the
            # parameter names
            with unittest.mock.patch.object(
                roi, "_get_catalog_data_from_butler", return_value=[]
            ):
                with pytest.raises(RuntimeError, match="No suitable guide stars found"):
                    roi.get_guider_rois(
                        ra=127.5,  # Changed from boresight_RA
                        dec=-44.2,  # Changed from boresight_DEC
                        sky_angle=316.4,  # Changed from boresight_RotAngle
                        roi_size=400,
                        roi_time=200,
                        band="i",  # Changed from filter
                    )

    @pytest.mark.skipif(not DM_STACK_AVAILABLE, reason="DM stack not available.")
    def test_get_guider_rois_without_dm_stack(self) -> None:
        """Test that get_guider_rois fails when DM stack is not available."""
        mock_best_effort = unittest.mock.Mock()
        mock_butler = unittest.mock.Mock()
        mock_best_effort.butler = mock_butler

        mock_dataset_type = unittest.mock.Mock()
        mock_dataset_type.dimensions.required = {"healpix5"}
        mock_butler.registry.getDatasetType.return_value = mock_dataset_type

        vignetting_correction = _create_mock_vignetting_correction()

        with unittest.mock.patch(
            "lsst.ts.observatory.control.utils.extras.guider_roi.BEST_EFFORT_ISR_AVAILABLE",
            True,
        ), unittest.mock.patch(
            "lsst.ts.observatory.control.utils.extras.guider_roi.BestEffortIsr",
            return_value=mock_best_effort,
        ), unittest.mock.patch(
            "lsst.ts.observatory.control.utils.extras.guider_roi.get_vignetting_correction_from_butler",
            return_value=vignetting_correction,
        ):
            roi = GuiderROIs()

            # Test that get_guider_rois fails when DM stack is marked as
            # unavailable
            with unittest.mock.patch(
                "lsst.ts.observatory.control.utils.extras.guider_roi.DM_STACK_AVAILABLE",
                False,
            ):
                with pytest.raises(RuntimeError, match="DM stack not available"):
                    roi.get_guider_rois(
                        ra=127.5,
                        dec=-44.2,
                        sky_angle=316.4,
                        roi_size=400,
                        roi_time=200,
                        band="i",
                    )

    @pytest.mark.skipif(not DM_STACK_AVAILABLE, reason="DM stack not available.")
    def test_get_guider_rois_no_camera(self) -> None:
        """Test that get_guider_rois fails when camera is not available."""
        mock_best_effort = unittest.mock.Mock()
        mock_butler = unittest.mock.Mock()
        mock_best_effort.butler = mock_butler

        mock_dataset_type = unittest.mock.Mock()
        mock_dataset_type.dimensions.required = {"healpix5"}
        mock_butler.registry.getDatasetType.return_value = mock_dataset_type

        vignetting_correction = _create_mock_vignetting_correction()

        with unittest.mock.patch(
            "lsst.ts.observatory.control.utils.extras.guider_roi.BEST_EFFORT_ISR_AVAILABLE",
            True,
        ), unittest.mock.patch(
            "lsst.ts.observatory.control.utils.extras.guider_roi.BestEffortIsr",
            return_value=mock_best_effort,
        ), unittest.mock.patch(
            "lsst.ts.observatory.control.utils.extras.guider_roi.get_vignetting_correction_from_butler",
            return_value=vignetting_correction,
        ):
            roi = GuiderROIs()
            roi.camera = None  # Force camera to be None

            with pytest.raises(RuntimeError, match="Camera object not available"):
                roi.get_guider_rois(
                    ra=127.5,
                    dec=-44.2,
                    sky_angle=316.4,
                    roi_size=400,
                    roi_time=200,
                    band="i",
                )


def test_dm_stack_available_flag() -> None:
    """Test that DM_STACK_AVAILABLE flag is accessible."""
    from lsst.ts.observatory.control.utils.extras.guider_roi import DM_STACK_AVAILABLE

    assert isinstance(DM_STACK_AVAILABLE, bool)


def test_best_effort_isr_available_flag() -> None:
    """Test that BEST_EFFORT_ISR_AVAILABLE flag is accessible."""
    assert isinstance(BEST_EFFORT_ISR_AVAILABLE, bool)


def test_get_vignetting_correction_from_butler() -> None:
    """Test the vignetting correction loader function."""
    if not DM_STACK_AVAILABLE:
        pytest.skip("DM stack not available")

    mock_butler = unittest.mock.Mock()
    mock_butler.registry.queryDatasets.return_value = []

    with pytest.raises(RuntimeError, match="No vignetting dataset"):
        get_vignetting_correction_from_butler(mock_butler)
    mock_butler.registry.queryDatasets.assert_called_once_with(
        "guider_roi_vignetting_correction", collections=["guider_roi_data"]
    )

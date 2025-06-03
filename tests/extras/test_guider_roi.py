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

import unittest.mock

import pytest
from lsst.ts.observatory.control.utils.extras import DM_STACK_AVAILABLE, GuiderROIs


class TestGuiderROIs:
    """Test GuiderROIs class functionality."""

    @pytest.mark.skipif(not DM_STACK_AVAILABLE, reason="DM stack not available.")
    def test_init_without_dm_stack(self) -> None:
        """Test that GuiderROIs fails gracefully when DM stack is not
        available."""
        with unittest.mock.patch(
            "lsst.ts.observatory.control.utils.extras.guider_roi.DM_STACK_AVAILABLE",
            False,
        ):
            with pytest.raises(RuntimeError, match="DM stack not available"):
                GuiderROIs()

    @pytest.mark.skipif(not DM_STACK_AVAILABLE, reason="DM stack not available.")
    def test_init_without_best_effort_isr(self) -> None:
        """Test that GuiderROIs requires butler when BestEffortIsr is not
        available."""
        with unittest.mock.patch(
            "lsst.ts.observatory.control.utils.extras.guider_roi.BEST_EFFORT_ISR_AVAILABLE",
            False,
        ):
            # Should fail without butler
            with pytest.raises(
                RuntimeError,
                match="BestEffortIsr is not available and no butler was provided",
            ):
                GuiderROIs()

            # Should succeed with butler
            mock_butler = unittest.mock.Mock()
            vignetting_data = {
                "theta": [0.0, 0.5, 1.0, 1.5],
                "vignetting": [1.0, 0.95, 0.9, 0.85],
            }

            with unittest.mock.patch(
                "lsst.ts.observatory.control.utils.extras.guider_roi.get_vignetting_data_from_butler",
                return_value=vignetting_data,
            ):
                roi = GuiderROIs(butler=mock_butler)
                assert roi.butler is mock_butler
                assert roi.best_effort_isr is None

    @pytest.mark.skipif(not DM_STACK_AVAILABLE, reason="DM stack not available.")
    def test_init_with_custom_butler(self) -> None:
        """Test initialization with custom butler."""
        mock_butler = unittest.mock.Mock()

        # Mock valid vignetting data
        vignetting_data = {
            "theta": [0.0, 0.5, 1.0, 1.5],
            "vignetting": [1.0, 0.95, 0.9, 0.85],
        }

        with unittest.mock.patch(
            "lsst.ts.observatory.control.utils.extras.guider_roi.get_vignetting_data_from_butler",
            return_value=vignetting_data,
        ):
            roi = GuiderROIs(butler=mock_butler)
            assert roi.butler is mock_butler
            assert roi.best_effort_isr is None

    @pytest.mark.skipif(not DM_STACK_AVAILABLE, reason="DM stack not available.")
    def test_init_with_default_butler(self) -> None:
        """Test initialization with default BestEffortIsr butler."""
        mock_best_effort = unittest.mock.Mock()
        mock_butler = unittest.mock.Mock()
        mock_best_effort.butler = mock_butler

        # Mock valid vignetting data
        vignetting_data = {
            "theta": [0.0, 0.5, 1.0, 1.5],
            "vignetting": [1.0, 0.95, 0.9, 0.85],
        }

        with unittest.mock.patch(
            "lsst.ts.observatory.control.utils.extras.guider_roi.BEST_EFFORT_ISR_AVAILABLE",
            True,
        ), unittest.mock.patch(
            "lsst.ts.observatory.control.utils.extras.guider_roi.BestEffortIsr",
            return_value=mock_best_effort,
        ), unittest.mock.patch(
            "lsst.ts.observatory.control.utils.extras.guider_roi.get_vignetting_data_from_butler",
            return_value=vignetting_data,
        ):
            roi = GuiderROIs()
            assert roi.butler is mock_butler
            assert roi.best_effort_isr is mock_best_effort

    @pytest.mark.skipif(not DM_STACK_AVAILABLE, reason="DM stack not available.")
    def test_init_constants(self) -> None:
        """Test that initialization sets correct constants."""
        mock_butler = unittest.mock.Mock()

        # Mock valid vignetting data
        vignetting_data = {
            "theta": [0.0, 0.5, 1.0, 1.5],
            "vignetting": [1.0, 0.95, 0.9, 0.85],
        }

        with unittest.mock.patch(
            "lsst.ts.observatory.control.utils.extras.guider_roi.get_vignetting_data_from_butler",
            return_value=vignetting_data,
        ):
            roi = GuiderROIs(butler=mock_butler)

            # Test constants
            assert roi.ccd_diag == 0.15852
            assert roi.nside == 32  # 2^5
            assert roi.npix == 12 * 32**2
            assert roi.bad_guideramps == {193: "C1", 198: "C1", 201: "C0"}
            assert roi.filters == ["u", "g", "r", "i", "z", "y"]
            assert roi.catalog_name == "monster_guide_catalog"
            assert roi.vignetting_dataset == "vignetting_correction"

    @pytest.mark.skipif(not DM_STACK_AVAILABLE, reason="DM stack not available.")
    def test_init_custom_dataset_names(self) -> None:
        """Test initialization with custom dataset names."""
        mock_butler = unittest.mock.Mock()

        # Mock valid vignetting data
        vignetting_data = {
            "theta": [0.0, 0.5, 1.0, 1.5],
            "vignetting": [1.0, 0.95, 0.9, 0.85],
        }

        with unittest.mock.patch(
            "lsst.ts.observatory.control.utils.extras.guider_roi.get_vignetting_data_from_butler",
            return_value=vignetting_data,
        ):
            roi = GuiderROIs(
                butler=mock_butler,
                catalog_name="custom_catalog",
                vignetting_dataset="custom_vignetting",
            )
            assert roi.catalog_name == "custom_catalog"
            assert roi.vignetting_dataset == "custom_vignetting"

    @pytest.mark.skipif(not DM_STACK_AVAILABLE, reason="DM stack not available.")
    def test_init_missing_vignetting_data(self) -> None:
        """Test that initialization fails when vignetting data is not
        available."""
        mock_butler = unittest.mock.Mock()

        with unittest.mock.patch(
            "lsst.ts.observatory.control.utils.extras.guider_roi.get_vignetting_data_from_butler",
            return_value=None,
        ):
            with pytest.raises(
                RuntimeError, match="Vignetting correction data.*not found in butler"
            ):
                GuiderROIs(butler=mock_butler)

    @pytest.mark.skipif(not DM_STACK_AVAILABLE, reason="DM stack not available.")
    def test_init_invalid_vignetting_data_missing_theta(self) -> None:
        """Test that initialization fails when vignetting data is missing
        'theta' column."""
        mock_butler = unittest.mock.Mock()

        with unittest.mock.patch(
            "lsst.ts.observatory.control.utils.extras.guider_roi.get_vignetting_data_from_butler",
            side_effect=ValueError(
                "Vignetting data missing required columns: ['theta']"
            ),
        ):
            with pytest.raises(
                ValueError, match="Vignetting data missing required columns.*theta"
            ):
                GuiderROIs(butler=mock_butler)

    @pytest.mark.skipif(not DM_STACK_AVAILABLE, reason="DM stack not available.")
    def test_init_invalid_vignetting_data_missing_vignetting(self) -> None:
        """Test that initialization fails when vignetting data is missing
        'vignetting' column."""
        mock_butler = unittest.mock.Mock()

        # Mock vignetting data missing 'vignetting'
        with unittest.mock.patch(
            "lsst.ts.observatory.control.utils.extras.guider_roi.get_vignetting_data_from_butler",
            side_effect=ValueError(
                "Vignetting data missing required columns: ['vignetting']"
            ),
        ):
            with pytest.raises(
                ValueError, match="Vignetting data missing required columns.*vignetting"
            ):
                GuiderROIs(butler=mock_butler)

    @pytest.mark.skipif(not DM_STACK_AVAILABLE, reason="DM stack not available.")
    def test_init_invalid_vignetting_data_missing_both(self) -> None:
        """Test that initialization fails when vignetting data is missing both
        required columns."""
        mock_butler = unittest.mock.Mock()

        with unittest.mock.patch(
            "lsst.ts.observatory.control.utils.extras.guider_roi.get_vignetting_data_from_butler",
            side_effect=ValueError(
                "Vignetting data missing required columns: ['theta', 'vignetting']"
            ),
        ):
            with pytest.raises(
                ValueError,
                match="Vignetting data missing required columns.*theta.*vignetting",
            ):
                GuiderROIs(butler=mock_butler)

    @pytest.mark.skipif(not DM_STACK_AVAILABLE, reason="DM stack not available.")
    def test_vignetting_correction_with_butler_data(self) -> None:
        """Test vignetting correction with data from butler."""
        mock_butler = unittest.mock.Mock()

        # Mock vignetting data
        vignetting_data = {
            "theta": [0.0, 0.5, 1.0, 1.5],
            "vignetting": [1.0, 0.95, 0.9, 0.85],
        }

        with unittest.mock.patch(
            "lsst.ts.observatory.control.utils.extras.guider_roi.get_vignetting_data_from_butler",
            return_value=vignetting_data,
        ):
            roi = GuiderROIs(butler=mock_butler)

            # Test that vignetting correction works
            correction = roi.vignetting_correction(0.0)
            assert isinstance(correction, float)
            assert correction >= 0.0

    @pytest.mark.skipif(not DM_STACK_AVAILABLE, reason="DM stack not available.")
    def test_get_catalog_data_for_healpix_no_data(self) -> None:
        """Test _get_catalog_data_for_healpix when no catalog data is
        available."""
        mock_butler = unittest.mock.Mock()

        # Mock valid vignetting data for initialization
        vignetting_data = {
            "theta": [0.0, 0.5, 1.0, 1.5],
            "vignetting": [1.0, 0.95, 0.9, 0.85],
        }

        # Make the mock butler raise an exception when trying to get
        # catalog data
        # This simulates the real behavior when catalog data is not available
        mock_butler.get.side_effect = Exception("Dataset not found")

        with unittest.mock.patch(
            "lsst.ts.observatory.control.utils.extras.guider_roi.get_vignetting_data_from_butler",
            return_value=vignetting_data,
        ):
            roi = GuiderROIs(butler=mock_butler)

            # Now test the catalog data method with no data available
            tables = roi._get_catalog_data_for_healpix([12000, 12001])
            assert tables == []

    @pytest.mark.skipif(not DM_STACK_AVAILABLE, reason="DM stack not available.")
    def test_get_guider_rois_without_dm_stack(self) -> None:
        """Test that get_guider_rois fails when DM stack is not available."""
        mock_butler = unittest.mock.Mock()

        # Mock valid vignetting data for initialization
        vignetting_data = {
            "theta": [0.0, 0.5, 1.0, 1.5],
            "vignetting": [1.0, 0.95, 0.9, 0.85],
        }

        with unittest.mock.patch(
            "lsst.ts.observatory.control.utils.extras.guider_roi.get_vignetting_data_from_butler",
            return_value=vignetting_data,
        ):
            roi = GuiderROIs(butler=mock_butler)

            # Now test that get_guider_rois fails when DM stack is marked as
            # unavailable
            with unittest.mock.patch(
                "lsst.ts.observatory.control.utils.extras.guider_roi.DM_STACK_AVAILABLE",
                False,
            ):
                with pytest.raises(RuntimeError, match="DM stack not available"):
                    roi.get_guider_rois(
                        boresight_RA=127.5,
                        boresight_DEC=-44.2,
                        boresight_RotAngle=316.4,
                        roi_size=400,
                        roi_time=200,
                        band="i",
                    )

    @pytest.mark.skipif(not DM_STACK_AVAILABLE, reason="DM stack not available.")
    def test_get_guider_rois_no_catalog_data(self) -> None:
        """Test behavior when no catalog data is found in butler."""
        mock_butler = unittest.mock.Mock()

        # Mock valid vignetting data for initialization
        vignetting_data = {
            "theta": [0.0, 0.5, 1.0, 1.5],
            "vignetting": [1.0, 0.95, 0.9, 0.85],
        }

        with unittest.mock.patch(
            "lsst.ts.observatory.control.utils.extras.guider_roi.get_vignetting_data_from_butler",
            return_value=vignetting_data,
        ):
            roi = GuiderROIs(butler=mock_butler)

            # Mock the catalog data method to return empty list
            with unittest.mock.patch.object(
                roi, "_get_catalog_data_for_healpix", return_value=[]
            ):
                with pytest.raises(RuntimeError, match="No suitable guide stars found"):
                    roi.get_guider_rois(
                        boresight_RA=127.5,
                        boresight_DEC=-44.2,
                        boresight_RotAngle=316.4,
                        roi_size=400,
                        roi_time=200,
                        band="i",
                    )

    @pytest.mark.skipif(not DM_STACK_AVAILABLE, reason="DM stack not available.")
    def test_get_guider_rois_with_mock_data(self) -> None:
        """Test get_guider_rois with mock catalog data."""
        # TODO: Simple placeholder test - replace with real test later

        mock_butler = unittest.mock.Mock()

        # Create fake data that the class expects during initialization
        # Need at least 4 points for cubic spline (k=3) to work
        # These are just made-up numbers
        fake_data = {
            "theta": [0.0, 0.5, 1.0, 1.5],
            "vignetting": [1.0, 0.95, 0.9, 0.85],
        }

        with unittest.mock.patch(
            "lsst.ts.observatory.control.utils.extras.guider_roi.get_vignetting_data_from_butler",
            return_value=fake_data,
        ):
            # Just test that we can create the object without errors
            roi = GuiderROIs(butler=mock_butler)

            # Simple check that it worked
            assert roi.butler == mock_butler
            assert hasattr(roi, "vigspline")  # Check that the spline was created

    @pytest.mark.skipif(not DM_STACK_AVAILABLE, reason="DM stack not available.")
    def test_detector_type_selection(self) -> None:
        """Test that detector type selection works correctly."""
        mock_butler = unittest.mock.Mock()

        # Mock valid vignetting data for initialization
        vignetting_data = {
            "theta": [0.0, 0.5, 1.0, 1.5],
            "vignetting": [1.0, 0.95, 0.9, 0.85],
        }

        with unittest.mock.patch(
            "lsst.ts.observatory.control.utils.extras.guider_roi.get_vignetting_data_from_butler",
            return_value=vignetting_data,
        ):
            roi = GuiderROIs(butler=mock_butler)

            # Test that we can create GuiderROIs object and access camera
            assert roi.camera is not None

            # Test different detector type combinations
            test_cases = [
                (True, False, False),  # Only guiders
                (False, True, False),  # Only science
                (False, False, True),  # Only wavefront
                (True, True, True),  # All types
            ]

            for use_guider, use_science, use_wavefront in test_cases:
                # Mock to return empty catalog data so we get expected error
                with unittest.mock.patch.object(
                    roi, "_get_catalog_data_for_healpix", return_value=[]
                ):
                    with pytest.raises(
                        RuntimeError
                    ):  # Will fail due to no catalog data
                        roi.get_guider_rois(
                            boresight_RA=127.5,
                            boresight_DEC=-44.2,
                            boresight_RotAngle=316.4,
                            roi_size=400,
                            roi_time=200,
                            band="i",
                            use_guider=use_guider,
                            use_science=use_science,
                            use_wavefront=use_wavefront,
                        )


def test_dm_stack_available_flag() -> None:
    """Test that DM_STACK_AVAILABLE flag is accessible."""
    from lsst.ts.observatory.control.utils.extras.guider_roi import DM_STACK_AVAILABLE

    assert isinstance(DM_STACK_AVAILABLE, bool)


def test_best_effort_isr_available_flag() -> None:
    """Test that BEST_EFFORT_ISR_AVAILABLE flag is accessible."""
    from lsst.ts.observatory.control.utils.extras.guider_roi import (
        BEST_EFFORT_ISR_AVAILABLE,
    )

    assert isinstance(BEST_EFFORT_ISR_AVAILABLE, bool)


def test_get_monster_catalog_loader_from_butler() -> None:
    """Test the Monster catalog loader function."""
    if not DM_STACK_AVAILABLE:
        pytest.skip("DM stack not available")

    from lsst.ts.observatory.control.utils.extras.guider_roi import (
        get_monster_catalog_loader_from_butler,
    )

    mock_butler = unittest.mock.Mock()
    mock_refs = unittest.mock.Mock()
    mock_refs.expanded.return_value = []
    mock_butler.registry.queryDatasets.return_value = mock_refs

    result = get_monster_catalog_loader_from_butler(mock_butler)
    assert result == []
    mock_butler.registry.queryDatasets.assert_called_once_with("monster_guide_catalog")


def test_get_vignetting_data_from_butler() -> None:
    """Test the vignetting data loader function."""
    if not DM_STACK_AVAILABLE:
        pytest.skip("DM stack not available")

    from lsst.ts.observatory.control.utils.extras.guider_roi import (
        get_vignetting_data_from_butler,
    )

    mock_butler = unittest.mock.Mock()
    mock_butler.registry.queryDatasets.return_value = []

    result = get_vignetting_data_from_butler(mock_butler)
    assert result is None
    mock_butler.registry.queryDatasets.assert_called_once_with("vignetting_correction")

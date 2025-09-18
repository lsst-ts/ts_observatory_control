# This file is part of ts_observatory_control.
#
# Developed for the Vera Rubin Observatory Telescope and Site.
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
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""Vignetting correction data class for guider ROI selection."""

__all__ = ["VignettingCorrection"]

import logging
from pathlib import Path
from typing import Any, Dict, Optional, Union

import numpy as np
from astropy.table import Table
from scipy.interpolate import make_interp_spline

logger = logging.getLogger(__name__)


class VignettingCorrection:
    """Class to handle vignetting correction data with metadata.

    This class represents vignetting correction data as a function of angle
    from the boresight. It provides interpolation capabilities and metadata
    handling for versioning and provenance tracking.

    The data is stored in ECSV format which supports metadata.

    Parameters
    ----------
    theta : `numpy.ndarray`
        Array of angles from boresight in degrees.
    vignetting : `numpy.ndarray`
        Array of vignetting correction factors (0-1).
    metadata : `dict`, optional
        Dictionary containing metadata about the vignetting data.

    Attributes
    ----------
    theta : `numpy.ndarray`
        Array of angles from boresight in degrees.
    vignetting : `numpy.ndarray`
        Array of vignetting correction factors (0-1).
    metadata : `dict`
        Dictionary containing metadata about the vignetting data.
    spline : `scipy.interpolate.BSpline`
        Interpolation spline for vignetting correction.
    """

    def __init__(
        self,
        theta: np.ndarray,
        vignetting: np.ndarray,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Initialize VignettingCorrection.

        Parameters
        ----------
        theta : `numpy.ndarray`
            Array of angles from boresight in degrees.
        vignetting : `numpy.ndarray`
            Array of vignetting correction factors (0-1).
        metadata : `dict`, optional
            Dictionary containing metadata about the vignetting data.
            Should include provenance fields like 'data_source' and
            'processing_pipeline', etc.
            If provided, used as-is without modification.

        Raises
        ------
        ValueError
            If theta and vignetting arrays have different lengths or are empty.
        """

        theta = np.asarray(theta)
        vignetting = np.asarray(vignetting)

        if len(theta) != len(vignetting):
            raise ValueError(
                f"theta and vignetting arrays must have same length: "
                f"got {len(theta)} and {len(vignetting)}"
            )

        if len(theta) == 0:
            raise ValueError("theta and vignetting arrays cannot be empty")

        if not np.all(np.isfinite(theta)):
            raise ValueError("theta array contains non-finite values")

        if not np.all(np.isfinite(vignetting)):
            raise ValueError("vignetting array contains non-finite values")

        # Store data as Quantity objects with built-in units
        import astropy.units as u

        self.theta = theta.copy() * u.deg
        self.vignetting = vignetting.copy() * u.dimensionless_unscaled

        self.metadata = dict(metadata) if metadata is not None else {}

        # NOTE: This core spline interpolation logic was extracted
        # from the original guiderrois.py implementation by
        # Aaron Roodman and refactored here.
        self._create_spline()

    def _create_spline(self) -> None:
        """Create cubic spline interpolation for vignetting correction."""
        try:
            self.spline = make_interp_spline(
                self.theta.value, self.vignetting.value, k=3
            )
        except Exception as e:
            raise RuntimeError(
                f"Failed to create vignetting correction spline: {e}"
            ) from e

    def __call__(self, angle: Union[float, np.ndarray]) -> Union[float, np.ndarray]:
        """Calculate vignetting correction factor for given angle(s).

        Parameters
        ----------
        angle : `float` or `numpy.ndarray`
            Angle(s) from boresight in degrees.

        Returns
        -------
        correction_factor : `float` or `numpy.ndarray`
            Vignetting correction factor(s) (0-1).
        """
        return self.spline(angle)

    def delta_magnitude(
        self, angle: Union[float, np.ndarray]
    ) -> Union[float, np.ndarray]:
        """Calculate magnitude correction due to vignetting.

        Parameters
        ----------
        angle : `float` or `numpy.ndarray`
            Angle(s) from boresight in degrees.

        Returns
        -------
        delta_mag : `float` or `numpy.ndarray`
            Change in magnitude due to vignetting.
        """
        vignetting_factor = self(angle)
        return -2.5 * np.log10(vignetting_factor)

    @classmethod
    def from_batoid_simulation(
        cls,
        theta: np.ndarray,
        vignetting: np.ndarray,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "VignettingCorrection":
        """Create VignettingCorrection from Batoid ray-tracer simulation.

        This is a convenience method for programmatically creating vignetting
        data from Batoid simulations. For production use, consider saving data
        to NPZ + YAML metadata files and using the ingestion workflow.

        Parameters
        ----------
        theta : `numpy.ndarray`
            Array of angles from boresight in degrees.
        vignetting : `numpy.ndarray`
            Array of vignetting correction factors (0-1).
        metadata : `dict`, optional
            Metadata including provenance information. Should include
            'data_source' and 'processing_pipeline' fields.

        Returns
        -------
        vignetting_correction : `VignettingCorrection`
            VignettingCorrection object.
        """
        return cls(theta, vignetting, metadata=metadata)

    @classmethod
    def from_npz_file(
        cls,
        filepath: Union[str, Path],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "VignettingCorrection":
        """Create VignettingCorrection from NPZ file.

        Parameters
        ----------
        filepath : `str` or `pathlib.Path`
            Path to NPZ file containing 'theta' and 'vignetting' arrays.
        metadata : `dict`, optional
            Additional metadata to include.

        Returns
        -------
        vignetting_correction : `VignettingCorrection`
            VignettingCorrection instance.

        Raises
        ------
        FileNotFoundError
            If the file does not exist.
        KeyError
            If required keys are missing from the NPZ file.
        """
        filepath = Path(filepath)
        if not filepath.exists():
            raise FileNotFoundError(f"Vignetting file not found: {filepath}")

        try:
            data = np.load(filepath)
            theta = data["theta"]
            vignetting = data["vignetting"]
        except KeyError as e:
            raise KeyError(
                f"Required key {e} not found in NPZ file. "
                f"Available keys: {list(data.keys())}"
            ) from e

        # Add source file to metadata
        file_metadata = {"source_file": str(filepath.absolute())}
        if metadata is not None:
            file_metadata.update(metadata)

        return cls(theta, vignetting, metadata=file_metadata)

    @classmethod
    def from_ecsv_file(cls, filepath: Union[str, Path]) -> "VignettingCorrection":
        """Create VignettingCorrection from ECSV file.

        Parameters
        ----------
        filepath : `str` or `pathlib.Path`
            Path to ECSV file containing theta and vignetting columns.

        Returns
        -------
        vignetting_correction : `VignettingCorrection`
            VignettingCorrection instance.

        Raises
        ------
        FileNotFoundError
            If the file does not exist.
        ValueError
            If required columns are missing.
        """
        filepath = Path(filepath)
        if not filepath.exists():
            raise FileNotFoundError(f"Vignetting file not found: {filepath}")

        try:
            table = Table.read(filepath, format="ascii.ecsv")
        except Exception as e:
            raise ValueError(f"Failed to read ECSV file {filepath}: {e}") from e

        required_cols = ["theta", "vignetting"]
        missing_cols = [col for col in required_cols if col not in table.colnames]
        if missing_cols:
            raise ValueError(
                f"Missing required columns {missing_cols} in ECSV file. "
                f"Available columns: {table.colnames}"
            )

        metadata = dict(table.meta) if table.meta else {}
        metadata["source_file"] = str(filepath.absolute())

        # Extract data from table columns
        theta_data = table["theta"]
        vignetting_data = table["vignetting"]

        return cls(theta_data, vignetting_data, metadata=metadata)

    def to_ecsv_file(self, filepath: Union[str, Path]) -> None:
        """Save VignettingCorrection to ECSV file.

        Parameters
        ----------
        filepath : `str` or `pathlib.Path`
            Path where to save the ECSV file.
        """
        filepath = Path(filepath)

        # Create astropy table
        table = Table()
        table["theta"] = self.theta
        table["vignetting"] = self.vignetting

        # Add metadata
        table.meta.update(self.metadata)

        # Write to ECSV format
        table.write(filepath, format="ascii.ecsv", overwrite=True)
        logger.info(f"Saved vignetting correction to {filepath}")

    def to_table(self) -> Table:
        """Convert VignettingCorrection to Astropy Table.

        Returns
        -------
        table : `astropy.table.Table`
            Table containing theta, vignetting columns and metadata.
        """
        table = Table()
        table["theta"] = self.theta
        table["vignetting"] = self.vignetting
        table.meta.update(self.metadata)
        return table

    def __repr__(self) -> str:
        """String representation of VignettingCorrection."""
        return (
            f"VignettingCorrection(data_points={len(self.theta)}, "
            f"theta_range=[{self.theta.min():.2f}, {self.theta.max():.2f}] deg, "
            f"vignetting_range=[{self.vignetting.min():.3f}, {self.vignetting.max():.3f}])"
        )

    def __str__(self) -> str:
        """Human-readable string representation."""
        return self.__repr__()

    def validate(self) -> bool:
        """Validate the vignetting correction data.

        Returns
        -------
        valid : `bool`
            True if data is valid.

        Raises
        ------
        ValueError
            If validation fails.
        """
        # Check that theta is monotonically increasing
        if not np.all(np.diff(self.theta) > 0):
            raise ValueError("theta array must be monotonically increasing")

        # Check that vignetting values are reasonable (0-1.2 range)
        if np.any(self.vignetting < 0) or np.any(self.vignetting > 1.2):
            raise ValueError(
                "vignetting values should be in range [0, 1.2], "
                f"got range [{self.vignetting.min():.3f}, {self.vignetting.max():.3f}]"
            )

        # Check that spline exists and is functional
        if not hasattr(self, "spline"):
            raise ValueError("Interpolation spline not created")

        # Test spline with a sample value
        try:
            test_angle = (self.theta.min() + self.theta.max()) / 2
            _ = self.spline(test_angle)
        except Exception as e:
            raise ValueError(f"Spline interpolation failed: {e}") from e

        return True

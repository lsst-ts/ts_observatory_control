#!/usr/bin/env python3
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


"""
HEALPix ingestion of guide star catalog data into Butler repository.

This script ingests guide star catalog CSV files using Butler's HEALPix
dimensions.

Key features:
- Uses Butler's built-in HEALPix dimensions (healpix5 for nside=32)
- Supports metadata sidecar files for catalog andvignetting data
  provenance

Metadata Sidecar Files:
- Vignetting: Uses "guider_roi_vignetting.metadata.yaml"
- Catalogs: Uses "guider_roi_star_catalog.metadata.yaml"
- Standard location: python/lsst/ts/observatory/control/data/
- Data-specific location: Next to data files (overrides standard)

Usage:
    # Summit environment with LSSTCam (default)
    python ingest_guider_data.py \
        --ingested-by "Your Name <your.email@lsst.org>" \
        --contact "your.email@lsst.org" \
        --catalog-path /path/to/Monster_guide \
        --vignetting-file /path/to/vignetting_vs_angle.npz

    # Summit environment with LATISS
    python ingest_guider_data.py \
        --repo-name LATISS \
        --ingested-by "Your Name <your.email@lsst.org>" \
        --contact "your.email@lsst.org" \
        --catalog-path /path/to/Monster_guide \
        --vignetting-file /path/to/vignetting_vs_angle.npz

    # Test environment (uses local Butler repository)
    python ingest_guider_data.py \
        --repo-path /path/to/butler_data \
        --ingested-by "Your Name <your.email@lsst.org>" \
        --contact "your.email@lsst.org" \
        --catalog-path /path/to/Monster_guide \
        --vignetting-file /path/to/vignetting_vs_angle.npz

    # Dry run to check files without ingesting
    python ingest_guider_data.py \
        --dry-run \
        --ingested-by "Your Name <your.email@lsst.org>" \
        --contact "your.email@lsst.org" \
        --catalog-path /path/to/Monster_guide \
        --vignetting-file /path/to/vignetting_vs_angle.npz
"""

import argparse
import logging
import math
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import healpy as hp
from astropy.table import Table
from lsst.daf.butler import Butler, CollectionType, DatasetType

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

try:
    from lsst.ts.observatory.control.utils.extras.vignetting_correction import (
        VignettingCorrection,
    )
    from lsst.ts.observatory.control.utils.extras.vignetting_storage import (
        register_vignetting_storage_class,
    )
except ImportError as e:
    logger.error(f"Required classes not available: {e}")
    logger.error("Cannot proceed with ingestion without VignettingCorrection")
    sys.exit(1)

try:
    from lsst.summit.utils import makeDefaultButler
except ImportError:
    makeDefaultButler = None  # type: ignore

DEFAULT_CATALOG_DATASET_NAME = "guider_roi_monster_guide_catalog"
DEFAULT_VIGNETTING_DATASET_NAME = "guider_roi_vignetting_correction"

# Butler Storage class names
CATALOG_STORAGE_CLASS = "ArrowAstropy"
VIGNETTING_STORAGE_CLASS = "VignettingCorrection"

# Metadata sidecar file names
VIGNETTING_METADATA_FILENAME = "guider_roi_vignetting.metadata.yaml"
CATALOG_METADATA_FILENAME = "guider_roi_star_catalog.metadata.yaml"


def get_isolated_guide_count(catalog: Table) -> int:
    """Get count of isolated guide stars (guide_flag > 63).

    Parameters
    ----------
    catalog : `astropy.table.Table`
        Guide star catalog table.

    Returns
    -------
    count : `int`
        Number of isolated guide stars.
    """
    return len(catalog[catalog["guide_flag"] > 63])


def setup_catalog_metadata(
    catalog: Table, pixel_metadata: dict, provenance_metadata: Optional[dict] = None
) -> None:
    """Set up comprehensive metadata for guide star catalog.

    Parameters
    ----------
    catalog : `astropy.table.Table`
        Guide star catalog table.
    pixel_metadata : `dict`
        Pixel-specific and ingestion metadata to add.
    provenance_metadata : `dict`, optional
        Provenance metadata from YAML sidecar file.
    """
    # Guider-specific constants (always the same for this script)
    guider_constants = {
        # lsst organizational constants
        "facility_name": "vera c. rubin observatory",
        "access_format": "application/x-parquet",
        # guider catalog constants
        "dataproduct_type": "catalog",
        "dataproduct_subtype": "lsst.guide_star_catalog",
        "calib_level": 1,  # processed/calibrated catalog
        "target_name": "guide star selection",
        "science_program": "operations",
        "observation_reason": "guider_roi_selection",
        # default descriptions (can be overridden by yaml)
        "description": "guide star catalog for lsstcam guider roi selection",
        "version": "1.0",
        "coordinate_system": "icrs",
        "coordinate_epoch": "j2000.0",
        "magnitude_system": "ab",
        "guide_flag_description": "quality flag: >63 = isolated guide star",
        "data_source": "monster catalog + gaia dr3",  # default, can be overridden
        # technical metadata
        "created_date": datetime.now().isoformat(),
        "total_stars": len(catalog),
    }

    combined_metadata = {**guider_constants, **pixel_metadata}
    if provenance_metadata:
        combined_metadata.update(provenance_metadata)

    catalog.meta.update(combined_metadata)

    setup_column_metadata(catalog)


def setup_column_metadata(catalog: Table) -> None:
    """Set up column metadata with units and descriptions.

    Parameters
    ----------
    catalog : `astropy.table.Table`
        Guide star catalog table.
    """
    import astropy.units as u

    column_info = {
        "coord_ra": {
            "unit": u.deg,
            "description": "Right ascension (ICRS, J2000.0)",
        },
        "coord_dec": {"unit": u.deg, "description": "Declination (ICRS, J2000.0)"},
        "mag_u": {"unit": u.mag, "description": "u-band AB magnitude"},
        "mag_g": {"unit": u.mag, "description": "g-band AB magnitude"},
        "mag_r": {"unit": u.mag, "description": "r-band AB magnitude"},
        "mag_i": {"unit": u.mag, "description": "i-band AB magnitude"},
        "mag_z": {"unit": u.mag, "description": "z-band AB magnitude"},
        "mag_y": {"unit": u.mag, "description": "y-band AB magnitude"},
        "guide_flag": {"description": "Guide star quality flag (>63 = isolated)"},
        "healpix_id": {"description": "HEALPix pixel identifier"},
        "gaia_G": {"unit": u.mag, "description": "Gaia DR3 G-band magnitude"},
        "source_id": {"description": "Unique source identifier"},
        "pm_ra": {
            "unit": u.mas / u.yr,
            "description": "Proper motion in RA * cos(Dec)",
        },
        "pm_dec": {"unit": u.mas / u.yr, "description": "Proper motion in Dec"},
    }

    for col_name in catalog.colnames:
        if col_name in column_info:
            info = column_info[col_name]
            if "unit" in info:
                catalog[col_name].unit = info["unit"]
            if "description" in info:
                catalog[col_name].description = info["description"]


class GuiderDataIngester:
    """Ingest Monster guide catalog data using Butler's HEALPix dimensions."""

    def __init__(
        self,
        repo_path: Optional[str],
        ingested_by: str,
        ingestion_contact: str,
        collection: str = "guider_roi_data",
        catalog_path: Optional[str] = None,
        vignetting_file: Optional[str] = None,
        nside: int = 32,
        catalog_dataset_name: Optional[str] = None,
        vignetting_dataset_name: Optional[str] = None,
        repo_name: str = "LSSTCam",
    ) -> None:
        """Initialize the ingester.

        Parameters
        ----------
        repo_path : str, optional
            Path to Butler repository. If None, will use BestEffortIsr.
        ingested_by : str
            Name and email of person performing ingestion
            (e.g., "Your Name <your.email@lsst.org>")
        ingestion_contact : str
            Contact email for questions about this data
            (e.g., "your.email@lsst.org")
        collection : str
            Collection name for the ingested data
        catalog_path : str, optional
            Path to catalog directory. Required if ingesting catalogs.
        vignetting_file : str, optional
            Path to vignetting file. Required if ingesting vignetting.
        nside : int
            HEALPix nside parameter (default: 32, level 5)
        catalog_dataset_name : str, optional
            Name for catalog dataset type. If None, uses default.
        vignetting_dataset_name : str, optional
            Name for vignetting dataset type. If None, uses default.
        repo_name : str, optional
            Repository name for BestEffortIsr (e.g., LATISS, LSSTCam).
            Only used when repo_path is None. Default: LSSTCam.
        """
        self.repo_path = Path(repo_path) if repo_path else None
        self.repo_name = repo_name
        self.collection = collection
        self.ingested_by = ingested_by
        self.ingestion_contact = ingestion_contact

        # Store paths (will be validated later based on what's being ingested)
        self.catalog_path = Path(catalog_path) if catalog_path else None
        self.vignetting_file = Path(vignetting_file) if vignetting_file else None

        self.nside = nside
        self.healpix_level = int(math.log2(nside))
        self.npix = hp.nside2npix(nside)

        self.catalog_dataset_name = catalog_dataset_name or DEFAULT_CATALOG_DATASET_NAME
        self.vignetting_dataset_name = (
            vignetting_dataset_name or DEFAULT_VIGNETTING_DATASET_NAME
        )

        logger.info(
            f"HEALPix configuration: nside={self.nside}, level={self.healpix_level}"
        )
        logger.info(
            f"Dataset names: catalog={self.catalog_dataset_name}, "
            f"vignetting={self.vignetting_dataset_name}"
        )

        self.butler: Optional[Butler] = None
        self.use_besteffort: bool = False
        self.best_effort_isr: Optional[Any] = None

    def detect_butler_environment(self) -> Butler:
        """Detect and create appropriate Butler instance.

        Returns
        -------
        butler : Butler
            Butler instance ready for use

        Raises
        ------
        RuntimeError
            If no Butler can be created
        """
        logger.info("Detecting Butler environment...")

        if self.repo_path:
            logger.info(f" Using local repository: {self.repo_path}")
            return self._create_local_butler()
        else:
            if makeDefaultButler is None:
                raise RuntimeError(
                    "No --repo-path provided and summit_utils not available. "
                    "Either provide --repo-path for local Butler or run in an "
                    "environment with summit_utils installed."
                )
            logger.info(f"️  Using summit Butler for instrument: {self.repo_name}")
            return self._create_summit_butler()

    def _create_summit_butler(self) -> Butler:
        """Create Butler using makeDefaultButler for the specified
        instrument."""
        if makeDefaultButler is None:
            raise RuntimeError(
                "summit_utils is required but not available. "
                "Either provide --repo-path for local Butler or ensure summit_utils "
                "is available in your environment."
            )

        try:
            logger.info(f" Creating Butler for instrument: {self.repo_name}")
            butler = makeDefaultButler(
                self.repo_name,
                writeable=True,
                extraCollections=[],
            )
            if butler is None:
                raise RuntimeError(
                    f"makeDefaultButler returned None for {self.repo_name}"
                )
            self.use_besteffort = True
            self.best_effort_isr = None  # Not using BestEffortIsr anymore
            logger.info(f" Butler created successfully for {self.repo_name}")
            return butler
        except Exception as e:
            raise RuntimeError(f"Failed to create Butler for {self.repo_name}: {e}")

    def _create_local_butler(self) -> Butler:
        """Create Butler using local repository path.

        Note: Local Butler repositories for guider data ingestion are typically
        instrument-agnostic since we're only storing catalog and vignetting
        correction data, not actual instrument images.
        """
        if not self.repo_path:
            raise RuntimeError("No repository path provided for local Butler")

        try:
            if not self.repo_path.exists():
                Butler.makeRepo(self.repo_path)
                logger.info(f"Created new Butler repository: {self.repo_path}")
            else:
                logger.info(f"Using existing Butler repository: {self.repo_path}")

            # For local repositories, we don't specify instrument since
            # the catalog and vignetting data are instrument-agnostic
            butler = Butler.from_config(self.repo_path, writeable=True)
            self.use_besteffort = False
            logger.info(" Local Butler created successfully")
            logger.info(f"   Repository will store data for use with: {self.repo_name}")
            return butler
        except Exception as e:
            raise RuntimeError(
                f"Failed to create local Butler at {self.repo_path}: {e}"
            )

    def setup_butler_repo(
        self, register_catalog: bool = True, register_vignetting: bool = True
    ) -> None:
        """Set up Butler repository and register HEALPix dataset types."""
        try:
            self.butler = self.detect_butler_environment()

            try:
                register_vignetting_storage_class(self.butler)
                logger.info("Registered VignettingCorrection storage class")
            except Exception as e:
                logger.error(
                    f"Failed to register VignettingCorrection storage class: {e}"
                )
                raise

            logger.info("Registering HEALPix dataset types...")

            healpix_dim = f"healpix{self.healpix_level}"
            dimensions = self.butler.dimensions.conform([healpix_dim])

            logger.info(f"Using built-in HEALPix dimension: {healpix_dim}")
            logger.info(f"Dimension group: {dimensions}")

            if register_catalog:
                try:
                    self.butler.registry.getDatasetType(self.catalog_dataset_name)
                    logger.info(
                        f"Dataset type {self.catalog_dataset_name} already exists"
                    )
                except Exception:
                    catalog_dataset_type = DatasetType(
                        self.catalog_dataset_name,
                        dimensions=dimensions,
                        storageClass=CATALOG_STORAGE_CLASS,
                    )
                    self.butler.registry.registerDatasetType(catalog_dataset_type)
                    logger.info(
                        "Registered %s dataset type with storage class %s",
                        self.catalog_dataset_name,
                        CATALOG_STORAGE_CLASS,
                    )

            if register_vignetting:
                try:
                    self.butler.registry.getDatasetType(self.vignetting_dataset_name)
                    logger.info(
                        f"Dataset type {self.vignetting_dataset_name} already exists"
                    )
                except Exception:
                    # Dataset type doesn't exist, register it
                    vignetting_dataset_type = DatasetType(
                        self.vignetting_dataset_name,
                        dimensions=self.butler.dimensions.empty,
                        storageClass=VIGNETTING_STORAGE_CLASS,
                    )
                    self.butler.registry.registerDatasetType(vignetting_dataset_type)
                    logger.info(
                        "Registered %s dataset type with storage class %s",
                        self.vignetting_dataset_name,
                        VIGNETTING_STORAGE_CLASS,
                    )

            # Register collection
            try:
                existing_collections = list(
                    self.butler.registry.queryCollections(self.collection)
                )
                if self.collection in existing_collections:
                    logger.info(f"Collection {self.collection} already exists")
                else:
                    self.butler.registry.registerCollection(
                        self.collection, CollectionType.RUN
                    )
                    logger.info("Created collection: %s", self.collection)
            except Exception:
                # Try to create collection anyway
                try:
                    self.butler.registry.registerCollection(
                        self.collection, CollectionType.RUN
                    )
                    logger.info("Created collection: %s", self.collection)
                except Exception:
                    logger.warning(f"Could not create collection {self.collection}")

        except Exception as e:
            logger.error("Failed to set up Butler repository: %s", e)
            raise

    def check_source_files(
        self, check_catalog: bool = True, check_vignetting: bool = True
    ) -> bool:
        """Check if Monster guide catalog files and vignetting data exist
        and are readable."""
        logger.info("Checking source files...")

        missing_files = []

        if check_vignetting:
            if self.vignetting_file is None:
                missing_files.append("vignetting_file (not specified)")
            elif not self.vignetting_file.exists():
                missing_files.append(str(self.vignetting_file))
            else:
                logger.info(f"Found vignetting file: {self.vignetting_file}")

        # Check catalog files (nested directory structure)
        if check_catalog:
            if self.catalog_path is None:
                missing_files.append("catalog_path (not specified)")
            elif not self.catalog_path.exists():
                missing_files.append(str(self.catalog_path))
            else:
                # Find HEALPix pixel directories
                pixel_dirs = [
                    d
                    for d in self.catalog_path.iterdir()
                    if d.is_dir() and d.name.isdigit()
                ]

                if not pixel_dirs:
                    missing_files.append(f"{self.catalog_path}/<pixel_directories>")
                else:
                    total_csv_files = 0
                    for pixel_dir in pixel_dirs[:3]:  # Check first 3 directories
                        csv_files = list(pixel_dir.glob("*.csv"))
                        total_csv_files += len(csv_files)

                    logger.info(
                        f"Found {len(pixel_dirs)} directories in {self.catalog_path}"
                    )
                    logger.info(
                        f"Sample directories contain ~{total_csv_files} CSV files"
                    )
                    logger.info(
                        "Note: CSV filenames (without .csv) are the actual HEALPix pixel IDs"
                    )

                    # Check a sample file format from the first directory
                    if pixel_dirs:
                        sample_dir = pixel_dirs[0]
                        csv_files = list(sample_dir.glob("*.csv"))
                        if csv_files:
                            sample_file = csv_files[0]
                            try:
                                sample_catalog = Table.read(sample_file)
                                expected_columns = [
                                    "coord_ra",
                                    "coord_dec",
                                    "gaia_G",
                                    "mag_u",
                                    "mag_g",
                                    "mag_r",
                                    "mag_i",
                                    "mag_z",
                                    "mag_y",
                                    "guide_flag",
                                    # Note: healpix_id will be added
                                    # during ingestion
                                ]

                                missing_columns = [
                                    col
                                    for col in expected_columns
                                    if col not in sample_catalog.colnames
                                ]
                                if missing_columns:
                                    logger.warning(
                                        f"Missing expected columns in {sample_file.name}: "
                                        f"{missing_columns} (will be added during ingestion if needed)"
                                    )

                                logger.info(
                                    f"Sample file {sample_file.name} format check"
                                )
                                logger.info(f"  - Columns: {sample_catalog.colnames}")
                                logger.info(f"  - Stars: {len(sample_catalog)}")

                            except Exception as e:
                                logger.error(
                                    f"Failed to read sample file {sample_file.name}: {e}"
                                )
                                return False

        if missing_files:
            logger.error("Missing required files:")
            for f in missing_files:
                logger.error(f" - {f}")
            logger.error("\nPlease ensure the following exist:")
            if check_vignetting:
                logger.error(f"  1. Vignetting file: {self.vignetting_file}")
            if check_catalog:
                logger.error(f"  2. Catalog directory: {self.catalog_path}")
                logger.error("     with CSV files named by HEALPix pixel numbers")
            return False

        return True

    def ingest_vignetting_data(self) -> None:
        """Ingest vignetting correction data."""
        logger.info("Ingesting vignetting correction data...")

        if self.butler is None:
            raise RuntimeError("Butler not initialized")

        if self.vignetting_file is None:
            raise RuntimeError("Vignetting file not specified")

        try:
            # Look for metadata sidecar file in standard location
            package_data_dir = Path(__file__).parent.parent.parent
            standard_metadata_file = package_data_dir / VIGNETTING_METADATA_FILENAME

            # overrides standard location
            fallback_metadata_file = (
                self.vignetting_file.parent / VIGNETTING_METADATA_FILENAME
            )

            provenance_metadata: dict[str, Any] = {}
            metadata_file = None

            if fallback_metadata_file.exists():
                metadata_file = fallback_metadata_file
                logger.info(f"Found data-specific metadata file: {metadata_file}")
            elif standard_metadata_file.exists():
                metadata_file = standard_metadata_file
                logger.info(f"Using standard metadata file: {metadata_file}")

            if metadata_file:
                import yaml

                try:
                    with open(metadata_file, "r") as f:
                        provenance_metadata = yaml.safe_load(f) or {}
                    logger.info(
                        f"Loaded provenance metadata: {list(provenance_metadata.keys())}"
                    )
                except Exception as e:
                    logger.warning(f"Failed to read metadata file {metadata_file}: {e}")
            else:
                logger.warning("No metadata sidecar file found at:")
                logger.warning(f"  - Data-specific location: {fallback_metadata_file}")
                logger.warning(f"  - Standard location: {standard_metadata_file}")
                logger.warning(
                    "Consider creating a metadata file with provenance information"
                )

            # Combine guider-specific meta parameterswith ingestion ones
            ingestion_metadata = {
                # LSST organizational constants
                "facility_name": "Vera C. Rubin Observatory",
                "access_format": "text/ecsv",
                # Guider-specific constants (always the same for this script)
                "dataproduct_type": "calibration",
                "dataproduct_subtype": "Vignetting Correction",
                "target_name": "Vignetting Correction",
                "science_program": "Operations",
                "observation_reason": "guider_roi_calibration",
                # Default description (can be overridden by YAML)
                "description": "Vignetting correction vs angle from boresight for guide star flux correction",
                "version": "1.0",
                "coordinate_system": "boresight_angle",
                # Ingestion process tracking
                "ingestion_collection": self.collection,
                "ingested_by": self.ingested_by,
                "ingestion_contact": self.ingestion_contact,
                "ingestion_date": datetime.now().isoformat(),
            }

            # Provenance metadata takes precedence over defaults
            combined_metadata = {**ingestion_metadata, **provenance_metadata}

            logger.info("Creating VignettingCorrection object from NPZ file")
            vignetting_correction = VignettingCorrection.from_npz_file(
                self.vignetting_file,
                metadata=combined_metadata,
            )

            # Store the VignettingCorrection object
            self.butler.put(
                vignetting_correction,
                self.vignetting_dataset_name,
                dataId={},
                run=self.collection,
            )

            logger.info("Successfully ingested VignettingCorrection object")
            logger.info(f"  - Data points: {len(vignetting_correction.theta)}")
            logger.info(
                f"  - Theta range: {vignetting_correction.theta.min():.2f} to "
                f"{vignetting_correction.theta.max():.2f} degrees"
            )
            logger.info(
                f"  - Vignetting range: {vignetting_correction.vignetting.min():.3f} "
                f"to {vignetting_correction.vignetting.max():.3f}"
            )

        except Exception as e:
            logger.error(f"Failed to ingest vignetting data: {e}")
            raise

    def ingest_catalog_data(self) -> None:
        """Ingest Monster guide catalog data using HEALPix dimensions.

        Handles the nested directory structure where each CSV file
        represents a single HEALPix pixel (filename is the pixel ID).
        """
        logger.info("Ingesting Monster guide catalog data with HEALPix dimensions...")

        if self.butler is None:
            raise RuntimeError("Butler not initialized")

        if self.catalog_path is None:
            raise RuntimeError("Catalog path not specified")

        # Look for catalog metadata sidecar file in standard location
        package_data_dir = Path(__file__).parent.parent.parent
        standard_catalog_metadata_file = package_data_dir / CATALOG_METADATA_FILENAME

        # Fallback to override location in catalog directory
        fallback_catalog_metadata_file = self.catalog_path / CATALOG_METADATA_FILENAME

        catalog_provenance_metadata: dict[str, Any] = {}
        catalog_metadata_file = None

        if fallback_catalog_metadata_file.exists():
            catalog_metadata_file = fallback_catalog_metadata_file
            logger.info(
                f"Found data-specific catalog metadata file: {catalog_metadata_file}"
            )
        elif standard_catalog_metadata_file.exists():
            catalog_metadata_file = standard_catalog_metadata_file
            logger.info(
                f"Using standard catalog metadata file: {catalog_metadata_file}"
            )

        if catalog_metadata_file:
            import yaml

            try:
                with open(catalog_metadata_file, "r") as f:
                    catalog_provenance_metadata = yaml.safe_load(f) or {}
                logger.info(
                    f"Loaded catalog provenance metadata: {list(catalog_provenance_metadata.keys())}"
                )
            except Exception as e:
                logger.warning(
                    f"Failed to read catalog metadata file {catalog_metadata_file}: {e}"
                )
        else:
            logger.info("No catalog metadata sidecar file found at:")
            logger.info(f"  - Data-specific location: {fallback_catalog_metadata_file}")
            logger.info(f"  - Standard location: {standard_catalog_metadata_file}")
            logger.info(
                "Using default catalog metadata - consider creating a metadata file for provenance"
            )

        # Find all CSV files in all directories
        all_csv_files = []
        for pixel_dir in self.catalog_path.iterdir():
            if pixel_dir.is_dir() and pixel_dir.name.isdigit():
                csv_files = list(pixel_dir.glob("*.csv"))
                all_csv_files.extend(csv_files)

        if not all_csv_files:
            raise RuntimeError(f"No CSV files found in {self.catalog_path}")

        logger.info(f"Found {len(all_csv_files)} CSV files to ingest")

        success_count = 0
        total_stars = 0

        for csv_file in sorted(all_csv_files):
            try:
                # Extract HEALPix pixel ID from filename
                pixel_num = int(csv_file.stem)

                # Validate pixel number
                if pixel_num < 0 or pixel_num >= self.npix:
                    logger.warning(
                        f"Skipping pixel {pixel_num} outside valid range "
                        f"[0, {self.npix-1}]"
                    )
                    continue

                try:
                    table = Table.read(csv_file, format="ascii.csv")

                    if "healpix_id" not in table.colnames:
                        table["healpix_id"] = pixel_num

                except Exception as e:
                    logger.error(f"Failed to read {csv_file}: {e}")
                    raise RuntimeError(f"Failed to read CSV file {csv_file}: {e}")

                if len(table) == 0:
                    logger.warning(f"Empty catalog in {csv_file}")
                    continue

                pixel_metadata = {
                    "healpix_pixel": pixel_num,
                    "healpix_nside": self.nside,
                    "healpix_level": self.healpix_level,
                    "ingestion_collection": self.collection,
                    "ingested_by": self.ingested_by,
                    "ingestion_contact": self.ingestion_contact,
                    "ingestion_date": datetime.now().isoformat(),
                    "source_file": str(csv_file),
                    "source_directory": csv_file.parent.name,
                }

                setup_catalog_metadata(
                    table, pixel_metadata, catalog_provenance_metadata
                )

                healpix_dim = f"healpix{self.healpix_level}"
                dataId = {healpix_dim: int(pixel_num)}

                self.butler.put(
                    table,
                    self.catalog_dataset_name,
                    dataId=dataId,
                    run=self.collection,
                )

                success_count += 1
                total_stars += len(table)
                isolated_count = get_isolated_guide_count(table)
                isolated_pct = 100 * isolated_count / len(table)

                logger.info(
                    f"  Ingested HEALPix pixel {pixel_num}: "
                    f"{len(table)} stars from {csv_file.name}, "
                    f"{isolated_count} isolated guides ({isolated_pct:.1f}%)"
                )

            except Exception as e:
                logger.error(f"Failed to ingest CSV file {csv_file}: {e}")
                raise RuntimeError(f"CSV ingestion failed for {csv_file}: {e}")

        logger.info("Catalog ingestion complete:")
        logger.info(f"- Successfully processed: {success_count} HEALPix pixels")
        logger.info(f"- Total stars ingested: {total_stars}")

    def verify_ingestion(
        self, verify_catalog: bool = True, verify_vignetting: bool = True
    ) -> bool:
        """Verify that data was ingested correctly."""
        logger.info("Verifying ingested data...")

        if self.butler is None:
            raise RuntimeError("Butler not initialized")

        try:
            if verify_vignetting:
                vignetting = self.butler.get(
                    self.vignetting_dataset_name,
                    dataId={},
                    collections=[self.collection],
                )

                if not isinstance(vignetting, VignettingCorrection):
                    logger.error(
                        f"Expected VignettingCorrection object, got {type(vignetting)}"
                    )
                    return False

                logger.info(
                    "Vignetting correction data verified (VignettingCorrection)"
                )
                logger.info(f"  - Data points: {len(vignetting.theta)}")
                logger.info(
                    f"  - Theta range: [{vignetting.theta.min():.2f}, {vignetting.theta.max():.2f}] degrees"
                )
                logger.info(
                    f"  - Vignetting range: [{vignetting.vignetting.min():.3f}, "
                    f"{vignetting.vignetting.max():.3f}]"
                )
                description = vignetting.metadata.get("description", "No description")
                logger.info(f"  - Description: {description}")

            if verify_catalog:
                # Query all catalog datasets
                catalog_refs = list(
                    self.butler.registry.queryDatasets(
                        self.catalog_dataset_name, collections=[self.collection]
                    )
                )

                logger.info(f"Found {len(catalog_refs)} catalog datasets")

                if len(catalog_refs) == 0:
                    logger.error("No catalog datasets found")
                    return False

                # Verify a few datasets
                total_stars = 0
                total_isolated = 0
                pixel_ids = []

                # Check first 5
                for i, catalog_ref in enumerate(catalog_refs[:5]):
                    catalog = self.butler.get(catalog_ref)
                    pixel_id = catalog_ref.dataId[f"healpix{self.healpix_level}"]
                    pixel_ids.append(pixel_id)

                    isolated_count = len(catalog[catalog["guide_flag"] > 63])
                    total_stars += len(catalog)
                    total_isolated += isolated_count
                    isolated_pct = 100 * isolated_count / len(catalog)

                    metadata_info = ""
                    if hasattr(catalog, "meta") and catalog.meta:
                        version = catalog.meta.get("version", "unknown")
                        catalog_type = catalog.meta.get("catalog_type", "unknown")
                        metadata_info = f" [v{version}, {catalog_type}]"

                    logger.info(
                        f"  Pixel {pixel_id}: {len(catalog)} stars, "
                        f"{isolated_count} isolated ({isolated_pct:.1f}%){metadata_info}"
                    )

                logger.info("Sample verification complete:")
                logger.info(f"- Pixels checked: {pixel_ids}")
                logger.info(f"- Total stars in sample: {total_stars}")
                total_isolated_pct = 100 * total_isolated / total_stars
                logger.info(
                    f"- Total isolated guides: {total_isolated} "
                    f"({total_isolated_pct:.1f}%)"
                )

                # Check that we can query by HEALPix pixel
                test_pixel = pixel_ids[0]
                healpix_dim = f"healpix{self.healpix_level}"

                test_datasets = list(
                    self.butler.registry.queryDatasets(
                        self.catalog_dataset_name,
                        collections=[self.collection],
                        where=f"{healpix_dim} = pixel_id",
                        bind={"pixel_id": test_pixel},
                    )
                )

                if len(test_datasets) == 1:
                    logger.info(f" HEALPix query test passed for pixel {test_pixel}")
                else:
                    expected_count = 1
                    actual_count = len(test_datasets)
                    logger.error(
                        f"HEALPix query test failed: expected {expected_count} "
                        f"dataset, got {actual_count}"
                    )
                    return False

            return True

        except Exception as e:
            logger.error(f"Verification failed: {e}")
            return False

    def run_ingestion(
        self, ingest_catalog: bool = True, ingest_vignetting: bool = True
    ) -> bool:
        """Run the complete ingestion process."""
        logger.info("Starting Monster guide data ingestion...")
        logger.info(f"Repository: {self.repo_path}")
        logger.info(f"Collection: {self.collection}")
        logger.info(f"Catalog path: {self.catalog_path}")
        logger.info(f"Vignetting file: {self.vignetting_file}")
        logger.info(f"HEALPix: nside={self.nside}, level={self.healpix_level}")

        if not ingest_catalog and not ingest_vignetting:
            logger.error(
                "Must select at least one type of data to ingest "
                "(catalog or vignetting)"
            )
            return False

        logger.info(
            f"Ingestion plan: catalog={ingest_catalog}, "
            f"vignetting={ingest_vignetting}"
        )

        if not self.check_source_files(ingest_catalog, ingest_vignetting):
            return False

        self.setup_butler_repo(ingest_catalog, ingest_vignetting)

        if ingest_vignetting:
            self.ingest_vignetting_data()

        if ingest_catalog:
            self.ingest_catalog_data()

        if self.verify_ingestion(ingest_catalog, ingest_vignetting):
            logger.info("Ingestion completed successfully!")
            logger.info(f"Repository: {self.repo_path}")
            logger.info(f"Collection: {self.collection}")
            if ingest_catalog:
                logger.info(f"Catalog dataset type: {self.catalog_dataset_name}")
                logger.info(f"HEALPix dimension: healpix{self.healpix_level}")
            if ingest_vignetting:
                logger.info(f"Vignetting dataset type: {self.vignetting_dataset_name}")
            return True
        else:
            logger.error("Ingestion verification failed!")
            return False


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest Monster guide catalog data using Butler's HEALPix "
        "dimensions"
    )

    # Required data
    parser.add_argument(
        "--ingested-by",
        required=True,
        help="Name and email of person performing ingestion (e.g., 'your name <your.email@lsst.org>')",
    )
    parser.add_argument(
        "--contact",
        required=True,
        help="Contact email for questions about this data (e.g., 'your.email@lsst.org')",
    )

    # Repository and data parameters
    parser.add_argument(
        "--repo-path",
        help="Path to Butler repository. If provided, uses local Butler. "
        "If not provided, uses BestEffortIsr with --repo-name (default: LSSTCam)",
    )
    parser.add_argument(
        "--repo-name",
        default="LSSTCam",
        help="Repository name for BestEffortIsr (e.g., LATISS, LSSTCam). "
        "Only used when --repo-path is not specified. Default: LSSTCam",
    )
    parser.add_argument(
        "--collection",
        default="guider_roi_data",
        help="Collection name for ingested data (default: guider_roi_data)",
    )
    parser.add_argument(
        "--catalog-path",
        help="Path to Monster guide catalog directory. "
        f"Provenance metadata will be read from {CATALOG_METADATA_FILENAME} in this directory "
        "if present, or from the package data directory as fallback. "
        "Required unless --vignetting-only is specified.",
    )
    parser.add_argument(
        "--vignetting-file",
        help="Path to vignetting file. Provenance metadata will be read from "
        f"{VIGNETTING_METADATA_FILENAME} in the same directory as the file if present, "
        "or from the package data directory as fallback. "
        "Required unless --catalog-only is specified.",
    )
    parser.add_argument(
        "--nside", type=int, default=32, help="HEALPix nside parameter (default: 32)"
    )
    parser.add_argument(
        "--catalog-only",
        action="store_true",
        help="Only ingest catalog data (skip vignetting)",
    )
    parser.add_argument(
        "--vignetting-only",
        action="store_true",
        help="Only ingest vignetting data (skip catalog)",
    )
    parser.add_argument(
        "--catalog-dataset-name",
        help=f"Name for catalog dataset type (default: {DEFAULT_CATALOG_DATASET_NAME})",
    )
    parser.add_argument(
        "--vignetting-dataset-name",
        help=f"Name for vignetting dataset type "
        f"(default: {DEFAULT_VIGNETTING_DATASET_NAME})",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Check files without actually ingesting"
    )

    args = parser.parse_args()

    # Validate nside is a power of 2
    if args.nside <= 0 or (args.nside & (args.nside - 1)) != 0:
        logger.error(f"nside must be a power of 2, got {args.nside}")
        sys.exit(1)

    # Validate conflicting options
    if args.catalog_only and args.vignetting_only:
        logger.error("Cannot specify both --catalog-only and --vignetting-only")
        sys.exit(1)

    # Determine what to ingest
    ingest_catalog = not args.vignetting_only
    ingest_vignetting = not args.catalog_only

    if ingest_catalog and not args.catalog_path:
        logger.error("--catalog-path is required when ingesting catalog data")
        logger.error("Use --vignetting-only to skip catalog ingestion")
        sys.exit(1)

    if ingest_vignetting and not args.vignetting_file:
        logger.error("--vignetting-file is required when ingesting vignetting data")
        logger.error("Use --catalog-only to skip vignetting ingestion")
        sys.exit(1)

    ingester = GuiderDataIngester(
        args.repo_path,
        args.ingested_by,
        args.contact,
        collection=args.collection,
        catalog_path=args.catalog_path,
        vignetting_file=args.vignetting_file,
        nside=args.nside,
        catalog_dataset_name=args.catalog_dataset_name,
        vignetting_dataset_name=args.vignetting_dataset_name,
        repo_name=args.repo_name,
    )

    if args.dry_run:
        logger.info("Running in dry-run mode...")
        logger.info(
            f"Would ingest: catalog={ingest_catalog}, "
            f"vignetting={ingest_vignetting}"
        )
        if ingester.check_source_files(ingest_catalog, ingest_vignetting):
            logger.info("All required source files found - ready for ingestion")
        else:
            logger.error("Missing source files - cannot proceed")
        return

    success = ingester.run_ingestion(ingest_catalog, ingest_vignetting)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

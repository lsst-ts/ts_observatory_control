#!/usr/bin/env python3
"""
HEALPix ingestion of guide star catalog data into Butler repository.

This script ingests guide star catalog CSV files using Butler's HEALPix
dimensions.

Key features:
- Uses Butler's built-in HEALPix dimensions (healpix5 for nside=32)
- Preserves guide star catalog format exactly

Usage:
    python ingest_guider_data.py [--repo-path REPO_PATH] \
        [--collection COLLECTION]
    python ingest_guider_data.py [--catalog-path CATALOG_PATH] \
        [--nside NSIDE]
"""

import argparse
import logging
import math
import shutil
import sys
from pathlib import Path
from typing import Optional

import healpy as hp
import numpy as np
from astropy.table import Table
from lsst.daf.butler import Butler, CollectionType, DatasetType

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# DEFAULT_CATALOG_DATASET_NAME = "monster_guide_catalog"
DEFAULT_CATALOG_DATASET_NAME = "healpix_catalog"
DEFAULT_VIGNETTING_DATASET_NAME = "vignetting_correction"


class GuiderDataIngester:
    """Ingest Monster guide catalog data using Butler's HEALPix dimensions."""

    def __init__(
        self,
        repo_path: str,
        collection: str = "monster_guide",
        catalog_path: Optional[str] = None,
        vignetting_file: Optional[str] = None,
        nside: int = 32,
        catalog_dataset_name: Optional[str] = None,
        vignetting_dataset_name: Optional[str] = None,
    ) -> None:
        """Initialize the ingester.

        Parameters
        ----------
        repo_path : str
            Path to Butler repository
        collection : str
            Collection name for the ingested data
        catalog_path : str, optional
            Path to catalog directory. If None, uses Monster_guide in
            current directory.
        vignetting_file : str, optional
            Path to vignetting file. If None, uses default hardcoded path.
        nside : int
            HEALPix nside parameter (default: 32, level 5)
        catalog_dataset_name : str, optional
            Name for catalog dataset type. If None, uses default.
        vignetting_dataset_name : str, optional
            Name for vignetting dataset type. If None, uses default.
        """
        self.repo_path = Path(repo_path)
        self.collection = collection

        # Set catalog path
        if catalog_path is not None:
            self.catalog_path = Path(catalog_path)
        else:
            # Look for Monster_guide in ts_observatory_control directory
            self.catalog_path = Path(__file__).parent.parent / "Monster_guide"

        # Set vignetting file path
        if vignetting_file is not None:
            self.vignetting_file = Path(vignetting_file)
        else:
            # Use default path
            self.vignetting_file = Path("vignetting_vs_angle.npz")

        # HEALPix configuration
        self.nside = nside
        self.healpix_level = int(math.log2(nside))  # Calculate level from nside
        self.npix = hp.nside2npix(nside)

        # Dataset names
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

    def setup_butler_repo(
        self, register_catalog: bool = True, register_vignetting: bool = True
    ) -> None:
        """Set up Butler repository and register HEALPix dataset types."""
        logger.info("Setting up Butler repository at %s", self.repo_path)

        try:
            # Create repository if it doesn't exist, otherwise clean it
            if self.repo_path.exists():
                logger.info("Removing existing repository for fresh start...")
                shutil.rmtree(self.repo_path)

            Butler.makeRepo(self.repo_path)
            logger.info("Created new Butler repository")

            # Connect to the repository
            self.butler = Butler(self.repo_path, writeable=True)

            # Register HEALPix dataset types
            logger.info("Registering HEALPix dataset types...")

            healpix_dim = f"healpix{self.healpix_level}"
            dimensions = self.butler.dimensions.conform([healpix_dim])

            logger.info(f"Using built-in HEALPix dimension: {healpix_dim}")
            logger.info(f"Dimension group: {dimensions}")

            # Register catalog dataset type
            if register_catalog:
                catalog_dataset_type = DatasetType(
                    self.catalog_dataset_name,
                    dimensions=dimensions,
                    storageClass="ArrowAstropy",
                )
                self.butler.registry.registerDatasetType(catalog_dataset_type)
                logger.info("Registered %s dataset type", self.catalog_dataset_name)

            # Register vignetting dataset type (no dimensions - global data)
            if register_vignetting:
                vignetting_dataset_type = DatasetType(
                    self.vignetting_dataset_name,
                    dimensions=self.butler.dimensions.empty,
                    storageClass="StructuredDataDict",
                )
                self.butler.registry.registerDatasetType(vignetting_dataset_type)
                logger.info("Registered %s dataset type", self.vignetting_dataset_name)

            # Register collection
            self.butler.registry.registerCollection(self.collection, CollectionType.RUN)
            logger.info("Created collection: %s", self.collection)

        except Exception as e:
            logger.error("Failed to set up Butler repository: %s", e)
            raise

    def check_source_files(
        self, check_catalog: bool = True, check_vignetting: bool = True
    ) -> bool:
        """Check if Monster guide catalog files and vignetting data exist and
        are readable."""
        logger.info("Checking source files...")

        missing_files = []

        # Check vignetting file
        if check_vignetting:
            if not self.vignetting_file.exists():
                missing_files.append(str(self.vignetting_file))
            else:
                logger.info(f"Found vignetting file: {self.vignetting_file}")

        # Check catalog files
        if check_catalog:
            if not self.catalog_path.exists():
                missing_files.append(str(self.catalog_path))
            else:
                csv_files = list(self.catalog_path.glob("*.csv"))

                if not csv_files:
                    missing_files.append(f"{self.catalog_path}/*.csv")
                else:
                    logger.info(
                        f"Found {len(csv_files)} CSV files in {self.catalog_path}"
                    )

                    # Check a sample file format
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
                            "healpix_id",
                        ]

                        missing_columns = [
                            col
                            for col in expected_columns
                            if col not in sample_catalog.colnames
                        ]
                        if missing_columns:
                            logger.error(
                                f"Missing expected columns in {sample_file.name}: "
                                f"{missing_columns}"
                            )
                            return False

                        logger.info(
                            f"Sample file {sample_file.name} has correct format"
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

        try:
            vigdata = np.load(self.vignetting_file)

            vignetting_dict = {
                "theta": vigdata["theta"].tolist(),
                "vignetting": vigdata["vignetting"].tolist(),
                "metadata": {
                    "description": "Vignetting correction vs angle from boresight",
                    "theta_units": "degrees",
                    "vignetting_units": "fraction",
                    "source_file": str(self.vignetting_file),
                    "interpolation_kind": "cubic_spline_k3",
                },
            }

            self.butler.put(
                vignetting_dict,
                self.vignetting_dataset_name,
                dataId={},
                run=self.collection,
            )

            logger.info("Successfully ingested vignetting correction data")
            theta_min = vigdata["theta"].min()
            theta_max = vigdata["theta"].max()
            vig_min = vigdata["vignetting"].min()
            vig_max = vigdata["vignetting"].max()
            logger.info(f"  - Theta range: {theta_min:.2f} to {theta_max:.2f} degrees")
            logger.info(f"  - Vignetting range: {vig_min:.3f} to {vig_max:.3f}")

        except Exception as e:
            logger.error(f"Failed to ingest vignetting data: {e}")
            raise

    def ingest_catalog_data(self) -> None:
        """Ingest Monster guide catalog data using HEALPix dimensions."""
        logger.info("Ingesting Monster guide catalog data with HEALPix dimensions...")

        if self.butler is None:
            raise RuntimeError("Butler not initialized")

        csv_files = list(self.catalog_path.glob("*.csv"))

        success_count = 0
        error_count = 0
        total_stars = 0

        for csv_file in csv_files:
            try:
                # Extract HEALPix pixel number from filename
                pixel_str = csv_file.stem

                try:
                    pixel_num = int(pixel_str)
                except ValueError:
                    logger.warning(f"Skipping non-numeric filename: {csv_file.name}")
                    continue

                # Validate pixel number
                if pixel_num < 0 or pixel_num >= self.npix:
                    logger.warning(
                        f"Skipping pixel {pixel_num} outside valid range "
                        f"[0, {self.npix-1}]"
                    )
                    continue

                # Load catalog
                catalog = Table.read(csv_file)

                # Verify healpix_id matches filename
                if "healpix_id" in catalog.colnames:
                    catalog_pixels = set(catalog["healpix_id"])
                    if len(catalog_pixels) > 1 or pixel_num not in catalog_pixels:
                        logger.warning(
                            f"HEALPix ID mismatch in {csv_file.name}: "
                            f"expected {pixel_num}, found {catalog_pixels}"
                        )

                # Create data ID for HEALPix dimension
                healpix_dim = f"healpix{self.healpix_level}"
                dataId = {healpix_dim: int(pixel_num)}

                # Store the catalog
                self.butler.put(
                    catalog,
                    self.catalog_dataset_name,
                    dataId=dataId,
                    run=self.collection,
                )

                success_count += 1
                total_stars += len(catalog)
                isolated_stars = catalog[catalog["guide_flag"] > 63]
                isolated_pct = 100 * len(isolated_stars) / len(catalog)

                logger.info(
                    f"  ✓ Ingested HEALPix pixel {pixel_num}: {len(catalog)} stars, "
                    f"{len(isolated_stars)} isolated guides ({isolated_pct:.1f}%)"
                )

            except Exception as e:
                error_count += 1
                logger.error(f"Failed to ingest {csv_file.name}: {e}")
                if error_count > 5:
                    logger.error("Too many errors, stopping ingestion")
                    break

        logger.info("Catalog ingestion complete:")
        logger.info(f"- Successfully processed: {success_count} HEALPix pixels")
        logger.info(f"- Total stars ingested: {total_stars}")
        if error_count > 0:
            logger.warning(f"- Errors: {error_count} files")

    def verify_ingestion(
        self, verify_catalog: bool = True, verify_vignetting: bool = True
    ) -> bool:
        """Verify that data was ingested correctly."""
        logger.info("Verifying ingested data...")

        if self.butler is None:
            raise RuntimeError("Butler not initialized")

        try:
            # Check vignetting data
            if verify_vignetting:
                vignetting = self.butler.get(
                    self.vignetting_dataset_name,
                    dataId={},
                    collections=[self.collection],
                )
                logger.info("Vignetting correction data verified")
                logger.info(f"  - Theta points: {len(vignetting['theta'])}")
                metadata = vignetting.get("metadata", {})
                description = metadata.get("description", "No description")
                logger.info(f"  - Metadata: {description}")

            # Check catalog data
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

                for i, catalog_ref in enumerate(catalog_refs[:5]):  # Check first 5
                    catalog = self.butler.get(catalog_ref)
                    pixel_id = catalog_ref.dataId[f"healpix{self.healpix_level}"]
                    pixel_ids.append(pixel_id)

                    isolated_count = len(catalog[catalog["guide_flag"] > 63])
                    total_stars += len(catalog)
                    total_isolated += isolated_count
                    isolated_pct = 100 * isolated_count / len(catalog)

                    logger.info(
                        f"  Pixel {pixel_id}: {len(catalog)} stars, "
                        f"{isolated_count} isolated ({isolated_pct:.1f}%)"
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
                    logger.info(f"✓ HEALPix query test passed for pixel {test_pixel}")
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
            logger.info("🎉 ingestion completed successfully!")
            logger.info(f"Repository: {self.repo_path}")
            logger.info(f"Collection: {self.collection}")
            if ingest_catalog:
                logger.info(f"Catalog dataset type: {self.catalog_dataset_name}")
                logger.info(f"HEALPix dimension: healpix{self.healpix_level}")
            if ingest_vignetting:
                logger.info(f"Vignetting dataset type: {self.vignetting_dataset_name}")
            return True
        else:
            logger.error("❌ ingestion verification failed!")
            return False


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest Monster guide catalog data using Butler's HEALPix "
        "dimensions"
    )
    parser.add_argument(
        "--repo-path",
        default="monster_guide_repo",
        help="Path to Butler repository (default: monster_guide_repo)",
    )
    parser.add_argument(
        "--collection",
        default="monster_guide",
        help="Collection name for ingested data (default: monster_guide)",
    )
    parser.add_argument(
        "--catalog-path", help="Override path to Monster guide catalog directory"
    )
    parser.add_argument(
        "--vignetting-file",
        help="Override path to vignetting file (default: vignetting_vs_angle.npz)",
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

    # Determine what to ingest
    if args.catalog_only and args.vignetting_only:
        logger.error("Cannot specify both --catalog-only and --vignetting-only")
        sys.exit(1)

    ingest_catalog = not args.vignetting_only
    ingest_vignetting = not args.catalog_only

    ingester = GuiderDataIngester(
        args.repo_path,
        args.collection,
        catalog_path=args.catalog_path,
        vignetting_file=args.vignetting_file,
        nside=args.nside,
        catalog_dataset_name=args.catalog_dataset_name,
        vignetting_dataset_name=args.vignetting_dataset_name,
    )

    if args.dry_run:
        logger.info("Running in dry-run mode...")
        logger.info(
            f"Would ingest: catalog={ingest_catalog}, "
            f"vignetting={ingest_vignetting}"
        )
        if ingester.check_source_files(ingest_catalog, ingest_vignetting):
            logger.info("✓ All required source files found - ready for ingestion")
        else:
            logger.error("❌ Missing source files - cannot proceed")
        return

    success = ingester.run_ingestion(ingest_catalog, ingest_vignetting)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

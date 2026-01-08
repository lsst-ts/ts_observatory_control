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
Simple test script for GuiderROIs with existing Butler repository.

This script tests GuiderROIs functionality with an existing Butler repository
containing ingested guide star catalog and vignetting data.

Usage:
    # Summit environment (uses makeDefaultButler, defaults to LSSTCam)
    python guider_roi_test_script.py \\
        --collection u/your_username/guider_roi_data \\
        --pixel 1064

    # Summit environment with LATISS repository
    python guider_roi_test_script.py \\
        --repo-name LATISS \\
        --collection latiss_guider_data \\
        --pixel 1064

    # Local environment (uses local Butler repository)
    cd ts_observatory_control
    PYTHONPATH=${PWD}/python python \\
        python/lsst/ts/observatory/control/ \\
        data/scripts/guider_roi/guider_roi_test_script.py \\
        --repo-path butler_data \\
        --collection guider_roi_data \\
        --pixel 1064

    # Test with specific RA/Dec coordinates
    python guider_roi_test_script.py \\
        --collection u/your_username/guider_roi_data \\
        --ra 45.0 --dec -30.0
"""

import argparse
import sys
from pathlib import Path
from typing import Any, Optional

import healpy as hp
import numpy as np
from lsst.daf.butler import Butler
from lsst.ts.observatory.control.utils.extras.guider_roi import GuiderROIs  # noqa: F401


def check_dependencies() -> bool:
    """Check if required dependencies are available."""
    print(" Checking Dependencies:")
    print("=" * 40)

    # Basic dependencies
    try:
        import healpy  # noqa: F401
        from astropy.coordinates import angular_separation  # noqa: F401
        from astropy.table import Table, vstack  # noqa: F401
        from scipy.interpolate import make_interp_spline  # noqa: F401

        print(" Basic deps (healpy, astropy, scipy)")
    except ImportError as e:
        print(f"ERROR: Basic deps not available: {e}")
        return False

    # DM Stack
    try:
        import lsst.geom  # noqa: F401
        from lsst.afw import cameraGeom  # noqa: F401
        from lsst.obs.lsst import LsstCam  # noqa: F401

        print(" DM Stack (includes Butler)")
    except ImportError as e:
        print(f"ERROR: DM Stack not available: {e}")
        return False

    try:
        from lsst.summit.utils import makeDefaultButler  # noqa: F401

        summit_utils = True
        print(" summit_utils (makeDefaultButler)")
    except ImportError:
        summit_utils = False

        print("ERROR: summit_utils not available")

    print(f"\n Mode: {'Summit' if summit_utils else 'Local'} environment")
    return True


def check_butler_repository(
    repo_path: Optional[str],
    collection: str,
    catalog_dataset: str,
    nside: int = 32,
    repo_name: str = "LSSTCam",
) -> list[int]:
    """Check if Butler repository exists and has data."""
    if repo_path:
        print(f"\n Checking Butler repository: {repo_path}")
        repo = Path(repo_path)
        if not repo.exists():
            print(f"ERROR: Butler repository not found: {repo}")
            return []
        butler = Butler.from_config(repo_path)
    else:
        print(f"\n Checking Butler repository: Summit ({repo_name})")
        try:
            from lsst.summit.utils import makeDefaultButler

            butler = makeDefaultButler(repo_name, writeable=False)
            if butler is None:
                print(f"ERROR: makeDefaultButler returned None for {repo_name}")
                return []
        except Exception as e:
            print(f"ERROR: Failed to create Butler for {repo_name}: {e}")
            return []

    try:

        # Check collection exists
        collections = list(butler.registry.queryCollections())
        if collection not in collections:
            print(f"ERROR: Collection '{collection}' not found")
            print(f"   Available: {collections}")
            return []

        # Get catalog datasets
        try:
            datasets = list(
                butler.registry.queryDatasets(catalog_dataset, collections=[collection])
            )
        except Exception as dataset_error:
            print(f"ERROR: Failed to query datasets: {dataset_error}")
            return []

        if not datasets:
            print("ERROR: No catalog datasets found")
            print(f"   Dataset name: {catalog_dataset}")
            print(f"   Collection: {collection}")
            return []

        # Extract HEALPix pixel IDs (using notebook approach)
        pixels = []
        # Calculate healpix dimension name from nside
        healpix_level = int(np.log2(nside))
        healpix_dim = f"healpix{healpix_level}"
        print(f"   Looking for HEALPix dimension: {healpix_dim} (nside={nside})")

        for dataset in datasets:
            try:
                if healpix_dim in dataset.dataId:
                    pixel_id = int(dataset.dataId[healpix_dim])
                    pixels.append(pixel_id)
                else:
                    # Fallback: try to find any healpix dimension
                    found = False
                    for key in dataset.dataId.dimensions.data_coordinate_keys:
                        if key.startswith("healpix"):
                            pixels.append(int(dataset.dataId[key]))
                            found = True
                            break
                    if not found:
                        print(
                            f"   Warning: No healpix dimension found in dataset {dataset}"
                        )
            except Exception as pixel_error:
                print(
                    f"   Warning: Could not extract pixel from dataset {dataset}: {pixel_error}"
                )
                continue

        pixels = sorted(pixels)
        print(f" Repository verified: {len(datasets)} datasets")
        print(f"   Collection: {collection}")
        truncated = "..." if len(pixels) > 10 else ""
        print(f"   HEALPix pixels: {pixels[:10]}{truncated}")

        return pixels

    except Exception as e:
        print(f"ERROR: Error checking repository: {e}")
        import traceback

        traceback.print_exc()
        return []


def test_vignetting_correction(groi: Any) -> None:
    """Test vignetting correction functionality."""
    print("\n Testing vignetting correction:")
    test_angles = [0.0, 0.5, 1.0, 1.5, 2.0]
    for angle in test_angles:
        correction = groi.vignetting_correction(angle)
        print(f"  Angle {angle:3.1f}°: Δmag = {correction:+.4f}")


def test_catalog_access(groi: Any, nside: int) -> None:
    """Test catalog data access."""
    print("\n Testing catalog access:")

    try:
        # Get some datasets to test with
        datasets = list(
            groi.butler.registry.queryDatasets(
                groi.catalog_name, collections=[groi.collection]
            )
        )[
            :3
        ]  # Test first 3

        if not datasets:
            print("   ERROR: No catalog datasets found")
            return

        # Extract pixel IDs (use groi's healpix dimension)
        test_pixels = []
        healpix_dim = groi.healpix_dim  # Get the dimension from GuiderROIs

        for dataset in datasets:
            try:
                if healpix_dim in dataset.dataId:
                    pixel_id = dataset.dataId[healpix_dim]
                    test_pixels.append(pixel_id)
                else:
                    print(
                        f"     Warning: Expected dimension {healpix_dim} not found in dataset {dataset}"
                    )
            except Exception as pixel_error:
                print(
                    f"     Warning: Could not extract pixel from {dataset}: {pixel_error}"
                )
                continue

        print(f"  Testing with pixels: {test_pixels}")

        # Test catalog retrieval
        tables = groi._get_catalog_data_from_butler(test_pixels)
        print(f"  Retrieved {len(tables)} catalog tables")

        if tables:
            total_stars = sum(len(table) for table in tables)
            print(f"  Total stars: {total_stars}")

            # Count isolated guide stars
            isolated_counts = []
            for table in tables:
                isolated = table["guide_flag"] > 63
                isolated_counts.append(isolated.sum())

            print(f"  Isolated guide stars: {isolated_counts}")
            print(f"  Total isolated: {sum(isolated_counts)}")

    except Exception as e:
        print(f"   ERROR: Catalog test failed: {e}")
        import traceback

        traceback.print_exc()


def test_roi_selection(
    groi: Any,
    nside: int,
    ra: Optional[float] = None,
    dec: Optional[float] = None,
    pixel: Optional[int] = None,
) -> None:
    """Test ROI selection with specified or auto-selected coordinates."""
    print("\n Testing ROI selection:")

    if ra is not None and dec is not None:
        # Priority 1: Use user-specified RA/Dec coordinates
        test_pixel = hp.ang2pix(nside, ra, dec, lonlat=True)
        print(f"  User coordinates: RA={ra:.3f}°, Dec={dec:.3f}° (pixel {test_pixel})")
    elif pixel is not None:
        # Priority 2: Use user-specified pixel ID
        max_pixels = 12 * nside * nside  # Total HEALPix pixels for this nside
        if pixel < 0 or pixel >= max_pixels:
            print(
                f"  WARNING: Pixel {pixel} is outside valid range [0, {max_pixels-1}]"
            )
            print("  Using middle pixel instead")
            test_pixel = max_pixels // 2
        else:
            test_pixel = pixel
        ra, dec = hp.pix2ang(nside, test_pixel, lonlat=True)
        print(f"  User pixel: {test_pixel} → RA={ra:.3f}°, Dec={dec:.3f}°")
    else:
        # Priority 3: Auto-select middle pixel
        max_pixels = 12 * nside * nside  # Total HEALPix pixels for this nside
        test_pixel = max_pixels // 2  # Middle pixel
        ra, dec = hp.pix2ang(nside, test_pixel, lonlat=True)
        print(
            f"  Auto-selected: pixel {test_pixel} → RA={ra:.3f}°, "
            f"Dec={dec:.3f}° (middle of {max_pixels} pixels)"
        )

    try:
        roi_spec, selected_stars = groi.get_guider_rois(
            ra=ra,
            dec=dec,
            sky_angle=0.0,  # degrees
            roi_size=64,  # pixels
            roi_time=200,  # ms (max allowed by ROICommon validation: 5-200)
            band="r",
            use_guider=True,
            use_science=False,
            use_wavefront=False,
        )

        print("  ROI selection successful!")
        print(f"  Selected {len(selected_stars)} guide stars")

        if len(selected_stars) > 0:
            print("\n  * Selected stars:")
            for i, star in enumerate(selected_stars):
                ra_deg = np.degrees(star["coord_ra"])
                dec_deg = np.degrees(star["coord_dec"])
                mag = star.get("mag_r", star["gaia_G"])
                print(
                    f"    Star {i+1}: RA={ra_deg:.3f}°, Dec={dec_deg:.3f}°, mag={mag:.2f}"
                )
                ccd_name = star["ccdName"]
                amp_name = star["ampName"]
                print(f"             CCD={ccd_name}, Amp={amp_name}")

            print("\n  ROI Specification:")
            print(
                f"    Common: rows={roi_spec.common.rows}, cols={roi_spec.common.cols}, "
            )
            print(
                f"            integration_time={roi_spec.common.integrationTimeMillis}ms"
            )
            print(f"    ROIs: {len(roi_spec.roi)} detector(s)")
            for ccd_name, roi in list(roi_spec.roi.items())[:3]:
                print(
                    f"      {ccd_name}: segment={roi.segment}, "
                    f"start_row={roi.startRow}, start_col={roi.startCol}"
                )
            if len(roi_spec.roi) > 3:
                print(f"      ... ({len(roi_spec.roi)-3} more ROIs)")

    except RuntimeError as e:
        if "No suitable guide stars found" in str(e):
            print("  WARNING: No guide stars found for test coordinates")
            print("  This may be normal with limited test data")
        else:
            print(f"   ERROR: ROI selection failed: {e}")
    except Exception as e:
        print(f"   ERROR: Unexpected error: {e}")


def setup_guider_rois_with_butler(
    repo_path: Optional[str],
    catalog_dataset: str,
    vignetting_dataset: str,
    collection: str,
    repo_name: str = "LSSTCam",
) -> Any:
    """Setup GuiderROIs with appropriate Butler (summit or local).

    Parameters
    ----------
    repo_path : str, optional
        Path to local Butler repository. If None, uses makeDefaultButler.
    catalog_dataset : str
        Name of catalog dataset
    vignetting_dataset : str
        Name of vignetting dataset
    collection : str
        Collection name
    repo_name : str, optional
        Repository name for makeDefaultButler (e.g., "LATISS", "LSSTCam").
        Only used when repo_path is None. Default: "LSSTCam".

    Returns
    -------
    groi : GuiderROIs
        Initialized GuiderROIs instance
    """
    if repo_path is None:
        print(f"\n Setting up GuiderROIs with summit Butler ({repo_name})...")
        try:
            groi = GuiderROIs(
                catalog_name=catalog_dataset,
                vignetting_dataset=vignetting_dataset,
                collection=collection,
                repo_name=repo_name,
            )
            print(" Direct initialization successful (summit Butler)")
            return groi
        except RuntimeError as e:
            print(f" ERROR: Failed to initialize GuiderROIs with summit Butler: {e}")
            raise
    else:
        print(f"\n Setting up GuiderROIs with local Butler: {repo_path}")
        try:
            # First try direct initialization
            # (in case we're in an environment with both)
            groi = GuiderROIs(
                catalog_name=catalog_dataset,
                vignetting_dataset=vignetting_dataset,
                collection=collection,
                repo_name=repo_name,
            )
            print(" Direct initialization successful")
            return groi
        except RuntimeError as e:
            if "summit_utils" in str(e):
                print(" summit_utils not available, using local Butler with mocking...")
                return setup_mocked_guider_rois(
                    repo_path, catalog_dataset, vignetting_dataset, collection
                )
            else:
                raise e


def setup_mocked_guider_rois(
    repo_path: str, catalog_dataset: str, vignetting_dataset: str, collection: str
) -> Any:
    """Setup GuiderROIs with mocked BestEffortIsr (like the notebook does)."""
    # Need to import the module this way as the python `import` seems
    # to have a clash with the utils package.
    import sys

    gr_module = sys.modules["lsst.ts.observatory.control.utils.extras.guider_roi"]

    print(f" Loading GuiderROIs module: {gr_module.__file__}")

    setattr(gr_module, "DM_STACK_AVAILABLE", True)
    setattr(gr_module, "BEST_EFFORT_ISR_AVAILABLE", True)

    local_butler = Butler.from_config(repo_path)

    # Create a fake BestEffortIsr class
    class _MockBestEffortIsr:
        def __init__(self) -> None:
            self.butler = local_butler

    # Monkey-patch the module
    setattr(gr_module, "BestEffortIsr", _MockBestEffortIsr)
    print(f" Patched BestEffortIsr to use local Butler: {repo_path}")

    # Initialize GuiderROIs with the patched module
    GuiderROIs = getattr(gr_module, "GuiderROIs")
    groi = GuiderROIs(
        catalog_name=catalog_dataset,
        vignetting_dataset=vignetting_dataset,
        collection=collection,
    )
    print(" GuiderROIs initialized with mocked BestEffortIsr")

    return groi


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Test GuiderROIs with existing Butler repository"
    )
    parser.add_argument(
        "--repo-path",
        default=None,
        help="Path to local Butler repository. If not provided, uses makeDefaultButler (summit environment)",
    )
    parser.add_argument(
        "--collection",
        default="guider_roi_data",
        help="Collection name (default: guider_roi_data)",
    )
    parser.add_argument(
        "--catalog-dataset",
        default="guider_roi_monster_guide_catalog",
        help="Catalog dataset name",
    )
    parser.add_argument(
        "--vignetting-dataset",
        default="guider_roi_vignetting_correction",
        help="Vignetting dataset name",
    )
    parser.add_argument(
        "--nside", type=int, default=32, help="HEALPix nside parameter (default: 32)"
    )
    parser.add_argument(
        "--repo-name",
        default="LSSTCam",
        help="Repository name for makeDefaultButler (e.g., LATISS, LSSTCam). "
        "Only used when --repo-path is not specified. Default: LSSTCam",
    )
    parser.add_argument(
        "--ra",
        type=float,
        help="RA in degrees for ROI selection test (takes precedence over --pixel)",
    )
    parser.add_argument(
        "--dec",
        type=float,
        help="Dec in degrees for ROI selection test (takes precedence over --pixel)",
    )
    parser.add_argument(
        "--pixel",
        type=int,
        help="HEALPix pixel ID for ROI selection test (default: auto-select middle pixel)",
    )

    args = parser.parse_args()

    print("### GuiderROIs Test Script")
    print("=" * 50)

    if not check_dependencies():
        print("\n ERROR: Missing required dependencies")
        sys.exit(1)

    pixels = check_butler_repository(
        args.repo_path,
        args.collection,
        args.catalog_dataset,
        args.nside,
        args.repo_name,
    )
    if not pixels:
        print("\n ERROR: No test data available")
        if args.repo_path:
            print(
                f"Please run: python ingest_guider_data.py --repo-path {args.repo_path}"
            )
        else:
            print(
                f"Please ensure data has been ingested to the {args.repo_name} Butler"
            )
        sys.exit(1)

    try:
        groi = setup_guider_rois_with_butler(
            args.repo_path,
            args.catalog_dataset,
            args.vignetting_dataset,
            args.collection,
            args.repo_name,
        )

    except Exception as e:
        print(f" ERROR: Failed to initialize GuiderROIs: {e}")
        sys.exit(1)

    test_vignetting_correction(groi)
    test_catalog_access(groi, args.nside)
    test_roi_selection(groi, args.nside, args.ra, args.dec, args.pixel)

    print("\n Testing completed!")
    if args.repo_path:
        print(f"Repository: {args.repo_path}")
    else:
        print(f"Repository: Summit Butler ({args.repo_name})")
    print(f"Collection: {args.collection}")
    print(f"Available pixels: {len(pixels)}")


if __name__ == "__main__":
    main()

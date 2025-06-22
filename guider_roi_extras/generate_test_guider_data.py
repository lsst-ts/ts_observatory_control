#!/usr/bin/env python3
"""
Generate test data for guider ROI ingestion testing.

This script creates test data that matches what I think is the
format in the original guiderroi.py
1. vignetting_vs_angle.npz - Vignetting correction data
2. Monster_guide/*.csv - Star catalog files organized by HEALPix pixels

Usage:
    python generate_test_guider_data.py [--num-catalogs N] \
        [--stars-per-catalog N]
    python generate_test_guider_data.py --target-ra 127.5 --target-dec -44.2 \
        --neighbor-radius 2
    python generate_test_guider_data.py --target-healpix 4123 \
        --include-neighbors
"""

import argparse
import logging
from pathlib import Path
from typing import List, Optional

import healpy as hp
import numpy as np
from astropy.table import Table

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def create_vignetting_data(filename: str = "vignetting_vs_angle.npz") -> None:
    """Create vignetting correction data using cos^4 law."""
    logger.info(f"Creating vignetting data: {filename}")

    # Angle range from 0 to 2 degrees (typical for guider CCDs??)
    theta = np.linspace(0.0, 2.0, 51)  # 51 points from 0 to 2 degrees

    # vignetting using cos^4 law
    # Convert angle to radians for calculation
    theta_rad = np.radians(theta)

    # Simple cos^4 vignetting model
    # At 0 degrees (center): vignetting = 1.0
    # At larger angles: vignetting decreases (??)
    cos_theta = np.cos(theta_rad)
    vignetting = cos_theta**4

    # Ensure minimum vignetting doesn't go below reasonable limits
    vignetting = np.maximum(vignetting, 0.85)  # Minimum 85% transmission

    # Save in the expected format
    np.savez(filename, theta=theta, vignetting=vignetting)

    logger.info(f"  - Created {len(theta)} vignetting points")
    logger.info(f"  - Theta range: {theta.min():.1f} to {theta.max():.1f} degrees")
    logger.info(
        f"  - Vignetting range: {vignetting.min():.3f} to {vignetting.max():.3f}"
    )


def create_star_catalog(healpix_id: int, num_stars: int = 50, nside: int = 32) -> Table:
    """Create a star catalog for a HEALPix pixel."""

    # Get the boundaries of this HEALPix pixel
    # Get center of pixel
    theta_center, phi_center = hp.pix2ang(nside, healpix_id)
    ra_center = phi_center
    dec_center = np.pi / 2 - theta_center

    # Create random stars within this HEALPix pixel
    # For simplicity, generate stars in a small area around the center
    pixel_size = hp.nside2resol(nside)  # Resolution in radians

    # Generate random offsets within the pixel
    np.random.seed(healpix_id)

    # Random offsets within pixel boundaries
    ra_offset = np.random.uniform(-pixel_size / 2, pixel_size / 2, num_stars)
    dec_offset = np.random.uniform(-pixel_size / 2, pixel_size / 2, num_stars)

    coord_ra = ra_center + ra_offset
    coord_dec = dec_center + dec_offset

    # Ensure coordinates are in valid ranges
    coord_ra = np.mod(coord_ra, 2 * np.pi)  # RA: 0 to 2π
    coord_dec = np.clip(coord_dec, -np.pi / 2, np.pi / 2)  # Dec: -π/2 to π/2

    # Generate realistic? magnitudes
    # Most stars should be guide stars (mag 14-18)
    gaia_G = np.random.uniform(14.0, 18.0, num_stars)

    # Create band magnitudes with color terms
    mag_g = gaia_G + np.random.normal(0, 0.1, num_stars)
    mag_r = mag_g - np.random.uniform(0.2, 0.8, num_stars)  # g-r color
    mag_i = mag_r - np.random.uniform(0.1, 0.5, num_stars)  # r-i color
    mag_z = mag_i - np.random.uniform(0.0, 0.3, num_stars)  # i-z color
    mag_y = mag_z - np.random.uniform(0.0, 0.2, num_stars)  # z-y color
    mag_u = mag_g + np.random.uniform(0.5, 1.5, num_stars)  # u-g color

    # Generate guide flags
    # Most stars should be isolated (guide_flag > 63)
    # ~80% isolated, ~20% not isolated
    isolated_fraction = 0.8
    guide_flag = np.where(
        np.random.random(num_stars) < isolated_fraction,
        np.random.randint(64, 127, num_stars),  # Isolated stars
        np.random.randint(0, 63, num_stars),  # Non-isolated stars
    )

    # Create the catalog table
    catalog = Table(
        {
            "coord_ra": coord_ra,
            "coord_dec": coord_dec,
            "gaia_G": gaia_G,
            "mag_u": mag_u,
            "mag_g": mag_g,
            "mag_r": mag_r,
            "mag_i": mag_i,
            "mag_z": mag_z,
            "mag_y": mag_y,
            "guide_flag": guide_flag,
            "healpix_id": np.full(num_stars, healpix_id, dtype=int),
        }
    )

    return catalog


def create_monster_catalogs(
    output_dir: str = "Monster_guide",
    num_catalogs: int = 20,
    stars_per_catalog: int = 50,
    target_ra: Optional[float] = None,
    target_dec: Optional[float] = None,
    target_healpix: Optional[int] = None,
    include_neighbors: bool = True,
    neighbor_radius: int = 1,
) -> List[int]:
    """Create multiple star catalog CSV files organized by HEALPix pixels.

    Args:
        output_dir: Directory for catalog files
        num_catalogs: Number of catalog files to create
        stars_per_catalog: Number of stars per catalog
        target_ra: Target RA in degrees (optional)
        target_dec: Target Dec in degrees (optional)
        target_healpix: Target HEALPix pixel ID (optional)
        include_neighbors: Include neighboring HEALPix pixels around target
        neighbor_radius: Radius of neighbor ring
            (1=immediate neighbors, 2=next ring, etc.)
    """
    logger.info(f"Creating {num_catalogs} monster guide catalogs in {output_dir}/")

    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)

    # Use nside=32 (same as in guider_roi.py)
    nside = 32
    npix_total = 12 * nside**2

    # Determine target pixels
    selected_pixels = []

    if target_healpix is not None:
        logger.info(f"Targeting HEALPix pixel: {target_healpix}")
        selected_pixels.append(target_healpix)

        if include_neighbors:
            # Get neighbors using healpy
            for radius in range(1, neighbor_radius + 1):
                neighbors = hp.get_all_neighbours(nside, target_healpix, nest=False)
                # Filter out invalid neighbors (-1)
                valid_neighbors = [n for n in neighbors if n != -1]
                selected_pixels.extend(valid_neighbors)
                logger.info(
                    f"Added {len(valid_neighbors)} neighbors at radius {radius}"
                )

            # Remove duplicates while preserving order
            seen = set()
            unique_pixels = []
            for pixel in selected_pixels:
                if pixel not in seen:
                    seen.add(pixel)
                    unique_pixels.append(pixel)
            selected_pixels = unique_pixels

    elif target_ra is not None and target_dec is not None:
        logger.info(
            f"Targeting coordinates: RA={target_ra:.6f}°, Dec={target_dec:.6f}°"
        )

        # Convert to HEALPix pixel
        target_healpix = hp.ang2pix(nside, target_ra, target_dec, lonlat=True)
        logger.info(f"Target coordinates correspond to HEALPix pixel: {target_healpix}")

        selected_pixels.append(target_healpix)

        if include_neighbors:
            # Get neighboring pixels in expanding rings
            pixels_in_area = [target_healpix]

            for radius in range(1, neighbor_radius + 1):
                # Get pixels within radius using query_disc
                # Convert target coordinates to vector
                vec = hp.ang2vec(target_ra, target_dec, lonlat=True)
                # Radius in radians
                search_radius = radius * np.sqrt(4 * np.pi / npix_total)
                nearby_pixels = hp.query_disc(nside, vec, search_radius, nest=False)
                pixels_in_area.extend(nearby_pixels)

            # Remove duplicates
            selected_pixels = list(set(pixels_in_area))
            logger.info(
                f"Found {len(selected_pixels)} pixels within radius "
                f"{neighbor_radius} of target"
            )

    else:
        logger.info("Using random pixel selection")
        # Original random selection
        np.random.seed(42)  # Reproducible selection
        selected_pixels = np.random.choice(npix_total, size=num_catalogs, replace=False)

    # Limit to requested number of catalogs
    if len(selected_pixels) > num_catalogs:
        logger.info(
            f"Limiting to {num_catalogs} catalogs from "
            f"{len(selected_pixels)} candidate pixels"
        )
        # Prioritize target pixel if specified
        if target_healpix is not None:
            # Keep target pixel first, then random selection from remainder
            other_pixels = [p for p in selected_pixels if p != target_healpix]
            np.random.shuffle(other_pixels)
            selected_pixels = [target_healpix] + other_pixels[: num_catalogs - 1]
        else:
            np.random.shuffle(selected_pixels)
            selected_pixels = selected_pixels[:num_catalogs]

    logger.info(f"Selected HEALPix pixels: {sorted(selected_pixels)}")

    created_count = 0
    total_stars = 0

    for pixel_id in selected_pixels:
        try:
            catalog = create_star_catalog(pixel_id, stars_per_catalog, nside)

            # Save as CSV file named by pixel ID
            output_file = output_path / f"{pixel_id}.csv"
            catalog.write(output_file, format="csv", overwrite=True)

            created_count += 1
            total_stars += len(catalog)

            if created_count % 5 == 0:
                logger.info(f"  Created {created_count} catalogs...")

        except Exception as e:
            logger.error(f"Failed to create catalog for pixel {pixel_id}: {e}")

    logger.info("Monster guide catalog creation complete:")
    logger.info(f"  - Created {created_count} catalog files")
    logger.info(f"  - Total stars: {total_stars}")
    logger.info(f"  - Average stars per catalog: {total_stars/created_count:.1f}")
    logger.info(f"  - HEALPix configuration: nside={nside}, total_pixels={npix_total}")

    # Create a summary file
    summary_file = output_path / "catalog_summary.txt"
    with open(summary_file, "w") as f:
        f.write("Monster Guide Catalog Summary\n")
        f.write("============================\n")
        f.write(f"Created: {created_count} catalog files\n")
        f.write(f"Total stars: {total_stars}\n")
        f.write(f"HEALPix nside: {nside}\n")
        f.write(f"Pixel IDs: {sorted(selected_pixels)}\n")

        if target_ra is not None and target_dec is not None:
            f.write(f"Target coordinates: RA={target_ra:.6f}°, Dec={target_dec:.6f}°\n")
        if target_healpix is not None:
            f.write(f"Target HEALPix pixel: {target_healpix}\n")
        if include_neighbors:
            f.write(f"Neighbor radius: {neighbor_radius}\n")

        f.write("\nExpected data structure:\n")
        f.write("- coord_ra, coord_dec: Star coordinates (radians)\n")
        f.write("- guide_flag: >63 for isolated guide stars\n")
        f.write("- mag_u,g,r,i,z,y: Band magnitudes\n")
        f.write("- gaia_G: Gaia G magnitude\n")

    logger.info(f"  - Summary written to {summary_file}")

    return selected_pixels


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate test data for guider ROI ingestion testing"
    )
    parser.add_argument(
        "--num-catalogs",
        type=int,
        default=20,
        help="Number of catalog files to create (default: 20)",
    )
    parser.add_argument(
        "--stars-per-catalog",
        type=int,
        default=50,
        help="Number of stars per catalog file (default: 50)",
    )
    parser.add_argument(
        "--catalog-dir",
        default="Monster_guide",
        help="Directory name for catalog files (default: Monster_guide)",
    )
    parser.add_argument(
        "--vignetting-file",
        default="vignetting_vs_angle.npz",
        help="Vignetting data filename (default: vignetting_vs_angle.npz)",
    )
    parser.add_argument(
        "--vignetting-only", action="store_true", help="Only create vignetting data"
    )
    parser.add_argument(
        "--catalogs-only", action="store_true", help="Only create catalog data"
    )

    # New targeted generation arguments
    parser.add_argument(
        "--target-ra",
        type=float,
        help="Target RA coordinate in degrees (for targeted generation)",
    )
    parser.add_argument(
        "--target-dec",
        type=float,
        help="Target Dec coordinate in degrees (for targeted generation)",
    )
    parser.add_argument(
        "--target-healpix",
        type=int,
        help="Target HEALPix pixel ID (for targeted generation)",
    )
    parser.add_argument(
        "--include-neighbors",
        action="store_true",
        default=True,
        help="Include neighboring HEALPix pixels around target (default: True)",
    )
    parser.add_argument(
        "--no-neighbors",
        action="store_true",
        help="Don't include neighboring pixels (opposite of --include-neighbors)",
    )
    parser.add_argument(
        "--neighbor-radius",
        type=int,
        default=1,
        help="Radius of neighbor ring to include (default: 1)",
    )

    args = parser.parse_args()

    logger.info("Starting test data generation...")

    if args.vignetting_only and args.catalogs_only:
        logger.error("Cannot specify both --vignetting-only and --catalogs-only")
        return 1

    # Validate target coordinate arguments
    if (args.target_ra is not None) != (args.target_dec is not None):
        logger.error("Both --target-ra and --target-dec must be specified together")
        return 1

    if args.target_healpix is not None and args.target_ra is not None:
        logger.error(
            "Cannot specify both --target-healpix and --target-ra/--target-dec"
        )
        return 1

    # Handle neighbor inclusion flag
    include_neighbors = args.include_neighbors and not args.no_neighbors

    # Create vignetting data
    if not args.catalogs_only:
        create_vignetting_data(args.vignetting_file)

    # Create catalog data
    if not args.vignetting_only:
        selected_pixels = create_monster_catalogs(
            args.catalog_dir,
            args.num_catalogs,
            args.stars_per_catalog,
            target_ra=args.target_ra,
            target_dec=args.target_dec,
            target_healpix=args.target_healpix,
            include_neighbors=include_neighbors,
            neighbor_radius=args.neighbor_radius,
        )

        # Log the results for easy reference
        if args.target_ra is not None and args.target_dec is not None:
            logger.info("\n🎯 Targeted generation complete!")
            logger.info(
                f"   Target: RA={args.target_ra:.6f}°, Dec={args.target_dec:.6f}°"
            )
            logger.info(f"   Generated {len(selected_pixels)} HEALPix pixels")
            logger.info(f"   Pixels: {sorted(selected_pixels)}")
        elif args.target_healpix is not None:
            logger.info("\n🎯 Targeted generation complete!")
            logger.info(f"   Target HEALPix: {args.target_healpix}")
            logger.info(f"   Generated {len(selected_pixels)} HEALPix pixels")
            logger.info(f"   Pixels: {sorted(selected_pixels)}")

    logger.info("Test data generation complete!")
    logger.info("\nNext steps:")
    logger.info("1. Run the ingestion script:")
    if not args.catalogs_only:
        logger.info(
            f"   python ingest_guider_data.py --vignetting-file {args.vignetting_file}"
        )
    if not args.vignetting_only:
        logger.info(
            f"   python ingest_guider_data.py --catalog-path {args.catalog_dir}"
        )
    if not args.vignetting_only and not args.catalogs_only:
        cmd = (
            f"   python ingest_guider_data.py --catalog-path {args.catalog_dir} "
            f"--vignetting-file {args.vignetting_file}"
        )
        logger.info(cmd)
    logger.info("2. Test with the notebook: guider_roi_butler_example.ipynb")

    return 0


if __name__ == "__main__":
    exit(main())

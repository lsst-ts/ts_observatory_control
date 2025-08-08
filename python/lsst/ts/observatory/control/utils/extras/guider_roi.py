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

"""Guider ROI selection for LSSTCam.

This module implements guider ROI selection functionality based on the
original algorithm developed by Aaron Roodman. The implementation has been
adapted for integration with ts_observatory_control.

Original algorithm credit: Aaron Roodman
"""

__all__ = [
    "BASIC_DEPS_AVAILABLE",
    "DM_STACK_AVAILABLE",
    "BEST_EFFORT_ISR_AVAILABLE",
    "GuiderROIs",
]

import math
import os
import warnings
from typing import Any

import numpy as np

DEFAULT_CATALOG_DATASET_NAME = "monster_guide_catalog"
DEFAULT_VIGNETTING_DATASET_NAME = "vignetting_correction"
DEFAULT_COLLECTION_NAME = "guider_roi_data"

try:
    import healpy as hp
    from astropy.coordinates import angular_separation
    from astropy.table import Table, vstack
    from scipy.interpolate import make_interp_spline

    BASIC_DEPS_AVAILABLE = True
except ImportError as e:
    BASIC_DEPS_AVAILABLE = False
    print(f"Cannot import basic required libraries. GuiderROIs will not work. {e}")
    warnings.warn(
        "Cannot import basic required libraries (healpy, astropy, scipy). "
        "GuiderROIs will not work."
    )

# DM Stack imports (includes Butler)
DM_STACK_AVAILABLE = True
try:
    # Core DM stack imports
    import lsst.geom as geom
    from lsst.afw import cameraGeom
    from lsst.daf.butler import Butler
    from lsst.daf.butler._exceptions import DatasetNotFoundError
    from lsst.geom import Angle, Extent2I, SpherePoint
    from lsst.obs.base import createInitialSkyWcsFromBoresight
    from lsst.obs.lsst import LsstCam
    from lsst.obs.lsst.cameraTransforms import LsstCameraTransforms
except ImportError:
    DM_STACK_AVAILABLE = False
    print("DM Stack not available. GuiderROIs will work in file-based mode only.")

# BestEffortIsr (optional for summit environment?)
BEST_EFFORT_ISR_AVAILABLE = True
try:
    from lsst.summit.utils import BestEffortIsr
except ImportError:
    BEST_EFFORT_ISR_AVAILABLE = False
    BestEffortIsr = None


def get_vignetting_data_from_butler(
    butler: Any,
    vignetting_dataset: str = DEFAULT_VIGNETTING_DATASET_NAME,
    collection: str = DEFAULT_COLLECTION_NAME,
) -> dict[str, Any]:
    """Get vignetting correction data from Butler.

    Parameters
    ----------
    butler : `lsst.daf.butler.Butler`
        Butler instance to query.
    vignetting_dataset : `str`
        Name of the vignetting dataset.
    collection : `str`
        Collection name to query.

    Returns
    -------
    vignetting_data : `dict`
        Vignetting data.

    Raises
    ------
    RuntimeError
        If DM stack is not available (required for Butler operations).
    ValueError
        If vignetting data is found but required columns are missing.
    Exception
        Any exception from Butler operations (e.g., DatasetNotFoundError,
        AttributeError, etc.) will be raised directly.
    """
    if not DM_STACK_AVAILABLE:
        raise RuntimeError("DM stack is not available")

    vignetting_refs = list(
        butler.registry.queryDatasets(vignetting_dataset, collections=[collection])
    )
    if not vignetting_refs:
        raise RuntimeError(
            f"No vignetting dataset '{vignetting_dataset}' found in collection '{collection}'."
        )

    ref = vignetting_refs[0]
    data = butler.get(ref)

    if data is None:
        raise RuntimeError(
            f"Retrieved vignetting dataset '{vignetting_dataset}' is empty or unavailable."
        )

    required_keys = ["theta", "vignetting"]
    missing_keys = [key for key in required_keys if key not in data]
    if missing_keys:
        raise ValueError(
            f"Vignetting data missing required columns: {missing_keys}. "
            f"Available columns: {list(data.keys())}"
        )

    return data


class GuiderROIs:
    """GuiderROIs definition.

    This class provides code to select Guider ROIs for LSSTCam based on the
    original algorithm developed by Aaron Roodman. It can work with or without
    the DM stack

    Original algorithm credit: Aaron Roodman

    Notes
    -----
    The class can operate in three modes:
    1. Full DM stack mode with butler
    2. File-based only mode (minimal dependencies - healpy, astropy, scipy)
    3. Summit environment mode (DM stack + BestEffortIsr convenience)
    """

    def __init__(
        self,
        butler: Any | None = None,
        butler_config: str | Any | None = None,
        catalog_name: str = DEFAULT_CATALOG_DATASET_NAME,
        vignetting_dataset: str = DEFAULT_VIGNETTING_DATASET_NAME,
        collection: str = DEFAULT_COLLECTION_NAME,
        catalog_path: str | None = None,
        vignetting_file: str | None = None,
        nside: int = 32,
    ) -> None:
        """Initialize GuiderROIs.

        Parameters
        ----------
        butler : `lsst.daf.butler.Butler`, optional
            Butler instance to use for data access. If None, will try to create
            from butler_config (if DM stack available), or use BestEffortIsr
            butler (if available), otherwise will use file-based mode.
        butler_config : `str` or `lsst.daf.butler.ButlerConfig`, optional
            Butler configuration (repo path or config object) to create Butler
            from. Only used if butler is None and DM stack is available.
            If string, treated as repository path.
        catalog_name : `str`, optional
            Name of the HEALPix catalog dataset in butler.
        vignetting_dataset : `str`, optional
            Name of the vignetting correction dataset in butler.
        collection : `str`, optional
            Collection name for data queries.
        catalog_path : `str`, optional
            Path to catalog files (used when DM stack/butler is not available).
            Should contain HEALPix-indexed CSV files.
        vignetting_file : `str`, optional
            Path to vignetting correction file (used when DM stack/butler is
            not available). Should be an NPZ file with 'theta' and 'vignetting'
            arrays.
        nside : `int`, optional
            HEALPix nside parameter (default: 32). Must match the nside used
            in the Butler repository.

        Raises
        ------
        RuntimeError
            If basic dependencies are not available or if neither DM stack
            (for Butler functionality) nor file paths are provided.
        ValueError
            If vignetting data is missing required columns or if nside is
            invalid.

        Notes
        -----
        Operating modes:
        1. **DM stack mode**: Full functionality with Butler
        2. **Summit mode**: DM stack + BestEffortIsr convenience (automatic
           Butler)
        3. **File mode**: Minimal dependencies, requires catalog_path and
           vignetting_file
        """
        if not BASIC_DEPS_AVAILABLE:
            raise RuntimeError(
                "Basic dependencies (healpy, astropy, scipy) not available. "
                "Cannot initialize GuiderROIs."
            )

        # Validate nside parameter
        if nside <= 0 or (nside & (nside - 1)) != 0:
            raise ValueError(f"nside must be a power of 2, got {nside}")

        # Store configuration
        self.catalog_name = catalog_name
        self.vignetting_dataset = vignetting_dataset
        self.collection = collection
        self.catalog_path = catalog_path
        self.vignetting_file = vignetting_file

        # HEALPix configuration
        self.nside = nside
        self.healpix_level = int(math.log2(nside))  # Calculate level from nside
        self.healpix_dim = f"healpix{self.healpix_level}"
        self.npix = hp.nside2npix(nside)

        # Set up butler (optional)
        self.butler = None
        self.best_effort_isr = None
        self._setup_butler(butler, butler_config)

        # Constants
        self.ccd_diag = 0.15852  # Guider CCD diagonal radius in Degrees
        self.bad_guideramps = {193: ["C1"], 198: ["C1"], 201: ["C0"]}
        self.filters = ["u", "g", "r", "i", "z", "y"]

        # Initialize camera (optional, requires DM stack)
        self.camera = None
        if DM_STACK_AVAILABLE:
            self.camera = LsstCam.getCamera()

        # Initialize vignetting correction
        self._init_vignetting_correction()

    def _setup_butler(
        self,
        butler: Any | None,
        butler_config: str | Any | None = None,
    ) -> None:
        """Set up butler for data access."""

        if butler is not None:
            self.butler = butler
            return

        # Create Butler from provided config (requires DM stack)
        if DM_STACK_AVAILABLE and butler_config is not None:
            try:
                if isinstance(butler_config, str):
                    # Assume it's a repository path
                    self.butler = Butler.from_config(butler_config)
                else:
                    # Assume it's a ButlerConfig object
                    self.butler = Butler.from_config(butler_config)
                return
            except Exception as e:
                warnings.warn(f"Failed to create Butler from config: {e}")

        # Fall back to BestEffortIsr (summit environment convenience)
        if BEST_EFFORT_ISR_AVAILABLE and BestEffortIsr is not None:
            try:
                self.best_effort_isr = BestEffortIsr()
                if self.best_effort_isr is not None:
                    self.butler = self.best_effort_isr.butler
                return
            except Exception as e:
                warnings.warn(f"Failed to create BestEffortIsr butler: {e}")

        # No butler available - will use file-based mode
        self.butler = None

        # Provide helpful feedback about the mode
        mode_info = []
        if DM_STACK_AVAILABLE:
            mode_info.append("DM stack available")
            if butler_config is None:
                mode_info.append("no butler_config provided")
        else:
            mode_info.append("DM stack not available")

        if BEST_EFFORT_ISR_AVAILABLE:
            mode_info.append("BestEffortIsr available but failed to initialize")
        else:
            mode_info.append("BestEffortIsr not available")

        warnings.warn(
            f"No butler available ({', '.join(mode_info)}). "
            "GuiderROIs will operate in file-based mode. "
            "To use Butler functionality, provide either a butler instance or "
            "butler_config parameter if DM stack is available."
        )

    def _init_vignetting_correction(self) -> None:
        """Initialize vignetting correction spline.

        Raises
        ------
        RuntimeError
            If vignetting data is not available from any source.
        ValueError
            If vignetting data is missing required columns.
        FileNotFoundError
            If no vignetting file is found when butler data is not available.
        """
        vignetting_data = None

        # Try to get vignetting data from butler first
        if self.butler is not None:
            try:
                vignetting_data = get_vignetting_data_from_butler(
                    self.butler, self.vignetting_dataset, self.collection
                )
            except RuntimeError:
                # DM stack not available, fall back to file-based approach
                vignetting_data = None

        # Fall back to file-based approach
        if vignetting_data is None:
            try:
                vignetting_data = self._load_vignetting_from_file()
            except FileNotFoundError as e:
                raise RuntimeError(
                    "Vignetting correction data not available from butler or file. "
                    "Cannot initialize GuiderROIs without vignetting correction data. "
                    "Please provide vignetting_file parameter or ensure butler has "
                    "the data."
                ) from e

        try:
            # Create interpolation spline with the validated data
            self.vigspline = make_interp_spline(
                vignetting_data["theta"], vignetting_data["vignetting"], k=3
            )
        except Exception as e:
            raise RuntimeError(f"Failed to create vignetting correction spline: {e}")

    def _load_vignetting_from_file(
        self,
    ) -> dict[str, np.ndarray]:
        """Load vignetting data from file.

        Returns
        -------
        vignetting_data : `dict`
            Dictionary with 'theta' and 'vignetting' arrays.

        Raises
        ------
        FileNotFoundError
            If no vignetting file is found in any of the default locations.
        Exception
            Any other exception from numpy.load() or file operations.
        """
        if self.vignetting_file is None:
            # Try default locations
            default_files = [
                "vignetting_vs_angle.npz",
                os.path.join(os.path.dirname(__file__), "vignetting_vs_angle.npz"),
                os.path.join(os.getcwd(), "vignetting_vs_angle.npz"),
            ]

            for default_file in default_files:
                if os.path.exists(default_file):
                    self.vignetting_file = default_file
                    break

        if self.vignetting_file is None or not os.path.exists(self.vignetting_file):
            raise FileNotFoundError(f"No vignetting file found. Tried: {default_files}")

        vigdata = np.load(self.vignetting_file)
        return {"theta": vigdata["theta"], "vignetting": vigdata["vignetting"]}

    def vignetting_correction(self, angle: float) -> float:
        """Calculate vignetting correction.

        Parameters
        ----------
        angle : float
            Angle from boresight in degrees

        Returns
        -------
        deltam : float
            Change in magnitude due to vignetting
        """
        vigfraction = self.vigspline(angle)
        deltam = -2.5 * np.log10(vigfraction)
        return deltam

    def _get_catalog_data_for_healpix(self, hp_indices: list[int]) -> list[Table]:
        """Get catalog data for given HEALPix indices using HEALPix dimensions.

        Parameters
        ----------
        hp_indices : `list` of `int`
            HEALPix indices to query.

        Returns
        -------
        tables : `list` of `astropy.table.Table`
            Catalog tables for the requested indices.
        """
        tables: list[Table] = []

        # Try butler approach first
        if self.butler is not None:
            tables = self._get_catalog_data_from_butler(hp_indices)

        # Fall back to file-based approach
        if not tables:
            tables = self._get_catalog_data_from_files(hp_indices)

        return tables

    def _get_catalog_data_from_butler(self, hp_indices: list[int]) -> list[Table]:
        """Get catalog data from butler using HEALPix dimensions."""
        tables: list[Table] = []

        if not DM_STACK_AVAILABLE:
            warnings.warn(
                "DM stack (including Butler) not available for catalog data access"
            )
            return tables

        if self.butler is None:
            return tables

        try:
            # Query each HEALPix pixel individually
            for hp_idx in hp_indices:
                try:
                    # Create data ID for HEALPix dimension
                    dataId = {self.healpix_dim: int(hp_idx)}

                    # Query datasets for this specific HEALPix pixel
                    datasets = list(
                        self.butler.registry.queryDatasets(
                            self.catalog_name,
                            collections=[self.collection],
                            where=f"{self.healpix_dim} = pixel_id",
                            bind={"pixel_id": int(hp_idx)},
                        )
                    )

                    if datasets:
                        # Get the catalog for this pixel
                        catalog = self.butler.get(datasets[0])
                        if len(catalog) > 0:
                            tables.append(catalog)
                    else:
                        # Try direct get approach as fallback
                        try:
                            catalog = self.butler.get(
                                self.catalog_name,
                                dataId=dataId,
                                collections=self.collection,
                            )
                            if len(catalog) > 0:
                                tables.append(catalog)
                        except (DatasetNotFoundError, Exception):
                            warnings.warn(
                                f"No catalog data found for HEALPix pixel {hp_idx}"
                            )

                except Exception as e:
                    warnings.warn(f"Could not load catalog for HEALPix {hp_idx}: {e}")
                    continue

        except Exception as e:
            warnings.warn(f"Could not load catalog data from butler: {e}")

        return tables

    def _get_catalog_data_from_files(self, hp_indices: list[int]) -> list[Table]:
        """Get catalog data from CSV files."""
        tables: list[Table] = []

        if self.catalog_path is None:
            # Try default locations
            default_paths = [
                "Monster_guide",
                os.path.join(os.path.dirname(__file__), "Monster_guide"),
                os.path.join(os.getcwd(), "Monster_guide"),
                "/home/s/shuang92/rubin-user/Monster_guide",  # Legacy path
            ]

            for default_path in default_paths:
                if os.path.exists(default_path):
                    self.catalog_path = default_path
                    break

        if self.catalog_path is None or not os.path.exists(self.catalog_path):
            warnings.warn(
                f"Catalog path not found: {self.catalog_path}. "
                "Please provide catalog_path parameter."
            )
            return tables

        for hp_idx in hp_indices:
            try:
                catalog_file = os.path.join(self.catalog_path, f"{hp_idx}.csv")
                if os.path.exists(catalog_file):
                    table = Table.read(catalog_file)
                    tables.append(table)
                else:
                    warnings.warn(f"Catalog file not found: {catalog_file}")
            except Exception as e:
                warnings.warn(f"Could not load catalog for HEALPix {hp_idx}: {e}")

        return tables

    def get_guider_rois(
        self,
        boresight_RA: float,
        boresight_DEC: float,
        boresight_RotAngle: float,
        roi_size: int,
        roi_time: int,
        band: str,
        npix_edge: int = 50,
        npix_boundary: int = 25,
        use_guider: bool = True,
        use_wavefront: bool = False,
        use_science: bool = False,
    ) -> tuple[str, Table]:
        """Get guider ROI configuration.

        Parameters
        ----------
        boresight_RA : float
            Boresight RA in degrees
        boresight_DEC : float
            Boresight Dec in degrees
        boresight_RotAngle : float
            Boresight Rot Angle in degrees (needs to match
            visitInfo.boreSightRotAngle)
        roi_size : int
            Size of the ROI in pixels
        roi_time : int
            Integration time for the ROI in millisec
        band : str
            First letter of the Filter band, ie. u,g,r,i,z,y
        npix_edge : int
            Number of edge pixels on the CCD where stars are not used,
            default=50
        npix_boundary : int
            Minimum distance from star to edge of ROI, default=25
        use_guider : bool
            Use Guiders, default=True
        use_science : bool
            Use Science CCDs, default=False
        use_wavefront : bool
            Use Wavefront CCDs, default=False

        Returns
        -------
        config_text : str
            ROI configuration text
        cat_all : Table
            Table of chosen Guider stars

        Raises
        ------
        RuntimeError
            If DM stack is not available when needed or no suitable guide
            stars found.
        """
        if not DM_STACK_AVAILABLE:
            raise RuntimeError(
                "DM stack not available. Cannot perform ROI selection without "
                "lsst.geom, lsst.afw.cameraGeom, and related modules."
            )

        if self.camera is None:
            raise RuntimeError("Camera object not available.")

        # make DM objects
        boresight_radec = SpherePoint(boresight_RA, boresight_DEC, geom.degrees)
        boresight_rotang = Angle(boresight_RotAngle, geom.degrees)

        # roi/2
        roi_halfsize = int(roi_size / 2)  # assume even roi_size

        # Detector types
        dtypelist = []
        if use_guider:
            dtypelist.append(cameraGeom.DetectorType.GUIDER)
        if use_science:
            dtypelist.append(cameraGeom.DetectorType.SCIENCE)
        if use_wavefront:
            dtypelist.append(cameraGeom.DetectorType.WAVEFRONT)

        # find WCS and RaDec of the central pixel for each detector
        cam_wcs = {}
        cam_radec = {}
        cam_vec_corners = {}
        for detector in self.camera:
            if detector.getType() in dtypelist:
                # build wcs
                cam_wcs[detector.getId()] = createInitialSkyWcsFromBoresight(
                    boresight_radec, boresight_rotang, detector, flipX=False
                )

                # get central pixel
                x0, y0 = (
                    detector.getBBox().getCenterX(),
                    detector.getBBox().getCenterY(),
                )

                # get ra,dec of the Center of the CCD
                ra_center, dec_center = cam_wcs[detector.getId()].pixelToSky(x0, y0)
                cam_radec[detector.getId()] = [
                    ra_center.asDegrees(),
                    dec_center.asDegrees(),
                ]

                # also get 4 corners of the CCD
                ra_corners = []
                dec_corners = []
                for corner_pt in detector.getBBox().getCorners():
                    ra_corner, dec_corner = cam_wcs[detector.getId()].pixelToSky(
                        geom.Point2D(corner_pt)
                    )
                    ra_corners.append(ra_corner)
                    dec_corners.append(dec_corner)

                # Convert to astropy SkyCoord and get cartesian unit vectors
                import astropy.units as u
                from astropy.coordinates import SkyCoord

                # Convert lsst.geom.Angle objects to degrees
                ra_corners_deg = [ra.asDegrees() for ra in ra_corners]
                dec_corners_deg = [dec.asDegrees() for dec in dec_corners]

                coords = SkyCoord(ra=ra_corners_deg, dec=dec_corners_deg, unit=u.deg)
                cam_vec_corners[detector.getId()] = np.array(
                    [
                        [
                            coord.cartesian.x.value,
                            coord.cartesian.y.value,
                            coord.cartesian.z.value,
                        ]
                        for coord in coords
                    ]
                )

        # loop over detectors, getting the optimal guider star in each
        first = True
        cat_all = Table()  # Initialize empty table

        for idet, wcs in cam_wcs.items():
            ra_ccd, dec_ccd = cam_radec[idet]
            detector = self.camera[idet]

            # get BBox for this detector
            ccd_bbox = detector.getBBox()
            ccd_nx, ccd_ny = ccd_bbox.getDimensions()
            ccd_nyhalf = ccd_ny // 2

            # build BBox for top and bottom halves of the CCD
            ccd_bbox_top = geom.Box2I(
                geom.Point2I(ccd_bbox.getMinX(), ccd_nyhalf),
                geom.Extent2I(ccd_nx, ccd_ny - ccd_nyhalf),
            )
            ccd_bbox_top.grow(-Extent2I(npix_edge, npix_edge))
            ccd_bbox_bottom = geom.Box2I(
                geom.Point2I(ccd_bbox.getMinX(), 0),
                geom.Extent2I(ccd_nx, ccd_nyhalf),
            )
            ccd_bbox_bottom.grow(-Extent2I(npix_edge, npix_edge))

            # query the Monster-based Guider star catalog with the CCD polygon
            catalog_indices = hp.query_polygon(
                self.nside, cam_vec_corners[detector.getId()], inclusive=True, fact=8
            )

            # Get neighboring pixels for catalog query
            try:

                # Get catalog data using HEALPix dimensions
                tables = self._get_catalog_data_for_healpix(catalog_indices)

                if not tables:
                    warnings.warn(f"No catalog data found for detector {idet}")
                    continue

                star_cat = vstack(tables)

            except Exception as e:
                warnings.warn(f"Error reading catalog for detector {idet}: {e}")
                continue

                # check that stars are isolated and are inside the CCD
            isolated = star_cat["guide_flag"] > 63

            # using the wcs to locate the stars inside the CCD minus npix_edge
            # and also avoiding the midline break
            ccdx, ccdy = wcs.skyToPixelArray(
                star_cat["coord_ra"], star_cat["coord_dec"], degrees=False
            )
            # Check if stars are in either the top or bottom half of the CCD
            in_top = ccd_bbox_top.contains(ccdx, ccdy)
            in_bottom = ccd_bbox_bottom.contains(ccdx, ccdy)
            in_CCD = in_top | in_bottom  # Use bitwise OR for arrays

            # Selection 1: the Star is isolated and inside top or bottom of CCD
            cat_select1 = star_cat[(isolated & in_CCD)]

            if len(cat_select1) == 0:
                # TBD: should we raise an error here?
                warnings.warn(f"No isolated stars found inside CCD for detector {idet}")
                continue

            # Get the corresponding CCD coordinates for the filtered stars
            # Use the same mask that was used to create cat_select1
            mask = isolated & in_CCD
            ccdx_filtered = ccdx[mask]
            ccdy_filtered = ccdy[mask]

            # fill with CCD pixel x,y
            cat_select1["ccdx"] = ccdx_filtered
            cat_select1["ccdy"] = ccdy_filtered

            # get the Amp coordinates and check that Amp is not in the bad amp
            # list
            detName = detector.getName()
            lct = LsstCameraTransforms(self.camera, detName)
            ccdNames = []
            ampNames = []
            ampXs = []
            ampYs = []
            ampOk = []

            for arow in cat_select1:
                ampName, ampX, ampY = lct.ccdPixelToAmpPixel(arow["ccdx"], arow["ccdy"])
                # check if the amp is in the bad_guideramps list
                if idet in self.bad_guideramps:
                    if ampName in self.bad_guideramps[idet]:
                        ampOk.append(False)
                    else:
                        ampOk.append(True)
                else:
                    ampOk.append(True)

                ccdNames.append(detName)
                ampNames.append(ampName)
                ampXs.append(ampX)
                ampYs.append(ampY)

            # add info on star position to the catalog
            cat_select1["ccdName"] = ccdNames
            cat_select1["ampName"] = ampNames
            cat_select1["ampX"] = ampXs
            cat_select1["ampY"] = ampYs
            cat_select1["ampOk"] = ampOk

            # currently just have star's central locations
            # find the location of the ROI containing this star, such that
            # the star is not within npix_boundary of the edge of the ROI
            # and the ROI does not cross the midline break

            ccdxLLs = []
            ccdyLLs = []
            ampNameLLs = []
            ampxLLs = []
            ampyLLs = []

            for arow in cat_select1:
                # find ROI LL position in CCD coordinates
                ccdxLL = arow["ccdx"] - roi_halfsize
                ccdyLL = arow["ccdy"] - roi_halfsize

                # find ROI UR position in CCD coordinates
                ccdxUR = arow["ccdx"] + roi_halfsize
                ccdyUR = arow["ccdy"] + roi_halfsize

                # check that the ROI is fully within the CCD and
                # does not cross the midline break

                # first check and adjust the ROI in x
                if ccdxLL < 0:
                    ccdxLL = 0
                    ccdxUR = ccdxLL + roi_size
                elif ccdxUR > ccd_nx:
                    ccdxUR = ccd_nx
                    ccdxLL = ccdxUR - roi_size

                # then check and adjust the ROI in y
                # first see if the star is in the upper
                # or lower half of the CCD
                if arow["ccdy"] < ccd_nyhalf:
                    if ccdyLL < 0:
                        ccdyLL = 0
                        ccdyUR = ccdyLL + roi_size
                    elif ccdyUR > ccd_nyhalf:
                        ccdyUR = ccd_nyhalf
                        ccdyLL = ccdyUR - roi_size
                else:
                    if ccdyLL < ccd_nyhalf:
                        ccdyLL = ccd_nyhalf
                        ccdyUR = ccdyLL + roi_size
                    elif ccdyUR > ccd_ny:
                        ccdyUR = ccd_ny
                        ccdyLL = ccdyUR - roi_size

                ampNameLL, ampxLL, ampyLL = lct.ccdPixelToAmpPixel(ccdxLL, ccdyLL)
                ccdxLLs.append(ccdxLL)
                ccdyLLs.append(ccdyLL)
                ampNameLLs.append(ampNameLL)
                ampxLLs.append(ampxLL)
                ampyLLs.append(ampyLL)

            # add info on LL of ROI to the catalog
            cat_select1["ccdxLL"] = ccdxLLs
            cat_select1["ccdyLL"] = ccdyLLs
            cat_select1["ampNameLL"] = ampNameLLs
            cat_select1["ampxLL"] = ampxLLs
            cat_select1["ampyLL"] = ampyLLs

            # get the change in magnitude due to the vignetting factor
            cat_select1["dangle_boresight"] = np.degrees(
                angular_separation(
                    np.deg2rad(boresight_RA),
                    np.deg2rad(boresight_DEC),
                    cat_select1["coord_ra"],
                    cat_select1["coord_dec"],
                )
            )

            cat_select1["delta_mag"] = self.vignetting_correction(
                cat_select1["dangle_boresight"]
            )

            # Selection2: check that the amplifier is ok
            cat_select2 = cat_select1[cat_select1["ampOk"]]

            if len(cat_select2) == 0:
                # TBD: should we raise an error here?
                warnings.warn(f"No stars in good amplifiers for detector {idet}")
                continue

            # find the brightest Star in the CCD: first check stars with
            # magnitudes for this band, if no stars are present then use
            # Gaia magnitudes
            if band in self.filters:
                themag = f"mag_{band}"
                # check if the band magnitude is present in the catalog
                if themag in cat_select2.colnames:
                    magok = ~np.isnan(cat_select2[themag])
                    if len(cat_select2[magok]) > 0:
                        mags = cat_select2[themag] + cat_select2["delta_mag"]
                        ibrightest = np.argmin(mags)
                    else:
                        # Fall back to Gaia G
                        mags = cat_select2["gaia_G"] + cat_select2["delta_mag"]
                        ibrightest = np.argmin(mags)
                else:
                    # Fall back to Gaia G
                    mags = cat_select2["gaia_G"] + cat_select2["delta_mag"]
                    ibrightest = np.argmin(mags)
            else:
                mags = cat_select2["gaia_G"] + cat_select2["delta_mag"]
                ibrightest = np.argmin(mags)

            cat_thestar = cat_select2[ibrightest]

            if first:
                first = False
                cat_all = Table(cat_thestar)
            else:
                cat_all = vstack([cat_thestar, cat_all])

        # build the configuration string for the ROIs from the catalog with
        # all stars

        # Check if any guide stars were found
        if len(cat_all) == 0:
            raise RuntimeError(
                f"No suitable guide stars found for the given pointing. "
                f"Boresight: RA={boresight_RA:.6f}°, Dec={boresight_DEC:.6f}°. "
                f"This may be due to limited catalog coverage or overly "
                f"restrictive selection criteria."
            )

        config_text = f"""
roi_spec:
 common:
  rows: {int(roi_size)}
  cols: {int(roi_size)}
  integration_time_millis: {int(roi_time)}"""

        for arow in cat_all:
            ccdname = arow["ccdName"]
            # Remove underscore from CCD name
            ccd_guider_name = ccdname[0:3] + ccdname[4:]
            ampname = arow["ampNameLL"]
            amp_guider_name = ampname[1:]  # remove the C in Cxy
            start_col = int(arow["ampxLL"])
            start_row = int(arow["ampyLL"])

            ccd_text = f"""
roi:
 {ccd_guider_name}:
  segment: {amp_guider_name}
  start_row: {start_row}
  start_col: {start_col}"""

            config_text = config_text + ccd_text

        # done!
        return config_text, cat_all

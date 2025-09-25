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
    "DM_STACK_AVAILABLE",
    "BEST_EFFORT_ISR_AVAILABLE",
    "GuiderROIs",
    "get_vignetting_data_from_butler",
]

import logging
import warnings
from typing import TYPE_CHECKING, Any

import healpy as hp
from astropy.coordinates import angular_separation
from astropy.table import Table, vstack
from scipy.interpolate import make_interp_spline

if TYPE_CHECKING:
    from lsst.summit.utils import BestEffortIsr as BestEffortIsrType

import numpy as np

DEFAULT_CATALOG_DATASET_NAME = "monster_guide_catalog"
DEFAULT_VIGNETTING_DATASET_NAME = "vignetting_correction"
DEFAULT_COLLECTION_NAME = "guider_roi_data"


# DM Stack imports (includes Butler)
DM_STACK_AVAILABLE = True
try:
    # Core DM stack imports
    import lsst.geom as geom
    from lsst.afw import cameraGeom
    from lsst.daf.butler import Butler
    from lsst.daf.butler._exceptions import DatasetNotFoundError
    from lsst.obs.base import createInitialSkyWcsFromBoresight
    from lsst.obs.lsst import LsstCam
    from lsst.obs.lsst.cameraTransforms import LsstCameraTransforms
except ImportError:
    DM_STACK_AVAILABLE = False
    warnings.warn(
        "DM Stack not available. GuiderROIs will work in file-based mode only."
    )

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
        catalog_name: str = DEFAULT_CATALOG_DATASET_NAME,
        vignetting_dataset: str = DEFAULT_VIGNETTING_DATASET_NAME,
        collection: str = DEFAULT_COLLECTION_NAME,
        log: logging.Logger | None = None,
    ) -> None:
        """Initialize GuiderROIs.

        Parameters
        ----------
        catalog_name : `str`, optional
            Name of the HEALPix catalog dataset in butler.
        vignetting_dataset : `str`, optional
            Name of the vignetting correction dataset in butler.
        collection : `str`, optional
            Collection name for data queries.
        log : `logging.Logger`, optional
            Parent logger. If provided, a child logger will be created from it
            named after this class; otherwise, a class-scoped logger will be
            obtained from the root logger.

        Raises
        ------
        RuntimeError
            If basic dependencies are not available, or the DM stack or
            BestEffortIsr is unavailable.
        ValueError
            If vignetting data is missing required columns.

        Notes
        -----
        Operating mode:
        - Summit/DM environment via BestEffortIsr (required). Butler is
          obtained from BestEffortIsr, and HEALPix settings are derived from
          the repository.
        """
        if not DM_STACK_AVAILABLE:
            raise RuntimeError(
                "DM Stack not available. BestEffortIsr mode is required for GuiderROIs."
            )
        if not BEST_EFFORT_ISR_AVAILABLE or BestEffortIsr is None:
            raise RuntimeError(
                "BestEffortIsr is required but not available in this environment."
            )

        # Store configuration
        self.catalog_name = catalog_name
        self.vignetting_dataset = vignetting_dataset
        self.collection = collection

        # Butler via BestEffortIsr only
        self.best_effort_isr: "BestEffortIsrType | None" = BestEffortIsr()
        self.butler: Butler | None = (
            self.best_effort_isr.butler if self.best_effort_isr is not None else None
        )
        if self.butler is None:
            raise RuntimeError("Failed to obtain Butler from BestEffortIsr.")

        self.log = (
            logging.getLogger(type(self).__name__)
            if log is None
            else log.getChild(type(self).__name__)
        )

        # Derive HEALPix settings from the DatasetType dimensions
        self._init_healpix()

        # Constants
        self.ccd_diag = 0.15852  # Guider CCD diagonal radius in Degrees
        self.bad_guideramps = {193: ["C1"], 198: ["C1"], 201: ["C0"]}

        # Initialize camera (optional, requires DM stack)
        self.camera = None
        if DM_STACK_AVAILABLE:
            self.camera = LsstCam.getCamera()

        # Initialize vignetting correction
        self._init_vignetting_correction()

    def _init_healpix(self) -> None:
        """Initialize HEALPix configuration from Butler DatasetType if
        possible.

        When Butler is available, prefer deriving the HEALPix dimension and
        corresponding level/nside from the catalog dataset type's required
        dimensions. This ensures consistency with the repository schema.

        Falls back to the user-provided ``nside`` only if Butler is not
        available. If the dataset type lacks a HEALPix dimension, an error is
        raised.
        """
        if not DM_STACK_AVAILABLE or self.butler is None:
            return

        dt = self.butler.registry.getDatasetType(self.catalog_name)
        dim_required = dt.dimensions.required
        hp_dims = [
            str(name) for name in dim_required if str(name).startswith("healpix")
        ]

        if not hp_dims:
            raise RuntimeError(
                f"DatasetType '{self.catalog_name}' has no HEALPix dimension; "
                "cannot derive nside from repository."
            )

        hp_name = hp_dims[0]
        level = int(hp_name.replace("healpix", ""))
        derived_nside = 2**level

        self.nside = derived_nside
        self.healpix_level = level
        self.healpix_dim = hp_name

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
        if self.butler is None:
            raise RuntimeError("Butler is not available")

        vignetting_data = get_vignetting_data_from_butler(
            self.butler, self.vignetting_dataset, self.collection
        )

        try:
            # Create interpolation spline with the validated data
            self.vigspline = make_interp_spline(
                vignetting_data["theta"], vignetting_data["vignetting"], k=3
            )
        except Exception as e:
            raise RuntimeError("Failed to create vignetting correction spline.") from e

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

    def _get_catalog_data_from_butler(self, hp_indices: list[int]) -> list[Table]:
        """Get catalog data from butler using HEALPix dimensions."""
        tables: list[Table] = []

        if not DM_STACK_AVAILABLE:
            self.log.warning(
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
                            self.log.warning(
                                f"No catalog data found for HEALPix pixel {hp_idx}"
                            )

                except Exception as e:
                    self.log.warning(
                        f"Could not load catalog for HEALPix {hp_idx}: {e}"
                    )
                    continue

        except Exception as e:
            self.log.warning(f"Could not load catalog data from butler: {e}")

        return tables

    def get_guider_rois(
        self,
        ra: float,
        dec: float,
        sky_angle: float,
        roi_size: int,
        roi_time: int,
        band: str,
        npix_edge: int = 50,
        use_guider: bool = True,
        use_wavefront: bool = False,
        use_science: bool = False,
    ) -> tuple[str, Table]:
        """Get guider ROI configuration.

        Parameters
        ----------
        ra : float
            Boresight RA in degrees
        dec : float
            Boresight Dec in degrees
        sky_angle : float
            Boresight rotation angle in degrees (needs to match
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
        boresight_radec = geom.SpherePoint(ra, dec, geom.degrees)
        boresight_rotang = geom.Angle(sky_angle, geom.degrees)

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
            ccd_bbox_top.grow(-geom.Extent2I(npix_edge, npix_edge))
            ccd_bbox_bottom = geom.Box2I(
                geom.Point2I(ccd_bbox.getMinX(), 0),
                geom.Extent2I(ccd_nx, ccd_nyhalf),
            )
            ccd_bbox_bottom.grow(-geom.Extent2I(npix_edge, npix_edge))

            # query the Monster-based Guider star catalog with the CCD polygon
            catalog_indices = hp.query_polygon(
                self.nside, cam_vec_corners[detector.getId()], inclusive=True, fact=8
            )

            # Get neighboring pixels for catalog query
            try:

                # Get catalog data using HEALPix dimensions
                tables = self._get_catalog_data_from_butler(catalog_indices)

                if not tables:
                    self.log.warning(f"No catalog data found for detector {idet}")
                    continue

                star_cat = vstack(tables)

            except Exception as e:
                self.log.warning(f"Error reading catalog for detector {idet}: {e}")
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
                self.log.warning(
                    f"No isolated stars found inside CCD for detector {idet}"
                )
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
                    np.deg2rad(ra),
                    np.deg2rad(dec),
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
                self.log.warning(f"No stars in good amplifiers for detector {idet}")
                continue

            # Find the brightest star using the requested band
            themag = f"mag_{band}"
            if themag not in cat_select2.colnames:
                raise ValueError(
                    f"Requested band '{band}' not available in catalog columns."
                )

            # Require at least one valid magnitude in the requested band
            mag_values = cat_select2[themag]
            magok = ~np.isnan(mag_values)
            if len(cat_select2[magok]) == 0:
                raise ValueError(
                    f"No valid magnitudes for band '{band}' found in catalog."
                )

            mags = mag_values + cat_select2["delta_mag"]
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
                f"Boresight: RA={ra:.6f}°, Dec={dec:.6f}°. "
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

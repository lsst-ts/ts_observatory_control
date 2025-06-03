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
adapted for integration with ts_observatory_control while maintaining
the core algorithmic approach.

Original algorithm credit: Aaron Roodman
"""

__all__ = [
    "DM_STACK_AVAILABLE",
    "BEST_EFFORT_ISR_AVAILABLE",
    "GuiderROIs",
]

import typing
import warnings

import numpy as np

DM_STACK_AVAILABLE = True
BEST_EFFORT_ISR_AVAILABLE = True
try:
    import healpy as hp
    import lsst.geom as geom
    from astropy.coordinates import angular_separation
    from astropy.table import Table, vstack
    from lsst.afw import cameraGeom
    from lsst.geom import Angle, Extent2I, SpherePoint
    from lsst.obs.base import createInitialSkyWcsFromBoresight
    from lsst.obs.lsst import LsstCam
    from lsst.obs.lsst.cameraTransforms import LsstCameraTransforms
    from scipy.interpolate import make_interp_spline
except ImportError as e:
    DM_STACK_AVAILABLE = False
    BEST_EFFORT_ISR_AVAILABLE = False
    print(f"Cannot import required libraries. GuiderROIs will not work. {e}")
    warnings.warn("Cannot import required libraries. GuiderROIs will not work.")

# Try to import BestEffortIsr separately - it's optional for basic
# functionality
try:
    from lsst.summit.utils import BestEffortIsr
except ImportError as e:
    BEST_EFFORT_ISR_AVAILABLE = False
    BestEffortIsr = None  # Make it available for mocking in tests
    if DM_STACK_AVAILABLE:
        print(f"BestEffortIsr not available but core DM stack is available. {e}")
        warnings.warn(
            "BestEffortIsr not available. You must provide a butler when initializing GuiderROIs."
        )


def get_monster_catalog_loader_from_butler(
    butler: typing.Any,
    catalog_name: str = "monster_guide_catalog",
    **kwargs: typing.Any,
) -> typing.Any:
    """Get Monster guide catalog data from a Butler.

    Parameters
    ----------
    butler : `lsst.daf.butler.Butler`
        Butler instance to query.
    catalog_name : `str`
        Name of the Monster guide catalog dataset.
    **kwargs : `dict`
        Additional kwargs for queryDatasets.

    Returns
    -------
    catalog_refs : `list`
        List of dataset references for the catalog.
    """
    try:
        catalog_refs = butler.registry.queryDatasets(
            catalog_name,
            **kwargs,
        ).expanded()
        return list(catalog_refs)
    except Exception as e:
        warnings.warn(f"Could not query Monster guide catalog: {e}")
        return []


def get_vignetting_data_from_butler(
    butler: typing.Any, vignetting_dataset: str = "vignetting_correction"
) -> typing.Optional[typing.Any]:
    """Get vignetting correction data from Butler.

    Parameters
    ----------
    butler : `lsst.daf.butler.Butler`
        Butler instance to query.
    vignetting_dataset : `str`
        Name of the vignetting dataset.

    Returns
    -------
    vignetting_data : `dict` or `None`
        Vignetting data if available, None otherwise.

    Raises
    ------
    ValueError
        If vignetting data is found but required columns are missing.
    """
    try:
        vignetting_refs = butler.registry.queryDatasets(vignetting_dataset)
        if vignetting_refs:
            ref = next(iter(vignetting_refs))
            data = butler.get(ref)

            # Validate required columns exist
            if data is not None:
                required_keys = ["theta", "vignetting"]
                missing_keys = [key for key in required_keys if key not in data]
                if missing_keys:
                    raise ValueError(
                        f"Vignetting data missing required columns: {missing_keys}. "
                        f"Available columns: {list(data.keys())}"
                    )

            return data
    except Exception as e:
        if isinstance(e, ValueError):
            raise  # Re-raise ValueError for missing columns
        warnings.warn(f"Could not get vignetting data from butler: {e}")
    return None


class GuiderROIs:
    """GuiderROIs definition.

    This class provides code to select Guider ROIs for LSSTCam based on the
    original algorithm developed by Aaron Roodman. The implementation includes
    improvements for integration with the LSST DM stack and
    ts_observatory_control.

    Original algorithm credit: Aaron Roodman

    Notes
    -----
    The class depends on the LSST DM stack and vignetting correction data.
    It will fail during initialization if the DM stack is not available or
    if the required vignetting data cannot be found in the butler.
    """

    def __init__(
        self,
        butler: typing.Optional[typing.Any] = None,
        catalog_name: str = "monster_guide_catalog",
        vignetting_dataset: str = "vignetting_correction",
    ) -> None:
        """Initialize GuiderROIs.

        Parameters
        ----------
        butler : `lsst.daf.butler.Butler`, optional
            Butler instance to use for data access. If None, will create
            a BestEffortIsr butler (requires lsst.summit.utils to be
            available).
        catalog_name : `str`, optional
            Name of the Monster guide catalog dataset in butler.
        vignetting_dataset : `str`, optional
            Name of the vignetting correction dataset in butler.

        Raises
        ------
        RuntimeError
            If DM stack is not available, if vignetting data is not found,
            or if butler is None and BestEffortIsr is not available.
        ValueError
            If vignetting data is missing required columns ('theta',
            'vignetting').
        """
        if not DM_STACK_AVAILABLE:
            raise RuntimeError("DM stack not available. Cannot initialize GuiderROIs.")

        # Set up butler
        if butler is None:
            if not BEST_EFFORT_ISR_AVAILABLE or BestEffortIsr is None:
                raise RuntimeError(
                    "BestEffortIsr is not available and no butler was provided. "
                    "Please provide a butler instance or install lsst.summit.utils."
                )
            self.best_effort_isr = BestEffortIsr()
            self.butler = self.best_effort_isr.butler
        else:
            self.butler = butler
            self.best_effort_isr = None

        self.catalog_name = catalog_name
        self.vignetting_dataset = vignetting_dataset

        # Constants
        self.ccd_diag = 0.15852  # Guider CCD diagonal radius in Degrees
        res = 5
        self.nside = 2**res
        self.npix = 12 * self.nside**2
        self.bad_guideramps = {193: "C1", 198: "C1", 201: "C0"}
        self.filters = ["u", "g", "r", "i", "z", "y"]
        self.camera = LsstCam.getCamera()

        # Initialize vignetting correction
        self._init_vignetting_correction()

    def _init_vignetting_correction(self) -> None:
        """Initialize vignetting correction spline.

        Raises
        ------
        RuntimeError
            If vignetting data is not available or invalid.
        ValueError
            If vignetting data is missing required columns.
        """
        vignetting_data = get_vignetting_data_from_butler(
            self.butler, self.vignetting_dataset
        )

        if vignetting_data is None:
            raise RuntimeError(
                f"Vignetting correction data '{self.vignetting_dataset}' not found in butler. "
                "Cannot initialize GuiderROIs without vignetting correction data."
            )

        try:
            # Create interpolation spline with the validated data
            self.vigspline = make_interp_spline(
                vignetting_data["theta"], vignetting_data["vignetting"], k=3
            )
        except Exception as e:
            raise RuntimeError(f"Failed to create vignetting correction spline: {e}")

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

    def _get_catalog_data_for_healpix(
        self, hp_indices: typing.List[int]
    ) -> typing.List[Table]:
        """Get catalog data for given HEALPix indices from butler.

        Parameters
        ----------
        hp_indices : `list` of `int`
            HEALPix indices to query.

        Returns
        -------
        tables : `list` of `astropy.table.Table`
            Catalog tables for the requested indices.

        Notes
        -----
        This is an interim implementation that attempts to get available
        catalog data from Butler. Exact dataset structure is TBD.
        """
        tables = []

        for hp_idx in hp_indices:
            try:
                # This is what we SHOULD be able to do once structure is known
                dataId = {"healpix": hp_idx}
                table = self.butler.get(self.catalog_name, dataId=dataId)
                tables.append(table)
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
    ) -> typing.Tuple[str, typing.Any]:
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
            If DM stack is not available or no suitable guide stars found.
        """
        if not DM_STACK_AVAILABLE:
            raise RuntimeError("DM stack not available.")

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

        # loop over detectors, getting the optimal guider star in each
        first = True
        for idet, wcs in cam_wcs.items():
            ra_ccd, dec_ccd = cam_radec[idet]
            detector = self.camera[idet]

            # get BBox for this detector, removing some number of edge pixels
            ccd_bbox = detector.getBBox()
            ccd_nx, ccd_ny = ccd_bbox.getDimensions()
            ccd_bbox.grow(-Extent2I(npix_edge, npix_edge))

            # query the Monster-based Guider star catalog via butler
            hp_ind = hp.ang2pix(self.nside, ra_ccd, dec_ccd, lonlat=True)

            # Get neighboring pixels for catalog query
            try:
                SW, W, NW, N, NE, E, SE, S = hp.get_all_neighbours(self.nside, hp_ind)

                # Get catalog data from butler
                catalog_indices = [hp_ind, E, W, S, N, SW, SE, NW, NE]
                tables = self._get_catalog_data_for_healpix(catalog_indices)

                if not tables:
                    warnings.warn(f"No catalog data found for detector {idet}")
                    continue

                star_cat = vstack(tables)

            except Exception as e:
                warnings.warn(f"Error reading catalog for detector {idet}: {e}")
                continue

            # check that stars are isolated and are inside the CCD radius
            isolated = star_cat["guide_flag"] > 63

            star_cat["dangle"] = np.degrees(
                angular_separation(
                    np.deg2rad(ra_ccd),
                    np.deg2rad(dec_ccd),
                    star_cat["coord_ra"],
                    star_cat["coord_dec"],
                )
            )
            inside_CCD_radius = star_cat["dangle"] < self.ccd_diag

            # Selection 1: the Star is isolated and inside the CCD radius
            cat_select1 = star_cat[(isolated & inside_CCD_radius)]

            if len(cat_select1) == 0:
                # TBD: should we raise an error here?
                warnings.warn(
                    f"No isolated stars found in CCD radius for detector {idet}"
                )
                continue

            # using the wcs to locate the stars inside the CCD minus npix_edge
            ccdx, ccdy = wcs.skyToPixelArray(
                cat_select1["coord_ra"], cat_select1["coord_dec"], degrees=False
            )
            in_CCD = ccd_bbox.contains(ccdx, ccdy)

            # fill with CCD pixel x,y
            cat_select1["ccdx"] = ccdx
            cat_select1["ccdy"] = ccdy

            # Selection 2: that the Star is located inside the CCD
            cat_select2 = cat_select1[in_CCD]

            if len(cat_select2) == 0:
                # TBD: should we raise an error here?
                warnings.warn(
                    f"No stars found inside CCD boundaries for detector {idet}"
                )
                continue

            # get the Amp coordinates and check that Amp is not in the bad amp
            # list
            detName = detector.getName()
            lct = LsstCameraTransforms(self.camera, detName)
            ccdNames = []
            ampNames = []
            ampXs = []
            ampYs = []
            ampOk = []

            for arow in cat_select2:
                ampName, ampX, ampY = lct.ccdPixelToAmpPixel(arow["ccdx"], arow["ccdy"])

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
            cat_select2["ccdName"] = ccdNames
            cat_select2["ampName"] = ampNames
            cat_select2["ampX"] = ampXs
            cat_select2["ampY"] = ampYs
            cat_select2["ampOk"] = ampOk
            # currently just have star's central locations
            # also need to get the LL edge of the ROI, do this using CCD pixels
            #  first then convert to Amp pixels
            ccdxLLs = []
            ccdyLLs = []
            ampNameLLs = []
            ampxLLs = []
            ampyLLs = []

            for arow in cat_select2:
                # find CCD LL position
                ccdxLL = arow["ccdx"] - roi_halfsize
                ccdyLL = arow["ccdy"] - roi_halfsize

                # adjust LL position if needed, star will be offset in ROI
                if ccdxLL < npix_boundary:
                    ccdxLL = npix_boundary
                elif ccdxLL > ccd_nx - npix_boundary:
                    ccdxLL = ccd_nx - npix_boundary

                if ccdyLL < npix_boundary:
                    ccdyLL = npix_boundary
                elif ccdyLL > ccd_ny - npix_boundary:
                    ccdyLL = ccd_ny - npix_boundary

                ampNameLL, ampxLL, ampyLL = lct.ccdPixelToAmpPixel(ccdxLL, ccdyLL)
                ccdxLLs.append(ccdxLL)
                ccdyLLs.append(ccdyLL)
                ampNameLLs.append(ampNameLL)
                ampxLLs.append(ampxLL)
                ampyLLs.append(ampyLL)

            # add info on LL of ROI to the catalog
            cat_select2["ccdxLL"] = ccdxLLs
            cat_select2["ccdyLL"] = ccdyLLs
            cat_select2["ampNameLL"] = ampNameLLs
            cat_select2["ampxLL"] = ampxLLs
            cat_select2["ampyLL"] = ampyLLs

            # get the change in magnitude due to the vignetting factor
            cat_select2["dangle_boresight"] = np.degrees(
                angular_separation(
                    np.deg2rad(boresight_RA),
                    np.deg2rad(boresight_DEC),
                    cat_select2["coord_ra"],
                    cat_select2["coord_dec"],
                )
            )

            cat_select2["delta_mag"] = self.vignetting_correction(
                cat_select2["dangle_boresight"]
            )

            # Selection3: check that the amplifier is ok
            cat_select3 = cat_select2[cat_select2["ampOk"]]

            if len(cat_select3) == 0:
                # TBD: should we raise an error here?
                warnings.warn(f"No stars in good amplifiers for detector {idet}")
                continue

            # find the brightest Star in the CCD: first check stars with
            # magnitudes for this band, if no stars are present then use
            # Gaia magnitudes
            if band in self.filters:
                themag = f"mag_{band}"
                if themag in cat_select3.colnames:
                    magok = ~np.isnan(cat_select3[themag])
                    if len(cat_select3[magok]) > 0:
                        mags = cat_select3[themag] + cat_select3["delta_mag"]
                        ibrightest = np.argmin(mags)
                    else:
                        # Fall back to Gaia G
                        mags = cat_select3["gaia_G"] + cat_select3["delta_mag"]
                        ibrightest = np.argmin(mags)
                else:
                    # Fall back to Gaia G
                    mags = cat_select3["gaia_G"] + cat_select3["delta_mag"]
                    ibrightest = np.argmin(mags)
            else:
                mags = cat_select3["gaia_G"] + cat_select3["delta_mag"]
                ibrightest = np.argmin(mags)

            cat_thestar = cat_select3[ibrightest]

            if first:
                first = False
                cat_all = Table(cat_thestar)
            else:
                cat_all = vstack([cat_thestar, cat_all])

        if first:  # No stars found for any detector
            raise RuntimeError("No suitable guide stars found for any detector")

        # build the configuration string for the ROIs from the catalog with
        # all stars
        config_text = f"""
roi_spec:
 common:
  rows: {int(roi_size)}
  cols: {int(roi_size)}
  integration_time_millis: {int(roi_time)}"""

        for arow in cat_all:
            ccdname = arow["ccdName"]
            ccd_guider_name = ccdname[0:3]
            +ccdname[4:]  # remove the underscore
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

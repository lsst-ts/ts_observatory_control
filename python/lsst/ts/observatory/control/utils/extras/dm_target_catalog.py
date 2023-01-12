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

__all__ = [
    "DM_STACK_AVAILABLE",
    "find_target_radec",
]

import typing

import astropy.coordinates
import astropy.units
import numpy as np

DM_STACK_AVAILABLE = True
try:
    from lsst.daf.butler import DeferredDatasetHandle
    from lsst.geom import SpherePoint
    from lsst.meas.algorithms import ReferenceObjectLoader
    from lsst.sphgeom import Angle, Vector3d
    from lsst.summit.utils import BestEffortIsr
except ImportError:
    DM_STACK_AVAILABLE = False
    import warnings

    warnings.warn("Cannot import required libraries. Module will not work.")


def get_reference_object_loader_from_butler(
    butler: typing.Any,
    refcat_name: str,
    config: typing.Any = None,
    **kwargs: typing.Any
) -> typing.Any:
    """Get a ReferenceObjectLoader from a Butler.

    Parameters
    ----------
    butler : `lsst.daf.butler.Butler`
    refcat_name : `str`
        Name of the reference catalog.
        Must be in the collections in the butler or listed here.
    config : `lsst.meas.algorithms.LoadReferenceObjectsConfig`, optional
        Reference catalog loader config.
    **kwargs : `dict`
        Additional kwargs for queryDatasets, particularly ``collections`` and
        ``where`` to do location, and ``skymap`` if tract locations are used.
    """
    refcat_refs = butler.registry.queryDatasets(
        refcat_name,
        **kwargs,
    ).expanded()

    refcat_handles = [
        DeferredDatasetHandle(butler=butler, ref=ref, parameters=None)
        for ref in refcat_refs
    ]

    refcat_dataids = [butler.registry.expandDataId(ref.dataId) for ref in refcat_refs]

    loader = ReferenceObjectLoader(
        refcat_dataids,
        refcat_handles,
        name=refcat_name,
        config=config,
    )

    return loader


def find_target_radec(
    radec: astropy.coordinates.ICRS,
    radius: astropy.coordinates.Angle,
    mag_limit: tuple[float, float],
) -> astropy.coordinates.ICRS:
    """Find target around a RA/Dec coordinates.

    Parameters
    ----------
    radec : `astropy.coordinates.ICRS`
        Ra/Dec coordinates to find targets around.
    radius : `astropy.coordinates.Angle`
        Radius of the search.
    mag_limit : `tuple`[`float`, `float`]
        Magnitude limit (min, max).

    Returns
    -------
    radec_icrs : `astropy.coordinates.ICRS`
        Coordinate of the brightest target in the specified region/magnitude
        limit.
    """
    best_effort_isr = BestEffortIsr()

    reference_object_loader = get_reference_object_loader_from_butler(
        butler=best_effort_isr.butler,
        refcat_name="gaia_dr2_20200414",
    )
    vector_3d = Vector3d(radec.cartesian.x, radec.cartesian.y, radec.cartesian.z)
    sphere_point = SpherePoint(vector_3d)
    radius = Angle(radians=radius.to(astropy.units.rad).value)

    source_cat = reference_object_loader.loadSkyCircle(
        ctrCoord=sphere_point,
        radius=radius,
        filterName="phot_g_mean",
    )

    mag_g = (source_cat.refCat["phot_g_mean_flux"] * astropy.units.nJy).to_value(
        astropy.units.ABmag
    )

    mag_mask = np.bitwise_and(mag_g < mag_limit[1], mag_g > mag_limit[0])

    masked_source_cat = source_cat.refCat[mag_mask]

    source_index = np.argmin(mag_g[mag_mask])

    radec_icrs = astropy.coordinates.ICRS(
        ra=astropy.coordinates.Angle(
            masked_source_cat["coord_ra"][source_index] * astropy.units.rad
        ),
        dec=astropy.coordinates.Angle(
            masked_source_cat["coord_dec"][source_index] * astropy.units.rad
        ),
    )

    return radec_icrs

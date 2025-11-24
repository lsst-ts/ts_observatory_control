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

"""Butler storage class and formatter for VignettingCorrection."""

__all__ = ["VignettingCorrectionFormatter", "register_vignetting_storage_class"]

import logging
from typing import Any

# Optional Butler imports - only available with DM stack
try:
    from lsst.daf.butler import FormatterV2, StorageClass
    from lsst.resources import ResourcePath
except ImportError:
    # Define dummy classes for when Butler is not available
    FormatterV2 = object  # type: ignore
    StorageClass = object  # type: ignore
    ResourcePath = object  # type: ignore

from .vignetting_correction import VignettingCorrection

logger = logging.getLogger(__name__)


class VignettingCorrectionFormatter(FormatterV2):
    """Formatter for VignettingCorrection using ECSV format.

    This formatter handles reading and writing VignettingCorrection objects
    to/from ECSV files, which is the preferred format for LSST calibration
    data.
    """

    default_extension = ".ecsv"
    can_read_from_uri = True
    can_read_from_local_file = True

    def read_from_local_file(
        self, path: str, component: str | None = None, expected_size: int = -1
    ) -> VignettingCorrection:
        """Read VignettingCorrection from local ECSV file."""
        logger.debug(f"Reading VignettingCorrection from {path}")
        return VignettingCorrection.from_ecsv_file(path)

    def write_local_file(
        self, in_memory_dataset: VignettingCorrection, uri: ResourcePath
    ) -> None:
        """Write VignettingCorrection to local ECSV file."""
        logger.debug(f"Writing VignettingCorrection to {uri.ospath}")
        in_memory_dataset.to_ecsv_file(uri.ospath)


def register_vignetting_storage_class(butler: Any) -> None:
    """Register VignettingCorrection storage class and formatter with Butler.

    This function registers the custom storage class and formatter with the
    specific Butler instance's datastore, following the pattern used in
    daf_butler tests.

    Parameters
    ----------
    butler : `Any`
        Butler instance to register with.

    Raises
    ------
    ValueError
        If butler is None.
    Exception
        Any exception from Butler registration operations.
    """
    if butler is None:
        raise ValueError("Butler instance is required for registration")

    storage_class = StorageClass(
        name="VignettingCorrection",
        pytype=VignettingCorrection,
        parameters=[],
        components={},
    )
    butler._datastore.storageClassFactory.registerStorageClass(storage_class)
    logger.info("Registered VignettingCorrection storage class")

    # Register formatter with Butler's datastore formatter factory
    # Use the full class path as a string (following daf_butler pattern)
    formatter_class_path = (
        "lsst.ts.observatory.control.utils.extras.vignetting_storage."
        "VignettingCorrectionFormatter"
    )
    butler._datastore.formatterFactory.registerFormatter(
        "VignettingCorrection",
        formatter_class_path,
    )
    logger.info(f"Registered VignettingCorrection formatter: {formatter_class_path}")

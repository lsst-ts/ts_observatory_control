# This file is part of ts_observatory_control.
#
# Developed for the Vera C. Rubin Observatory Telescope and Site Systems.
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
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

"""Record real Simbad responses used as fixtures by the unit tests.

The unit tests do not query Simbad. Instead they replay the tables stored
next to this script. When Simbad (or astroquery) changes the format of its
responses, the remote tests (see ``tests/conftest.py``) will fail; re-run
this script to refresh the fixtures and adapt the parsing code if needed::

    python tests/data/simbad/record_fixtures.py [--server simbad.harvard.edu]
"""

import argparse
import pathlib

import astropy.units as u
from astropy.coordinates import ICRS, Angle
from astroquery.simbad import Simbad

FIXTURES_DIR = pathlib.Path(__file__).parent

# Keep these in sync with the queries made in ``BaseTCS``.
OBJECT_NAME = "HD 185975"
REGION_RADEC = ICRS(ra=Angle(120.0, unit=u.deg), dec=Angle(-60.0, unit=u.deg))
REGION_RADIUS = 0.5 * u.deg
REGION_VOTABLE_FIELDS = ("V", "rvz_redshift", "ident")
REGION_CRITERIA = "V>9.0 AND V<11.0 AND ident.id LIKE 'HD%'"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--server",
        default=None,
        help="Simbad mirror to query (e.g. simbad.harvard.edu). "
        "Defaults to astroquery's configured server.",
    )
    args = parser.parse_args()

    simbad = Simbad()
    if args.server is not None:
        simbad.server = args.server

    object_table = simbad.query_object(OBJECT_NAME)
    object_table.write(FIXTURES_DIR / "query_object.ecsv", overwrite=True)

    simbad.add_votable_fields(*REGION_VOTABLE_FIELDS)
    region_table = simbad.query_region(
        REGION_RADEC, radius=REGION_RADIUS, criteria=REGION_CRITERIA
    )
    region_table.write(FIXTURES_DIR / "query_region.ecsv", overwrite=True)

    print(
        f"Recorded {len(object_table)} object row(s), {len(region_table)} region row(s)."
    )


if __name__ == "__main__":
    main()

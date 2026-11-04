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

"""Shared pytest configuration.

Simbad
------
By default, tests do not reach the Simbad server. ``BaseTCS`` queries are
replaced by replays of real responses recorded in ``tests/data/simbad``
(see ``tests/data/simbad/record_fixtures.py`` to refresh them).

Tests marked with ``@pytest.mark.remote`` exercise the real server. They are
skipped unless enabled with ``--run-remote`` or by setting the environment
variable ``TS_OBSERVATORY_CONTROL_RUN_REMOTE=1``. Those tests are not patched,
so they also catch changes in the Simbad/astroquery interface.
"""

import os
import pathlib
import typing

import pytest
from astropy.table import Table
from lsst.ts.observatory.control.base_tcs import BaseTCS

SIMBAD_FIXTURES_DIR = pathlib.Path(__file__).parent / "data" / "simbad"
RUN_REMOTE_ENV_VAR = "TS_OBSERVATORY_CONTROL_RUN_REMOTE"


def load_simbad_fixture(name: str) -> Table:
    """Load a recorded Simbad response.

    Parameters
    ----------
    name : `str`
        Fixture name, e.g. "query_object" or "query_region".

    Returns
    -------
    `Table`
        Recorded response.
    """
    return Table.read(SIMBAD_FIXTURES_DIR / f"{name}.ecsv")


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-remote",
        action="store_true",
        default=False,
        help="Run tests that access remote services (e.g. Simbad).",
    )


def _run_remote(config: pytest.Config) -> bool:
    return bool(config.getoption("--run-remote")) or os.environ.get(
        RUN_REMOTE_ENV_VAR, ""
    ).lower() in ("1", "true", "yes")


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    if _run_remote(config):
        return

    skip_remote = pytest.mark.skip(
        reason=f"Remote test; use --run-remote or {RUN_REMOTE_ENV_VAR}=1 to run."
    )
    for item in items:
        if "remote" in item.keywords:
            item.add_marker(skip_remote)


@pytest.fixture(autouse=True)
def offline_simbad(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Replay recorded Simbad responses instead of querying the server.

    Only the object recorded in the fixture is known; any other name behaves
    as not found in Simbad. Cone searches always return the recorded table.
    """
    if request.node.get_closest_marker("remote") is not None:
        return

    object_table = load_simbad_fixture("query_object")
    region_table = load_simbad_fixture("query_region")
    known_objects = {str(main_id).strip() for main_id in object_table["main_id"]}

    def query_object_from_simbad(self: BaseTCS, object_name: str) -> Table:
        if object_name.strip() not in known_objects:
            raise RuntimeError(f"Could not find {object_name} in Simbad database.")
        return object_table.copy()

    def query_region_from_simbad(
        self: BaseTCS, *args: typing.Any, **kwargs: typing.Any
    ) -> Table:
        return region_table.copy()

    monkeypatch.setattr(BaseTCS, "_query_object_from_simbad", query_object_from_simbad)
    monkeypatch.setattr(BaseTCS, "_query_region_from_simbad", query_region_from_simbad)

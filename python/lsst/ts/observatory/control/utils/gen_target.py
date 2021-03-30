# This file is part of ts_observatory_control.
#
# Developed for the Vera Rubin Observatory Telescope and Site Systems.
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

__all__ = ["Target"]

from astroquery.simbad import Simbad


class Target:
    def __init__(self, name, ra, dec, mag_v):
        self.name = name
        self.ra = ra
        self.dec = dec
        self.mag_v = mag_v

    @classmethod
    def gen_target(cls, target_name):

        simbad = Simbad()
        simbad.add_votable_fields("flux(V)")
        object_table = Simbad.query_object(target_name)

        return cls(
            target_name,
            object_table["RA"][0],
            object_table["DEC"][0],
            object_table["FLUX_V"][0],
        )

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

import dataclasses

plate_scale = 0.05  # mm/arcsecond at the telescope focal plane


@dataclasses.dataclass(frozen=True)
class SimonyiVentParameters:
    """Named, immutable parameters for the Simonyi (Main) Telescope's
    evening venting protocol.

    Attributes
    ----------
    sun_elevation_high : `float`
        Sun elevation (deg) above which the dome shutter and louvers stay
        fully closed; the dome is only nudged for sun-avoidance.
    sun_elevation_horizon : `float`
        Sun elevation (deg) at/below which the sun-avoidance constraint no
        longer applies and the dome/telescope reposition for the wind.
    sun_elevation_stop : `float`
        Sun elevation (deg) at which venting proceeds regardless of the
        temperature condition.
    tel_vent_elevation : `float`
        Telescope elevation (deg) used while venting.
    louver_sun_avoidance_angle : `float`
        Minimum angular separation (deg) a louver must keep from the sun.
    louver_sun_exposed_percent : `float`
        Percent-open cap for louvers within the sun avoidance angle.
    temperature_differential_threshold : `float`
        Outside-minus-indoor temperature threshold (deg C) that must be met
        before venting starts.
    loop_wait_time : `float`
        Seconds to wait between iterations of the venting polling loops.
    dome_min_az : `float`
        Minimum dome azimuth (deg) allowed while the sun is up.
    dome_max_az : `float`
        Maximum dome azimuth (deg) allowed while the sun is up.
    """

    sun_elevation_high: float = 6.0
    sun_elevation_horizon: float = -1.0
    sun_elevation_stop: float = -6.0
    tel_vent_elevation: float = 30.0
    louver_sun_avoidance_angle: float = 60.0
    louver_sun_exposed_percent: float = 50.0
    temperature_differential_threshold: float = -1.0
    loop_wait_time: float = 30.0
    dome_min_az: float = 30.0
    dome_max_az: float = 150.0

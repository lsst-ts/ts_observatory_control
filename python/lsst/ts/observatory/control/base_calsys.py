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

__all__ = ["BaseCalsys"]

import abc
import logging
import typing

import yaml
from lsst.ts import salobj

from .remote_group import RemoteGroup
from .utils import CalibrationType


class BaseCalsys(RemoteGroup, metaclass=abc.ABCMeta):
    """Base class for calibration systems operation

    Parameters
    ----------
    components : `list` [`str`]
        A list of strings with the names of the SAL components that are part
        of the calibration system group.
    instrument_setup_attributes : `list` [`str`]
        Names of the attributes needed to setup the instrument for taking an
        exposure. This is used to check for bad input with functions calls.
    domain : `lsst.ts.salobj.Domain`
        Domain for remotes. If `None` create a domain.
    log : `logging.Logger`
        Optional logging class to be used for logging operations. If `None`,
        create a new logger.
    intended_usage: `int`
        Optional integer that maps to a list of intended operations. This is
        used to limit the resources allocated by the class by gathering some
        knowledge about the usage intention. By default allocates all
        resources.
    """

    def __init__(
        self,
        components: typing.List[str],
        domain: typing.Optional[salobj.Domain] = None,
        log: typing.Optional[logging.Logger] = None,
        intended_usage: typing.Optional[int] = None,
    ) -> None:
        super().__init__(
            components=components,
            domain=domain,
            log=log,
            intended_usage=intended_usage,
        )

        self.calibration_config_file = "data/calibration_config.yaml"

    @abc.abstractmethod
    async def setup_calsys(self, calib_type: typing.Optional[CalibrationType]) -> None:
        """Calibration instrument is prepared so that illumination source
        can be turned ON. Initial instrument settings are configured
        based on calib_type.

        Parameters
        ----------
        calib_type : CalibrationType (enum)
            Identifies if WhiteLight or Mono. This is only relevant for the
            MainTelescope, so it is optional. If not identified, all light
            sources will be setup.

        Raises
        -------
        RuntimeError:
            If setup is unable to complete.

        Notes
        -----
        The dome and telescope can be moving into place concurrently.

        """
        raise NotImplementedError()

    @abc.abstractmethod
    async def configure_flat(self, config_name: str) -> None:
        """Configure calibration system to be ready to take a flat

        Parameters
        ----------
        filter : `str`
            Rubin Filter: ['u','g','r','i','z','y']
        wavelength : `float`
            (units = nm)
            If monochromatic flats, wavelength range [350, 1200] nm

        Raises
        -------
        RuntimeError:
            If error in configuration

        Notes
        -----
        This will include the check the configuration of the telescope, dome,
        and camera in addition to calsys.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    async def perform_flat(self, exptime_dict: dict[str, float]) -> None:
        """Perform flat, by taking image of calibration screen

        Parameters
        ----------
        exptime_dict : `dict`
            This will contain exposure times for the camera, electrometer,
            and fiber spectrographs based on the light source, filter and
            wavelength.

        Raises
        -------
        RuntimeError:
            If there is some error in the data taking of the camera,
            electrometer or fiber spectrographs
        """
        raise NotImplementedError()

    def read_config_file(self, filename: str) -> dict:
        """Read in a yaml file for a specific configuration"""

        with open(filename, "r") as f:
            full_data = yaml.safe_load(f)

        return full_data["calibration_config"]

    def get_config(self, config_name: str) -> dict:
        """Returns the configuration attributes given a configuration
        name
        """

        full_data = self.read_config_file(self.calibration_config_file)
        data = next((d for d in full_data if d["name"] == config_name), None)

        if data is None:
            options = self.configuration_options()
            raise RuntimeError(
                f"That configuration is not available."
                f" Must be in following options"
                f"{options}"
            )
        else:
            return data

    def configuration_options(self) -> typing.List:
        """Will read the yaml file and detail configurations available"""

        full_data = self.read_config_file(self.calibration_config_file)

        options = [d["name"] for d in full_data]

        return options

    @abc.abstractmethod
    async def get_optimized_exposure_times(
        self,
        calib_name: str,
        wavelength: typing.Union[float, None],
    ) -> dict[str, float]:
        """Determines the best exposure time for the camera, electrometer,
        and fiber spectrographs based on the calsys setup

        Parameters
        ----------
        calib_type : `str`
            White Light or Monochromatic illumination system: ['White','Mono']
        filter : `str`
            Rubin Filter: ['u','g','r','i','z','y']
        wavelength : `float`
            (units = nm)
            If monochromatic flats, wavelength range [350, 1200] nm

        Returns
        -------
        `dict`
            Exposure times for all components

        """
        raise NotImplementedError()

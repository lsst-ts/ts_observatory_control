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

__all__ = [
    "BaseCalsys",
]

import abc
import logging
import typing

import jsonschema
import yaml
from lsst.ts import salobj
from lsst.ts.xml.enums.Electrometer import UnitToRead

from .remote_group import RemoteGroup
from .utils import get_data_path


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

        self.calibration_config: dict[str, dict[str, typing.Any]] = dict()

    async def setup_electrometers(
        self,
        mode: str,
        range: float,
        integration_time: float,
        electrometer_names: list | None = None,
    ) -> None:
        """Setup all electrometers.

        Parameters
        ----------
        mode : `str`
            Electrometer measurement mode.
        range : `float`
            Electrometer measurement range. -1 for autorange.
        integration_time : `float`
            Electrometer measurement range.
        """
        electrometer_mode = getattr(UnitToRead, mode).value

        if electrometer_names is None:

            electrometers = [
                getattr(self.rem, component_name)
                for component_name in self.components_attr
                if "electrometer" in component_name
            ]

        else:

            electrometers = [getattr(self.rem, name) for name in electrometer_names]

        for electrometer in electrometers:
            await electrometer.cmd_setMode.set_start(
                mode=electrometer_mode,
                timeout=self.long_timeout,
            )
            await electrometer.cmd_setRange.set_start(
                setRange=range,
                timeout=self.long_timeout,
            )
            await electrometer.cmd_setIntegrationTime.set_start(
                intTime=integration_time,
                timeout=self.long_timeout,
            )
            await electrometer.cmd_performZeroCalib.start(timeout=self.long_timeout)
            await electrometer.cmd_setDigitalFilter.set_start(
                activateFilter=False,
                activateAvgFilter=False,
                activateMedFilter=False,
                timeout=self.long_timeout,
            )

    @abc.abstractmethod
    async def setup_calsys(self, sequence_name: str) -> None:
        """Calibration instrument is prepared so that illumination source
        can be turned ON. Initial instrument settings are configured
        based on calib_type.

        Parameters
        ----------
        sequence_name : `str`
            Name of the calibration sequence to prepare for.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    async def prepare_for_flat(self, sequence_name: str) -> None:
        """Configure calibration system to be ready to take a flat

        Parameters
        ----------
        sequence_name : `str`
            Name of the calibration sequence to prepare for.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    async def run_calibration_sequence(
        self, sequence_name: str, exposure_metadata: dict
    ) -> dict:
        """Perform full calibration sequence, taking flats with the
        camera and all ancillary instruments.

        Parameters
        ----------
        sequence_name : `str`
            Name of the calibration sequence to execute.
        exposure_metadata : `dict`
            Metadata to be passed to the LATISS.take_flats method.

        Returns
        -------
        calibration_summary : `dict`
            Dictionary with summary information about the sequence.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    async def calculate_optimized_exposure_times(
        self, wavelengths: list, config_data: dict
    ) -> list:
        """Calculates the exposure times for the electrometer and
        fiber spectrograph given the type and wavelength of the exposure
        and the length of the camera exposure time

        Parameters
        ----------
        wavelengths : `list`
            List of all wavelengths for this exposure list
        config_data : `dict`
            All information from configuration file

        Returns
        -------
        exposure_list : `list`[ATCalsysExposure|MTCalsysExposure]
            List of exposure information, includes wavelength
            and camera, fiberspectrograph and electrometer exposure times.
        """
        # TO-DO: DM-44777
        raise NotImplementedError()

    def load_calibration_config_file(self, filename: str | None = None) -> None:
        """Load the calibration configuration file.

        By default it will determine the filename based on the class
        name. However, it is possible to provide an override with the
        full file name.

        It performs schema validation of the calibration configuration
        file against the corresponding schema validation YAML file. The
        schema file must be present and should be named with the class
        name followed by the '_schema' suffix. If the validation fails,
        an exception is raised.

        Parameters
        ----------
        filename : `str`, optional
            Alternative file name with the calibration configuration
            file.

        Raises
        ------
        FileNotFoundError:
            If the calibration configuration file or the schema
            validation file doesn't exist.

        RuntimeError:
            If the validation of the calibration configuration file
            fails.

        """

        base_name = type(self).__name__.lower()

        data_path = (
            (get_data_path() / f"{base_name}.yaml").as_posix()
            if filename is None
            else filename
        )

        schema_path = (get_data_path() / f"{base_name}_schema.yaml").as_posix()

        if len(self.calibration_config) > 0:
            self.log.warning(
                "Calibration configuration already loaded."
                f"Overriding with data from {data_path}."
            )

        with open(data_path, "r") as f:
            self.calibration_config = yaml.safe_load(f)

        with open(schema_path, "r") as f:
            config_validator = salobj.DefaultingValidator(schema=yaml.safe_load(f))

        validation_errors = ""
        log_defaults = ""
        for item in self.calibration_config:
            config_original = dict(self.calibration_config[item])
            try:
                self.calibration_config[item] = config_validator.validate(
                    self.calibration_config[item]
                )
            except jsonschema.ValidationError as e:
                validation_errors += f"\t{item} failed validation: {e.message}.\n"
                self.log.exception(f"{item} failed validation.")
            config_with_defaults = self.calibration_config[item]
            defaulted_attributes = set(config_with_defaults) - set(config_original)
            log_defaults += f"\n{item}:\n" + "\n".join(
                f"    {attr}: {config_with_defaults[attr]}"
                for attr in defaulted_attributes
            )
        if validation_errors:
            raise RuntimeError(
                f"Failed schema validation:\n{validation_errors}Check logs for more information."
            )
        self.log.debug(f"\n=== Applied Default Values ===\n{log_defaults}\n")

    def get_calibration_configuration(self, name: str) -> dict[str, typing.Any]:
        """Returns the configuration attributes given a configuration
        name.

        Before running this method, you might want to call
        `load_calibration_config_file`. If the calibration configuration
        is not loaded, load it.

        Parameters
        ----------
        name : `str`
            Name of the configuration to return.

        Returns
        -------
        calibration_configuration : `dict`[`str`, `str` | `float` | `int`]
            The calibration configuration.

        Raises
        ------
        RuntimeError
            If the requested name is not in the available configuration.
        """

        if len(self.calibration_config) == 0:
            self.log.warning("Calibration configuration not loaded, loading.")
            self.load_calibration_config_file()

        if (
            calibration_configuration := self.calibration_config.get(name, None)
        ) is None:
            raise RuntimeError(
                f"Calibration {name} is not in the list of available calibrations. "
                f"Must be one of {', '.join(self.calibration_config.keys())}"
            )
        return calibration_configuration

    def get_configuration_options(self) -> list[str]:
        """Will read the yaml file and detail configurations available"""

        return list(self.calibration_config.keys())

    def assert_valid_configuration_option(self, name: str) -> None:
        """Assert that the configuration name is valid.

        Raises
        ------
        AssertionError:
            If input name in not in the list of calibration
            configuration options.
        """
        assert name in self.get_configuration_options()

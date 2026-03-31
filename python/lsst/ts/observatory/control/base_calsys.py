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
import numpy as np
import yaml
from lsst.ts import salobj
from lsst.ts.xml.enums.Electrometer import UnitToRead

from .exposure_log import ExposureLog
from .remote_group import RemoteGroup
from .utils import CalibrationType, get_data_path


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
        self.exposure_log = ExposureLog()

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
            Dict of all configuration data

        Returns
        -------
        exposure_list : `list`[ATCalsysExposure|MTCalsysExposure]
            List of exposure information, includes wavelength
            and camera, fiberspectrograph and electrometer exposure times.
        """
        # TO-DO: DM-44777
        raise NotImplementedError()

    # ---- Exposure log helpers ----

    async def register_exposure(self, exposure_id: str, wavelength: float) -> None:
        """Register a new pending exposure in the log.

        Parameters
        ----------
        exposure_id : `str`
            Unique identifier for this exposure.
        wavelength : `float`
            Wavelength of the exposure in nm.
        """
        await self.exposure_log.add_entry(
            exposure_id,
            {"wavelength": wavelength, "status": "pending"},
        )

    async def mark_exposure_success(
        self,
        exposure_id: str,
        metadata: dict[str, typing.Any] | None = None,
    ) -> None:
        """Mark an exposure as successful in the log.

        Parameters
        ----------
        exposure_id : `str`
            Unique identifier for the exposure.
        metadata : `dict`, optional
            Additional metadata to record alongside
            the success status.
        """
        update: dict[str, typing.Any] = {"status": "success"}
        if metadata:
            update.update(metadata)
        await self.exposure_log.update_entry(exposure_id, update)

    async def mark_exposure_failed(self, exposure_id: str, error: Exception) -> None:
        """Mark an exposure as failed in the log.

        Parameters
        ----------
        exposure_id : `str`
            Unique identifier for the exposure.
        error : `Exception`
            The exception that caused the failure.
        """
        await self.exposure_log.update_entry(
            exposure_id,
            {"status": "failed", "error_message": str(error)},
        )

    # ---- Template hooks for subclasses ----

    def make_exposure_id(self, index: int, exposure: typing.Any) -> str:
        """Build an exposure identifier.

        Subclasses may override to include additional
        information such as wavelength.

        Parameters
        ----------
        index : `int`
            Zero-based index of the exposure in the
            sequence.
        exposure : exposure dataclass
            The exposure dataclass instance (e.g.
            ATCalsysExposure or MTCalsysExposure).

        Returns
        -------
        exposure_id : `str`
            A unique string identifier for this exposure.
        """
        return f"exposure_{index + 1}"

    def compute_calibration_wavelengths(
        self,
        calibration_type: CalibrationType,
        config_data: dict[str, typing.Any],
    ) -> np.ndarray:
        """Compute the array of wavelengths for a
        calibration sequence.

        Subclasses may override for telescope-specific
        wavelength logic.

        .. note::
            ATCalsys uses ``wavelength_end + resolution``
            (inclusive), MTCalsys uses ``wavelength_end``
            (exclusive) in ``np.arange``. If the configs
            are homogenized (e.g. adding
            ``set_wavelength_range`` to ATCalsys schema),
            the MTCalsys override could replace this
            base implementation and serve both without
            subclass overrides.

        Parameters
        ----------
        calibration_type : `CalibrationType`
            The type of calibration being performed.
        config_data : `dict`
            The calibration configuration dictionary.

        Returns
        -------
        wavelengths : `np.ndarray`
            Array of calibration wavelengths in nm.
        """
        if calibration_type == CalibrationType.WhiteLight:
            return np.array([float(config_data["wavelength"])])

        wavelength = float(config_data["wavelength"])
        wavelength_width = float(config_data["wavelength_width"])
        wavelength_resolution = float(config_data["wavelength_resolution"])
        wavelength_start = wavelength - wavelength_width / 2.0
        wavelength_end = wavelength + wavelength_width / 2.0

        return np.arange(
            wavelength_start,
            wavelength_end + wavelength_resolution,
            wavelength_resolution,
        )

    @abc.abstractmethod
    async def execute_exposure_step(
        self,
        exposure: typing.Any,
        exposure_metadata: dict,
        config_data: dict[str, typing.Any],
        calibration_type: CalibrationType,
        sequence_name: str,
    ) -> dict:
        """Execute a single exposure step.

        This method contains all subclass-specific logic:
        hardware pre-steps (wavelength changes, LED
        adjustments, etc.) and the call to ``_take_data``.

        Parameters
        ----------
        exposure : exposure dataclass
            The exposure dataclass instance containing
            wavelength, camera exposure time, and
            ancillary instrument exposure times.
        exposure_metadata : `dict`
            Metadata to pass to the camera take_flats
            method (group_id, reason, program, etc.).
        config_data : `dict`
            The full calibration configuration dictionary.
        calibration_type : `CalibrationType`
            The type of calibration being performed.
        sequence_name : `str`
            Name of the calibration sequence.

        Returns
        -------
        step : `dict`
            Dictionary with step summary information to
            be appended to the calibration summary.
        """
        raise NotImplementedError()

    async def run_calibration_sequence(
        self, sequence_name: str, exposure_metadata: dict
    ) -> dict:
        """Perform full calibration sequence with exposure
        log tracking.

        Handles the shared loop, metadata, and exposure
        log bookkeeping. Subclass-specific hardware
        interaction is delegated to
        ``execute_exposure_step``.

        Parameters
        ----------
        sequence_name : `str`
            Name of the calibration sequence to execute.
        exposure_metadata : `dict`
            Metadata for exposures (group_id, reason,
            program, note, etc.).

        Returns
        -------
        calibration_summary : `dict`
            Dictionary with summary information about the
            sequence, including exposure log entries.
        """
        calibration_summary: dict = dict(
            steps=[],
            sequence_name=sequence_name,
        )

        config_data = self.get_calibration_configuration(sequence_name)
        calibration_type = getattr(CalibrationType, str(config_data["calib_type"]))

        calibration_wavelengths = self.compute_calibration_wavelengths(
            calibration_type, config_data
        )

        exposure_table = await self.calculate_optimized_exposure_times(
            wavelengths=calibration_wavelengths, config_data=config_data
        )

        await self.exposure_log.clear()

        for i, exposure in enumerate(exposure_table):
            self.log.debug(
                f"Performing {calibration_type.name} calibration with {exposure.wavelength=}."
            )

            exposure_id = self.make_exposure_id(i, exposure)
            await self.register_exposure(exposure_id, exposure.wavelength)

            _exposure_metadata = exposure_metadata.copy()
            if "group_id" in _exposure_metadata:
                _exposure_metadata["group_id"] += f"#{i+1}"

            try:
                step = await self.execute_exposure_step(
                    exposure=exposure,
                    exposure_metadata=_exposure_metadata,
                    config_data=config_data,
                    calibration_type=calibration_type,
                    sequence_name=sequence_name,
                )
                await self.mark_exposure_success(exposure_id)
            except Exception as e:
                self.log.exception(
                    f"Failed to take exposure at wavelength {exposure.wavelength}"
                )
                await self.mark_exposure_failed(exposure_id, e)
                step = dict(
                    wavelength=exposure.wavelength,
                    error=str(e),
                )

            calibration_summary["steps"].append(step)

        return calibration_summary

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

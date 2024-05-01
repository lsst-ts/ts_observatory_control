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

__all__ = ["ATCalsys", "ATCalsysUsages"]

import asyncio
import logging
import time
import typing

from lsst.ts import salobj

from ..base_calsys import BaseCalsys
from ..remote_group import Usages
from ..util import CalibrationType
from . import LATISS


class ATCalsysUsages(Usages):
    """ATCalsys usages definition.

    Notes
    -----

    Additional usages definition:

    * Setup: Enable ATWhitelight and perform warmup. Enable
             ATMonochromator, Electrometer, and FiberSpectrographs.
    * Configure: Adjust ATWhitelight and ATMonochromator for type of flat.
    * TakeFlat: Take flatfield image with LATISS, Electrometer and FiberSpec
    * DryTest: Disable CSCs and unit tests
    """

    Setup = 1 << 3
    Configure = 1 << 4
    TakeFlat = 1 << 5

    def __iter__(self) -> typing.Iterator[int]:
        return iter(
            [
                self.All,
                self.StateTransition,
                self.MonitorState,
                self.MonitorHeartBeat,
                self.Setup,
                self.Configure,
                self.TakeFlat,
                self.DryTest,
            ]
        )


class ATCalsys(BaseCalsys):
    """LSST Auxiliary Telescope Calibration System.

    ATCalsys encapsulates core functionality from the following CSCs:
    ATWhiteLight, ATMonochromoter, Fiberspectrograph, Electrometer.

    Parameters
    ----------
    domain : `lsst.ts.salobj.Domain`
        Domain for remotes. If `None` create a domain.
    log : `logging.Logger`
        Optional logging class to be used for logging operations. If `None`,
        creates a new logger. Useful to use in salobj.BaseScript and allow
        logging in the class use the script logging.
    intended_usage: `int`
        Optional integer that maps to a list of intended operations. This is
        used to limit the resources allocated by the class by gathering some
        knowledge about the usage intention. By default allocates all
        resources.
    latiss: LATISS
    """

    def __init__(
        self,
        domain: typing.Optional[salobj.Domain] = None,
        log: typing.Optional[logging.Logger] = None,
        intended_usage: typing.Optional[int] = None,
        latiss: typing.Optional[LATISS] = None,
    ) -> None:

        self.electrometer_index = 1
        self.fiberspectrograph_index = 1

        super().__init__(
            components=[
                "ATMonochromator",
                "ATWhiteLight",
                f"FiberSpectrograph:{self.fiberspectrograph_index}",
                f"Electrometer:{self.electrometer_index}",
            ],
            domain=domain,
            log=log,
            intended_usage=intended_usage,
        )

        self.latiss = latiss

        self.whitelight_startup_power = 1000

        self.chiller_temp_tolerance_relative = 0.2
        self.chiller_temperature = 20

        self.exptime_dict: dict[str, float] = dict(
            camera=0.0,
            electrometer=0.0,
            fiberspectrograph=0.0,
        )
        self.delay = 1

    async def change_wavelength(self, wavelength: float) -> None:
        """Change the ATMonochromator wavelength setting"""

        await self.rem.atmonochromator.cmd_changeWavelength.set_start(
            wavelength=wavelength, timeout=self.long_long_timeout
        )

    async def is_ready_for_flats(self) -> bool:
        """Add doctring"""
        # TODO (DM-44310): Implement method to check that the
        # system is ready for flats.
        return True

    async def setup_calsys(self, calib_type: typing.Optional[CalibrationType]) -> None:
        """Turn on the Chiller and the ATWhiteLight and wait for the
        warmup to complete. This is independent of Calibration Type.
        """
        await self.start_chiller()
        await self.wait_for_chiller_temp_within_tolerance()
        await self.switch_lamp_on()
        await self.wait_for_lamp_to_warm_up()

    async def configure_flat(self, config_name: str) -> None:
        """Configure the ATMonochromator according to the flat parameters

        Parameters
        ----------
        config_name : `str`
            name of the type of configuration you will run, which is saved
            in the configuration.yaml files

        Raises
        ------
        RuntimeError:

        """
        config_data = self.get_config(config_name)

        await self.setup_latiss(config_data)

        await self.rem.atmonochromator.cmd_updateMonochromatorSetup.set_start(
            wavelength=config_data["wavelength"],
            gratingType=config_data["monochromator_grating"],
            fontExitSlitWidth=config_data["exit_slit"],
            fontEntranceSlitWidth=config_data["entrance_slit"],
            timeout=self.long_timeout,
        )

    async def setup_latiss(self, config_data: dict) -> None:
        """Seteup Latiss"""

        assert config_data["use_camera"]
        assert self.latiss is not None
        await self.latiss.setup_instrument()

    async def electrometer_scan(self, duration: float) -> salobj.type_hints.BaseMsgType:
        """Perform an electrometer scan for the specified duration.

        Parameters
        ----------
        duration : `float`
            Total duration of scan.

        Returns
        -------
        RunTimeError

        """

        self.rem.electrometer_1.evt_largeFileObjectAvailable.flush()

        try:
            await self.electrometer.cmd_startScanDt.set_start(
                scanDuration=duration, timeout=duration + self.long_timeout
            )
        except salobj.AckTimeoutError:
            self.log.exception("Timed out waiting for the command ack. Continuing.")

        # Make sure that a new lfo was created
        lfo = await self.electrometer.evt_largeFileObjectAvailable.next(
            timeout=self.long_timeout, flush=False
        )
        return lfo

    async def take_fiber_spectrum(
        self,
        delay: float,
        integration_time: float,
    ) -> salobj.type_hints.BaseMsgType:
        """Wait, then start an acquisition with the fiber spectrograph.

        By default, this method will wait for `delay` seconds then start
        an acquisition with the fiber spectrograph. Optionally the user may
        provide a coroutine that will be awaited before the delay starts.

        Parameters
        ----------
        delay : `float`
            Seconds to wait before starting fiber spectrograph acquisition.
        integration_time : `float`
            Integration time for the fiber spectrum (seconds).

        Returns
        -------
        RuntimeError : If exposure or return of lfo doesn't occur.
        """
        self.fiberspectrograph.evt_largeFileObjectAvailable.flush()

        try:
            await self.fiberspectrograph.cmd_expose.set_start(
                integrationTime=integration_time,
                timeout=integration_time + self.long_timeout,
            )
        except salobj.AckTimeoutError:
            self.log.exception("Timed out waiting for the command ack. Continuing.")

        lfo = await self.fiberspectrograph.evt_largeFileObjectAvailable.next(
            timeout=self.long_timeout, flush=False
        )
        return lfo

    async def perform_flat(self, exptime_dict: dict[str, float]) -> None:
        # check dictionary
        # Get the image number
        # Somehow need to make sure camera is setup
        assert self.latiss is not None
        asyncio.gather(
            self.electrometer_scan(duration=exptime_dict["electrometer"]),
            self.take_fiber_spectrum(
                delay=self.delay, integration_time=exptime_dict["fiberspectrograph"]
            ),
            self.latiss.take_flats(exptime=exptime_dict["camera"], nflats=1),
        )

    async def get_optimized_exposure_times(
        self,
        config_name: str,
        wavelength: typing.Union[float, None],
    ) -> dict[str, float]:
        """Need exposure time for camera, electrometer and fiberspectrograph

        TO-DO (DM-44361): implement this correctly
        """
        return dict(
            camera=10.0,
            electrometer=10.0,
            fiberspectrograph=10.0,
        )

    async def start_chiller(self) -> None:
        """Starts chiller to run at self.chiller_temperature"""

        await self.rem.atwhitelight.cmd_setChillerTemperature.set_start(
            temperature=self.chiller_temperature, timeout=self.long_timeout
        )
        await self.rem.atwhitelight.cmd_startChiller.set_start(
            timeout=self.long_timeout
        )

    async def switch_lamp_on(self) -> None:
        """Switches on the white light source with an output
        power of self.whitelight_power W
        """
        self.rem.atwhitelight.evt_lampState.flush()

        await self.rem.atwhitelight.cmd_turnLampOn.set_start(
            power=self.whitelight_startup_power, timeout=self.long_long_timeout * 8
        )

    async def wait_for_chiller_temp_within_tolerance(self) -> None:
        """Checks if chiller reaches set self.chiller_temperature within
        set self.chiller_temp_tolerance_relative in
        less than self.timeout_chiller_cool_down s.

        Raises
        ------
        TimeOutError:
            If the chiller doesn't reach self.chiller_temperature
            within tolerance in self.timeout_chiller_cool_down s.

        Note
        ----
        Taken from power_on_atcalsys.py
        PAF: I think this can be improved.
        """
        start_chill_time = time.time()
        while time.time() - start_chill_time < self.long_long_timeout * 8:
            chiller_temps = await self.rem.atwhitelight.tel_chillerTemperatures.next(
                flush=True, timeout=self.long_timeout
            )
            tel_chiller_temp = chiller_temps.supplyTemperature
            self.log.debug(
                f"Chiller supply temperature: {tel_chiller_temp:0.1f} deg "
                f"[set:{chiller_temps.setTemperature} deg]."
            )
            if (
                abs(chiller_temps.setTemperature - tel_chiller_temp)
                / chiller_temps.setTemperature
                <= self.chiller_temp_tolerance_relative
            ):
                chill_time = time.time() - start_chill_time
                self.log.info(
                    f"Chiller reached target temperature, {tel_chiller_temp:0.1f} deg "
                    f"within tolerance, in {chill_time:0.1f} s."
                )
                break
        else:
            raise TimeoutError(
                f"Timeout waiting after {self.long_long_timeout * 8} s "
                f"for the chiller to chill to {chiller_temps.setTemperature} deg. "
                f"Stayed at {tel_chiller_temp:0.1f} deg."
            )

    async def wait_for_lamp_to_warm_up(self) -> None:
        """Confirms the white light source has warmed up and is on.

        Raises:
        ------
        TimeOutError:
            If the lamp fails to turn on after self.timeout_lamp_warm_up

        Note
        ----
        Taken from power_on_atcalsys.py
        PAF: I think this can be improved.
        """
        lamp_state = await self.rem.atwhitelight.evt_lampState.aget(
            timeout=self.long_long_timeout, flush=True
        )
        self.log.info(
            f"Lamp state: {self.rem.atwhitelight.LampBasicState(lamp_state.basicState)!r}."
        )

        while lamp_state.basicState != self.rem.atwhitelight.LampBasicState.ON:
            try:
                lamp_state = await self.rem.atwhitelight.evt_lampState.next(
                    flush=False, timeout=self.long_long_timeout * 8
                )
                self.log.info(
                    f"Lamp state: {self.rem.atwhitelight.LampBasicState(lamp_state.basicState)!r}."
                )
            except asyncio.TimeoutError:
                raise RuntimeError(
                    f"White Light Lamp failed to turn on after {self.long_long_timeout * 8} s."
                )

    @property
    def electrometer(self) -> salobj.Remote:
        return getattr(self.rem, f"electrometer_{self.electrometer_index}")

    @property
    def fiberspectrograph(self) -> salobj.Remote:
        return getattr(self.rem, f"fiberspectrograph_{self.fiberspectrograph_index}")

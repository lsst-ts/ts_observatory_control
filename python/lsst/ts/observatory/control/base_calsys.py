from abc import ABCMeta, abstractmethod
from .remote_group import RemoteGroup
from typing import Iterable, Optional, Tuple, List, Union, Callable
from functools import reduce
from operator import mul
from lsst.ts import salobj
import logging
import asyncio

class CalsysThroughputCalculationMixin:
    """mixin class to allow pluggable source for calculation of throughputs"""

    @abstractmethod
    @property
    def detector_throughput(self, wavelen: float) -> float:
        """the throughput value will return (in appropriate units TBD) the detector throughput of the particular
        calibration system specified in the class for which this mixin class is specified as a base.

        Parameters
        ----------

        wavelen: float - wavelength of the calibration to be performed in nm


        Returns
        -------

        A value (units TBD, likely electrons per pixel per second), which can be used to
        either determine how long to integrate the sensor for to achieve a desired level of calibration
        field in electrons, or determine how many electrons will be obtained for a specific integration time

        """

    @abstractmethod
    @property
    def spectrograph_throughput(self, wavelen: float, calsys_power: float) -> float:
        """ the throughput expected of the fiber spectrograph of the calibration system.
        To aid calculations  of total throughput
        """

    @abstractmethod
    @property
    def radiometer_throughput(self, wavelen: float, calsys_power: float) -> float:
        """ same as spectrograph_throughput but for radiometer """

    def end_to_end_throughput(self, wavelen: float, calsys_power: float) -> float:
        #intended to be SOMETHING LIKE
        return reduce(lambda t, f: t*f(wavelen, calsys_power),
                      [self.detector_throughput, self.spectrograph_throughput,
                       self.radiometer_throughput])


class ButlerCalsysThroughput(CalsysThroughpu_etCalculationMixin):
    """Mixin class for calculating throughput of the calibration system backed by measurements stored
    in  a DM butler"""


class HardcodeCalsysThroughput(CalsysThroughputCalculationMixin):
    """Mixin class for calculating throughput of the calibration system with hardcoded values,
    i.e. which can be directly imported from python code """



class BaseCalsys(RemoteGroup, metaclass=ABCMeta):
    """Base class for calibration systems"""


    def __init__(self,
                 components: Iterable[str],
                 domain: Optional[salobj.domain] = None,
                 cmd_timeout: Optional[int] = 10,
                 log: Optional[logging.Logger] = None):

        super().__init__(components, domain, log=log,
                         intended_usage=salobj.BaseUsages.StateTransition,
                         concurrent_operation = False) #QUESTION: is this last one true????

        self._cmd_timeout = cmd_timeout


    def _sal_cmd_helper(self, salobj, cmdname: str, run_immediate: bool= True, **setargs):
        if isinstance(salobj, str):
            salobj = getattr(self, salobj)
        cmdfun = getattr(salobj, f"cmd_{cmdname}")
        cmdfun.set(**setargs)
        pkgtask = lambda : cmdfun.start(timeout = self._cmd_timeout)
        if run_immediate:
            return asyncio.createtask(pkgtask())
        return pkgtask()

    def _lfa_event_helper(self, salobj,  run_immediate: bool=True, **evtargs):
        if isinstance(salobj, str):
            salobj = getattr(self, salobj)
        cmdfun = getattr(salobj, "evt_largeFileObjectAvailable")
        pkgtask = lambda: cmdfun.start(timeout  = self._cmd_timeout)
        if run_immediate:
            return asyncio.create_task(pkgtask())
        return pkgtask()


    def detector_exposure_time_for_nelectrons(self, wavelen: float, nelec: float) -> float:
        """ using the appropriate mixin for obtaining calibration data on throughput,
        will calculate and return the exposure time needed to obtain a flat field calibration of n
        electrons at the imager specified in the class definition

        Parameters
        ----------

        wavelen: float - wavelength (in nm??) of the intended calibration
        nelec: float - number of electrons (probably measured in ke-??) desired in calibration field

        Returns
        -------

        exposure time: float - time  (in seconds??) needed for the imager to obtain desired calibration field

        """
        
        #must have a way to access the calibration data
        assert issubclass(type(self), CalsysThroughputCalculationMixin)


    def spectrograph_exposure_time_for_nelectrons(self, nelec: float) -> float:
        pass

    def pd_exposure_time_for_nelectrons(self, nelec: float) -> float:
        pass

    @abstractmethod
    async def turn_on_light(self) -> None:
        """awaitable command which turns on the calibration light, having 
        already set up the appropriate wavelength and (if applicable) time delays for stabilization etc

        """

    @abstractmethod
    async def turn_off_light(self) -> None:
        """ awaitable which turns off the calibration light"""


    @abstractmethod
    async def setup_for_wavelength(self, wavelen: float, **extra_params) -> None:
        """ awaitable which sets up the various remote components of a calibration system
        to perform a calibration at a particular wavelength.

        Intended to be a 'high level' setup function, such that user doesn't have to worry about e.g. setting up integration times for spectrographs etc

        Parameters
        ----------

        wavelen: float - desired wavelength (in nm)

        extra_params: to handle things which are specific to individual calibration systems
        (e.g that the auxtel can also adjust spectral bandwidth)

        """
        pass

    @abstractmethod
    async def take_calibration_instr_exposures(self) -> None:
        """ awaitable which starts the exposures for the calibration instruments (i.e the spectrographs, electrometers etc) according to the setup. It does not take images with the instrument under test, it is intended that script components which use this class do that themselves"""
        pass

        
    @property
    @abstractmethod
    def wavelen(self) -> float:
        """ returns the currently configured wavelength"""

    @abstractmethod
    async def take_data(self):
        """This will fire off all async tasks to take calibration data in sequence, and return locations and metadata about the files supplied etc"""

        
    

    

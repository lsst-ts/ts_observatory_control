from typing import List, Optional, NamedTuple
from ..base_calsys import BaseCalsys, HardcodeCalsysThroughput
from lsst.ts import salobj
from lsst.ts.idl.enums import ATMonochromator
import asyncio

class ATSpectrographSlits(NamedTuple):
    FRONTENTRANCE: float
    FRONTEXIT: float


class ATCalsys(BaseCalsys, HardcodeCalsysThroughput):
    """ class which specifically handles the calibration system for auxtel"""
    _AT_SAL_COMPONENTS: List[str] = ["ATMonochromator", "FiberSpectrograph", "Electrometer"]
    CHANGE_GRATING_TIME: int = 60

    #these below numbers should be able to be loaded from a (fairly static) config!
    GRATING_CHANGEOVER_WL: float = 532.0 #WARNING: PLACEHOLDER VALUE!!!
    GRATING_CHANGEOVER_BW: float = 55.0 #WARNING! PLACEHOLDER VALUE!!!


    def __init__(self, **kwargs:)
        super().__init__(self._AT_SAL_COMPONENTS, **kwargs)
        self._specsposure_time: Optional[float] = None
        self._elecsposure_time: Optional[float] = None



    async def setup_for_wavelength(self, wavelen: float, nelec: float, spectral_res: float) -> None:
        # to be copied basically from existing SAL script mechanisms

        grating = self.calculate_grating_type(wavelen, spectral_res)
        slit_widths = self.calculate_slit_widths(spectral_res, grating)

        self.log.debug(f"setting up monochromtor with wavlength {wavelen} nm and spectral resolution {spectral_res}")
        self.log.debug(f"calculated slit widthsare {slit_widths}")
        self.log.debug(f"calculated grating is {grating}")
        
        monoch_fut = self._sal_cmd_helper("monochromator", "updateMonochromatorSetup",
                                   gratingType = grating,
                                   frontExitSlitWidth = slit_widths.FRONTEXIT,
                                   frontEntranceSlitWdth = slit_widths.FRONTENTRACE,
                                   wavelength = wavelen)

        elect_fut = self._sal_cmd_helper("electrometer", "performZeroCalib")
        elect_fut2 = self._sal_cmd_helper("electrometer", "setDigitalFilter",
                                          activateFilter=False,
                                          activateAvgFilter=False,
                                          activateMedFilter=False)

        
                                         

        #TODO: electrometer
        #TODO: fibre spectrograph

        asyncio.wait([monoch_fut, elect_fut, elect_fut2], return_when=asyncio.ALL_COMPLETED)
        self.log.debug("all SAL setup commands returned")

        specsposure_time = self.spectrograph_exposure_time_for_nelectrons(nelec)

        
        return


    def calculate_slit_width(self, spectral_res: float, grating) -> ATSpectrographSlits:
        #NOTE: this will either need to be derived by doing calculations on the Grating equation, or by loading in calibration data (which I couldn't find yet!)
        pass

    def calculate_grating_type(self, wavelen: float, spectral_res: float):
        #TODO: placeholder logic, in particular the exact numbers will be WRONG!
        #likely something like the below
        if spectral_res > self.GRATING_CHANGEOVER_BW:
            return ATMonochromator.Grating.MIRROR
        elif wavelen < self.GRATING_CHANGEOVER_WL:
            return ATMonochromator.Grating.BLUE
        return ATMonochromator.Grating.RED    
            

    async def _setup_spectrograph(self, int_time: float) -> None:
        pass

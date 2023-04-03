from typing import List

from ..base_calsys import BaseCalsys

class MTCalsys(BaseCalsys):
    """ class which specifically handles the calibration system for maintel """
    _MT_SAL_COMPONENTS: List[str] = [] #TODO, what do we actually need here???!

    def __init__(self,
                 domain: Optional[salobj.Domain] = None):
        super().__init__(self._MT_SAL_COMPONENTS, domain)
    
    async def turn_on_light(self) -> None: ...

    async def turn_off_light(self) -> None: ...

    async def setup_for_wavelength(self, wavelen: float) -> None: ... 

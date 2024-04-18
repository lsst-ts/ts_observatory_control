import typing
import unittest
import logging
import pytest
from lsst.ts import salobj
from lsst.ts.observatory.control.utils import RemoteGroupTestCase
from lsst.ts.observatory.control.mock.latiss_mock import LATISSMock
from lsst.ts.observatory.control.base_calsys import HardcodeCalsysThroughput


class TestBaseCalsysLogic(unittest.TestCase):
    """ Test cases for the abstract calculation logic and shared functionality
    of BaseCalsys """

    def test_load_calibration(self):
        calfile = HardcodeCalsysThroughput.load_calibration_csv("hamamatsu_responsivity.csv")

        self.assertIn("wavelength", calfile)
        self.assertIn("responsivity", calfile)

    def test_interpolate(self):
        obj = HardcodeCalsysThroughput()
        throughput_low = obj.radiometer_throughput(875.0)


class TestATCalsys(RemoteGroupTestCase, unittest.IsolatedAsyncioTestCase):
    """Test cases for the ATCalsys concrete implementation """

    @classmethod
    def setUpClass(cls) -> None:
        """set up mocks and such that we need for all the tests"""
        
        
    
    async def basic_make_group(
            self, usage: typing.Optional[int] = None) -> typing.Iterable[typing.Union[RemoteGroup, salobj.BaseCsc]]:
        pass

    

    


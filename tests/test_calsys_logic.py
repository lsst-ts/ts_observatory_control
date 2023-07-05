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
        


class TestATCalsys(unittest.TestCase): ...
class TestMTCalsys(unittest.TestCase): ...


"""Useful constants for running auxTel"""
from lsst.geom import PointD

plate_scale = 0.1045  # arcsec/pixel

boresight = PointD(2036.5, 2000.5)  # boreSight on detector (pixels)
sweet_spots = {  # the sweet spots for the gratings (pixels)
    "ronchi90lpmm": PointD(1780, 1800),
    "empty_1": PointD(1780, 1800),
}

# -*- coding: utf-8 -*-
"""Initialize pyrga package."""

import logging
from logging import NullHandler
from pyrga.driver import RGAClient, RGAException

__version__ = '0.0.3'
logging.getLogger(__name__).addHandler(NullHandler())
logging.basicConfig(level=logging.INFO)

"""cjdata package - local stock data toolkit."""
from __future__ import annotations

import warnings

# Suppress xtquant's pkg_resources deprecation warning before any imports
warnings.filterwarnings("ignore", message=".*pkg_resources is deprecated.*", category=UserWarning)

from .builder import CJDataBuilder
from .local_data import LocalData, TrendType, CodeFormat

__all__ = [
    "CJDataBuilder",
    "LocalData",
    "TrendType",
    "CodeFormat",
]

"""DIF — Developer Identity Fingerprint module.

Exports the primary public API surface for the DIF scoring system.
"""

from openclaw.analysis.dif.config import DIFConfig
from openclaw.analysis.dif.engine import DIFResult, compute_dif
from openclaw.analysis.dif.components import ComponentResult

__all__ = ["DIFConfig", "compute_dif", "DIFResult", "ComponentResult"]

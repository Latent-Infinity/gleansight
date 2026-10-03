"""Serialize in-process registry calls around Piccolo's shared table bindings."""

from threading import RLock
from typing import Final

REGISTRY_EXECUTION_LOCK: Final = RLock()

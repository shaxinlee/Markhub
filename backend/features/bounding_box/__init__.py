"""Bounding-box annotation feature module.

This module provides object detection annotation capabilities for images.
"""

from .server import main, register

__all__ = ["main", "register"]

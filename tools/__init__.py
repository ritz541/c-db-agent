"""
Tools Package

Auto-discovers all tools in this directory.
Just drop a new tool file here, and it'll be automatically loaded.
"""

from .registry import registry

__all__ = ["registry"]

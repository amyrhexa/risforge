"""Exception hierarchy for risforge."""

from __future__ import annotations


class RisForgeError(Exception):
    """Base class for risforge-specific errors."""


class RisParsingError(RisForgeError, ValueError):
    """Raised when a RIS file cannot be decoded or read as text.

    Inherits from ValueError so existing handlers in CLI, pipeline,
    and GUI worker continue to catch it.
    """

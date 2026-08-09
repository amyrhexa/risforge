"""Exception types for risforge.

We deliberately keep this hierarchy small. Most failure modes in this
package are already well described by the standard library's own
exceptions (``FileNotFoundError``, ``ValueError``, etc.), and the
original scripts caught those precisely rather than reaching for
generic ``Exception``. We keep that pattern. ``RisForgeError`` exists
only as a common base for the handful of errors that are specific to
this package's domain logic, so library users can catch
``RisForgeError`` if they want a single net for "something in risforge
itself went wrong" without having to also catch unrelated stdlib
errors they may want to handle differently.
"""

from __future__ import annotations


class RisForgeError(Exception):
    """Base class for errors raised directly by risforge's own logic."""


class RisParsingError(RisForgeError):
    """Raised when a RIS file cannot be parsed into any usable records."""

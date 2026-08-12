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


class RisParsingError(RisForgeError, ValueError):
    """Raised when a RIS file's content can't be decoded/read at all.

    Deliberately inherits from ``ValueError`` too (like
    ``json.JSONDecodeError`` does in the standard library) so every
    existing ``except (OSError, ValueError, RuntimeError)`` clause
    throughout this codebase (CLI, pipeline, GUI worker) already
    catches it correctly, with no call site changes required. Catch
    ``RisParsingError`` specifically, or ``RisForgeError`` generally,
    for finer-grained handling.

    This is for whole-file failures only (e.g. the file's bytes can't
    be decoded as text) -- a malformed *individual record* within an
    otherwise-readable file is not an error at this level; see
    :func:`risforge.cleaning.parse_ris_records`, which tolerates and
    reports those per-block instead of raising.
    """

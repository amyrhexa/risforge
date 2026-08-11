"""risforge_gui: a desktop GUI for the risforge package.

This is a thin PySide6 presentation layer over the ``risforge`` core
library -- it contains no merging, cleaning, deduplication, or
enrichment logic of its own. Every operation it performs is a direct
call into the public ``risforge`` API (:func:`risforge.risforge`,
:func:`risforge.merge_ris_files`, :func:`risforge.clean_ris_file`,
:class:`risforge.RisEnricher`).

Deliberately not imported here: PySide6. Importing this top-level
package should never require the GUI extra to be installed; only
:mod:`risforge_gui.app` (the entry point) and the widget modules it
pulls in do that. This keeps ``import risforge_gui`` itself cheap and
side-effect-free, consistent with how ``risforge`` (the core package)
never imports GUI dependencies.

Install with the GUI extra and launch via the console entry point::

    pip install "risforge[gui]"
    risforge-gui
"""

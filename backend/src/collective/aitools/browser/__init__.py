"""Classic-UI browser package for collective.aitools."""

from importlib.util import find_spec


_mosaic_installed = None


def mosaic_installed() -> bool:
    """Return ``True`` when ``plone.app.mosaic`` is importable.

    Mosaic is not part of Plone core, so the Mosaic-specific behaviour of the
    editor tools (the "Help me write" bar on inline rich-text tiles and the
    "Get image details" button filling an image tile's own fields) is only
    offered when Mosaic is present. The result is cached: whether a package is
    importable does not change over a process's lifetime.
    """
    global _mosaic_installed
    if _mosaic_installed is None:
        _mosaic_installed = find_spec("plone.app.mosaic") is not None
    return _mosaic_installed

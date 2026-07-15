"""Shared base class and lookup helpers for the AI tools."""

from collective.aisettings.interfaces import IAIService
from collective.aitools import logger
from collective.aitools.interfaces import IAITool
from collective.aitools.interfaces import IAIToolsSettings
from plone.registry.interfaces import IRegistry
from zope.component import getUtilitiesFor
from zope.component import getUtility
from zope.component import queryUtility
from zope.interface import implementer


def get_tools_settings():
    """Return the :class:`IAIToolsSettings` registry proxy.

    Uses ``check=False`` so a missing record (e.g. before an upgrade) falls
    back to the field default instead of raising.
    """
    registry = getUtility(IRegistry)
    return registry.forInterface(IAIToolsSettings, check=False)


def get_tools():
    """Return ``(name, tool)`` pairs for every registered ``IAITool``."""
    return list(getUtilitiesFor(IAITool))


def get_tool(name):
    """Return the named ``IAITool`` utility, or ``None`` if not registered."""
    return queryUtility(IAITool, name=name)


@implementer(IAITool)
class AITool:
    """Base class for AI tools.

    Subclasses set :attr:`name` (matching the utility registration name),
    :attr:`title` and :attr:`description`, and implement :meth:`run`. The
    enable flag and model override are read from the control panel using the
    ``<name>_enabled`` / ``<name>_model`` registry records.
    """

    name = ""
    title = ""
    description = ""

    @property
    def service(self):
        """The ``collective.aisettings`` AI service utility."""
        return getUtility(IAIService)

    @property
    def settings(self):
        return get_tools_settings()

    def is_enabled(self):
        return bool(getattr(self.settings, f"{self.name}_enabled", False))

    def get_model(self):
        model = (getattr(self.settings, f"{self.name}_model", "") or "").strip()
        return model or None

    def available_for(self, context):
        return self.is_enabled()

    def _skip_if_disabled(self):
        """Return ``True`` (and log) when the tool is disabled."""
        if not self.is_enabled():
            logger.info("AI tool %r is disabled; call skipped.", self.name)
            return True
        return False

    def run(self, context, **kwargs):  # pragma: no cover - abstract
        raise NotImplementedError

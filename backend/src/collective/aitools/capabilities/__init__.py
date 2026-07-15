"""Capabilities the chat "Assistant" may call (tool/function calling).

See :mod:`collective.aitools.capabilities.base` for the shared base class and
the helpers used to enumerate and build the per-request capability manifest.
"""

from collective.aitools.capabilities.base import AICapability
from collective.aitools.capabilities.base import get_capabilities
from collective.aitools.capabilities.base import get_capability
from collective.aitools.capabilities.base import manifest_for


__all__ = [
    "AICapability",
    "get_capabilities",
    "get_capability",
    "manifest_for",
]

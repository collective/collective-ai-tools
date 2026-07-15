"""Base class and lookup helpers for the assistant's capabilities.

A *capability* is a function the chat assistant may call (OpenAI-style tool /
function calling). Each is registered as a named ``IAIAssistantCapability``
utility, mirroring how the editor tools are registered as ``IAITool``
utilities. See :class:`collective.aitools.interfaces.IAIAssistantCapability`.
"""

from AccessControl import getSecurityManager
from collective.aitools.interfaces import IAIAssistantCapability
from typing import ClassVar
from zope.component import getUtilitiesFor
from zope.component import queryUtility
from zope.interface import implementer


def get_capabilities():
    """Return ``(name, capability)`` pairs for every registered capability."""
    return list(getUtilitiesFor(IAIAssistantCapability))


def get_capability(name):
    """Return the named capability utility, or ``None`` if not registered."""
    return queryUtility(IAIAssistantCapability, name=name)


def manifest_for(context):
    """Return the OpenAI-style tool schemas for every capability the current
    user is allowed to use against ``context``.

    This is the list handed to the model. It is a filter, not the security
    boundary: each capability re-checks its permission in
    :meth:`AICapability.run` when actually invoked.
    """
    schemas = []
    for _name, capability in get_capabilities():
        if capability.allowed_for(context):
            schemas.append(capability.tool_schema())
    return schemas


@implementer(IAIAssistantCapability)
class AICapability:
    """Base class for assistant capabilities.

    Subclasses set :attr:`name`, :attr:`description`, :attr:`parameters` (a JSON
    Schema for the call arguments) and :attr:`permission`, and implement
    :meth:`run`. Read-only capabilities are safe to run inside the agent loop;
    a capability that writes must instead return a *proposal* for the user to
    confirm through a separate endpoint (it must not mutate content in
    :meth:`run`).
    """

    name = ""
    description = ""
    #: JSON Schema for the arguments. Default: a no-argument object.
    parameters: ClassVar[dict] = {"type": "object", "properties": {}}
    #: Zope permission required on the context. ``zope2.View`` means "any
    #: authenticated (or anonymous) user who can see the context".
    permission = "zope2.View"

    def allowed_for(self, context):
        return bool(getSecurityManager().checkPermission(self.permission, context))

    def tool_schema(self):
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def run(self, context, request, **kwargs):  # pragma: no cover - abstract
        raise NotImplementedError

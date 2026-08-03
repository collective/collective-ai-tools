"""Base class and lookup helpers for the assistant's capabilities.

A *capability* is a function the chat assistant may call (OpenAI-style tool /
function calling). Each is registered as a named ``IAIAssistantCapability``
utility, mirroring how the editor tools are registered as ``IAITool``
utilities. See :class:`collective.aitools.interfaces.IAIAssistantCapability`.
"""

from AccessControl import getSecurityManager
from AccessControl.Permission import getPermissions
from collective.aitools import logger
from collective.aitools.interfaces import IAIAssistantCapability
from Products.CMFCore.permissions import View
from typing import ClassVar
from zope.component import getUtilitiesFor
from zope.component import queryUtility
from zope.interface import implementer


def _check_permission(permission, context, capability=""):
    """Check ``permission`` on ``context`` for the current user.

    ``getSecurityManager().checkPermission`` takes a Zope permission *title* —
    ``"View"``, ``"Modify portal content"`` — not the dotted ZCML id used in
    ``configure.zcml`` (``zope2.View``, ``cmf.ModifyPortalContent``). Handing it
    an unregistered name is not an error: it falls back to the default
    ``('Manager',)`` roles, so the check quietly answers "no" for every ordinary
    editor. Warn loudly rather than silently hiding a capability.
    """
    if permission not in {entry[0] for entry in getPermissions()}:
        logger.warning(
            "capability %r declares unknown permission %r; checkPermission only "
            "understands permission titles (e.g. 'View', 'Modify portal "
            "content'), so this will be treated as Manager-only.",
            capability or "<unnamed>",
            permission,
        )
    return bool(getSecurityManager().checkPermission(permission, context))


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
    #: Zope permission required on the context, as a permission *title* (see
    #: :func:`_check_permission`). ``View`` means "any user, authenticated or
    #: not, who can see the context".
    permission = View

    def allowed_for(self, context):
        return _check_permission(self.permission, context, capability=self.name)

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

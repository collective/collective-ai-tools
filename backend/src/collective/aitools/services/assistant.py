"""REST endpoints backing the classic-UI chat assistant.

``POST <context>/@aitools-assistant`` with body ``{"messages": [...]}`` (the
OpenAI-style conversation history) drives the ``assistant`` ``IAITool`` and
returns ``{"reply": "...", "steps": [...]}``.

``POST <context>/@aitools-assistant-apply`` is the (stubbed) explicit,
user-confirmed write endpoint: the assistant only ever *proposes* content
changes; the actual mutation happens here, behind the edit permission, when the
user confirms. Not implemented yet — see the first editor slice.
"""

from collective.aitools import logger
from collective.aitools.capabilities.propose_draft import validate_draft
from collective.aitools.tools import get_tool
from plone import api
from plone.app.textfield.interfaces import IRichText
from plone.app.textfield.value import RichTextValue
from plone.dexterity.utils import iterSchemata
from plone.restapi.deserializer import json_body
from plone.restapi.services import Service
from zope.schema import getFields


#: Cap on how many turns of history we accept from the client.
MAX_MESSAGES = 40
#: Roles we accept in the incoming history.
ALLOWED_ROLES = {"user", "assistant"}


def _has_richtext_field(obj, name):
    """Return ``True`` when ``obj``'s schema (type + behaviors) has a RichText
    field named ``name`` — so we only set a body on types that have one."""
    for schema in iterSchemata(obj):
        field = getFields(schema).get(name)
        if field is not None and IRichText.providedBy(field):
            return True
    return False


def _sanitize_messages(raw):
    """Return a clean ``[{"role", "content"}]`` list from client input.

    Drops anything that is not a ``user``/``assistant`` turn with string
    content, and clamps the history length. The system prompt and any tool
    turns are added server-side by the tool, never taken from the client.
    """
    messages = []
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = item.get("content")
        if role in ALLOWED_ROLES and isinstance(content, str) and content.strip():
            messages.append({"role": role, "content": content})
    return messages[-MAX_MESSAGES:]


class Assistant(Service):
    """``POST @aitools-assistant`` — run one assistant turn over the history."""

    def reply(self):
        data = json_body(self.request)
        messages = _sanitize_messages(data.get("messages"))

        if not messages:
            self.request.response.setStatus(400)
            return {
                "error": {
                    "type": "BadRequest",
                    "message": "messages is required (a non-empty conversation).",
                }
            }

        tool = get_tool("assistant")
        if tool is None or not tool.is_enabled():
            self.request.response.setStatus(403)
            return {
                "error": {
                    "type": "Forbidden",
                    "message": "The 'Assistant' tool is not enabled.",
                }
            }

        try:
            result = tool.run(self.context, messages=messages, request=self.request)
        except Exception as exc:
            logger.exception("assistant endpoint failed")
            self.request.response.setStatus(500)
            return {"error": {"type": "InternalServerError", "message": str(exc)}}

        if not result or not result.get("reply"):
            self.request.response.setStatus(502)
            return {
                "error": {
                    "type": "BadGateway",
                    "message": (
                        "No response from the AI service. Check that a "
                        "tool-calling-capable model is configured in AI "
                        "Settings."
                    ),
                }
            }

        return {
            "reply": result["reply"],
            "steps": result.get("steps", []),
            "proposals": result.get("proposals", []),
        }


class AssistantApply(Service):
    """``POST @aitools-assistant-apply`` — apply a user-confirmed proposal.

    The assistant only ever *proposes* write actions; this endpoint performs
    the mutation once the user confirms. It re-validates everything
    server-side (the proposal from the client is untrusted), so tampering with
    it can never let a user create something they could not create anyway.

    Body: ``{"proposal": {"type": "create_draft", ...}}``.
    """

    def _create_draft(self, proposal):
        """Create a private draft from a ``create_draft`` proposal.

        Returns ``(payload, status)``: a success dict + ``None``, or an error
        dict + an HTTP status to set.
        """
        container, resolved_type, error = validate_draft(
            proposal.get("container_path"), proposal.get("portal_type")
        )
        if error:
            return {"error": {"type": "BadRequest", "message": error}}, 400

        title = (proposal.get("title") or "").strip()
        if not title:
            return (
                {"error": {"type": "BadRequest", "message": "title is required"}},
                400,
            )

        obj = api.content.create(
            container=container,
            type=resolved_type,
            title=title,
            description=(proposal.get("description") or "").strip(),
            safe_id=True,
        )
        body = (proposal.get("body") or "").strip()
        if body and _has_richtext_field(obj, "text"):
            obj.text = RichTextValue(body, "text/html", "text/x-html-safe")
            obj.reindexObject()

        return {
            "created": True,
            "url": obj.absolute_url(),
            "title": obj.Title(),
        }, None

    def reply(self):
        data = json_body(self.request)
        proposal = data.get("proposal")
        if not isinstance(proposal, dict):
            self.request.response.setStatus(400)
            return {"error": {"type": "BadRequest", "message": "proposal is required"}}

        handlers = {"create_draft": self._create_draft}
        handler = handlers.get(proposal.get("type"))
        if handler is None:
            self.request.response.setStatus(400)
            return {
                "error": {
                    "type": "BadRequest",
                    "message": f"unknown proposal type {proposal.get('type')!r}",
                }
            }

        try:
            payload, status = handler(proposal)
        except Exception as exc:
            logger.exception("assistant-apply endpoint failed")
            self.request.response.setStatus(500)
            return {"error": {"type": "InternalServerError", "message": str(exc)}}

        if status is not None:
            self.request.response.setStatus(status)
        return payload

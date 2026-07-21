"""REST endpoints backing the classic-UI chat assistant.

``POST <context>/@aitools-assistant`` with body ``{"messages": [...]}`` (the
OpenAI-style conversation history) starts the ``assistant`` turn on a background
thread and returns ``202 {"task_id": "...", "status": "running"}``. The agent
loop is slow (several LLM round-trips), so it runs asynchronously to avoid HTTP
timeouts; the client polls ``GET <context>/@aitools-assistant-status/<task_id>``
until the task is ``done`` (``result`` = ``{"reply", "steps", "proposals"}``) or
``error``.

``POST <context>/@aitools-assistant-apply`` is the (stubbed) explicit,
user-confirmed write endpoint: the assistant only ever *proposes* content
changes; the actual mutation happens here, behind the edit permission, when the
user confirms. Not implemented yet — see the first editor slice.
"""

from collective.aisettings.services.tasks import get_task
from collective.aitools import logger
from collective.aitools.capabilities.propose_draft import validate_draft
from collective.aitools.services.async_runner import start_assistant_task
from collective.aitools.tools import get_tool
from plone import api
from plone.app.textfield.interfaces import IRichText
from plone.app.textfield.value import RichTextValue
from plone.dexterity.utils import iterSchemata
from plone.restapi.deserializer import json_body
from plone.restapi.services import Service
from datetime import datetime
from datetime import timedelta
from zope.interface import implementer
from zope.publisher.interfaces import IPublishTraverse
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


def _is_event(obj):
    """Return ``True`` when ``obj`` carries the event start/end behavior.

    ``plone.app.event`` is an optional dependency, so import it lazily; when it
    is absent nothing is an event and no dates are ever set."""
    try:
        from plone.app.event.dx.behaviors import IEventBasic
    except Exception:
        return False
    return IEventBasic.providedBy(obj)


def _parse_dt(value, context):
    """Parse an ISO 8601 string into a timezone-aware datetime, or ``None``.

    Naive values are localized to the portal/user timezone (what the event
    widgets use). Anything unparseable returns ``None`` so the caller falls back
    to plone.app.event's defaults rather than failing the whole creation."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    # Tolerate a trailing "Z" (UTC) which fromisoformat rejects before 3.11.
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is not None:
        return dt
    from plone.app.event.base import default_timezone

    tz = default_timezone(context, as_tzinfo=True)
    # pytz zones localize via .localize(); other tzinfos via replace().
    if hasattr(tz, "localize"):
        return tz.localize(dt)
    return dt.replace(tzinfo=tz)


def _apply_event_dates(obj, proposal, context):
    """Set ``start``/``end`` on an event ``obj`` from the proposal, if present.

    Defaults ``end`` to one hour after ``start`` when it is missing or not after
    it. No-ops (leaving plone.app.event defaults) when there is no valid
    start."""
    start = _parse_dt(proposal.get("start"), context)
    if start is None:
        return False
    end = _parse_dt(proposal.get("end"), context)
    if end is None or end < start:
        end = start + timedelta(hours=1)
    obj.start = start
    obj.end = end
    obj.reindexObject()
    return True


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
    """``POST @aitools-assistant`` — start an assistant turn asynchronously.

    Validates the request, enqueues the (slow, multi-step) agent loop on a
    background thread, and returns ``202`` with a task id the client polls via
    :class:`AssistantStatus`.
    """

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
            task_id = start_assistant_task(self.context, self.request, messages)
        except Exception as exc:
            logger.exception("assistant endpoint failed to start task")
            self.request.response.setStatus(500)
            return {"error": {"type": "InternalServerError", "message": str(exc)}}

        self.request.response.setStatus(202)
        return {"task_id": task_id, "status": "running"}


@implementer(IPublishTraverse)
class AssistantStatus(Service):
    """``GET @aitools-assistant-status/<task_id>`` — poll an assistant turn.

    Returns ``{"task_id", "status": "running"}`` while the worker is busy,
    ``{"task_id", "status": "done", "result": {...}}`` on success, or
    ``{"task_id", "status": "error", "error": "..."}`` on failure.
    """

    # Populated by publishTraverse with the path segments after the service
    # name (the task id). Class-level default so no custom __init__ is needed
    # (plone.rest sets context/request on the instance itself).
    params: list[str] = None

    def publishTraverse(self, request, name):
        if self.params is None:
            self.params = []
        self.params.append(name)
        return self

    def reply(self):
        if not self.params:
            self.request.response.setStatus(400)
            return {"error": {"type": "BadRequest", "message": "task_id required"}}

        task_id = self.params[0]
        task = get_task(task_id)
        if task is None:
            self.request.response.setStatus(404)
            return {"error": {"type": "NotFound", "message": "task not found"}}

        return {"task_id": task_id, **task}


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

        if _is_event(obj):
            _apply_event_dates(obj, proposal, self.context)

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

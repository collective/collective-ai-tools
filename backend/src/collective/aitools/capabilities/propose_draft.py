"""The ``propose_draft`` capability: propose a new draft for the user to confirm.

The editor doesn't have to write the item — they give a rough *brief* (what it
should be about) and the draft's title, summary and body are AI-generated from
it, so the confirmed item lands as an editable starting point. Explicit values
may still be passed to override any generated field.

This capability never creates content. It validates that the target container
exists and that the requested type may be added there (as the current user),
generates the missing pieces, then returns a *proposal*. The widget renders the
proposal with a confirm button; only when the user confirms does
``@aitools-assistant-apply`` (see :mod:`collective.aitools.services.assistant`)
actually create the item — re-validating everything server-side.

The container/type validation lives in module-level helpers so the apply
endpoint reuses exactly the same checks it does here.
"""

from AccessControl import getSecurityManager
from collective.aisettings.interfaces import IAIService
from collective.aitools import _
from collective.aitools import logger
from collective.aitools.capabilities.base import AICapability
from collective.aitools.capabilities.types import resolve_portal_type
from collective.aitools.tools import get_tool
from plone import api
from plone.dexterity.utils import iterSchemataForType
from pydantic import BaseModel
from pydantic import Field
from typing import ClassVar
from typing import Optional
from zope.component import getUtility
from zope.schema import getFields
from zope.schema.interfaces import IDatetime


#: Permission required to add content (checked on the target container).
ADD_PERMISSION = "Add portal content"

#: System prompt steering draft generation from the editor's brief.
DRAFT_SYSTEM_PROMPT = (
    "You are drafting a new content item for a website from an editor's brief. "
    "Produce a helpful, well-structured starting draft the editor will refine: "
    "a concise title, a one- or two-sentence description, and a body written as "
    "simple, valid HTML (use <p>, <h2>, <ul>/<li>, <strong> — no <html>, <head> "
    "or <body> wrapper). Write in the same language as the brief. Be complete "
    "but not padded."
)

#: Extra instructions appended to the draft prompt when the item is an event, so
#: the model resolves any date/time in the brief into concrete start/end values.
DRAFT_EVENT_SYSTEM_PROMPT = (
    DRAFT_SYSTEM_PROMPT + " "
    "This item is an event. If the brief indicates when the event happens — "
    "either an explicit date ('on July 21st 2026', 'next Friday at 6pm') or a "
    "relative one ('in 2 weeks', 'tomorrow') — resolve it against the current "
    "date given to you and return 'start' and 'end' as ISO 8601 local datetimes "
    "(e.g. '2026-07-21T18:00:00'), no timezone suffix. If only a start is "
    "given, set 'end' to one hour after it. If the brief gives no timing at all, "
    "return null for both 'start' and 'end' — never invent a date."
)


class GeneratedDraft(BaseModel):
    """Structured draft produced from the editor's brief."""

    title: str = Field(description="A concise, descriptive title for the item.")
    description: str = Field(
        description="A one or two sentence summary, usable as the description."
    )
    body: str = Field(
        description="The body content as simple HTML (paragraphs, headings, lists)."
    )


class GeneratedEventDraft(GeneratedDraft):
    """A draft for an event: also carries the resolved start/end datetimes."""

    start: Optional[str] = Field(
        default=None,
        description=(
            "Event start as an ISO 8601 local datetime "
            "(e.g. '2026-07-21T18:00:00'), or null when the brief gives no date."
        ),
    )
    end: Optional[str] = Field(
        default=None,
        description=(
            "Event end as an ISO 8601 local datetime, or null. Defaults to one "
            "hour after the start when the brief gives a start but no end."
        ),
    )


def _is_event_type(portal_type) -> bool:
    """Return ``True`` when ``portal_type``'s schema has a ``start`` datetime
    field (i.e. it is an event-like type, e.g. carries ``IEventBasic``).

    Defensive: any lookup problem (unknown type, plone.app.event absent) simply
    means "not an event"."""
    try:
        for schema in iterSchemataForType(portal_type):
            field = getFields(schema).get("start")
            if field is not None and IDatetime.providedBy(field):
                return True
    except Exception:
        logger.exception("could not inspect schema for %r", portal_type)
    return False


def _current_date_line(context):
    """A 'current date' line to anchor relative dates, or '' when unavailable."""
    try:
        from plone.app.event.base import default_timezone
        from plone.app.event.base import localized_now

        now = localized_now(context)
        return (
            f"Current date and time: {now.isoformat()} "
            f"(timezone {default_timezone(context)}).\n\n"
        )
    except Exception:
        logger.exception("propose_draft: could not determine current date")
        return ""


def generate_draft(brief, portal_type, context=None, is_event=False):
    """Generate a :class:`GeneratedDraft` from ``brief``, or ``None``.

    Uses the AI service with the Assistant tool's configured model (falling
    back to a capability-picked completion model when unset). When ``is_event``
    the model also resolves the brief's date/time into ``start``/``end``, so the
    current date is supplied to anchor relative expressions.
    """
    service = getUtility(IAIService)
    assistant = get_tool("assistant")
    model = assistant.get_model() if assistant is not None else None

    if is_event:
        system = DRAFT_EVENT_SYSTEM_PROMPT
        output_type = GeneratedEventDraft
        date_line = _current_date_line(context)
    else:
        system = DRAFT_SYSTEM_PROMPT
        output_type = GeneratedDraft
        date_line = ""

    prompt = f"{date_line}Content type: {portal_type}\n\nEditor's brief:\n{brief}"
    try:
        return service.chat(
            prompt,
            model=model,
            system=system,
            context=context,
            output_type=output_type,
            use_tools=False,
        )
    except Exception:
        logger.exception("propose_draft: draft generation failed")
        return None


def resolve_container(path):
    """Return the folderish object at ``path`` the user can see, or ``None``."""
    path = (path or "").strip()
    if not path:
        return None
    container = api.content.get(path=path)
    if container is None:
        return None
    if not getattr(container, "isPrincipiaFolderish", False):
        return None
    return container


def validate_draft(container_path, portal_type):
    """Validate that ``portal_type`` may be added at ``container_path``.

    ``portal_type`` is resolved through :func:`resolve_portal_type`, so a loose
    name (a synonym, a title, an id in any case) is accepted. Returns
    ``(container, resolved_type, None)`` when allowed, or
    ``(None, None, error_message)`` otherwise. Used by both the proposal and the
    apply endpoint so the checks (and the resolution) can never drift apart.
    """
    resolved = resolve_portal_type(portal_type)
    if resolved is None:
        return None, None, f"Unknown content type {portal_type!r}."
    container = resolve_container(container_path)
    if container is None:
        return (
            None,
            None,
            f"No folder found at {container_path!r} (or not accessible).",
        )
    if not getSecurityManager().checkPermission(ADD_PERMISSION, container):
        return None, None, "You do not have permission to add content there."
    addable = {fti.getId() for fti in container.allowedContentTypes()}
    if resolved not in addable:
        return None, None, f"{resolved!r} cannot be added in that folder."
    return container, resolved, None


class ProposeDraftCapability(AICapability):
    """Propose creating a new draft item (does not create it)."""

    name = "propose_draft"
    description = _(
        "Propose creating a new draft content item for the editor to confirm. "
        "The editor only needs to give a rough 'brief' of what the item should "
        "be about — its title, description and body are AI-generated from that "
        "brief as an editable starting point. Provide the target folder path "
        "and the content type; pass explicit title/description/body only to "
        "override the generated ones. This does NOT create anything on its own; "
        "it returns a proposal the user must confirm. Use 'where_to_add' first "
        "if you are unsure of a valid folder."
    )
    parameters: ClassVar[dict] = {
        "type": "object",
        "properties": {
            "container_path": {
                "type": "string",
                "description": (
                    "Path of the folder to create the item in, e.g. '/news'."
                ),
            },
            "portal_type": {
                "type": "string",
                "description": (
                    "Content type to create. The exact id is best (e.g. "
                    "'Document', 'News Item', 'Event') but common names work "
                    "too (e.g. 'page', 'news', 'article', 'event')."
                ),
            },
            "brief": {
                "type": "string",
                "description": (
                    "A rough description of what the editor wants the item to "
                    "be about. The title, description and body are generated "
                    "from this. Required unless an explicit title and body are "
                    "supplied."
                ),
            },
            "title": {
                "type": "string",
                "description": "Optional explicit title (overrides the generated one).",
            },
            "description": {
                "type": "string",
                "description": (
                    "Optional explicit description (overrides the generated one)."
                ),
            },
            "body": {
                "type": "string",
                "description": (
                    "Optional explicit body, HTML or plain text (overrides the "
                    "generated one)."
                ),
            },
        },
        "required": ["container_path", "portal_type", "brief"],
    }
    permission = "cmf.ModifyPortalContent"

    def run(
        self,
        context,
        request,
        container_path="",
        portal_type="",
        brief="",
        title="",
        description="",
        body="",
    ):
        container, resolved_type, error = validate_draft(container_path, portal_type)
        if error:
            return {"error": error}

        brief = (brief or "").strip()
        title = (title or "").strip()
        description = (description or "").strip()
        body = (body or "").strip()
        is_event = _is_event_type(resolved_type)
        start = end = None

        # Generate whatever wasn't supplied explicitly, from the brief. For an
        # event we generate whenever a brief is present (even with explicit
        # title/body) so the brief's date can be resolved into start/end.
        generated = False
        if not (title and body) or (is_event and brief):
            if not brief:
                return {
                    "error": (
                        "Provide a 'brief' describing what to write, or both an "
                        "explicit title and body."
                    )
                }
            draft = generate_draft(
                brief, resolved_type, context=context, is_event=is_event
            )
            if draft is None:
                return {
                    "error": (
                        "Could not generate a draft. Check that a completion "
                        "model is configured in AI Settings."
                    )
                }
            title = title or (draft.title or "").strip()
            description = description or (draft.description or "").strip()
            body = body or (draft.body or "").strip()
            if is_event:
                start = (getattr(draft, "start", None) or "").strip() or None
                end = (getattr(draft, "end", None) or "").strip() or None
            generated = True

        if not title:
            return {"error": "title is required"}

        proposal = {
            "type": "create_draft",
            "container_path": "/".join(container.getPhysicalPath()),
            "container_title": container.Title(),
            "portal_type": resolved_type,
            "title": title,
            "description": description,
            "body": body,
        }
        if is_event:
            # May be null when the brief gave no timing; apply defaults then.
            proposal["start"] = start
            proposal["end"] = end

        # `proposal` is surfaced to the UI (as a confirm card) by the assistant
        # loop; the summary is what the model narrates to the user.
        when = f" starting {start}" if start else ""
        return {
            "proposal": proposal,
            "generated": generated,
            "summary": (
                f"Drafted a {resolved_type} titled {title!r}{when} for "
                f"{proposal['container_title']!r}. Ask the user to confirm; they "
                "can adjust it after it is created."
            ),
        }

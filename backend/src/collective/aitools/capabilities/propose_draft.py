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
from pydantic import BaseModel
from pydantic import Field
from zope.component import getUtility


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


class GeneratedDraft(BaseModel):
    """Structured draft produced from the editor's brief."""

    title: str = Field(description="A concise, descriptive title for the item.")
    description: str = Field(
        description="A one or two sentence summary, usable as the description."
    )
    body: str = Field(
        description="The body content as simple HTML (paragraphs, headings, lists)."
    )


def generate_draft(brief, portal_type, context=None):
    """Generate a :class:`GeneratedDraft` from ``brief``, or ``None``.

    Uses the AI service with the Assistant tool's configured model (falling
    back to a capability-picked completion model when unset).
    """
    service = getUtility(IAIService)
    assistant = get_tool("assistant")
    model = assistant.get_model() if assistant is not None else None
    prompt = f"Content type: {portal_type}\n\nEditor's brief:\n{brief}"
    try:
        return service.chat(
            prompt,
            model=model,
            system=DRAFT_SYSTEM_PROMPT,
            context=context,
            output_type=GeneratedDraft,
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
    parameters = {
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

        # Generate whatever wasn't supplied explicitly, from the brief.
        generated = False
        if not (title and body):
            if not brief:
                return {
                    "error": (
                        "Provide a 'brief' describing what to write, or both an "
                        "explicit title and body."
                    )
                }
            draft = generate_draft(brief, resolved_type, context=context)
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
        # `proposal` is surfaced to the UI (as a confirm card) by the assistant
        # loop; the summary is what the model narrates to the user.
        return {
            "proposal": proposal,
            "generated": generated,
            "summary": (
                f"Drafted a {resolved_type} titled {title!r} for "
                f"{proposal['container_title']!r}. Ask the user to confirm; they "
                "can adjust it after it is created."
            ),
        }

"""The ``where_to_add`` capability: suggest where new content should live.

Given a content type the editor wants to create, walk the folderish content
they can see and return the containers where that type is addable (optionally
narrowed by a keyword matching the container title/path). Read-only: it only
*suggests* a location — creating the content is a separate, confirmed step.
"""

from collective.aitools import _
from collective.aitools.capabilities.base import AICapability
from collective.aitools.capabilities.types import resolve_portal_type
from plone import api


#: Hard cap on candidate containers returned to the model.
MAX_RESULTS = 10


def _addable_type_ids(container):
    """Return the set of portal_type ids addable inside ``container``."""
    try:
        return {fti.getId() for fti in container.allowedContentTypes()}
    except Exception:
        return set()


class WhereToAddCapability(AICapability):
    """Suggest folders where a given content type may be added."""

    name = "where_to_add"
    description = _(
        "Given the type of content the editor wants to create, suggest "
        "folders where that type can be added. Returns candidate containers "
        "with their title and URL. Use this to answer 'where should I put …' "
        "questions. This only suggests a location; it does not create anything."
    )
    parameters = {
        "type": "object",
        "properties": {
            "portal_type": {
                "type": "string",
                "description": (
                    "The content type to add. The exact id is best (e.g. "
                    "'Document', 'News Item', 'Event') but common names work "
                    "too (e.g. 'page', 'news', 'article', 'event')."
                ),
            },
            "keyword": {
                "type": "string",
                "description": (
                    "Optional word to prefer containers whose title or path "
                    "contains it."
                ),
            },
        },
        "required": ["portal_type"],
    }
    # Only editors: they must be able to modify content to act on the answer.
    permission = "cmf.ModifyPortalContent"

    def run(self, context, request, portal_type="", keyword=""):
        if not (portal_type or "").strip():
            return {"candidates": [], "message": "portal_type is required"}
        resolved_type = resolve_portal_type(portal_type)
        if resolved_type is None:
            return {"candidates": [], "message": f"Unknown content type {portal_type!r}."}
        keyword = (keyword or "").strip().lower()

        catalog = api.portal.get_tool("portal_catalog")
        # Folderish content the current user can see (ACL enforced by catalog).
        brains = catalog.searchResults(is_folderish=True, sort_on="path")

        candidates = []
        for brain in brains:
            try:
                container = brain.getObject()
            except Exception:
                continue
            if resolved_type not in _addable_type_ids(container):
                continue
            title = brain.Title or brain.id
            path = brain.getPath()
            if keyword and keyword not in title.lower() and keyword not in path.lower():
                continue
            candidates.append(
                {
                    "title": title,
                    "url": brain.getURL(),
                    "path": path,
                }
            )
            if len(candidates) >= MAX_RESULTS:
                break

        return {
            "portal_type": resolved_type,
            "candidates": candidates,
            "count": len(candidates),
        }

"""The ``search_site`` capability: full-text search over the site catalog.

Read-only, so it is safe to run inside the agent loop. The catalog query runs
as the current user, so ``allowedRolesAndUsers`` filtering is automatic: an
anonymous visitor never sees private content in the results.
"""

from collective.aitools import _
from collective.aitools.capabilities.base import AICapability
from plone import api


#: Hard cap on results returned to the model (keeps the tool result bounded).
MAX_RESULTS = 10


class SearchSiteCapability(AICapability):
    """Search the site for content matching a query."""

    name = "search_site"
    description = _(
        "Search the website for content matching a free-text query. Returns "
        "matching items with their title, URL, type and short description. Use "
        "this to find existing pages or to answer 'where do I find …' "
        "questions."
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The free-text search query.",
            },
            "limit": {
                "type": "integer",
                "description": (
                    f"Maximum number of results (1-{MAX_RESULTS}, default 5)."
                ),
            },
        },
        "required": ["query"],
    }
    # Anyone who can view the context; catalog ACL does the real filtering.
    permission = "zope2.View"

    def run(self, context, request, query="", limit=5):
        query = (query or "").strip()
        if not query:
            return {"results": [], "message": "empty query"}
        try:
            limit = int(limit)
        except (TypeError, ValueError):
            limit = 5
        limit = max(1, min(limit, MAX_RESULTS))

        catalog = api.portal.get_tool("portal_catalog")
        brains = catalog.searchResults(SearchableText=query, sort_limit=limit)

        results = []
        for brain in brains[:limit]:
            results.append(
                {
                    "title": brain.Title or brain.id,
                    "url": brain.getURL(),
                    "type": brain.portal_type,
                    "description": (brain.Description or "").strip(),
                }
            )
        return {"results": results, "count": len(results)}

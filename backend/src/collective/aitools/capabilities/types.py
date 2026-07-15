"""Resolve a user/model-supplied content-type name to a real ``portal_type``.

The assistant (and the people talking to it) shouldn't have to know the exact
``portal_type`` id. :func:`resolve_portal_type` accepts a loose name — an id in
any case, a type's title, one of the built-in synonyms below, or a synonym
contributed by an add-on — and returns the actual id, but only when that type
really exists on the site.

Add-ons extend the synonyms by registering an ``IContentTypeSynonyms`` utility;
see :class:`SynonymProvider` for a convenience base class.
"""

from collective.aitools import logger
from collective.aitools.interfaces import IContentTypeSynonyms
from plone import api
from typing import ClassVar
from zope.component import getAllUtilitiesRegisteredFor
from zope.interface import implementer


#: Curated synonyms → canonical ``portal_type`` id for the standard Plone types.
#: Keys are matched case-insensitively (and whitespace-normalized). A synonym is
#: only honored when its target type actually exists on the site, so extending
#: this map is safe even if a given type isn't installed.
TYPE_SYNONYMS = {
    # Document
    "page": "Document",
    "document": "Document",
    "web page": "Document",
    "rich text page": "Document",
    "text page": "Document",
    # News Item
    "news": "News Item",
    "news page": "News Item",
    "news content": "News Item",
    "news item": "News Item",
    "news article": "News Item",
    "article": "News Item",
    "press release": "News Item",
    # Event
    "event": "Event",
    "events": "Event",
    "calendar event": "Event",
    "meeting": "Event",
    # Folder
    "folder": "Folder",
    "directory": "Folder",
    "section": "Folder",
    # File
    "file": "File",
    "attachment": "File",
    "document file": "File",
    # Image
    "image": "Image",
    "picture": "Image",
    "photo": "Image",
    # Link
    "link": "Link",
    "shortcut": "Link",
    "url": "Link",
    "bookmark": "Link",
    # Collection
    "collection": "Collection",
    "smart folder": "Collection",
    "saved search": "Collection",
}


@implementer(IContentTypeSynonyms)
class SynonymProvider:
    """Convenience base for an ``IContentTypeSynonyms`` utility.

    Set :attr:`synonyms` to a ``{synonym: portal_type_id}`` dict and register
    the subclass as a utility; that's all an add-on needs to contribute names::

        @implementer(IContentTypeSynonyms)  # or subclass SynonymProvider
        class MyProductSynonyms(SynonymProvider):
            synonyms = {"story": "my.product.Story", "gallery": "my.product.Gallery"}
    """

    synonyms: ClassVar[dict] = {}

    def get_synonyms(self):
        return dict(self.synonyms)


def _norm(value):
    """Lower-case and collapse internal whitespace for loose matching."""
    return " ".join((value or "").strip().lower().split())


def collect_synonyms():
    """Return the merged ``{normalized synonym: portal_type_id}`` mapping.

    Starts from the built-in :data:`TYPE_SYNONYMS`, then overlays every
    registered ``IContentTypeSynonyms`` utility (so add-ons can add — or
    override — names). A misbehaving provider is logged and skipped rather than
    breaking resolution.
    """
    merged = {_norm(k): v for k, v in TYPE_SYNONYMS.items()}
    for provider in getAllUtilitiesRegisteredFor(IContentTypeSynonyms):
        try:
            extra = provider.get_synonyms() or {}
        except Exception:
            logger.exception(
                "IContentTypeSynonyms provider %r failed; skipping.", provider
            )
            continue
        for key, target in extra.items():
            merged[_norm(key)] = target
    return merged


def resolve_portal_type(value):
    """Return the real ``portal_type`` id for ``value``, or ``None``.

    Matches, in order of precedence: an exact id, a case-insensitive id, a
    case-insensitive type title, then the :data:`TYPE_SYNONYMS` map. Only ids
    that exist on this site are ever returned.
    """
    value = (value or "").strip()
    if not value:
        return None

    types_tool = api.portal.get_tool("portal_types")
    ids = list(types_tool.listContentTypes())

    # 1) exact id
    if value in ids:
        return value

    norm = _norm(value)

    # 2) case-insensitive id
    by_norm_id = {_norm(tid): tid for tid in ids}
    if norm in by_norm_id:
        return by_norm_id[norm]

    # 3) case-insensitive type title
    for tid in ids:
        fti = types_tool.getTypeInfo(tid)
        if fti is not None and _norm(fti.Title()) == norm:
            return tid

    # 4) synonym — built-in plus any registered by add-ons (only if the target
    #    type is actually installed on this site)
    target = collect_synonyms().get(norm)
    if target and target in ids:
        return target

    return None

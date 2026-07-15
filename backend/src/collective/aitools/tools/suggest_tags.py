"""The "Suggest tags" tool: propose Subject keywords from an item's text.

Vocabulary-aware: the set of tags already in use on the site (the catalog
``Subject`` index) is passed to the model so it reuses existing tags instead of
inventing near-duplicates.
"""

from collective.aitools import _
from collective.aitools import logger
from collective.aitools.interfaces import DEFAULT_SUGGEST_TAGS_PROMPT
from collective.aitools.tools.base import AITool
from collective.aitools.tools.text import clean_tags
from collective.aitools.tools.text import get_body_text
from collective.aitools.tools.text import MAX_TAGS
from plone import api
from pydantic import BaseModel
from pydantic import Field


#: Cap on how many existing site tags we list to the model (keeps the prompt
#: bounded on sites with huge keyword sets).
MAX_EXISTING_TAGS = 200


class SuggestedTags(BaseModel):
    """Structured tag suggestion output."""

    tags: list[str] = Field(
        default_factory=list,
        description="Between 5 and 10 short keyword tags classifying the content.",
    )


def existing_site_tags(context=None, limit=MAX_EXISTING_TAGS):
    """Return up to ``limit`` tags already used on the site (sorted)."""
    try:
        catalog = api.portal.get_tool("portal_catalog")
        values = [v for v in catalog.uniqueValuesFor("Subject") if v]
    except Exception:
        return []
    values.sort(key=lambda v: v.lower())
    return values[:limit]


class SuggestTagsTool(AITool):
    """Suggest Subject keywords for an item from its text content."""

    name = "suggest_tags"
    title = _("Suggest tags")
    description = _(
        "Suggest Subject keywords for an item from its text content, reusing "
        "tags already in use on the site where possible."
    )

    def get_prompt(self):
        prompt = (getattr(self.settings, "suggest_tags_prompt", "") or "").strip()
        return prompt or DEFAULT_SUGGEST_TAGS_PROMPT

    def available_for(self, context):
        if not self.is_enabled():
            return False
        return bool(get_body_text(context))

    def _system_prompt(self, context):
        prompt = self.get_prompt()
        tags = existing_site_tags(context)
        if tags:
            prompt = (
                f"{prompt}\n\nExisting site tags (reuse these when they fit): "
                f"{', '.join(tags)}."
            )
        return prompt

    def suggest_for_text(self, text, context=None):
        """Suggest tags for the given ``text``. Returns a list of tags, or
        ``None`` when the tool is disabled, the text is empty, or no model is
        available."""
        if self._skip_if_disabled():
            return None
        text = (text or "").strip()
        if not text:
            logger.info("suggest_tags: empty text; nothing to do.")
            return None
        result = self.service.chat(
            text,
            model=self.get_model(),
            system=self._system_prompt(context),
            context=context,
            output_type=SuggestedTags,
            use_tools=False,
        )
        if result is None:
            return None
        return clean_tags(result.tags, MAX_TAGS)

    def run(self, context, text=None):
        """Suggest tags for ``context``'s text content (or the given ``text``)."""
        if self._skip_if_disabled():
            return None
        if text is None:
            text = get_body_text(context)
        return self.suggest_for_text(text, context=context)

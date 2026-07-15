"""The "Summarize" tool: generate a Description/summary from an item's text."""

from collective.aitools import _
from collective.aitools import logger
from collective.aitools.interfaces import DEFAULT_SUMMARIZE_PROMPT
from collective.aitools.tools.base import AITool
from collective.aitools.tools.text import get_body_text


class SummarizeTool(AITool):
    """Summarize an item's text content into a short description."""

    name = "summarize"
    title = _("Summarize")
    description = _(
        "Generate a concise description/summary of an item from its text "
        "content (also usable as the SEO meta description)."
    )

    def get_prompt(self):
        prompt = (getattr(self.settings, "summarize_prompt", "") or "").strip()
        return prompt or DEFAULT_SUMMARIZE_PROMPT

    def available_for(self, context):
        if not self.is_enabled():
            return False
        return bool(get_body_text(context))

    def summarize_text(self, text, context=None):
        """Summarize the given ``text``. Returns the summary, or ``None`` when
        the tool is disabled, the text is empty, or no model is available."""
        if self._skip_if_disabled():
            return None
        text = (text or "").strip()
        if not text:
            logger.info("summarize: empty text; nothing to do.")
            return None
        result = self.service.chat(
            text,
            model=self.get_model(),
            system=self.get_prompt(),
            context=context,
            use_tools=False,
        )
        return (result or "").strip() or None

    def run(self, context, text=None):
        """Summarize ``context``'s text content (or the supplied ``text``)."""
        if self._skip_if_disabled():
            return None
        if text is None:
            text = get_body_text(context)
        return self.summarize_text(text, context=context)

"""The "Help me write" tool: drafting and rewriting assistance for editors."""

from collective.aitools import _
from collective.aitools import logger
from collective.aitools.tools.base import AITool


# Operation -> system prompt steering the model. Plain English (sent to the
# model), not translatable message ids. The keys are the public API; the
# OPERATION_TITLES below are the translatable labels for any UI.
OPERATIONS = {
    "draft": (
        "You help an editor start writing. Given a topic or a few notes, "
        "produce a clear, well-structured first draft. Return only the draft "
        "text, with no preamble or explanation."
    ),
    "grammar": (
        "You are a meticulous copy editor. Correct grammar, spelling and "
        "punctuation in the given text while preserving its meaning, tone and "
        "language. Return only the corrected text."
    ),
    "professional": (
        "You are an editor. Rewrite the given text in a polished, professional "
        "tone while preserving its meaning and language. Return only the "
        "rewritten text."
    ),
    "casual": (
        "You are an editor. Rewrite the given text in a relaxed, friendly, "
        "non-professional tone while preserving its meaning and language. "
        "Return only the rewritten text."
    ),
}

OPERATION_TITLES = {
    "draft": _("Start a draft"),
    "grammar": _("Grammar check"),
    "professional": _("Rewrite in a professional tone"),
    "casual": _("Rewrite in a casual tone"),
}

#: Operations that need the editor to type something (rather than operating on
#: existing/selected text). Used by the edit-form UI to show an input field.
OPERATIONS_REQUIRING_INPUT = frozenset({"draft"})


class HelpMeWriteTool(AITool):
    """Generate or rewrite text on behalf of an editor.

    ``run`` takes an ``operation`` (one of :data:`OPERATIONS`) and the input:
    ``text`` for the rewrite/grammar operations, or ``topic`` (notes / subject)
    for ``draft``.
    """

    name = "help_me_write"
    title = _("Help me write")
    description = _(
        "Offer editors drafting and rewriting assistance (start a draft, "
        "grammar check, change tone, …)."
    )

    def run(self, context=None, operation="draft", text="", topic=""):
        """Run a writing operation and return the generated text, or ``None``
        when the tool is disabled, no model is available, or the input is
        empty.
        """
        if self._skip_if_disabled():
            return None
        if operation not in OPERATIONS:
            raise ValueError(
                f"Unknown operation {operation!r}; "
                f"expected one of {sorted(OPERATIONS)}."
            )
        prompt = topic if operation == "draft" else text
        if not (prompt and prompt.strip()):
            logger.info("help_me_write: empty input for %r; nothing to do.", operation)
            return None
        return self.service.chat(
            prompt,
            model=self.get_model(),
            system=OPERATIONS[operation],
            context=context,
            use_tools=False,
        )

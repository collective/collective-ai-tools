"""The "Help me write" tool: drafting and rewriting assistance for editors."""

from collective.aitools import _
from collective.aitools import logger
from collective.aitools.tools.base import AITool
from pydantic import BaseModel
from pydantic import Field


# Operation -> system prompt steering the model. Plain English (sent to the
# model), not translatable message ids. The keys are the public API; the
# OPERATION_TITLES below are the translatable labels for any UI.
OPERATIONS = {
    "draft": (
        "You help an editor start writing. Given a topic or a few notes, "
        "produce a clear, well-structured first draft as an HTML fragment, "
        "using the structure the content actually calls for — sections, lists "
        "or a table — rather than one undifferentiated run of paragraphs. "
        "Return only the fragment, with no preamble or explanation."
    ),
    "grammar": (
        "You are a meticulous copy editor. Correct grammar, spelling and "
        "punctuation in the given text while preserving its meaning, tone and "
        "language. Never translate, and leave wording that is already correct "
        "exactly as it is — change only what is actually wrong. Return only "
        "the corrected text."
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

#: Appended to the operation prompt when running over *segments* rather than one
#: block of text. The segments are consecutive pieces of a single passage, split
#: where inline markup starts or ends (``<strong>``, ``<a>``, …), so each one has
#: to be rewritten in place: text that moved from one segment to another would
#: land inside — or outside — an element it does not belong to, destroying the
#: editor's formatting.
SEGMENT_PROTOCOL = (
    "\n\n"
    "The text reaches you as numbered segments, one per line, in the form "
    "'[id] text'. They are consecutive pieces of one passage from a rich-text "
    "editor, split wherever inline formatting (bold, links, …) starts or ends, "
    "so reading them in order gives you the whole passage as context.\n"
    "\n"
    "Apply the instructions above to each segment separately:\n"
    "- Never move, merge, split or reorder text between segments. A change "
    "that would need text to cross a segment boundary must be left unmade.\n"
    "- A segment may begin or end mid-sentence, or even mid-word, and two "
    "segments are not necessarily separated by a space. That is expected — "
    "keep each segment's own extent as it is.\n"
    "- Whitespace at the very start and end of a segment has been removed and "
    "is restored afterwards, so do not add padding around your text.\n"
    "- Return an entry only for the segments you actually changed, each with "
    "its original id and its new text. Omit every segment you would return "
    "unchanged, and never invent an id that was not in the input or repeat "
    "the same id twice."
)


#: The formatting actually available in a Plone rich-text field, so the model
#: composes with what will survive instead of what would look good in a Markdown
#: preview. Two filters stand between the model and the page: TinyMCE's schema
#: when the fragment is inserted, and ``safe_html``
#: (``IFilterSchema.valid_tags`` / ``nasty_tags``) when the item is saved. The
#: palette below is inside both, and matches what the default Plone toolbar and
#: table styles offer, so nothing here is silently dropped on the way in.
HTML_FORMATTING = (
    "\n\n"
    "Formatting is at your disposal, and worth using wherever it genuinely "
    "helps the reader:\n"
    "- <h2> to <h6> for sections. Do not use <h1>: the page title already "
    "fills that role.\n"
    "- <p> for paragraphs; <br> only for a line break *within* a paragraph.\n"
    "- <ul>/<ol> with <li> for lists, and <dl> with <dt>/<dd> for "
    "term-and-definition pairs.\n"
    '- <table class="listing"> with <caption>, <thead>, <tbody>, <tr>, <th> '
    "and <td> for tabular data — real header cells as <th>, and the class is "
    "what picks up the site's table styling.\n"
    "- <strong> and <em> for emphasis, <blockquote> for a quoted passage, <q> "
    'for an inline quote, <cite> for a source, <abbr title="…"> for an '
    "abbreviation.\n"
    "- <code> for inline code, <pre> for a code block, <kbd> for keys to "
    "press, <sub>/<sup> for subscript and superscript, <hr> for a thematic "
    "break.\n"
    '- <a href="…"> for links, and <figure> with <figcaption> to caption an '
    "image.\n"
    "\n"
    "Prefer that list over anything else, and keep the markup as plain as the "
    "content allows. No <script> or <style> — Plone blocks both outright. No "
    "embedded <iframe> or media, no style= attributes, and no class= beyond "
    "the table class above: the site's own stylesheet owns appearance. Do not "
    "add a doctype or <html>/<head>/<body> wrapper, and return only the "
    "fragment itself — no explanation and no Markdown code fences."
)

#: Appended for the tone rewrites when the input is an HTML fragment. They are
#: meant to restructure the passage, so the editor replaces the whole selection
#: with what comes back rather than threading it through the original markup.
HTML_REWRITE_PROTOCOL = (
    "\n\n"
    "The text comes from a rich-text editor as an HTML fragment; return an HTML "
    "fragment the same way. Changing the structure is expected here — resplit "
    "paragraphs, move emphasis, and reach for a list, a table or headings when "
    "the passage reads better that way than as prose.\n"
    "\n"
    "- Keep every link (<a>) with its href unchanged, and every image (<img>) "
    "with its src and alt, unless the text they belong to genuinely goes away.\n"
    "- Keep the contents of <code> and <pre> verbatim: reword the prose around "
    "them, never the code itself."
)

#: Appended when the input is an HTML fragment but the operation only *corrects*
#: the wording (see :data:`OPERATIONS_CORRECTING_IN_PLACE`). This is the whole
#: job done in the prompt, for a caller that has an HTML string and no DOM to
#: patch; the editor UI does not need it, because :meth:`run_segments` gets the
#: same guarantee structurally by never showing the model any markup at all.
HTML_PRESERVE_PROTOCOL = (
    "\n\n"
    "The text is an HTML fragment from a rich-text editor. Return the same "
    "fragment with only the wording corrected — the markup is not yours to "
    "change:\n"
    "- Keep every tag, attribute, attribute value, entity and comment exactly "
    "as given: same names, same order, same quoting, same nesting. Do not add, "
    "remove, reorder, merge, split or tidy any element or attribute, not even "
    "a redundant, empty or malformed one.\n"
    "- Edit text between tags only, and only where something is actually "
    "wrong. Leave correct text character-for-character identical.\n"
    "- Preserve whitespace, line breaks and &nbsp; as they are. Do not reflow, "
    "re-indent or pretty-print.\n"
    "- Never move text across an element boundary: a correction that would "
    "need that must be left unmade.\n"
    "- Leave the contents of <code>, <pre>, <kbd> and <samp> untouched.\n"
    "- Return only the fragment: no explanation and no Markdown code fences."
)


class SegmentCorrection(BaseModel):
    """A single rewritten segment, keyed by the id it was given in the prompt."""

    id: int = Field(description="The id of the segment this text replaces.")
    text: str = Field(description="The segment's new text.")


class SegmentCorrections(BaseModel):
    """Structured per-segment rewrite output."""

    corrections: list[SegmentCorrection] = Field(
        default_factory=list,
        description="One entry per changed segment; unchanged segments are omitted.",
    )


def split_whitespace(text):
    """Split ``text`` into its ``(leading, core, trailing)`` whitespace parts.

    ``leading + core + trailing == text`` always holds. A blank ``text`` yields
    three empty strings.
    """
    stripped = text.lstrip()
    leading = text[: len(text) - len(stripped)]
    core = stripped.rstrip()
    return leading, core, stripped[len(core) :]


OPERATION_TITLES = {
    "draft": _("Start a draft"),
    "grammar": _("Grammar check"),
    "professional": _("Rewrite in a professional tone"),
    "casual": _("Rewrite in a casual tone"),
}

#: Operations that need the editor to type something (rather than operating on
#: existing/selected text). Used by the edit-form UI to show an input field.
OPERATIONS_REQUIRING_INPUT = frozenset({"draft"})

#: Operations that only *correct* the existing wording, leaving the writing as
#: the editor wrote it. Their result can go back into the field's own text nodes,
#: so the markup never has to be rewritten (see :meth:`run_segments`). Every
#: other operation is a *rewrite*: it is supposed to restructure the passage —
#: resplit paragraphs, add or drop emphasis — which means new markup, so the
#: editor hands it HTML and replaces the selection with the HTML it gets back.
OPERATIONS_CORRECTING_IN_PLACE = frozenset({"grammar"})


def operation_mode(operation):
    """Return how ``operation``'s result is meant to be applied to the field.

    ``"draft"``   — generated from typed input, inserted at the cursor.
    ``"correct"`` — per-segment corrections, written back into the text nodes
    they came from (:meth:`HelpMeWriteTool.run_segments`).
    ``"rewrite"`` — the selection is replaced by the returned HTML fragment.
    """
    if operation in OPERATIONS_REQUIRING_INPUT:
        return "draft"
    if operation in OPERATIONS_CORRECTING_IN_PLACE:
        return "correct"
    return "rewrite"


def system_prompt(operation, html=False):
    """Assemble the full system prompt for ``operation``.

    ``html`` says the input is an HTML fragment and one is wanted back. What that
    licenses depends on the mode: a *rewrite* is free to restructure and gets the
    formatting palette, while a *correction* is told to leave the markup exactly
    as it found it. A draft is always composed as HTML — it is inserted straight
    into the editor — so it gets the palette either way.
    """
    prompt = OPERATIONS[operation]
    mode = operation_mode(operation)
    if mode == "draft":
        return prompt + HTML_FORMATTING
    if not html:
        return prompt
    if mode == "rewrite":
        return prompt + HTML_REWRITE_PROTOCOL + HTML_FORMATTING
    return prompt + HTML_PRESERVE_PROTOCOL


class HelpMeWriteTool(AITool):
    """Generate or rewrite text on behalf of an editor.

    ``run`` takes an ``operation`` (one of :data:`OPERATIONS`) and one input:
    ``topic`` (notes / subject) for ``draft``, ``text`` for a plain-text
    rewrite, or ``html`` for an HTML fragment, which comes back as HTML.

    :meth:`run_segments` is the third shape, for *correcting* text that carries
    formatting: the caller splits the passage at its inline-markup boundaries
    and gets back only the pieces that changed, so it can write each one into the
    node it came from and never touch the markup at all.

    Which shape an operation wants is :func:`operation_mode` — the editor UI
    reads it to decide what to send and how to apply the answer.
    """

    name = "help_me_write"
    title = _("Help me write")
    description = _(
        "Offer editors drafting and rewriting assistance (start a draft, "
        "grammar check, change tone, …)."
    )

    def run(self, context=None, operation="draft", text="", topic="", html=""):
        """Run a writing operation and return the generated text, or ``None``
        when the tool is disabled, no model is available, or the input is
        empty.

        Pass ``html`` instead of ``text`` when the input is an HTML fragment and
        an HTML fragment is wanted back — the model is told so, and is free to
        restructure the markup, which is what a tone rewrite needs to do.
        """
        if self._skip_if_disabled():
            return None
        if operation not in OPERATIONS:
            raise ValueError(
                f"Unknown operation {operation!r}; "
                f"expected one of {sorted(OPERATIONS)}."
            )
        prompt = topic if operation == "draft" else html or text
        system = system_prompt(operation, html=bool(html))
        if not (prompt and prompt.strip()):
            logger.info("help_me_write: empty input for %r; nothing to do.", operation)
            return None
        return self.service.chat(
            prompt,
            model=self.get_model(),
            system=system,
            context=context,
            use_tools=False,
        )

    def run_segments(self, context=None, operation="grammar", segments=()):
        """Run a text operation over ``segments``, returning what changed.

        ``segments`` is the passage split at its inline-markup boundaries, in
        document order. The result is a ``{index: new_text}`` mapping holding
        *only* the segments the model changed — an empty mapping means "nothing
        to change", which is a perfectly good answer.

        Returns ``None`` when the tool is disabled, no model is available, or
        there is no text worth sending.
        """
        if self._skip_if_disabled():
            return None
        if operation not in OPERATIONS:
            raise ValueError(
                f"Unknown operation {operation!r}; "
                f"expected one of {sorted(OPERATIONS)}."
            )
        if operation in OPERATIONS_REQUIRING_INPUT:
            raise ValueError(
                f"Operation {operation!r} needs typed input; use run() instead."
            )

        # Hold each segment's own leading/trailing whitespace back and restore it
        # on the way out. It is load-bearing (it is what separates words across
        # an inline boundary) and letting the model round-trip it only invites
        # dropped or doubled spaces.
        parts = {}
        for index, segment in enumerate(segments):
            leading, core, trailing = split_whitespace(segment)
            if core:
                parts[index] = (leading, core, trailing)
        if not parts:
            logger.info("help_me_write: no text in segments for %r.", operation)
            return None

        prompt = "\n".join(f"[{index}] {part[1]}" for index, part in parts.items())
        result = self.service.chat(
            prompt,
            model=self.get_model(),
            system=OPERATIONS[operation] + SEGMENT_PROTOCOL,
            context=context,
            output_type=SegmentCorrections,
            use_tools=False,
        )
        if result is None:
            return None
        return self._merge_corrections(parts, result.corrections)

    @staticmethod
    def _merge_corrections(parts, corrections):
        """Turn the model's ``corrections`` into a ``{index: new_text}`` mapping.

        Anything the model gets wrong is dropped rather than trusted: ids it was
        never given, an id repeated (the first wins), text that is unchanged, and
        text emptied out entirely.
        """
        merged = {}
        for correction in corrections:
            part = parts.get(correction.id)
            if part is None:
                logger.info(
                    "help_me_write: model returned unknown segment id %r; ignored.",
                    correction.id,
                )
                continue
            if correction.id in merged:
                continue
            leading, core, trailing = part
            # We stripped the ends on the way in, so strip them again here: any
            # padding the model added would otherwise double up the whitespace.
            text = correction.text.strip()
            if not text or text == core:
                continue
            merged[correction.id] = leading + text + trailing
        return merged

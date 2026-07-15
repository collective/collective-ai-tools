"""Shared helpers for the text-oriented AI tools.

- :func:`get_body_text` extracts a plain-text representation of an item's
  textual content (title, description and every RichText field) to feed a
  model.
- :func:`clean_tags` normalizes a model-produced tag list (trim, de-dupe
  case-insensitively, clamp to a maximum).
"""

from plone.app.textfield.interfaces import IRichText
from plone.app.textfield.interfaces import IRichTextValue
from plone.dexterity.utils import iterSchemata
from zope.schema import getFields

import re


#: Default cap for tag lists produced by the tools.
MAX_TAGS = 10

#: Upper bound on the characters we send to a model as "the content".
DEFAULT_MAX_CHARS = 20000

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t\r\f\v]+")
_BLANK_LINES_RE = re.compile(r"\n\s*\n+")


def html_to_text(html):
    """Very small HTML → text reduction good enough for prompting a model."""
    if not html:
        return ""
    # Turn block-ish tags into newlines so paragraphs stay separated.
    text = re.sub(r"(?i)<(br|/p|/div|/li|/h[1-6])\s*/?>", "\n", html)
    text = _TAG_RE.sub(" ", text)
    # Unescape the handful of entities that matter for readability.
    for entity, char in (
        ("&nbsp;", " "),
        ("&amp;", "&"),
        ("&lt;", "<"),
        ("&gt;", ">"),
        ("&quot;", '"'),
        ("&#39;", "'"),
    ):
        text = text.replace(entity, char)
    text = _WS_RE.sub(" ", text)
    text = _BLANK_LINES_RE.sub("\n\n", text)
    return text.strip()


def _richtext_to_text(value):
    if not IRichTextValue.providedBy(value):
        return ""
    mime = (getattr(value, "outputMimeType", "") or "").lower()
    raw_mime = (getattr(value, "mimeType", "") or "").lower()
    if "html" in mime or "html" in raw_mime:
        return html_to_text(getattr(value, "output", None) or value.raw)
    # text/plain, markdown, … — use the raw value as-is.
    return (value.raw or "").strip()


def get_body_text(context, max_chars=DEFAULT_MAX_CHARS):
    """Return a plain-text digest of ``context``'s textual content.

    Combines the title, description and every RichText field (content type +
    behaviors), truncated to ``max_chars``. Returns an empty string when the
    item carries no usable text.
    """
    parts = []
    title = (getattr(context, "title", "") or "").strip()
    if title:
        parts.append(title)
    description = (getattr(context, "description", "") or "").strip()
    if description:
        parts.append(description)

    seen = set()
    for schema in iterSchemata(context):
        for name, field in getFields(schema).items():
            if name in seen or not IRichText.providedBy(field):
                continue
            seen.add(name)
            text = _richtext_to_text(getattr(context, name, None))
            if text:
                parts.append(text)

    body = "\n\n".join(parts).strip()
    if max_chars and len(body) > max_chars:
        body = body[:max_chars].rstrip()
    return body


def clean_tags(tags, max_tags=MAX_TAGS):
    """Trim, de-dupe (case-insensitively) and clamp a list of tags."""
    result = []
    lowered = set()
    for tag in tags or []:
        tag = (tag or "").strip()
        if not tag:
            continue
        key = tag.lower()
        if key in lowered:
            continue
        lowered.add(key)
        result.append(tag)
        if len(result) >= max_tags:
            break
    return result

"""The "Recognize image" tool: describe an item's image with a vision model.

The tool asks a vision-capable model for *structured* metadata — a title, a
description and a handful of tags — returned as an :class:`ImageDetails`
pydantic model (enforced through the AI service's ``output_type``). Callers get
a plain ``dict`` back via :meth:`RecognizeImageTool.run` /
:meth:`RecognizeImageTool.describe`.
"""

from collective.aitools import _
from collective.aitools import logger
from collective.aitools.interfaces import DEFAULT_VISION_PROMPT
from collective.aitools.tools.base import AITool
from collective.aitools.tools.text import clean_tags
from collective.aitools.tools.text import MAX_TAGS
from plone.dexterity.utils import iterSchemata
from plone.namedfile.interfaces import INamedImageField
from pydantic import BaseModel
from pydantic import Field
from zope.schema import getFields

import base64


#: Minimum number of tags we ask the model for.
MIN_TAGS = 5


class ImageDetails(BaseModel):
    """Structured metadata describing an image."""

    title: str = Field(description="A short, descriptive title for the image.")
    description: str = Field(
        description="One or two sentences describing the image, suitable as alt text."
    )
    tags: list[str] = Field(
        default_factory=list,
        description="Between 5 and 10 short keyword tags categorizing the image.",
    )


def find_image(context):
    """Return ``(field_name, image)`` for the first non-empty image field on
    ``context``, or ``(None, None)`` when the item has no image.

    Walks every schema (content type + behaviors) and picks the first field
    providing ``INamedImageField`` that holds a value.
    """
    for schema in iterSchemata(context):
        for name, field in getFields(schema).items():
            if INamedImageField.providedBy(field):
                value = getattr(context, name, None)
                if value is not None and getattr(value, "data", None):
                    return name, value
    return None, None


def image_to_data_uri(image):
    """Turn a ``plone.namedfile`` image value into a ``data:`` URI."""
    media_type = getattr(image, "contentType", None) or "image/png"
    encoded = base64.b64encode(image.data).decode("ascii")
    return f"data:{media_type};base64,{encoded}"


def _as_dict(details):
    """Normalize an :class:`ImageDetails` (or ``None``) into a plain dict, with
    the tag list clamped to at most :data:`MAX_TAGS` unique, non-empty tags."""
    if details is None:
        return None
    return {
        "title": (details.title or "").strip(),
        "description": (details.description or "").strip(),
        "tags": clean_tags(details.tags, MAX_TAGS),
    }


class RecognizeImageTool(AITool):
    """Find an item's image and ask a vision-capable model to describe it."""

    name = "recognize_image"
    title = _("Recognize image")
    description = _(
        "Generate a title, description and tags for an item's image using a "
        "vision-capable model."
    )

    def get_prompt(self):
        prompt = (getattr(self.settings, "recognize_image_prompt", "") or "").strip()
        return prompt or DEFAULT_VISION_PROMPT

    def available_for(self, context):
        if not self.is_enabled():
            return False
        field_name, _image = find_image(context)
        return field_name is not None

    def describe(self, image_data_uri, context=None, prompt=None):
        """Ask the vision model to describe ``image_data_uri`` (a ``data:`` URI
        or ``http(s)`` URL).

        Returns a ``{"title", "description", "tags"}`` dict, or ``None`` when
        the tool is disabled or no vision model is available/permitted.
        """
        if self._skip_if_disabled():
            return None
        details = self.service.analyze_image(
            prompt or self.get_prompt(),
            image_data_uri,
            model=self.get_model(),
            context=context,
            output_type=ImageDetails,
        )
        return _as_dict(details)

    def run(self, context, prompt=None):
        """Describe the image on ``context``.

        Returns a ``{"title", "description", "tags"}`` dict, or ``None`` when
        the tool is disabled, the item has no image, or no vision model is
        available.
        """
        if self._skip_if_disabled():
            return None
        _field_name, image = find_image(context)
        if image is None:
            logger.info(
                "recognize_image: %r has no image field; nothing to do.",
                getattr(context, "absolute_url", lambda: context)(),
            )
            return None
        return self.describe(image_to_data_uri(image), context=context, prompt=prompt)

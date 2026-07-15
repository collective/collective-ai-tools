"""REST endpoint backing the classic-UI "Get image details" edit-form button.

``POST <context>/@aitools-recognize-image`` with body::

    {"image": "data:image/png;base64,..."}   // or an http(s) image URL

Returns ``{"result": {"title": ..., "description": ..., "tags": [...]}}`` on
success, or ``{"error": ...}`` with a 4xx/5xx status. The endpoint just drives
the ``recognize_image`` ``IAITool`` — model choice, the prompt and the enabled
gate all live in the tool / control panel, so the browser never sees them.

The image travels in the request body (rather than being read from the
context) because the button fires on the *add/edit* form, before the file has
been uploaded and the content object saved.
"""

from collective.aitools import logger
from collective.aitools.tools import get_tool
from plone.restapi.deserializer import json_body
from plone.restapi.services import Service


class RecognizeImage(Service):
    """``POST @aitools-recognize-image`` — describe a supplied image."""

    def reply(self):
        data = json_body(self.request)
        image = (data.get("image") or "").strip()

        if not image:
            self.request.response.setStatus(400)
            return {"error": {"type": "BadRequest", "message": "image is required"}}

        tool = get_tool("recognize_image")
        if tool is None or not tool.is_enabled():
            self.request.response.setStatus(403)
            return {
                "error": {
                    "type": "Forbidden",
                    "message": "The 'Recognize image' tool is not enabled.",
                }
            }

        try:
            result = tool.describe(image, context=self.context)
        except Exception as exc:
            logger.exception("recognize_image endpoint failed")
            self.request.response.setStatus(500)
            return {"error": {"type": "InternalServerError", "message": str(exc)}}

        if not result:
            # Disabled is handled above; here it means no model resolved/permitted
            # or the model returned nothing.
            self.request.response.setStatus(502)
            return {
                "error": {
                    "type": "BadGateway",
                    "message": (
                        "No response from the AI service. Check that a "
                        "vision-capable model is configured in AI Settings."
                    ),
                }
            }

        return {"result": result}

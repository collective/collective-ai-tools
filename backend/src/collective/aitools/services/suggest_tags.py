"""REST endpoint backing the classic-UI "Suggest tags" edit-form button.

``POST <context>/@aitools-suggest-tags`` with body ``{"text": "..."}`` (the
current content text taken from the form). Returns ``{"result": ["tag", ...]}``
on success, or ``{"error": ...}`` with a 4xx/5xx status. The endpoint just
drives the ``suggest_tags`` ``IAITool`` (which is vocabulary-aware).
"""

from collective.aitools import logger
from collective.aitools.tools import get_tool
from plone.restapi.deserializer import json_body
from plone.restapi.services import Service


class SuggestTags(Service):
    """``POST @aitools-suggest-tags`` — suggest tags for supplied text."""

    def reply(self):
        data = json_body(self.request)
        text = (data.get("text") or "").strip()

        if not text:
            self.request.response.setStatus(400)
            return {"error": {"type": "BadRequest", "message": "text is required"}}

        tool = get_tool("suggest_tags")
        if tool is None or not tool.is_enabled():
            self.request.response.setStatus(403)
            return {
                "error": {
                    "type": "Forbidden",
                    "message": "The 'Suggest tags' tool is not enabled.",
                }
            }

        try:
            result = tool.suggest_for_text(text, context=self.context)
        except Exception as exc:
            logger.exception("suggest_tags endpoint failed")
            self.request.response.setStatus(500)
            return {"error": {"type": "InternalServerError", "message": str(exc)}}

        if not result:
            self.request.response.setStatus(502)
            return {
                "error": {
                    "type": "BadGateway",
                    "message": (
                        "No response from the AI service. Check that a "
                        "completion-capable model is configured in AI Settings."
                    ),
                }
            }

        return {"result": result}

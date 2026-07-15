"""REST endpoint backing the classic-UI "Summarize" edit-form button.

``POST <context>/@aitools-summarize`` with body ``{"text": "..."}`` (the
current content text taken from the form). Returns ``{"result": "<summary>"}``
on success, or ``{"error": ...}`` with a 4xx/5xx status. The endpoint just
drives the ``summarize`` ``IAITool``.
"""

from collective.aitools import logger
from collective.aitools.tools import get_tool
from plone.restapi.deserializer import json_body
from plone.restapi.services import Service


class Summarize(Service):
    """``POST @aitools-summarize`` — summarize supplied text."""

    def reply(self):
        data = json_body(self.request)
        text = (data.get("text") or "").strip()

        if not text:
            self.request.response.setStatus(400)
            return {"error": {"type": "BadRequest", "message": "text is required"}}

        tool = get_tool("summarize")
        if tool is None or not tool.is_enabled():
            self.request.response.setStatus(403)
            return {
                "error": {
                    "type": "Forbidden",
                    "message": "The 'Summarize' tool is not enabled.",
                }
            }

        try:
            result = tool.summarize_text(text, context=self.context)
        except Exception as exc:
            logger.exception("summarize endpoint failed")
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

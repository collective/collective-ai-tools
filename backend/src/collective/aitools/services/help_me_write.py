"""REST endpoint backing the classic-UI "Help me write" edit-form button.

``POST <context>/@aitools-help-me-write`` with body::

    {
      "operation": "draft" | "grammar" | "professional" | "casual",
      "topic": "...",   // required for operations needing input (draft)
      "text": "..."     // the existing/selected text for the other operations
    }

Returns ``{"result": "<generated text>"}`` on success, or ``{"error": ...}``
with a 4xx/5xx status. The endpoint just drives the ``help_me_write``
``IAITool`` — model choice, the operation system prompts and the enabled gate
all live in the tool / control panel, so the browser never sees them.
"""

from collective.aitools import logger
from collective.aitools.tools import get_tool
from collective.aitools.tools.help_me_write import OPERATIONS
from plone.restapi.deserializer import json_body
from plone.restapi.services import Service


class HelpMeWrite(Service):
    """``POST @aitools-help-me-write`` — run a writing operation."""

    def reply(self):
        data = json_body(self.request)
        operation = (data.get("operation") or "").strip()

        if not operation:
            self.request.response.setStatus(400)
            return {"error": {"type": "BadRequest", "message": "operation is required"}}
        if operation not in OPERATIONS:
            self.request.response.setStatus(400)
            return {
                "error": {
                    "type": "BadRequest",
                    "message": f"unknown operation {operation!r}",
                }
            }

        tool = get_tool("help_me_write")
        if tool is None or not tool.is_enabled():
            self.request.response.setStatus(403)
            return {
                "error": {
                    "type": "Forbidden",
                    "message": "The 'Help me write' tool is not enabled.",
                }
            }

        try:
            result = tool.run(
                self.context,
                operation=operation,
                text=data.get("text") or "",
                topic=data.get("topic") or "",
            )
        except Exception as exc:
            logger.exception("help_me_write endpoint failed")
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
                        "completion-capable model is configured in AI Settings."
                    ),
                }
            }

        return {"result": result}

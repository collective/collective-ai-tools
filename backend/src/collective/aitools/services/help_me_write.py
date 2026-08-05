"""REST endpoint backing the classic-UI "Help me write" edit-form button.

``POST <context>/@aitools-help-me-write`` with body::

    {
      "operation": "draft" | "grammar" | "professional" | "casual",
      "topic": "...",        // draft: what to write about
      "segments": ["..."],   // correct: the selection's text nodes, in order
      "html": "...",         // rewrite: the selection as an HTML fragment
      "text": "..."          // …or as plain text
    }

Which one to send follows the operation's
:func:`~collective.aitools.tools.help_me_write.operation_mode`, and each shape
answers differently:

``topic`` / ``text`` / ``html`` return ``{"result": "<generated text>"}``.
``html`` returns an HTML fragment meant to *replace* the selection — the tone
rewrites restructure the passage, so their markup is new by design.

``segments`` returns ``{"corrections": [{"id": 0, "text": "..."}, …]}`` holding
only the segments the model changed, so the caller can write each one back into
the text node it came from and leave the field's markup untouched. An empty list
means the model had nothing to change. It is the caller that decides where the
passage splits, because it is the caller (the TinyMCE integration) that owns the
DOM — see ``resources/js/help-me-write.pattern.js``.

Either way errors come back as ``{"error": ...}`` with a 4xx/5xx status. The
endpoint just drives the ``help_me_write`` ``IAITool`` — model choice, the
operation system prompts and the enabled gate all live in the tool / control
panel, so the browser never sees them.
"""

from collective.aitools import logger
from collective.aitools.tools import get_tool
from collective.aitools.tools.help_me_write import OPERATIONS
from collective.aitools.tools.help_me_write import OPERATIONS_REQUIRING_INPUT
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

        segments = data.get("segments")
        if segments is not None and not (
            isinstance(segments, list)
            and all(isinstance(segment, str) for segment in segments)
        ):
            self.request.response.setStatus(400)
            return {
                "error": {
                    "type": "BadRequest",
                    "message": "segments must be a list of strings",
                }
            }
        if segments is not None and operation in OPERATIONS_REQUIRING_INPUT:
            self.request.response.setStatus(400)
            return {
                "error": {
                    "type": "BadRequest",
                    "message": f"operation {operation!r} does not take segments",
                }
            }
        if data.get("html") and operation in OPERATIONS_REQUIRING_INPUT:
            self.request.response.setStatus(400)
            return {
                "error": {
                    "type": "BadRequest",
                    "message": f"operation {operation!r} does not take html",
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

        if segments is not None:
            return self._reply_segments(tool, operation, segments)

        try:
            result = tool.run(
                self.context,
                operation=operation,
                text=data.get("text") or "",
                topic=data.get("topic") or "",
                html=data.get("html") or "",
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

    def _reply_segments(self, tool, operation, segments):
        """Run the segmented path and shape the ``corrections`` response."""
        try:
            corrections = tool.run_segments(
                self.context, operation=operation, segments=segments
            )
        except Exception as exc:
            logger.exception("help_me_write endpoint failed")
            self.request.response.setStatus(500)
            return {"error": {"type": "InternalServerError", "message": str(exc)}}

        # An empty mapping is a valid answer ("nothing to change"); only ``None``
        # means the call did not happen, so the two must not be conflated here.
        if corrections is None:
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

        return {
            "corrections": [
                {"id": index, "text": text}
                for index, text in sorted(corrections.items())
            ]
        }

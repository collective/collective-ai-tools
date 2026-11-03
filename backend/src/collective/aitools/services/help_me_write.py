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

Either way errors come back as ``{"error": ...}`` with a 4xx/5xx status. With
``"async": true`` the endpoint answers ``202 {"task_id", "status": "running"}``
instead and the same body arrives through ``@aitools-task-status``. The
endpoint just drives the ``help_me_write`` ``IAITool`` — model choice, the
operation system prompts and the enabled gate all live in the tool / control
panel, so the browser never sees them.
"""

from collective.aitools.services.base import BadInput
from collective.aitools.services.base import NO_COMPLETION
from collective.aitools.services.base import ToolService
from collective.aitools.services.base import ToolFailed
from collective.aitools.tools import get_tool
from collective.aitools.tools.help_me_write import OPERATIONS
from collective.aitools.tools.help_me_write import OPERATIONS_REQUIRING_INPUT


def help_me_write_job(context, request, operation, text, topic, html):
    result = get_tool("help_me_write").run(
        context, operation=operation, text=text, topic=topic, html=html
    )
    if not result:
        # Disabled is handled by the endpoint; here it means no model
        # resolved/permitted or the model returned nothing.
        raise ToolFailed(NO_COMPLETION)
    return {"result": result}


def help_me_write_segments_job(context, request, operation, segments):
    corrections = get_tool("help_me_write").run_segments(
        context, operation=operation, segments=segments
    )
    # An empty mapping is a valid answer ("nothing to change"); only ``None``
    # means the call did not happen, so the two must not be conflated here.
    if corrections is None:
        raise ToolFailed(NO_COMPLETION)
    return {
        "corrections": [
            {"id": index, "text": text} for index, text in sorted(corrections.items())
        ]
    }


class HelpMeWrite(ToolService):
    """``POST @aitools-help-me-write`` — run a writing operation."""

    tool_name = "help_me_write"
    disabled_message = "The 'Help me write' tool is not enabled."

    def validate(self, data):
        operation = (data.get("operation") or "").strip()
        if not operation:
            raise BadInput("operation is required")
        if operation not in OPERATIONS:
            raise BadInput(f"unknown operation {operation!r}")

        segments = data.get("segments")
        if segments is not None:
            if not (
                isinstance(segments, list)
                and all(isinstance(segment, str) for segment in segments)
            ):
                raise BadInput("segments must be a list of strings")
            if operation in OPERATIONS_REQUIRING_INPUT:
                raise BadInput(f"operation {operation!r} does not take segments")
            return {"operation": operation, "segments": segments}

        if data.get("html") and operation in OPERATIONS_REQUIRING_INPUT:
            raise BadInput(f"operation {operation!r} does not take html")
        return {
            "operation": operation,
            "text": data.get("text") or "",
            "topic": data.get("topic") or "",
            "html": data.get("html") or "",
        }

    def get_job(self, kwargs):
        if "segments" in kwargs:
            return help_me_write_segments_job
        return help_me_write_job

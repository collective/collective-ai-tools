"""REST endpoint backing the classic-UI "Summarize" edit-form button.

``POST <context>/@aitools-summarize`` with body ``{"text": "..."}`` (the
current content text taken from the form). Returns ``{"result": "<summary>"}``
on success, or ``{"error": ...}`` with a 4xx/5xx status. With ``"async": true``
it answers ``202 {"task_id", "status": "running"}`` instead and the same body
arrives through ``@aitools-task-status``. The endpoint just drives the
``summarize`` ``IAITool``.
"""

from collective.aitools.services.base import BadInput
from collective.aitools.services.base import NO_COMPLETION
from collective.aitools.services.base import ToolService
from collective.aitools.services.base import ToolFailed
from collective.aitools.tools import get_tool


def summarize_job(context, request, text):
    result = get_tool("summarize").summarize_text(text, context=context)
    if not result:
        raise ToolFailed(NO_COMPLETION)
    return {"result": result}


class Summarize(ToolService):
    """``POST @aitools-summarize`` — summarize supplied text."""

    tool_name = "summarize"
    disabled_message = "The 'Summarize' tool is not enabled."
    job = staticmethod(summarize_job)

    def validate(self, data):
        text = (data.get("text") or "").strip()
        if not text:
            raise BadInput("text is required")
        return {"text": text}

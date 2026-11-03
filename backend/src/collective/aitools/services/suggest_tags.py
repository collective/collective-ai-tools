"""REST endpoint backing the classic-UI "Suggest tags" edit-form button.

``POST <context>/@aitools-suggest-tags`` with body ``{"text": "..."}`` (the
current content text taken from the form). Returns ``{"result": ["tag", ...]}``
on success, or ``{"error": ...}`` with a 4xx/5xx status. With ``"async": true``
it answers ``202 {"task_id", "status": "running"}`` instead and the same body
arrives through ``@aitools-task-status``. The endpoint just drives the
``suggest_tags`` ``IAITool`` (which is vocabulary-aware).
"""

from collective.aitools.services.base import BadInput
from collective.aitools.services.base import NO_COMPLETION
from collective.aitools.services.base import ToolService
from collective.aitools.services.base import ToolFailed
from collective.aitools.tools import get_tool


def suggest_tags_job(context, request, text):
    result = get_tool("suggest_tags").suggest_for_text(text, context=context)
    if not result:
        raise ToolFailed(NO_COMPLETION)
    return {"result": result}


class SuggestTags(ToolService):
    """``POST @aitools-suggest-tags`` — suggest tags for supplied text."""

    tool_name = "suggest_tags"
    disabled_message = "The 'Suggest tags' tool is not enabled."
    job = staticmethod(suggest_tags_job)

    def validate(self, data):
        text = (data.get("text") or "").strip()
        if not text:
            raise BadInput("text is required")
        return {"text": text}

"""REST endpoint backing the classic-UI "Get image details" edit-form button.

``POST <context>/@aitools-recognize-image`` with body::

    {"image": "data:image/png;base64,..."}   // or an http(s) image URL

Returns ``{"result": {"title": ..., "description": ..., "tags": [...]}}`` on
success, or ``{"error": ...}`` with a 4xx/5xx status. With ``"async": true`` it
answers ``202 {"task_id", "status": "running"}`` instead and the same body
arrives through ``@aitools-task-status``. The endpoint just drives
the ``recognize_image`` ``IAITool`` — model choice, the prompt and the enabled
gate all live in the tool / control panel, so the browser never sees them.

The image travels in the request body (rather than being read from the
context) because the button fires on the *add/edit* form, before the file has
been uploaded and the content object saved.
"""

from collective.aitools.services.base import BadInput
from collective.aitools.services.base import ToolService
from collective.aitools.services.base import ToolFailed
from collective.aitools.tools import get_tool


NO_VISION = (
    "No response from the AI service. Check that a "
    "vision-capable model is configured in AI Settings."
)


def recognize_image_job(context, request, image):
    result = get_tool("recognize_image").describe(image, context=context)
    if not result:
        # Disabled is handled by the endpoint; here it means no model
        # resolved/permitted or the model returned nothing.
        raise ToolFailed(NO_VISION)
    return {"result": result}


class RecognizeImage(ToolService):
    """``POST @aitools-recognize-image`` — describe a supplied image."""

    tool_name = "recognize_image"
    disabled_message = "The 'Recognize image' tool is not enabled."
    job = staticmethod(recognize_image_job)

    def validate(self, data):
        image = (data.get("image") or "").strip()
        if not image:
            raise BadInput("image is required")
        return {"image": image}

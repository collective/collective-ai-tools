"""Shared plumbing for the endpoints that run one ``IAITool``.

Every tool endpoint does the same thing around its model call: check the
request, check the tool is enabled, then either run the call in the request or
hand it to a background task the client polls (``"async": true`` in the body).
:class:`ToolService` does all of that; a subclass only says which tool it
drives, how to validate its body, and which *job* produces its answer.

A job is a module-level function ``job(context, request, **kwargs)`` returning
the endpoint's 200 body. Both modes call the same job, so the body a client
polls for is exactly the body it would have received synchronously. A job
raises :class:`ToolFailed` when the model gave nothing usable (answered 502
inline); anything else it raises is a 500.
"""

from collective.aisettings.services.tasks import TaskStoreShuttingDown
from collective.aitools import logger
from collective.aitools.services.async_runner import start_task
from collective.aitools.services.async_runner import ToolFailed
from collective.aitools.tools import get_tool
from plone.restapi.deserializer import json_body
from plone.restapi.services import Service


#: The 502 message of the tools that make a plain completion call.
NO_COMPLETION = (
    "No response from the AI service. Check that a "
    "completion-capable model is configured in AI Settings."
)


class BadInput(Exception):
    """The request body is invalid; answered 400 with this message."""


class ToolService(Service):
    """``POST`` endpoint that runs one tool, inline or as a polled task."""

    #: ``get_tool()`` name; also the task label (it reaches Sentry reports).
    tool_name = None
    #: The 403 message when the tool is missing or disabled.
    disabled_message = None
    #: Start a task whatever the body says (the assistant has no inline mode).
    always_async = False
    #: The job; a ``staticmethod`` so it is not bound to the service.
    job = None

    def validate(self, data):
        """Return the job's keyword arguments, or raise :class:`BadInput`."""
        raise NotImplementedError

    def get_job(self, kwargs):
        """The job for these arguments; override when it depends on them."""
        return self.job

    def _error(self, status, type_, message):
        self.request.response.setStatus(status)
        return {"error": {"type": type_, "message": message}}

    def reply(self):
        self.request.response.setHeader("Cache-Control", "no-store")
        data = json_body(self.request)
        try:
            kwargs = self.validate(data)
        except BadInput as exc:
            return self._error(400, "BadRequest", str(exc))

        tool = get_tool(self.tool_name)
        if tool is None or not tool.is_enabled():
            return self._error(403, "Forbidden", self.disabled_message)

        job = self.get_job(kwargs)
        if self.always_async or data.get("async") is True:
            return self._start(job, kwargs)
        return self._run_inline(job, kwargs)

    def _start(self, job, kwargs):
        try:
            task_id = start_task(
                self.context, self.request, self.tool_name, job, **kwargs
            )
        except TaskStoreShuttingDown:
            # The process is going away; the client retries on another one.
            self.request.response.setHeader("Retry-After", "2")
            return self._error(
                503,
                "ServiceUnavailable",
                "The server is restarting. Please try again.",
            )
        except Exception as exc:
            logger.exception("%s endpoint failed to start task", self.tool_name)
            return self._error(500, "InternalServerError", str(exc))
        self.request.response.setStatus(202)
        return {"task_id": task_id, "status": "running"}

    def _run_inline(self, job, kwargs):
        try:
            return job(self.context, self.request, **kwargs)
        except ToolFailed as exc:
            return self._error(502, "BadGateway", str(exc))
        except Exception as exc:
            logger.exception("%s endpoint failed", self.tool_name)
            return self._error(500, "InternalServerError", str(exc))

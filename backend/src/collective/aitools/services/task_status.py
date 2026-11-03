"""``GET <context>/@aitools-task-status/<task_id>`` — poll a tool's task.

Every tool endpoint started with ``"async": true`` (and the Assistant, always)
answers ``202 {"task_id"}``; this is where the client then reads the outcome.
Returns ``{"task_id", "status": "running"}`` while the worker is busy,
``{"task_id", "status": "done", "result": {...}}`` on success, where ``result``
is the body the endpoint would have answered synchronously, or ``{"task_id",
"status": "error", "error": "..."}`` on failure (plus ``"retryable": true``
when a shutdown interrupted it). Only the user who started the task can read it
(when collective.aisettings' shared task store is on), and the answer is never
cacheable. Also registered as ``@aitools-assistant-status``, its name before
the other tools could run as tasks.
"""

from collective.aisettings.services.tasks import get_task
from collective.aisettings.services.tasks import shared_store_enabled
from collective.aitools import logger
from plone import api
from plone.restapi.services import Service
from zope.interface import implementer
from zope.publisher.interfaces import IPublishTraverse


_warned = False


def _warn_unshared_store():
    """Say once per process why polls may be missing their tasks.

    Without the shared store a task lives in the process that started it, so
    with several Zope processes a poll that lands elsewhere gets a 404 and the
    edit-form tools fall back to a synchronous call — working, but paying for
    the model call twice. This is the trace of that in the logs.
    """
    global _warned
    if _warned:
        return
    _warned = True
    logger.warning(
        "aitools task not found; with more than one Zope process set "
        "COLLECTIVE_AISETTINGS_TASK_STORE so tasks are shared between them"
    )


@implementer(IPublishTraverse)
class TaskStatus(Service):
    """``GET @aitools-task-status/<task_id>`` — poll a task."""

    # Populated by publishTraverse with the path segments after the service
    # name (the task id). Class-level default so no custom __init__ is needed
    # (plone.rest sets context/request on the instance itself).
    params: list[str] = None

    def publishTraverse(self, request, name):
        if self.params is None:
            self.params = []
        self.params.append(name)
        return self

    def reply(self):
        self.request.response.setHeader("Cache-Control", "no-store")
        if not self.params:
            self.request.response.setStatus(400)
            return {"error": {"type": "BadRequest", "message": "task_id required"}}
        task_id = self.params[0]
        task = get_task(task_id, owner=api.user.get_current().getId())
        if task is None:
            if not shared_store_enabled():
                _warn_unshared_store()
            self.request.response.setStatus(404)
            return {"error": {"type": "NotFound", "message": "task not found"}}
        return {"task_id": task_id, **task}

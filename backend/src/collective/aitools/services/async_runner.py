"""Run the agentic Assistant on a background thread.

The Assistant's turn is slow: it makes several LLM tool-calling round-trips, so
running it inside the request thread risks HTTP timeouts and ties up a ZServer
worker. Instead the endpoint enqueues the turn here, gets a task id back, and the
client polls for the result.

Unlike ``collective.aisettings``'s async ``@ai`` endpoint (which is deliberately
tool-less), the Assistant loop runs *capabilities* that need Plone: catalog
searches, object wake-ups, ``getSecurityManager()`` permission checks, the local
registry, and ``brain.getURL()`` links. A bare worker thread has none of that,
so :func:`_worker` bootstraps a full environment — its own ZODB connection, the
active site, the current user's security context, and a request rebuilt from the
originating request's environ (so generated URLs are correct).

Task state is kept in ``collective.aisettings``'s in-memory task registry, which
already gives us the exact ``running`` / ``done`` / ``error`` contract (and
pruning) the client polls against.
"""

from AccessControl.SecurityManagement import newSecurityManager
from AccessControl.SecurityManagement import noSecurityManager
from collective.aisettings.services.tasks import complete_task
from collective.aisettings.services.tasks import create_task
from collective.aisettings.services.tasks import fail_task
from collective.aitools import logger
from collective.aitools.tools import get_tool
from io import BytesIO
from plone import api
from threading import Thread
from zope.component.hooks import setSite
from ZPublisher.BaseRequest import RequestContainer
from ZPublisher.HTTPRequest import HTTPRequest
from ZPublisher.HTTPResponse import HTTPResponse

import transaction


#: Request environ keys we copy so the worker's rebuilt request produces the
#: same absolute URLs (host, port, virtual-hosting) the user would see.
_ENVIRON_KEYS = (
    "SERVER_NAME",
    "SERVER_PORT",
    "SERVER_URL",
    "HTTP_HOST",
    "SCRIPT_NAME",
    "REQUEST_METHOD",
    "VirtualHostBase",
    "VirtualHostRoot",
    "ACTUAL_URL",
    "URL",
)


def _no_reply(result) -> bool:
    """True when the tool produced nothing usable (disabled / no model)."""
    return not result or not result.get("reply")


def _snapshot_environ(request) -> dict:
    environ = getattr(request, "environ", None) or {}
    snapshot = {
        key: environ[key] for key in _ENVIRON_KEYS if environ.get(key) is not None
    }
    # HTTPRequest needs at least these to build URLs; fill sane defaults.
    snapshot.setdefault("SERVER_NAME", "localhost")
    snapshot.setdefault("SERVER_PORT", "80")
    snapshot.setdefault("REQUEST_METHOD", "GET")
    return snapshot


def _resolve_user(app, portal, user_id):
    """Return the acquisition-wrapped PAS user for ``user_id``, or ``None``."""
    for acl_users in (portal.acl_users, app.acl_users):
        user = acl_users.getUserById(user_id)
        if user is not None:
            return user.__of__(acl_users)
    return None


def _run_and_store(context, request, task_id, messages):
    """Run the Assistant tool and record the outcome on ``task_id``.

    Assumes the caller has already established the site and security context.
    Kept separate from :func:`_worker` so the agent logic can be tested without
    spinning up a thread / second ZODB connection.
    """
    try:
        tool = get_tool("assistant")
        if tool is None or not tool.is_enabled():
            fail_task(task_id, "The 'Assistant' tool is not enabled.")
            return
        result = tool.run(context, messages=messages, request=request)
        if _no_reply(result):
            fail_task(
                task_id,
                (
                    "No response from the AI service. Check that a "
                    "tool-calling-capable model is configured in AI Settings."
                ),
            )
            return
        complete_task(task_id, {
            "reply": result["reply"],
            "steps": result.get("steps", []),
            "proposals": result.get("proposals", []),
        })
    except Exception as exc:
        logger.exception("assistant task %s failed", task_id)
        fail_task(task_id, str(exc))


def _worker(db, environ, context_path, portal_path, user_id, task_id, messages):
    """Background body: bootstrap Plone, run the Assistant, store the outcome."""
    conn = db.open()
    try:
        request = HTTPRequest(BytesIO(b""), dict(environ), HTTPResponse())
        app = conn.root()["Application"].__of__(RequestContainer(REQUEST=request))
        portal = app.unrestrictedTraverse(portal_path)
        context = app.unrestrictedTraverse(context_path)
        setSite(portal)

        user = _resolve_user(app, portal, user_id)
        if user is None:
            fail_task(task_id, f"user {user_id!r} not found")
            return
        newSecurityManager(request, user)

        _run_and_store(context, request, task_id, messages)
    except Exception as exc:
        logger.exception("assistant task %s failed to bootstrap", task_id)
        fail_task(task_id, str(exc))
    finally:
        # The loop is read-only (writes happen only in the confirmed apply
        # endpoint); abort so nothing lingers and no conflict can occur.
        transaction.abort()
        noSecurityManager()
        setSite(None)
        conn.close()


def start_assistant_task(context, request, messages) -> str:
    """Enqueue an Assistant turn on a daemon thread; return its task id.

    Captures everything the worker needs while we still hold a live connection
    and request (the ZODB handle, physical paths, the current user id, and an
    environ snapshot), then hands off to :func:`_worker`.
    """
    db = context._p_jar.db()
    context_path = context.getPhysicalPath()
    portal_path = api.portal.get().getPhysicalPath()
    user_id = api.user.get_current().getId()
    environ = _snapshot_environ(request)

    task_id = create_task()
    Thread(
        target=_worker,
        args=(db, environ, context_path, portal_path, user_id, task_id, messages),
        daemon=True,
        name=f"aitools-assistant-{task_id[:8]}",
    ).start()
    return task_id

"""Run a tool's model call on a background thread.

A model call can outlast the proxies in front of Zope (Varnish answers 503
after its first-byte timeout while Zope keeps working) and ties up a worker
thread for its whole length. So an endpoint can hand the call to
:func:`start_task`, answer ``202`` with a task id at once, and let the client
poll for the result. The Assistant always does; the edit-form tools do when the
request asks for it (see :class:`~collective.aitools.services.base.ToolService`).

Unlike ``collective.aisettings``'s async ``@ai`` endpoint (which is deliberately
tool-less), the jobs run here need Plone: model resolution reads the registry,
the model's permission gate checks the current user, ``suggest_tags`` reads the
catalog, and the Assistant's capabilities search, wake objects and build
``brain.getURL()`` links. A bare worker thread has none of that, so
:func:`_worker` bootstraps a full environment — its own ZODB connection, the
active site, the current user's security context, and a request rebuilt from the
originating request's environ *plus* its virtual-hosting state (see
:func:`_snapshot_url_state`), so generated URLs match what the user sees.

Task state is kept in ``collective.aisettings``'s task store (in-process, or
memcached when ``COLLECTIVE_AISETTINGS_TASK_STORE`` is set), which gives us the
``running`` / ``done`` / ``error`` contract the client polls against.
"""

from AccessControl.SecurityManagement import newSecurityManager
from AccessControl.SecurityManagement import noSecurityManager
from collective.aisettings.services.tasks import complete_task
from collective.aisettings.services.tasks import create_task
from collective.aisettings.services.tasks import fail_task
from collective.aitools import logger
from io import BytesIO
from plone import api
from threading import Thread
from zope.component.hooks import setSite
from ZPublisher.BaseRequest import RequestContainer
from ZPublisher.HTTPRequest import HTTPRequest
from ZPublisher.HTTPResponse import HTTPResponse

import transaction


#: Request environ keys we copy so the worker's rebuilt request starts from the
#: same host/port/method as the originating one. This is only the *raw* CGI
#: view of the request; see :func:`_snapshot_url_state` for the virtual-hosting
#: state that actually decides what generated URLs look like.
_ENVIRON_KEYS = (
    "SERVER_NAME",
    "SERVER_PORT",
    "SERVER_URL",
    "HTTP_HOST",
    "SCRIPT_NAME",
    "REQUEST_METHOD",
    "ACTUAL_URL",
    "URL",
)


class ToolFailed(Exception):
    """The model produced nothing usable; the message says what to check.

    Answered 502 when the job runs inline, stored as the task's error when it
    runs here."""


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


def _snapshot_url_state(request) -> dict:
    """Capture the virtual-hosting state that shapes generated URLs.

    ``VirtualHostMonster`` never touches ``environ``: ``VirtualHostBase`` and
    ``VirtualHostRoot`` are traversal path segments it consumes, and its effects
    land in ``request.other['SERVER_URL']`` (``setServerURL``), plus
    ``request._script`` and ``other['VirtualRootPhysicalPath']``
    (``setVirtualRoot``). The environ keeps whatever the upstream hop sent, which
    behind a proxy is an internal name such as ``varnish:6080``.

    So an environ-only snapshot leaves the worker with that internal host and no
    virtual root, and every ``absolute_url()`` / ``brain.getURL()`` it produces
    comes out as ``http://varnish:6080/<site-id>/...`` instead of the public URL.
    """
    other = getattr(request, "other", None) or {}
    return {
        "server_url": other.get("SERVER_URL"),
        "script": list(getattr(request, "_script", ())),
        "vh_root": other.get("VirtualRootPhysicalPath"),
    }


def _apply_url_state(request, url_state) -> None:
    """Replay a :func:`_snapshot_url_state` snapshot onto a rebuilt request."""
    if not url_state:
        return
    if url_state.get("server_url"):
        request.other["SERVER_URL"] = url_state["server_url"]
    request._script[:] = list(url_state.get("script") or ())
    if url_state.get("vh_root"):
        request.other["VirtualRootPhysicalPath"] = url_state["vh_root"]
    request._resetURLS()


def _resolve_user(app, portal, user_id):
    """Return the acquisition-wrapped PAS user for ``user_id``, or ``None``."""
    for acl_users in (portal.acl_users, app.acl_users):
        user = acl_users.getUserById(user_id)
        if user is not None:
            return user.__of__(acl_users)
    return None


def _run_and_store(context, request, task_id, job, kwargs):
    """Run ``job`` and record its outcome on ``task_id``.

    Assumes the caller has already established the site and security context.
    Kept separate from :func:`_worker` so jobs can be tested without spinning
    up a thread / second ZODB connection.
    """
    try:
        complete_task(task_id, job(context, request, **kwargs))
    except ToolFailed as exc:
        fail_task(task_id, str(exc))
    except Exception as exc:
        logger.exception("aitools task %s failed", task_id)
        fail_task(task_id, str(exc))


def _worker(
    db, environ, url_state, context_path, portal_path, user_id, task_id, job, kwargs
):
    """Background body: bootstrap Plone, run the job, store the outcome."""
    conn = db.open()
    try:
        request = HTTPRequest(BytesIO(b""), dict(environ), HTTPResponse())
        _apply_url_state(request, url_state)
        app = conn.root()["Application"].__of__(RequestContainer(REQUEST=request))
        portal = app.unrestrictedTraverse(portal_path)
        context = app.unrestrictedTraverse(context_path)
        setSite(portal)

        user = _resolve_user(app, portal, user_id)
        if user is None:
            fail_task(task_id, f"user {user_id!r} not found")
            return
        newSecurityManager(request, user)

        _run_and_store(context, request, task_id, job, kwargs)
    except Exception as exc:
        logger.exception("aitools task %s failed to bootstrap", task_id)
        fail_task(task_id, str(exc))
    finally:
        # Every job is read-only (the assistant's writes happen only in the
        # confirmed apply endpoint); abort so nothing lingers and no conflict
        # can occur.
        transaction.abort()
        noSecurityManager()
        setSite(None)
        conn.close()


def start_task(context, request, label, job, **kwargs) -> str:
    """Run ``job(context, request, **kwargs)`` on a daemon thread.

    Returns the task id the client polls. Captures everything the worker needs
    while we still hold a live connection and request (the ZODB handle,
    physical paths, the current user id, and both halves of the request
    snapshot), then hands off to :func:`_worker`. ``label`` names the task in
    collective.aisettings' logs and lost-task events.
    """
    db = context._p_jar.db()
    context_path = context.getPhysicalPath()
    portal_path = api.portal.get().getPhysicalPath()
    user_id = api.user.get_current().getId()
    environ = _snapshot_environ(request)
    url_state = _snapshot_url_state(request)

    # Raises TaskStoreShuttingDown once the process is going away; the
    # endpoint answers 503 so the client retries on another instance.
    task_id = create_task(owner=user_id, label=label)
    Thread(
        target=_worker,
        args=(
            db,
            environ,
            url_state,
            context_path,
            portal_path,
            user_id,
            task_id,
            job,
            kwargs,
        ),
        daemon=True,
        name=f"aitools-{label}-{task_id[:8]}",
    ).start()
    return task_id


def start_assistant_task(context, request, messages) -> str:
    """Deprecated: ``start_task(..., "assistant", assistant_job, ...)``."""
    from collective.aitools.services.assistant import assistant_job

    return start_task(context, request, "assistant", assistant_job, messages=messages)

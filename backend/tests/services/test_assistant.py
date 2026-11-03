"""Tests for the async chat Assistant endpoint and background runner."""

from collective.aisettings.interfaces import IAIService
from collective.aisettings.services.tasks import complete_task
from collective.aisettings.services.tasks import create_task
from collective.aisettings.services import tasks
from collective.aisettings.services.tasks import get_task
from collective.aitools.services import async_runner
from collective.aitools.services.assistant import Assistant
from collective.aitools.services.assistant import assistant_job
from collective.aitools.services.assistant import AssistantStatus
from io import BytesIO
from plone import api
from zope.component import getGlobalSiteManager
from zope.interface import implementer
from ZPublisher.HTTPRequest import HTTPRequest
from ZPublisher.HTTPResponse import HTTPResponse

import json
import pytest


ENABLED = "collective.aitools.interfaces.IAIToolsSettings.assistant_enabled"


@implementer(IAIService)
class FakeAIService:
    """Minimal IAIService: one tool-call turn with no tool calls (final reply)."""

    def __init__(self, message=None):
        self.message = message or {"content": "Hello there", "tool_calls": []}
        self.calls = []

    def tool_call(self, messages, tools=None, model=None, context=None):
        self.calls.append(messages)
        return self.message


@pytest.fixture
def fake_service(portal):
    gsm = getGlobalSiteManager()
    original = gsm.queryUtility(IAIService)
    fake = FakeAIService()
    gsm.registerUtility(fake, IAIService)
    yield fake
    gsm.unregisterUtility(fake, IAIService)
    if original is not None:
        gsm.registerUtility(original, IAIService)


def _make_request(body):
    response = HTTPResponse()
    environ = {
        "REQUEST_METHOD": "POST",
        "SERVER_NAME": "localhost",
        "SERVER_PORT": "80",
    }
    request = HTTPRequest(BytesIO(b""), environ, response)
    request.set("BODY", json.dumps(body))
    return request


def _vhm_request(portal):
    """A request as VirtualHostMonster leaves it behind a proxy.

    Zope is reached over an internal hop (``varnish:6080``), while the rewrite
    ``/VirtualHostBase/https/example.com/<site>/VirtualHostRoot/...`` makes the
    site answer as ``https://example.com/``. Mimics what ``setServerURL`` and
    ``setVirtualRoot`` do, without needing a real traversal.
    """
    environ = {
        "REQUEST_METHOD": "POST",
        "SERVER_NAME": "varnish",
        "SERVER_PORT": "6080",
        "HTTP_HOST": "varnish:6080",
    }
    request = HTTPRequest(BytesIO(b""), environ, HTTPResponse())
    request.setServerURL("https", "example.com", 443)
    request._script[:] = []
    request.other["VirtualRootPhysicalPath"] = portal.getPhysicalPath()
    request._resetURLS()
    return request


def _reply(portal, body):
    request = _make_request(body)
    service = Assistant()
    service.context = portal
    service.request = request
    return service.reply(), request.response.getStatus()


class FakeThread:
    """Stand-in for threading.Thread that never actually runs the worker."""

    def __init__(self, *args, **kwargs):
        pass

    def start(self):
        pass


class TestAssistantEndpoint:
    def test_empty_messages_is_bad_request(self, portal, fake_service):
        result, status = _reply(portal, {"messages": []})
        assert status == 400
        assert "error" in result

    def test_disabled_is_forbidden(self, portal, fake_service):
        result, status = _reply(
            portal, {"messages": [{"role": "user", "content": "hi"}]}
        )
        assert status == 403
        assert "error" in result

    def test_enabled_starts_task(self, portal, fake_service, monkeypatch):
        # Don't spawn a real background thread; just check the endpoint hands
        # back a running task id.
        monkeypatch.setattr(async_runner, "Thread", FakeThread)
        api.portal.set_registry_record(ENABLED, True)

        result, status = _reply(
            portal, {"messages": [{"role": "user", "content": "hi"}]}
        )
        assert status == 202
        task_id = result["task_id"]
        assert result["status"] == "running"
        assert get_task(task_id) is not None

    def test_not_cacheable(self, portal, fake_service):
        request = _make_request({"messages": []})
        service = Assistant()
        service.context = portal
        service.request = request
        service.reply()
        assert request.response.getHeader("Cache-Control") == "no-store"

    def test_shutting_down_is_unavailable(self, portal, fake_service, monkeypatch):
        def shutting_down(*args, **kwargs):
            raise tasks.TaskStoreShuttingDown()

        monkeypatch.setattr(async_runner, "create_task", shutting_down)
        api.portal.set_registry_record(ENABLED, True)
        request = _make_request({"messages": [{"role": "user", "content": "hi"}]})
        service = Assistant()
        service.context = portal
        service.request = request
        result = service.reply()
        assert request.response.getStatus() == 503
        assert request.response.getHeader("Retry-After") == "2"
        assert result["error"]["type"] == "ServiceUnavailable"

    def test_task_carries_owner_and_label(self, portal, fake_service, monkeypatch):
        captured = {}

        def capture(**kwargs):
            captured.update(kwargs)
            return "task-id"

        monkeypatch.setattr(async_runner, "Thread", FakeThread)
        monkeypatch.setattr(async_runner, "create_task", capture)
        api.portal.set_registry_record(ENABLED, True)
        _reply(portal, {"messages": [{"role": "user", "content": "hi"}]})
        assert captured == {
            "owner": api.user.get_current().getId(),
            "label": "assistant",
        }


class TestAssistantRunner:
    def test_run_and_store_completes(self, portal, fake_service):
        api.portal.set_registry_record(ENABLED, True)
        task_id = create_task()
        request = _make_request({})

        async_runner._run_and_store(
            portal,
            request,
            task_id,
            assistant_job,
            {"messages": [{"role": "user", "content": "hi"}]},
        )

        task = get_task(task_id)
        assert task["status"] == "done"
        assert task["result"]["reply"] == "Hello there"
        assert task["result"]["steps"] == []
        assert task["result"]["proposals"] == []
        assert fake_service.calls  # the model was actually consulted

    def test_run_and_store_disabled_fails(self, portal, fake_service):
        # Tool disabled → task fails rather than completing.
        task_id = create_task()
        request = _make_request({})

        async_runner._run_and_store(
            portal,
            request,
            task_id,
            assistant_job,
            {"messages": [{"role": "user", "content": "hi"}]},
        )

        task = get_task(task_id)
        assert task["status"] == "error"
        assert "error" in task

    def test_worker_request_keeps_virtual_hosting(self, portal):
        # The worker's rebuilt request must generate the same public URLs the
        # user sees, not the internal host + site id an environ-only snapshot
        # would leave behind.
        with api.env.adopt_roles(["Manager"]):
            doc = api.content.create(
                container=portal, type="Document", id="a-doc", title="A doc"
            )
        original = _vhm_request(portal)

        environ = async_runner._snapshot_environ(original)
        url_state = async_runner._snapshot_url_state(original)

        rebuilt = HTTPRequest(BytesIO(b""), dict(environ), HTTPResponse())
        async_runner._apply_url_state(rebuilt, url_state)

        # This is what brain.getURL() / absolute_url() go through.
        assert rebuilt.physicalPathToURL(doc.getPhysicalPath()) == (
            "https://example.com/a-doc"
        )
        assert original.physicalPathToURL(doc.getPhysicalPath()) == (
            "https://example.com/a-doc"
        )

    def test_worker_request_without_virtual_hosting(self, portal):
        # No VHM in play: URLs keep the plain host and the site id, as they do
        # for a request that reaches Zope directly.
        with api.env.adopt_roles(["Manager"]):
            doc = api.content.create(
                container=portal, type="Document", id="a-doc", title="A doc"
            )
        original = _make_request({})

        rebuilt = HTTPRequest(
            BytesIO(b""), dict(async_runner._snapshot_environ(original)), HTTPResponse()
        )
        async_runner._apply_url_state(
            rebuilt, async_runner._snapshot_url_state(original)
        )

        assert rebuilt.physicalPathToURL(doc.getPhysicalPath()) == (
            original.physicalPathToURL(doc.getPhysicalPath())
        )

    def test_start_task_passes_url_state_to_worker(self, portal, monkeypatch):
        # Guard the wiring: whatever _snapshot_url_state captured has to reach
        # the worker, or the fix above is dead code in production.
        captured = {}

        class CapturingThread(FakeThread):
            def __init__(self, *args, **kwargs):
                captured.update(kwargs)

        monkeypatch.setattr(async_runner, "Thread", CapturingThread)
        request = _vhm_request(portal)

        async_runner.start_assistant_task(
            portal, request, [{"role": "user", "content": "hi"}]
        )

        assert async_runner._snapshot_url_state(request) in captured["args"]


def _status_service(portal):
    service = AssistantStatus()
    service.context = portal
    service.request = _make_request({})
    return service


class TestAssistantStatus:
    def test_unknown_task_is_not_found(self, portal):
        service = _status_service(portal)
        service.publishTraverse(service.request, "does-not-exist")
        result = service.reply()
        assert service.request.response.getStatus() == 404
        assert "error" in result

    def test_missing_task_id_is_bad_request(self, portal):
        service = _status_service(portal)
        result = service.reply()
        assert service.request.response.getStatus() == 400
        assert "error" in result

    def test_completed_task_is_returned(self, portal):
        task_id = create_task()
        complete_task(task_id, {"reply": "done", "steps": [], "proposals": []})

        service = _status_service(portal)
        service.publishTraverse(service.request, task_id)
        result = service.reply()

        assert result["task_id"] == task_id
        assert result["status"] == "done"
        assert result["result"]["reply"] == "done"
        assert service.request.response.getHeader("Cache-Control") == "no-store"

    def test_other_users_task_is_not_found(self, portal):
        """With the shared store on, a task is only readable by its owner."""
        from pymemcache.test.utils import MockMemcacheClient

        tasks.reset(tasks.SharedTaskStore(MockMemcacheClient()))
        try:
            task_id = create_task(owner="someone-else")
            service = _status_service(portal)
            service.publishTraverse(service.request, task_id)
            service.reply()
            assert service.request.response.getStatus() == 404
        finally:
            tasks.reset()

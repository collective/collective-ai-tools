"""Tests for the async chat Assistant endpoint and background runner."""

from collective.aisettings.interfaces import IAIService
from collective.aisettings.services.tasks import complete_task
from collective.aisettings.services.tasks import create_task
from collective.aisettings.services.tasks import get_task
from collective.aitools.services import async_runner
from collective.aitools.services.assistant import Assistant
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
        result, status = _reply(portal, {"messages": [{"role": "user", "content": "hi"}]})
        assert status == 403
        assert "error" in result

    def test_enabled_starts_task(self, portal, fake_service, monkeypatch):
        # Don't spawn a real background thread; just check the endpoint hands
        # back a running task id.
        monkeypatch.setattr(async_runner, "Thread", FakeThread)
        api.portal.set_registry_record(ENABLED, True)

        result, status = _reply(portal, {"messages": [{"role": "user", "content": "hi"}]})
        assert status == 202
        task_id = result["task_id"]
        assert result["status"] == "running"
        assert get_task(task_id) is not None


class TestAssistantRunner:
    def test_run_and_store_completes(self, portal, fake_service):
        api.portal.set_registry_record(ENABLED, True)
        task_id = create_task()
        request = _make_request({})

        async_runner._run_and_store(
            portal, request, task_id, [{"role": "user", "content": "hi"}]
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
            portal, request, task_id, [{"role": "user", "content": "hi"}]
        )

        task = get_task(task_id)
        assert task["status"] == "error"
        assert "error" in task


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

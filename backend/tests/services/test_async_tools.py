"""The edit-form tools run as polled tasks with ``"async": true``.

The body a task completes with must be exactly what the endpoint answers
synchronously, so each job is run here both ways and compared.
"""

from collective.aisettings.interfaces import IAIService
from collective.aisettings.services import tasks
from collective.aisettings.services.tasks import create_task
from collective.aisettings.services.tasks import get_task
from collective.aitools.services import async_runner
from collective.aitools.services import task_status
from collective.aitools.services.help_me_write import help_me_write_job
from collective.aitools.services.help_me_write import help_me_write_segments_job
from collective.aitools.services.help_me_write import HelpMeWrite
from collective.aitools.services.recognize_image import recognize_image_job
from collective.aitools.services.recognize_image import RecognizeImage
from collective.aitools.services.suggest_tags import suggest_tags_job
from collective.aitools.services.suggest_tags import SuggestTags
from collective.aitools.services.summarize import Summarize
from collective.aitools.services.summarize import summarize_job
from collective.aitools.services.task_status import TaskStatus
from io import BytesIO
from plone import api
from zope.component import getGlobalSiteManager
from zope.interface import implementer
from ZPublisher.HTTPRequest import HTTPRequest
from ZPublisher.HTTPResponse import HTTPResponse

import json
import logging
import pytest


ENABLED = "collective.aitools.interfaces.IAIToolsSettings.{}_enabled"

DATA_URI = "data:image/png;base64,iVBORw0KGgo="


@implementer(IAIService)
class FakeAIService:
    """Answers every tool: plain text, tags, segment corrections, an image."""

    def __init__(self):
        self.answer = True
        self.calls = []

    def chat(self, prompt, model=None, system=None, output_type=None, **kw):
        self.calls.append(prompt)
        if not self.answer:
            return None
        if output_type is None:
            return "FAKE TEXT"
        if "tags" in output_type.model_fields:
            return output_type(tags=["one", "two", "three"])
        return output_type(corrections=[{"id": 0, "text": "Hello"}])

    def analyze_image(self, prompt, image, model=None, output_type=None, **kw):
        self.calls.append(image)
        if not self.answer:
            return None
        return output_type(title="T", description="D", tags=["a", "b", "c"])


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


@pytest.fixture
def enabled(portal):
    for name in ("summarize", "suggest_tags", "recognize_image", "help_me_write"):
        api.portal.set_registry_record(ENABLED.format(name), True)


class FakeThread:
    """Stand-in for threading.Thread that never actually runs the worker."""

    def __init__(self, *args, **kwargs):
        pass

    def start(self):
        pass


@pytest.fixture
def no_thread(monkeypatch):
    monkeypatch.setattr(async_runner, "Thread", FakeThread)


def _request(body=None):
    environ = {
        "REQUEST_METHOD": "POST",
        "SERVER_NAME": "localhost",
        "SERVER_PORT": "80",
    }
    request = HTTPRequest(BytesIO(b""), environ, HTTPResponse())
    request.set("BODY", json.dumps(body or {}))
    return request


def _reply(factory, portal, body):
    service = factory()
    service.context = portal
    service.request = _request(body)
    return service.reply(), service.request.response


#: (endpoint, its body, the job and the kwargs it receives)
CASES = [
    (Summarize, {"text": "Some text."}, summarize_job, {"text": "Some text."}),
    (SuggestTags, {"text": "Some text."}, suggest_tags_job, {"text": "Some text."}),
    (RecognizeImage, {"image": DATA_URI}, recognize_image_job, {"image": DATA_URI}),
    (
        HelpMeWrite,
        {"operation": "professional", "text": "hi there"},
        help_me_write_job,
        {"operation": "professional", "text": "hi there", "topic": "", "html": ""},
    ),
    (
        HelpMeWrite,
        {"operation": "grammar", "segments": ["Helo"]},
        help_me_write_segments_job,
        {"operation": "grammar", "segments": ["Helo"]},
    ),
]
IDS = ["summarize", "suggest_tags", "recognize_image", "help_me_write", "segments"]


class TestAsyncStart:
    @pytest.mark.parametrize("factory,body,job,kwargs", CASES, ids=IDS)
    def test_async_starts_a_task(
        self, portal, fake_service, enabled, no_thread, factory, body, job, kwargs
    ):
        result, response = _reply(factory, portal, {**body, "async": True})
        assert response.getStatus() == 202
        assert result["status"] == "running"
        assert get_task(result["task_id"])["status"] == "running"
        assert response.getHeader("Cache-Control") == "no-store"
        # Nothing ran in the request.
        assert fake_service.calls == []

    @pytest.mark.parametrize("factory,body,job,kwargs", CASES, ids=IDS)
    def test_task_gets_the_job_and_its_arguments(
        self, portal, fake_service, enabled, monkeypatch, factory, body, job, kwargs
    ):
        captured = {}

        def capture(context, request, label, job, **kw):
            captured.update(label=label, job=job, kwargs=kw)
            return "task-id"

        monkeypatch.setattr("collective.aitools.services.base.start_task", capture)
        _reply(factory, portal, {**body, "async": True})
        assert captured == {"label": factory.tool_name, "job": job, "kwargs": kwargs}

    def test_task_carries_owner_and_label(
        self, portal, fake_service, enabled, no_thread, monkeypatch
    ):
        captured = {}

        def capture(**kwargs):
            captured.update(kwargs)
            return "task-id"

        monkeypatch.setattr(async_runner, "create_task", capture)
        _reply(Summarize, portal, {"text": "x", "async": True})
        assert captured == {
            "owner": api.user.get_current().getId(),
            "label": "summarize",
        }

    def test_without_the_flag_it_runs_inline(self, portal, fake_service, enabled):
        result, response = _reply(Summarize, portal, {"text": "x"})
        assert response.getStatus() == 200
        assert result == {"result": "FAKE TEXT"}

    def test_flag_must_be_true(self, portal, fake_service, enabled):
        result, response = _reply(Summarize, portal, {"text": "x", "async": "no"})
        assert response.getStatus() == 200
        assert result == {"result": "FAKE TEXT"}

    def test_bad_input_creates_no_task(
        self, portal, fake_service, enabled, monkeypatch
    ):
        monkeypatch.setattr(async_runner, "create_task", pytest.fail)
        _result, response = _reply(Summarize, portal, {"async": True})
        assert response.getStatus() == 400

    def test_disabled_creates_no_task(self, portal, fake_service, monkeypatch):
        monkeypatch.setattr(async_runner, "create_task", pytest.fail)
        _result, response = _reply(Summarize, portal, {"text": "x", "async": True})
        assert response.getStatus() == 403

    def test_shutting_down_is_unavailable(
        self, portal, fake_service, enabled, monkeypatch
    ):
        def shutting_down(*args, **kwargs):
            raise tasks.TaskStoreShuttingDown()

        monkeypatch.setattr(async_runner, "create_task", shutting_down)
        result, response = _reply(Summarize, portal, {"text": "x", "async": True})
        assert response.getStatus() == 503
        assert response.getHeader("Retry-After") == "2"
        assert result["error"]["type"] == "ServiceUnavailable"


class TestJobs:
    @pytest.mark.parametrize("factory,body,job,kwargs", CASES, ids=IDS)
    def test_task_result_is_the_inline_body(
        self, portal, fake_service, enabled, factory, body, job, kwargs
    ):
        inline, response = _reply(factory, portal, body)
        assert response.getStatus() == 200

        task_id = create_task()
        async_runner._run_and_store(portal, _request(), task_id, job, kwargs)
        task = get_task(task_id)
        assert task["status"] == "done"
        assert task["result"] == inline

    @pytest.mark.parametrize("factory,body,job,kwargs", CASES, ids=IDS)
    def test_no_answer_fails_the_task_with_the_502_message(
        self, portal, fake_service, enabled, factory, body, job, kwargs
    ):
        fake_service.answer = False
        inline, response = _reply(factory, portal, body)
        assert response.getStatus() == 502

        task_id = create_task()
        async_runner._run_and_store(portal, _request(), task_id, job, kwargs)
        task = get_task(task_id)
        assert task["status"] == "error"
        assert task["error"] == inline["error"]["message"]

    def test_unexpected_error_fails_the_task(self, portal):
        def broken(context, request):
            raise RuntimeError("boom")

        task_id = create_task()
        async_runner._run_and_store(portal, _request(), task_id, broken, {})
        task = get_task(task_id)
        assert task["status"] == "error"
        assert task["error"] == "boom"


class TestTaskStatus:
    @pytest.mark.parametrize(
        "name", ["@aitools-task-status", "@aitools-assistant-status"]
    )
    def test_registered_under_both_names(self, portal, name):
        # plone.rest registers a subclass per service, named after the method
        # and media type plus the service name.
        factories = [
            registration.factory
            for registration in getGlobalSiteManager().registeredAdapters()
            if registration.name.endswith(name)
        ]
        assert factories
        assert all(issubclass(factory, TaskStatus) for factory in factories)

    def test_unknown_task_warns_once_without_the_shared_store(
        self, portal, monkeypatch, caplog
    ):
        monkeypatch.setattr(task_status, "_warned", False)
        for _ in range(2):
            service = TaskStatus()
            service.context = portal
            service.request = _request()
            service.publishTraverse(service.request, "missing")
            with caplog.at_level(logging.WARNING):
                service.reply()
            assert service.request.response.getStatus() == 404
        warnings = [r for r in caplog.records if "TASK_STORE" in r.getMessage()]
        assert len(warnings) == 1

    def test_no_warning_with_the_shared_store(self, portal, monkeypatch, caplog):
        from pymemcache.test.utils import MockMemcacheClient

        monkeypatch.setattr(task_status, "_warned", False)
        tasks.reset(tasks.SharedTaskStore(MockMemcacheClient()))
        try:
            service = TaskStatus()
            service.context = portal
            service.request = _request()
            service.publishTraverse(service.request, "missing")
            with caplog.at_level(logging.WARNING):
                service.reply()
        finally:
            tasks.reset()
        assert not [r for r in caplog.records if "TASK_STORE" in r.getMessage()]

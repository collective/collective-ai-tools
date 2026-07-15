"""Endpoint tests for the text edit-form tools (@aitools-summarize /
@aitools-suggest-tags)."""

from collective.aisettings.interfaces import IAIService
from collective.aitools.services.suggest_tags import SuggestTags
from collective.aitools.services.summarize import Summarize
from io import BytesIO
from plone import api
from zope.component import getGlobalSiteManager
from zope.interface import implementer
from ZPublisher.HTTPRequest import HTTPRequest
from ZPublisher.HTTPResponse import HTTPResponse

import json
import pytest


ENABLED = "collective.aitools.interfaces.IAIToolsSettings.{}_enabled"


@implementer(IAIService)
class FakeAIService:
    def __init__(self, return_value="A summary."):
        self.return_value = return_value
        self.calls = []

    def chat(self, prompt, model=None, system=None, output_type=None, **kw):
        self.calls.append((prompt, model, system))
        if not self.return_value:
            return None
        if output_type is not None:
            return output_type(tags=["one", "two", "three", "four", "five"])
        return self.return_value


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


def _reply(service_factory, portal, body):
    response = HTTPResponse()
    environ = {"REQUEST_METHOD": "POST", "SERVER_NAME": "localhost", "SERVER_PORT": "80"}
    request = HTTPRequest(BytesIO(b""), environ, response)
    request.set("BODY", json.dumps(body))
    service = service_factory()
    service.context = portal
    service.request = request
    return service.reply(), request.response.getStatus()


class TestSummarizeEndpoint:
    def test_missing_text(self, portal, fake_service):
        result, status = _reply(Summarize, portal, {})
        assert status == 400
        assert "error" in result

    def test_disabled_is_forbidden(self, portal, fake_service):
        _result, status = _reply(Summarize, portal, {"text": "hello"})
        assert status == 403
        assert fake_service.calls == []

    def test_success(self, portal, fake_service):
        api.portal.set_registry_record(ENABLED.format("summarize"), True)
        result, _status = _reply(Summarize, portal, {"text": "a long body of text"})
        assert result == {"result": "A summary."}
        assert fake_service.calls[0][0] == "a long body of text"

    def test_no_model_is_bad_gateway(self, portal, fake_service):
        api.portal.set_registry_record(ENABLED.format("summarize"), True)
        fake_service.return_value = None
        _result, status = _reply(Summarize, portal, {"text": "x"})
        assert status == 502


class TestSuggestTagsEndpoint:
    def test_missing_text(self, portal, fake_service):
        result, status = _reply(SuggestTags, portal, {})
        assert status == 400
        assert "error" in result

    def test_disabled_is_forbidden(self, portal, fake_service):
        _result, status = _reply(SuggestTags, portal, {"text": "hello"})
        assert status == 403
        assert fake_service.calls == []

    def test_success(self, portal, fake_service):
        api.portal.set_registry_record(ENABLED.format("suggest_tags"), True)
        result, _status = _reply(SuggestTags, portal, {"text": "a long body of text"})
        assert result == {"result": ["one", "two", "three", "four", "five"]}

    def test_no_model_is_bad_gateway(self, portal, fake_service):
        api.portal.set_registry_record(ENABLED.format("suggest_tags"), True)
        fake_service.return_value = None
        _result, status = _reply(SuggestTags, portal, {"text": "x"})
        assert status == 502

from collective.aisettings.interfaces import IAIService
from collective.aitools.services.help_me_write import HelpMeWrite
from io import BytesIO
from plone import api
from zope.component import getGlobalSiteManager
from zope.interface import implementer
from ZPublisher.HTTPRequest import HTTPRequest
from ZPublisher.HTTPResponse import HTTPResponse

import json
import pytest


ENABLED = "collective.aitools.interfaces.IAIToolsSettings.help_me_write_enabled"


@implementer(IAIService)
class FakeAIService:
    def __init__(self, return_value="FAKE TEXT"):
        self.return_value = return_value
        self.calls = []

    def chat(self, prompt, model=None, system=None, **kw):
        self.calls.append((prompt, model, system))
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


def _reply(portal, body):
    response = HTTPResponse()
    environ = {
        "REQUEST_METHOD": "POST",
        "SERVER_NAME": "localhost",
        "SERVER_PORT": "80",
    }
    request = HTTPRequest(BytesIO(b""), environ, response)
    request.set("BODY", json.dumps(body))
    # plone.rest services are instantiated without args; the publisher sets
    # context/request as attributes.
    service = HelpMeWrite()
    service.context = portal
    service.request = request
    return service.reply(), request.response.getStatus()


class TestHelpMeWriteEndpoint:
    def test_missing_operation(self, portal, fake_service):
        result, status = _reply(portal, {})
        assert status == 400
        assert "error" in result

    def test_unknown_operation(self, portal, fake_service):
        result, status = _reply(portal, {"operation": "bogus", "text": "x"})
        assert status == 400
        assert "error" in result

    def test_disabled_is_forbidden(self, portal, fake_service):
        # The tool is disabled by default.
        result, status = _reply(portal, {"operation": "draft", "topic": "cats"})
        assert status == 403
        assert "error" in result
        assert fake_service.calls == []

    def test_success_draft(self, portal, fake_service):
        api.portal.set_registry_record(ENABLED, True)
        result, _status = _reply(portal, {"operation": "draft", "topic": "cats"})
        assert result == {"result": "FAKE TEXT"}
        assert fake_service.calls[0][0] == "cats"

    def test_success_rewrite(self, portal, fake_service):
        api.portal.set_registry_record(ENABLED, True)
        result, _status = _reply(
            portal, {"operation": "professional", "text": "hi there"}
        )
        assert result == {"result": "FAKE TEXT"}
        assert "professional" in fake_service.calls[0][2]

    def test_no_model_is_bad_gateway(self, portal, fake_service):
        api.portal.set_registry_record(ENABLED, True)
        fake_service.return_value = None
        result, status = _reply(portal, {"operation": "grammar", "text": "hi"})
        assert status == 502
        assert "error" in result

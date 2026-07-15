from collective.aisettings.interfaces import IAIService
from collective.aitools.services.recognize_image import RecognizeImage
from io import BytesIO
from plone import api
from zope.component import getGlobalSiteManager
from zope.interface import implementer
from ZPublisher.HTTPRequest import HTTPRequest
from ZPublisher.HTTPResponse import HTTPResponse

import json
import pytest


ENABLED = "collective.aitools.interfaces.IAIToolsSettings.recognize_image_enabled"

DATA_URI = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M8AAAMBAQDJ/pLvAAAAAElFTkSuQmCC"


@implementer(IAIService)
class FakeAIService:
    def __init__(self, return_value=True):
        self.return_value = return_value
        self.calls = []

    def analyze_image(self, prompt, image, model=None, output_type=None, **kw):
        self.calls.append((prompt, image, model))
        if not self.return_value:
            return None
        return output_type(
            title="A title", description="A description", tags=["a", "b", "c", "d", "e"]
        )


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
    service = RecognizeImage()
    service.context = portal
    service.request = request
    return service.reply(), request.response.getStatus()


class TestRecognizeImageEndpoint:
    def test_missing_image(self, portal, fake_service):
        result, status = _reply(portal, {})
        assert status == 400
        assert "error" in result

    def test_disabled_is_forbidden(self, portal, fake_service):
        result, status = _reply(portal, {"image": DATA_URI})
        assert status == 403
        assert "error" in result
        assert fake_service.calls == []

    def test_success(self, portal, fake_service):
        api.portal.set_registry_record(ENABLED, True)
        result, _status = _reply(portal, {"image": DATA_URI})
        assert result == {
            "result": {
                "title": "A title",
                "description": "A description",
                "tags": ["a", "b", "c", "d", "e"],
            }
        }
        assert fake_service.calls[0][1] == DATA_URI

    def test_no_model_is_bad_gateway(self, portal, fake_service):
        api.portal.set_registry_record(ENABLED, True)
        fake_service.return_value = False
        result, status = _reply(portal, {"image": DATA_URI})
        assert status == 502
        assert "error" in result

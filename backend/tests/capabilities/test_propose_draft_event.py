"""Tests for event date derivation in the propose_draft / create_draft flow."""

from collective.aisettings.interfaces import IAIService
from collective.aitools.capabilities.propose_draft import _is_event_type
from collective.aitools.capabilities.propose_draft import GeneratedEventDraft
from collective.aitools.capabilities.propose_draft import ProposeDraftCapability
from collective.aitools.services.assistant import AssistantApply
from datetime import timedelta
from io import BytesIO
from plone import api
from zope.component import getGlobalSiteManager
from zope.interface import implementer
from ZPublisher.HTTPRequest import HTTPRequest
from ZPublisher.HTTPResponse import HTTPResponse

import pytest


@implementer(IAIService)
class FakeAIService:
    """Returns a fixed structured draft; records the calls it received."""

    def __init__(self, fields):
        self.fields = fields
        self.calls = []

    def chat(
        self,
        prompt,
        model=None,
        system=None,
        context=None,
        output_type=None,
        use_tools=False,
    ):
        self.calls.append({"prompt": prompt, "system": system, "output_type": output_type})
        valid = {k: v for k, v in self.fields.items() if k in output_type.model_fields}
        return output_type(**valid)


@pytest.fixture
def fake_service(portal):
    gsm = getGlobalSiteManager()
    original = gsm.queryUtility(IAIService)
    fake = FakeAIService({
        "title": "Team offsite",
        "description": "A team offsite.",
        "body": "<p>Agenda</p>",
        "start": "2026-07-21T18:00:00",
        "end": "2026-07-21T20:00:00",
    })
    gsm.registerUtility(fake, IAIService)
    yield fake
    gsm.unregisterUtility(fake, IAIService)
    if original is not None:
        gsm.registerUtility(original, IAIService)


def _request():
    environ = {
        "REQUEST_METHOD": "POST",
        "SERVER_NAME": "localhost",
        "SERVER_PORT": "80",
    }
    return HTTPRequest(BytesIO(b""), environ, HTTPResponse())


def _portal_path(portal):
    return "/".join(portal.getPhysicalPath())


class TestIsEventType:
    def test_event_is_event(self, portal):
        assert _is_event_type("Event") is True

    def test_document_is_not_event(self, portal):
        assert _is_event_type("Document") is False

    def test_unknown_type_is_not_event(self, portal):
        assert _is_event_type("NoSuchType") is False


class TestProposeDraftEvent:
    def test_event_proposal_carries_dates(self, portal, fake_service):
        with api.env.adopt_roles(["Manager"]):
            result = ProposeDraftCapability().run(
                portal,
                _request(),
                container_path=_portal_path(portal),
                portal_type="Event",
                brief="a team offsite in 2 weeks",
            )
        proposal = result["proposal"]
        assert proposal["portal_type"] == "Event"
        assert proposal["start"] == "2026-07-21T18:00:00"
        assert proposal["end"] == "2026-07-21T20:00:00"
        # The current date is injected into the generation prompt.
        assert "Current date" in fake_service.calls[0]["prompt"]

    def test_non_event_proposal_has_no_dates(self, portal, fake_service):
        with api.env.adopt_roles(["Manager"]):
            result = ProposeDraftCapability().run(
                portal,
                _request(),
                container_path=_portal_path(portal),
                portal_type="Document",
                brief="a page about widgets",
            )
        proposal = result["proposal"]
        assert "start" not in proposal
        assert "end" not in proposal
        assert fake_service.calls[0]["output_type"] is not GeneratedEventDraft


def _apply(portal, proposal):
    service = AssistantApply()
    service.context = portal
    service.request = _request()
    return service._create_draft(proposal)


def _created_obj(portal, payload):
    """Resolve the object created by _create_draft from its returned URL."""
    obj_id = payload["url"].rstrip("/").rsplit("/", 1)[-1]
    return portal[obj_id]


class TestCreateDraftEventDates:
    def _base(self, portal, **extra):
        proposal = {
            "type": "create_draft",
            "container_path": _portal_path(portal),
            "portal_type": "Event",
            "title": "Team offsite",
        }
        proposal.update(extra)
        return proposal

    def test_sets_start_and_end(self, portal):
        with api.env.adopt_roles(["Manager"]):
            payload, status = _apply(
                portal,
                self._base(
                    portal,
                    start="2026-07-21T18:00:00",
                    end="2026-07-21T20:00:00",
                ),
            )
            obj = _created_obj(portal, payload)
        assert status is None
        assert obj.start.tzinfo is not None
        assert (obj.start.year, obj.start.month, obj.start.day) == (2026, 7, 21)
        assert obj.start.hour == 18
        assert obj.end.hour == 20

    def test_missing_end_defaults_to_one_hour(self, portal):
        with api.env.adopt_roles(["Manager"]):
            payload, status = _apply(
                portal, self._base(portal, start="2026-07-21T18:00:00")
            )
            obj = _created_obj(portal, payload)
        assert obj.end == obj.start + timedelta(hours=1)

    def test_end_before_start_is_clamped(self, portal):
        with api.env.adopt_roles(["Manager"]):
            payload, status = _apply(
                portal,
                self._base(
                    portal,
                    start="2026-07-21T18:00:00",
                    end="2026-07-21T17:00:00",
                ),
            )
            obj = _created_obj(portal, payload)
        assert obj.end == obj.start + timedelta(hours=1)

    def test_non_event_type_is_unaffected(self, portal):
        proposal = {
            "type": "create_draft",
            "container_path": _portal_path(portal),
            "portal_type": "Document",
            "title": "A page",
            "start": "2026-07-21T18:00:00",
        }
        with api.env.adopt_roles(["Manager"]):
            payload, status = _apply(portal, proposal)
        assert status is None
        assert payload["created"] is True

"""Tests for how the Assistant loop normalizes model-supplied tool arguments.

Models get the call shape wrong in a handful of recurring ways (wrapping the
arguments in ``{"parameters": {...}}``, inventing keys, double-encoding the JSON).
None of those may reach ``capability.run`` as ``**kwargs``, where they raise
``TypeError`` and waste an agent step.
"""

from collective.aitools.capabilities import get_capability
from collective.aitools.capabilities.base import AICapability
from collective.aitools.tools.assistant import AssistantTool
from collective.aitools.tools.assistant import _coerce_arguments
from collective.aitools.tools.assistant import _parse_arguments
from io import BytesIO
from plone import api
from typing import ClassVar
from ZPublisher.HTTPRequest import HTTPRequest
from ZPublisher.HTTPResponse import HTTPResponse

import json


class NoArgCapability(AICapability):
    """Declares no arguments, and its run() would reject any."""

    name = "no_args"

    def run(self, context, request):
        return {"ok": True}


class SchemalessCapability(AICapability):
    """Declares a schema without an explicit ``properties`` mapping."""

    name = "schemaless"
    parameters: ClassVar[dict] = {"type": "object"}

    def run(self, context, request, **kwargs):
        return {"ok": True}


def _request():
    environ = {
        "REQUEST_METHOD": "POST",
        "SERVER_NAME": "localhost",
        "SERVER_PORT": "80",
    }
    return HTTPRequest(BytesIO(b""), environ, HTTPResponse())


class TestParseArguments:
    def test_plain_json_string(self):
        assert _parse_arguments('{"query": "cats"}') == {"query": "cats"}

    def test_double_encoded_json(self):
        # Some providers send a JSON string *containing* JSON.
        assert _parse_arguments(json.dumps('{"query": "cats"}')) == {"query": "cats"}

    def test_already_a_dict(self):
        assert _parse_arguments({"query": "cats"}) == {"query": "cats"}

    def test_empty_and_broken_input(self):
        assert _parse_arguments(None) == {}
        assert _parse_arguments("") == {}
        assert _parse_arguments("not json") == {}
        # Valid JSON, wrong shape.
        assert _parse_arguments("[1, 2]") == {}
        assert _parse_arguments("42") == {}


class TestCoerceArguments:
    def test_wrapped_in_parameters(self, portal):
        # The production failure: model echoed the schema wrapper.
        capability = get_capability("search_site")
        kwargs, dropped = _coerce_arguments(
            capability, {"parameters": {"query": "cats", "limit": 3}}
        )
        assert kwargs == {"query": "cats", "limit": 3}
        assert dropped == []

    def test_wrapped_in_any_single_key(self, portal):
        # The unwrapping is not keyed to one magic name.
        capability = get_capability("search_site")
        kwargs, _dropped = _coerce_arguments(capability, {"args": {"query": "cats"}})
        assert kwargs == {"query": "cats"}

    def test_unknown_keys_are_dropped(self, portal):
        capability = get_capability("search_site")
        kwargs, dropped = _coerce_arguments(
            capability, {"query": "cats", "sort_on": "created", "b_start": 0}
        )
        assert kwargs == {"query": "cats"}
        assert dropped == ["b_start", "sort_on"]

    def test_no_unwrap_when_a_declared_key_is_present(self, portal):
        # A single *declared* key is an argument, never a wrapper — even when
        # its value happens to be a dict.
        capability = get_capability("search_site")
        kwargs, _dropped = _coerce_arguments(capability, {"query": {"raw": "cats"}})
        assert kwargs == {"query": {"raw": "cats"}}

    def test_no_arg_capability_drops_everything(self):
        kwargs, dropped = _coerce_arguments(NoArgCapability(), {"query": "cats"})
        assert kwargs == {}
        assert dropped == ["query"]

    def test_schema_without_properties_passes_through(self):
        kwargs, dropped = _coerce_arguments(SchemalessCapability(), {"anything": 1})
        assert kwargs == {"anything": 1}
        assert dropped == []

    def test_non_dict_arguments(self, portal):
        capability = get_capability("search_site")
        assert _coerce_arguments(capability, None) == ({}, [])
        assert _coerce_arguments(capability, ["cats"]) == ({}, [])


class TestRunCapability:
    """End-to-end through _run_capability: bad shapes must still do the work.

    Runs as Manager because ``_run_capability`` re-checks the capability's
    permission; the role keeps these tests about argument handling only.
    """

    def _doc(self, portal):
        with api.env.adopt_roles(["Manager"]):
            doc = api.content.create(
                container=portal, type="Document", id="cats", title="All about cats"
            )
        doc.reindexObject()
        return doc

    def _run(self, portal, arguments):
        with api.env.adopt_roles(["Manager"]):
            return AssistantTool()._run_capability(
                "search_site", arguments, portal, _request()
            )

    def test_wrapped_arguments_still_search(self, portal):
        self._doc(portal)
        result = self._run(portal, {"parameters": {"query": "cats"}})
        assert "error" not in result
        assert [item["title"] for item in result["results"]] == ["All about cats"]

    def test_unknown_argument_does_not_error(self, portal):
        self._doc(portal)
        result = self._run(portal, {"query": "cats", "sort_on": "created"})
        assert "error" not in result
        assert result["count"] == 1

    def test_unknown_capability_still_reports_error(self, portal):
        with api.env.adopt_roles(["Manager"]):
            result = AssistantTool()._run_capability("nope", {}, portal, _request())
        assert "error" in result

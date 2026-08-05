from collective.aisettings.interfaces import IAIService
from collective.aitools.tools import get_tool
from collective.aitools.tools import get_tools
from plone import api
from zope.component import getGlobalSiteManager
from zope.interface import implementer

import base64
import pytest


# A 1x1 transparent PNG, enough for the image-field discovery test.
PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M8AAAMBAQDJ"
    "/pLvAAAAAElFTkSuQmCC"
)

ENABLED = "collective.aitools.interfaces.IAIToolsSettings.{}_enabled"
MODEL = "collective.aitools.interfaces.IAIToolsSettings.{}_model"


@implementer(IAIService)
class FakeAIService:
    """Records calls so tests can assert how tools invoke the service."""

    def __init__(self):
        self.calls = []
        #: ``(id, text)`` pairs to answer with when asked for structured
        #: per-segment output. Empty means "nothing to change".
        self.corrections = []

    def chat(self, prompt, model=None, system=None, output_type=None, **kw):
        self.calls.append(("chat", prompt, model, system, kw))
        if output_type is None:
            return "FAKE TEXT"
        if "corrections" in output_type.model_fields:
            return output_type(
                corrections=[
                    {"id": index, "text": text} for index, text in self.corrections
                ]
            )
        return output_type(tags=["alpha", "beta", "gamma", "delta", "epsilon"])

    def analyze_image(self, prompt, image, model=None, output_type=None, **kw):
        self.calls.append(("analyze_image", prompt, image, model, kw))
        if output_type is not None:
            return output_type(
                title="FAKE TITLE",
                description="FAKE DESCRIPTION",
                tags=["a", "b", "c", "d", "e"],
            )
        return "FAKE DESCRIPTION"


@pytest.fixture
def fake_service(portal):
    """Replace the global IAIService utility with a recording fake."""
    gsm = getGlobalSiteManager()
    original = gsm.queryUtility(IAIService)
    fake = FakeAIService()
    gsm.registerUtility(fake, IAIService)
    yield fake
    gsm.unregisterUtility(fake, IAIService)
    if original is not None:
        gsm.registerUtility(original, IAIService)


def _make_document(portal, text="<p>Some rich body text about cats.</p>", subject=None):
    from plone.app.textfield.value import RichTextValue

    with api.env.adopt_roles(["Manager"]):
        doc = api.content.create(
            container=portal, type="Document", id="a-doc", title="A doc"
        )
    if text is not None:
        doc.text = RichTextValue(text, "text/html", "text/html")
    if subject is not None:
        doc.subject = tuple(subject)
        doc.reindexObject()
    return doc


class TestToolRegistration:
    def test_tools_registered(self, portal):
        names = {name for name, _tool in get_tools()}
        assert {
            "recognize_image",
            "help_me_write",
            "summarize",
            "suggest_tags",
        } <= names

    def test_get_tool(self, portal):
        tool = get_tool("recognize_image")
        assert tool is not None
        assert tool.name == "recognize_image"

    def test_unknown_tool(self, portal):
        assert get_tool("does_not_exist") is None

    def test_disabled_by_default(self, portal):
        assert get_tool("recognize_image").is_enabled() is False
        assert get_tool("help_me_write").is_enabled() is False

    def test_get_model_empty_is_none(self, portal):
        assert get_tool("help_me_write").get_model() is None

    def test_get_model_reads_setting(self, portal):
        api.portal.set_registry_record(MODEL.format("help_me_write"), "gpt-4o")
        assert get_tool("help_me_write").get_model() == "gpt-4o"


class TestHelpMeWrite:
    def test_disabled_returns_none(self, portal, fake_service):
        out = get_tool("help_me_write").run(operation="draft", topic="cats")
        assert out is None
        assert fake_service.calls == []

    def test_run_calls_chat(self, portal, fake_service):
        api.portal.set_registry_record(ENABLED.format("help_me_write"), True)
        out = get_tool("help_me_write").run(operation="professional", text="hi there")
        assert out == "FAKE TEXT"
        kind, prompt, model, system, _kw = fake_service.calls[0]
        assert kind == "chat"
        assert prompt == "hi there"
        assert model is None
        assert "professional" in system

    def test_empty_input_returns_none(self, portal, fake_service):
        api.portal.set_registry_record(ENABLED.format("help_me_write"), True)
        out = get_tool("help_me_write").run(operation="grammar", text="   ")
        assert out is None
        assert fake_service.calls == []

    def test_unknown_operation_raises(self, portal, fake_service):
        api.portal.set_registry_record(ENABLED.format("help_me_write"), True)
        with pytest.raises(ValueError):
            get_tool("help_me_write").run(operation="bogus", text="x")


class TestHelpMeWriteModes:
    """Each operation declares how its answer is meant to be applied."""

    def test_modes(self):
        from collective.aitools.tools.help_me_write import operation_mode

        assert operation_mode("draft") == "draft"
        assert operation_mode("grammar") == "correct"
        assert operation_mode("professional") == "rewrite"
        assert operation_mode("casual") == "rewrite"


class TestHelpMeWritePrompts:
    """What each mode is told about the markup it is allowed to produce."""

    def test_draft_is_always_composed_as_html(self):
        from collective.aitools.tools.help_me_write import system_prompt

        prompt = system_prompt("draft")
        assert "HTML fragment" in prompt
        # The palette is offered whether or not there was HTML on the way in.
        assert '<table class="listing">' in prompt
        assert system_prompt("draft", html=True) == prompt

    def test_rewrite_with_html_gets_the_palette(self):
        from collective.aitools.tools.help_me_write import system_prompt

        prompt = system_prompt("professional", html=True)
        assert "Changing the structure is expected" in prompt
        assert "<h2> to <h6> for sections" in prompt
        assert "No <script> or <style>" in prompt

    def test_rewrite_without_html_is_left_plain(self):
        from collective.aitools.tools.help_me_write import OPERATIONS
        from collective.aitools.tools.help_me_write import system_prompt

        assert system_prompt("casual") == OPERATIONS["casual"]

    def test_correcting_html_is_told_to_preserve_it(self):
        from collective.aitools.tools.help_me_write import system_prompt

        prompt = system_prompt("grammar", html=True)
        assert "the markup is not yours to change" in prompt
        # A correction must not be offered new formatting to reach for.
        assert "at your disposal" not in prompt
        assert "Changing the structure is expected" not in prompt


class TestHelpMeWriteHtml:
    """The rewrite path: tone changes get HTML and may restructure it."""

    def _enable(self):
        api.portal.set_registry_record(ENABLED.format("help_me_write"), True)
        return get_tool("help_me_write")

    def test_html_input_asks_for_html_back(self, portal, fake_service):
        tool = self._enable()
        out = tool.run(operation="professional", html="<p>hi there</p>")
        assert out == "FAKE TEXT"
        _kind, prompt, _model, system, _kw = fake_service.calls[0]
        assert prompt == "<p>hi there</p>"
        assert "return an HTML fragment" in system
        # It is a rewrite, not a patch: restructuring is explicitly allowed.
        assert "Changing the structure is expected" in system

    def test_plain_text_input_is_unchanged(self, portal, fake_service):
        tool = self._enable()
        tool.run(operation="professional", text="hi there")
        _kind, prompt, _model, system, _kw = fake_service.calls[0]
        assert prompt == "hi there"
        assert "HTML" not in system

    def test_html_wins_over_text(self, portal, fake_service):
        tool = self._enable()
        tool.run(operation="casual", text="ignored", html="<p>used</p>")
        assert fake_service.calls[0][1] == "<p>used</p>"

    def test_empty_html_returns_none(self, portal, fake_service):
        tool = self._enable()
        assert tool.run(operation="professional", html="   ") is None
        assert fake_service.calls == []


class TestHelpMeWriteSegments:
    """The correct path: each segment is rewritten in place, so the caller can
    put the answer back without touching the markup around it."""

    def _enable(self):
        api.portal.set_registry_record(ENABLED.format("help_me_write"), True)
        return get_tool("help_me_write")

    def test_sends_numbered_segments_without_their_padding(self, portal, fake_service):
        tool = self._enable()
        tool.run_segments(operation="grammar", segments=["Helo ", "wrold", " here"])
        assert fake_service.calls[0][1] == "[0] Helo\n[1] wrold\n[2] here"

    def test_segment_protocol_is_appended_to_the_operation_prompt(
        self, portal, fake_service
    ):
        tool = self._enable()
        tool.run_segments(operation="grammar", segments=["x"])
        system = fake_service.calls[0][3]
        assert "copy editor" in system
        assert "Never move, merge, split or reorder text between segments" in system
        # Segments are plain text, so there is no markup to talk about and no
        # formatting to offer — the model must only fix wording.
        assert "at your disposal" not in system
        assert "HTML" not in system

    def test_restores_the_segment_s_own_whitespace(self, portal, fake_service):
        tool = self._enable()
        fake_service.corrections = [(0, "Hello"), (2, "there")]
        out = tool.run_segments(
            operation="grammar", segments=["Helo ", "wrold", " here"]
        )
        # The padding we held back is put back around the model's text.
        assert out == {0: "Hello ", 2: " there"}

    def test_blank_segments_are_not_sent_but_keep_their_index(
        self, portal, fake_service
    ):
        tool = self._enable()
        fake_service.corrections = [(2, "Fixed")]
        out = tool.run_segments(operation="grammar", segments=["", "   ", "Fixd"])
        assert fake_service.calls[0][1] == "[2] Fixd"
        assert out == {2: "Fixed"}

    def test_unknown_and_repeated_ids_are_dropped(self, portal, fake_service):
        tool = self._enable()
        fake_service.corrections = [(9, "nope"), (0, "Hello"), (0, "again")]
        out = tool.run_segments(operation="grammar", segments=["Helo"])
        assert out == {0: "Hello"}

    def test_unchanged_and_emptied_segments_are_dropped(self, portal, fake_service):
        tool = self._enable()
        fake_service.corrections = [(0, "Helo"), (1, "   ")]
        out = tool.run_segments(operation="grammar", segments=["Helo", "wrold"])
        assert out == {}

    def test_disabled_returns_none(self, portal, fake_service):
        out = get_tool("help_me_write").run_segments(
            operation="grammar", segments=["x"]
        )
        assert out is None
        assert fake_service.calls == []

    def test_all_blank_returns_none(self, portal, fake_service):
        tool = self._enable()
        assert tool.run_segments(operation="grammar", segments=["", "  "]) is None
        assert fake_service.calls == []

    def test_draft_raises(self, portal, fake_service):
        tool = self._enable()
        with pytest.raises(ValueError):
            tool.run_segments(operation="draft", segments=["x"])

    def test_unknown_operation_raises(self, portal, fake_service):
        tool = self._enable()
        with pytest.raises(ValueError):
            tool.run_segments(operation="bogus", segments=["x"])


class TestRecognizeImage:
    def _make_image(self, portal):
        from plone.namedfile.file import NamedBlobImage

        with api.env.adopt_roles(["Manager"]):
            image = api.content.create(
                container=portal, type="Image", id="an-image", title="An image"
            )
        image.image = NamedBlobImage(
            data=PNG_1PX, filename="px.png", contentType="image/png"
        )
        return image

    def test_disabled_returns_none(self, portal, fake_service):
        image = self._make_image(portal)
        assert get_tool("recognize_image").run(image) is None
        assert fake_service.calls == []

    def test_no_image_returns_none(self, portal, fake_service):
        api.portal.set_registry_record(ENABLED.format("recognize_image"), True)
        with api.env.adopt_roles(["Manager"]):
            doc = api.content.create(
                container=portal, type="Document", id="a-doc", title="A doc"
            )
        assert get_tool("recognize_image").run(doc) is None
        assert fake_service.calls == []

    def test_run_calls_analyze_image(self, portal, fake_service):
        api.portal.set_registry_record(ENABLED.format("recognize_image"), True)
        image = self._make_image(portal)
        out = get_tool("recognize_image").run(image)
        assert out == {
            "title": "FAKE TITLE",
            "description": "FAKE DESCRIPTION",
            "tags": ["a", "b", "c", "d", "e"],
        }
        kind, _prompt, image_arg, model, _kw = fake_service.calls[0]
        assert kind == "analyze_image"
        assert image_arg.startswith("data:image/png;base64,")
        assert model is None

    def test_describe_accepts_data_uri(self, portal, fake_service):
        api.portal.set_registry_record(ENABLED.format("recognize_image"), True)
        out = get_tool("recognize_image").describe("data:image/png;base64,AAAA")
        assert out["title"] == "FAKE TITLE"
        assert out["tags"] == ["a", "b", "c", "d", "e"]

    def test_describe_disabled_returns_none(self, portal, fake_service):
        out = get_tool("recognize_image").describe("data:image/png;base64,AAAA")
        assert out is None
        assert fake_service.calls == []

    def test_tags_are_deduped_and_clamped(self, portal, fake_service):
        from collective.aitools.tools.recognize_image import _as_dict
        from collective.aitools.tools.recognize_image import ImageDetails

        details = ImageDetails(
            title=" T ",
            description=" D ",
            tags=["x", "X", " y ", ""] + [f"t{i}" for i in range(20)],
        )
        out = _as_dict(details)
        assert out["title"] == "T"
        assert out["description"] == "D"
        assert len(out["tags"]) == 10  # clamped to MAX_TAGS
        assert out["tags"][:2] == ["x", "y"]  # deduped case-insensitively


class TestSummarize:
    def test_disabled_returns_none(self, portal, fake_service):
        doc = _make_document(portal)
        assert get_tool("summarize").run(doc) is None
        assert fake_service.calls == []

    def test_run_summarizes_body(self, portal, fake_service):
        api.portal.set_registry_record(ENABLED.format("summarize"), True)
        doc = _make_document(portal)
        out = get_tool("summarize").run(doc)
        assert out == "FAKE TEXT"
        kind, prompt, _model, system, _kw = fake_service.calls[0]
        assert kind == "chat"
        assert "cats" in prompt  # body text was passed through
        assert "summar" in system.lower()

    def test_no_text_returns_none(self, portal, fake_service):
        api.portal.set_registry_record(ENABLED.format("summarize"), True)
        doc = _make_document(portal, text=None)
        # An empty Document still has a title, so blank the body only.
        out = get_tool("summarize").summarize_text("   ", context=doc)
        assert out is None
        assert fake_service.calls == []


class TestSuggestTags:
    def test_disabled_returns_none(self, portal, fake_service):
        doc = _make_document(portal)
        assert get_tool("suggest_tags").run(doc) is None
        assert fake_service.calls == []

    def test_run_suggests_tags(self, portal, fake_service):
        api.portal.set_registry_record(ENABLED.format("suggest_tags"), True)
        doc = _make_document(portal)
        out = get_tool("suggest_tags").run(doc)
        assert out == ["alpha", "beta", "gamma", "delta", "epsilon"]
        kind, prompt, _model, _system, _kw = fake_service.calls[0]
        assert kind == "chat"
        assert "cats" in prompt

    def test_existing_site_tags_in_prompt(self, portal, fake_service, monkeypatch):
        # The vocabulary lookup itself is exercised at runtime; here we stub it
        # and assert the tags are woven into the system prompt for the model.
        monkeypatch.setattr(
            "collective.aitools.tools.suggest_tags.existing_site_tags",
            lambda context=None, limit=None: ["existing-tag", "another-tag"],
        )
        api.portal.set_registry_record(ENABLED.format("suggest_tags"), True)
        doc = _make_document(portal)
        get_tool("suggest_tags").run(doc)
        _kind, _prompt, _model, system, _kw = fake_service.calls[0]
        assert "existing-tag" in system
        assert "another-tag" in system

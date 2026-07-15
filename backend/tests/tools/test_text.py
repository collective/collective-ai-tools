"""Unit tests for the shared text helpers."""

from collective.aitools.tools.text import clean_tags
from collective.aitools.tools.text import get_body_text
from collective.aitools.tools.text import html_to_text
from plone import api


class TestHtmlToText:
    def test_strips_tags_and_keeps_text(self):
        out = html_to_text("<p>Hello <b>world</b></p><p>Second para</p>")
        assert "Hello world" in out
        assert "Second para" in out
        assert "<" not in out

    def test_unescapes_entities(self):
        assert html_to_text("<p>a &amp; b &lt;c&gt;</p>") == "a & b <c>"


class TestCleanTags:
    def test_trims_dedupes_clamps(self):
        tags = ["  A ", "a", "B", ""] + [f"t{i}" for i in range(20)]
        out = clean_tags(tags, max_tags=5)
        assert out[0] == "A"
        assert "a" not in out[1:]  # case-insensitive de-dupe
        assert len(out) == 5

    def test_empty(self):
        assert clean_tags(None) == []
        assert clean_tags(["", "  "]) == []


class TestGetBodyText:
    def test_combines_title_description_and_body(self, portal):
        from plone.app.textfield.value import RichTextValue

        with api.env.adopt_roles(["Manager"]):
            doc = api.content.create(
                container=portal,
                type="Document",
                id="doc",
                title="My Title",
                description="My description",
            )
        doc.text = RichTextValue("<p>The body text.</p>", "text/html", "text/html")
        out = get_body_text(doc)
        assert "My Title" in out
        assert "My description" in out
        assert "The body text." in out

    def test_truncates(self, portal):
        with api.env.adopt_roles(["Manager"]):
            doc = api.content.create(
                container=portal, type="Document", id="doc2", title="x" * 100
            )
        assert len(get_body_text(doc, max_chars=10)) == 10

    def test_empty_when_no_text(self, portal):
        with api.env.adopt_roles(["Manager"]):
            doc = api.content.create(
                container=portal, type="Document", id="doc3", title=""
            )
        assert get_body_text(doc) == ""

"""Tests for the editor-tool viewlets' config, focused on Mosaic gating.

The viewlets emit a JSON config the Classic-UI bundle reads. Mosaic
(``plone.app.mosaic``) is not Plone core, so the Mosaic-specific parts of that
config must only appear when Mosaic is importable.
"""

from collective.aitools.browser.assistant import AssistantViewlet
from collective.aitools.browser.help_me_write import HelpMeWriteViewlet
from collective.aitools.browser.recognize_image import RecognizeImageViewlet
from collective.aitools.browser.suggest_tags import SuggestTagsViewlet
from collective.aitools.browser.summarize import SummarizeViewlet

import json
import pytest


def _config(viewlet_class, portal, http_request):
    viewlet = viewlet_class(portal, http_request, None, None)
    return json.loads(viewlet.config_json())


class TestHelpMeWriteConfig:
    def test_mosaic_absent_by_default(self, portal, http_request):
        """Mosaic is not installed in the test env: flag is falsy."""
        config = _config(HelpMeWriteViewlet, portal, http_request)
        assert config["endpoint"].endswith("/@aitools-help-me-write")
        assert config.get("mosaicInline") is False

    def test_mosaic_flag_set_when_installed(self, portal, http_request, monkeypatch):
        monkeypatch.setattr(
            "collective.aitools.browser.help_me_write.mosaic_installed",
            lambda: True,
        )
        config = _config(HelpMeWriteViewlet, portal, http_request)
        assert config["mosaicInline"] is True


class TestRecognizeImageConfig:
    def test_no_mosaic_block_by_default(self, portal, http_request):
        config = _config(RecognizeImageViewlet, portal, http_request)
        assert config["endpoint"].endswith("/@aitools-recognize-image")
        assert "mosaic" not in config

    def test_mosaic_block_when_installed(self, portal, http_request, monkeypatch):
        monkeypatch.setattr(
            "collective.aitools.browser.recognize_image.mosaic_installed",
            lambda: True,
        )
        config = _config(RecognizeImageViewlet, portal, http_request)
        assert "mosaic" in config
        mosaic = config["mosaic"]
        assert mosaic["tileFormSelector"]
        # Fields the pattern fills on an image tile's own form.
        assert "caption" in mosaic["fields"]
        assert "title" in mosaic["fields"]


class TestStatusEndpoint:
    """Every tool polls the same status endpoint for its async task."""

    @pytest.mark.parametrize(
        "viewlet_class",
        [
            AssistantViewlet,
            HelpMeWriteViewlet,
            RecognizeImageViewlet,
            SuggestTagsViewlet,
            SummarizeViewlet,
        ],
    )
    def test_config_carries_the_status_endpoint(
        self, portal, http_request, viewlet_class
    ):
        config = _config(viewlet_class, portal, http_request)
        assert config["statusEndpoint"] == (
            f"{portal.absolute_url()}/@aitools-task-status"
        )

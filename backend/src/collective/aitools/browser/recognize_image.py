"""Viewlet that emits the classic-UI "Get image details" Patternslib trigger.

Only renders when the ``recognize_image`` tool is enabled and the current view
is an edit or add form. It emits a hidden element carrying a small JSON config
(endpoint URL and the translated UI strings) in its
``data-pat-aitools-recognize-image`` attribute. The ``aitools`` bundle (built
from ``resources/``) picks that up and adds a "Get image details" button next
to each image file field. The bundle itself is loaded globally through the
resource registry, so the viewlet no longer injects any script/CSS.
"""

from collective.aitools import _
from collective.aitools.browser import mosaic_installed
from collective.aitools.tools import get_tool
from plone.app.layout.viewlets.common import ViewletBase
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from zope.i18n import translate

import json


class RecognizeImageViewlet(ViewletBase):
    index = ViewPageTemplateFile("templates/recognize_image_viewlet.pt")

    def _is_form_view(self) -> bool:
        url = (self.request.get("ACTUAL_URL", "") or self.request.getURL()).rstrip("/")
        last = url.rsplit("/", 1)[-1]
        return last in ("edit",) or "++add++" in url

    def available(self) -> bool:
        tool = get_tool("recognize_image")
        if tool is None or not tool.is_enabled():
            return False
        return self._is_form_view()

    def render(self):
        if not self.available():
            return ""
        return self.index()

    # -- template helpers --

    def endpoint_url(self) -> str:
        return f"{self.context.absolute_url()}/@aitools-recognize-image"

    def status_url(self) -> str:
        return f"{self.context.absolute_url()}/@aitools-task-status"

    def config_json(self) -> str:
        t = lambda msg: translate(msg, context=self.request)
        config = {
            "endpoint": self.endpoint_url(),
            # Poll base for the async task; the pattern appends "/<task_id>".
            "statusEndpoint": self.status_url(),
            "labels": {
                "button": t(_("Get image details")),
                "loading": t(_("Analyzing image...")),
                "error": t(_("Something went wrong. Please try again.")),
                "noImage": t(_("Choose an image first.")),
                "done": t(_("Filled in the empty fields.")),
                "readError": t(_("Could not read the selected image.")),
            },
        }
        # In the Mosaic editor, image tiles are edited in a modal tile form that
        # does not carry the page's Title/Description/Subject. When Mosaic is
        # present, tell the pattern to fill the tile's own fields instead.
        if mosaic_installed():
            config["mosaic"] = {
                "tileFormSelector": ".pat-modal form, .plone-modal form",
                "fields": [
                    "caption",
                    "alt_text",
                    "altText",
                    "alt",
                    "title",
                    "description",
                ],
            }
        return json.dumps(config)

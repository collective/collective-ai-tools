"""Viewlet that emits the classic-UI "Help me write" Patternslib trigger.

Only renders when the ``help_me_write`` tool is enabled and the current view
is an edit or add form. It emits a hidden element carrying a small JSON config
(endpoint URL, the operations with their labels and whether they need typed
input, and the translated UI strings) in its ``data-pat-aitools-help-me-write``
attribute. The ``aitools`` bundle (built from ``resources/``) picks that up and
builds the TinyMCE button. The bundle itself is loaded globally through the
resource registry, so the viewlet no longer injects any script/CSS.
"""

from collective.aitools import _
from collective.aitools.browser import mosaic_installed
from collective.aitools.tools import get_tool
from collective.aitools.tools.help_me_write import OPERATION_TITLES
from collective.aitools.tools.help_me_write import OPERATIONS_REQUIRING_INPUT
from plone.app.layout.viewlets.common import ViewletBase
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from zope.i18n import translate

import json


class HelpMeWriteViewlet(ViewletBase):
    index = ViewPageTemplateFile("templates/help_me_write_viewlet.pt")

    def _is_form_view(self) -> bool:
        url = (self.request.get("ACTUAL_URL", "") or self.request.getURL()).rstrip("/")
        last = url.rsplit("/", 1)[-1]
        return last in ("edit",) or "++add++" in url

    def available(self) -> bool:
        tool = get_tool("help_me_write")
        if tool is None or not tool.is_enabled():
            return False
        return self._is_form_view()

    def render(self):
        if not self.available():
            return ""
        return self.index()

    # -- template helpers --

    def endpoint_url(self) -> str:
        return f"{self.context.absolute_url()}/@aitools-help-me-write"

    def _operations(self):
        return [
            {
                "id": op_id,
                "label": translate(title, context=self.request),
                "needsInput": op_id in OPERATIONS_REQUIRING_INPUT,
            }
            for op_id, title in OPERATION_TITLES.items()
        ]

    def config_json(self) -> str:
        t = lambda msg: translate(msg, context=self.request)
        return json.dumps({
            "endpoint": self.endpoint_url(),
            "operations": self._operations(),
            # Mosaic rich-text tiles use inline TinyMCE editors; only wire the
            # bar into inline editors when Mosaic is present (see the pattern).
            "mosaicInline": mosaic_installed(),
            "labels": {
                "button": t(_("Help me write")),
                "send": t(_("Send")),
                "loading": t(_("Generating...")),
                "error": t(_("Something went wrong. Please try again.")),
                "noText": t(_("Select or enter some text first.")),
                "draftPlaceholder": t(_("What do you want to write about?")),
            },
        })

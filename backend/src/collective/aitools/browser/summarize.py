"""Viewlet that emits the classic-UI "Summarize" Patternslib trigger.

Renders (in ``IPortalFooter``, only on edit/add forms and only when the
``summarize`` tool is enabled) a hidden element whose
``data-pat-aitools-summarize`` attribute carries the endpoint + translated
labels. The ``aitools`` bundle attaches a "Summarize" button next to the
Description field that fills it (when empty) from the item's body text.
"""

from collective.aitools import _
from collective.aitools.tools import get_tool
from plone.app.layout.viewlets.common import ViewletBase
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from zope.i18n import translate

import json


class SummarizeViewlet(ViewletBase):
    index = ViewPageTemplateFile("templates/summarize_viewlet.pt")

    def _is_form_view(self) -> bool:
        url = (self.request.get("ACTUAL_URL", "") or self.request.getURL()).rstrip("/")
        last = url.rsplit("/", 1)[-1]
        return last in ("edit",) or "++add++" in url

    def available(self) -> bool:
        tool = get_tool("summarize")
        if tool is None or not tool.is_enabled():
            return False
        return self._is_form_view()

    def render(self):
        if not self.available():
            return ""
        return self.index()

    def endpoint_url(self) -> str:
        return f"{self.context.absolute_url()}/@aitools-summarize"

    def config_json(self) -> str:
        t = lambda msg: translate(msg, context=self.request)
        return json.dumps({
            "endpoint": self.endpoint_url(),
            "labels": {
                "button": t(_("Summarize")),
                "loading": t(_("Summarizing...")),
                "error": t(_("Something went wrong. Please try again.")),
                "noText": t(_("Add some content first.")),
                "done": t(_("Filled in the description.")),
                "notEmpty": t(_("The description already has a value.")),
            },
        })

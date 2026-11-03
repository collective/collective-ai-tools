"""Viewlet that emits the classic-UI "Suggest tags" Patternslib trigger.

Renders (in ``IPortalFooter``, only on edit/add forms and only when the
``suggest_tags`` tool is enabled) a hidden element whose
``data-pat-aitools-suggest-tags`` attribute carries the endpoint + translated
labels. The ``aitools`` bundle attaches a "Suggest tags" button next to the
Tags field that fills it (when empty) from the item's body text.
"""

from collective.aitools import _
from collective.aitools.tools import get_tool
from plone.app.layout.viewlets.common import ViewletBase
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from zope.i18n import translate

import json


class SuggestTagsViewlet(ViewletBase):
    index = ViewPageTemplateFile("templates/suggest_tags_viewlet.pt")

    def _is_form_view(self) -> bool:
        url = (self.request.get("ACTUAL_URL", "") or self.request.getURL()).rstrip("/")
        last = url.rsplit("/", 1)[-1]
        return last in ("edit",) or "++add++" in url

    def available(self) -> bool:
        tool = get_tool("suggest_tags")
        if tool is None or not tool.is_enabled():
            return False
        return self._is_form_view()

    def render(self):
        if not self.available():
            return ""
        return self.index()

    def endpoint_url(self) -> str:
        return f"{self.context.absolute_url()}/@aitools-suggest-tags"

    def status_url(self) -> str:
        return f"{self.context.absolute_url()}/@aitools-task-status"

    def config_json(self) -> str:
        t = lambda msg: translate(msg, context=self.request)
        return json.dumps({
            "endpoint": self.endpoint_url(),
            # Poll base for the async task; the pattern appends "/<task_id>".
            "statusEndpoint": self.status_url(),
            "labels": {
                "button": t(_("Suggest tags")),
                "loading": t(_("Suggesting tags...")),
                "error": t(_("Something went wrong. Please try again.")),
                "noText": t(_("Add some content first.")),
                "done": t(_("Added tags.")),
                "notEmpty": t(_("Tags are already set.")),
            },
        })

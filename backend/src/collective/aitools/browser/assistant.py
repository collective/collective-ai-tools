"""Viewlet that mounts the classic-UI chat "Assistant" widget.

Renders (site-wide, in ``IPortalFooter``) the Patternslib trigger for the chat
widget when the ``assistant`` tool is enabled and the visitor is *authenticated*
(anonymous visitors don't get the widget in this first, editor-focused slice).
We deliberately gate on "logged in or not" rather than a permission, because
the viewlet is rendered on the portal root where an editor permission may not
be granted; the individual capabilities enforce their own permissions.
"""

from collective.aitools import _
from collective.aitools.tools import get_tool
from plone import api
from plone.app.layout.viewlets.common import ViewletBase
from plone.protect.authenticator import createToken
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from zope.i18n import translate

import json


class AssistantViewlet(ViewletBase):
    index = ViewPageTemplateFile("templates/assistant_viewlet.pt")

    def available(self) -> bool:
        tool = get_tool("assistant")
        if tool is None or not tool.is_enabled():
            return False
        # Show only to authenticated users (not anonymous). No permission check:
        # the viewlet renders on the root, where editor perms may be absent.
        return not api.user.is_anonymous()

    def render(self):
        if not self.available():
            return ""
        return self.index()

    def endpoint_url(self) -> str:
        return f"{self.context.absolute_url()}/@aitools-assistant"

    def apply_url(self) -> str:
        return f"{self.context.absolute_url()}/@aitools-assistant-apply"

    def status_url(self) -> str:
        return f"{self.context.absolute_url()}/@aitools-task-status"

    def config_json(self) -> str:
        t = lambda msg: translate(msg, context=self.request)
        return json.dumps({
            "endpoint": self.endpoint_url(),
            "applyEndpoint": self.apply_url(),
            # Poll base; the widget appends "/<task_id>" (GET).
            "statusEndpoint": self.status_url(),
            # CSRF token for the write (apply) request; plone.protect accepts
            # it via the X-CSRF-TOKEN header. Freshly minted per page render.
            "token": createToken(),
            "labels": {
                "title": t(_("Assistant")),
                "open": t(_("Open the assistant")),
                "close": t(_("Close")),
                "new_chat": t(_("Start new chat")),
                "placeholder": t(_("Ask me anything about this site…")),
                "send": t(_("Send")),
                "loading": t(_("Thinking…")),
                "error": t(_("Something went wrong. Please try again.")),
                "create": t(_("Create draft")),
                "creating": t(_("Creating…")),
                "created": t(_("Draft created:")),
                "open_item": t(_("Open")),
            },
        })

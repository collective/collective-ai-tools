"""The "AI Tools" control panel (classic Plone + Volto REST adapter).

Mirrors the ``collective.aisettings`` "AI Settings" control panel: a
``RegistryEditForm`` wrapped for classic Plone, plus a
``RegistryConfigletPanel`` adapter so the same schema is reachable from Volto
via ``@controlpanels/ai-tools`` (the Volto widget itself comes later).
"""

from collective.aitools import _
from collective.aitools.interfaces import IAIToolsSettings
from plone.app.registry.browser.controlpanel import ControlPanelFormWrapper
from plone.app.registry.browser.controlpanel import RegistryEditForm
from plone.restapi.controlpanels import RegistryConfigletPanel
from plone.z3cform import layout
from zope.component import adapter
from zope.interface import Interface


@adapter(Interface, Interface)
class AIToolsControlpanel(RegistryConfigletPanel):
    """plone.restapi adapter exposing the AI tools settings to Volto via
    ``@controlpanels/ai-tools``."""

    schema = IAIToolsSettings
    configlet_id = "ai-tools"
    configlet_category_id = "plone-general"
    schema_prefix = None


class AIToolsSettingsEditForm(RegistryEditForm):
    schema = IAIToolsSettings
    label = _("AI Tools")
    description = _("Enable and configure the available AI tools.")


AIToolsControlPanel = layout.wrap_form(AIToolsSettingsEditForm, ControlPanelFormWrapper)

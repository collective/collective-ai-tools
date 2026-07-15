from collective.aitools.interfaces import IAIToolsSettings
from plone.registry.interfaces import IRegistry
from zope.component import getMultiAdapter
from zope.component import getUtility


class TestAIToolsControlpanel:
    def test_registry_records_installed(self, portal):
        """The IAIToolsSettings records are created by the default profile."""
        registry = getUtility(IRegistry)
        # forInterface() raises KeyError if any record is missing.
        settings = registry.forInterface(IAIToolsSettings)
        assert settings.recognize_image_enabled is False
        assert settings.help_me_write_enabled is False

    def test_classic_controlpanel_view(self, portal, http_request):
        """The classic control panel page is registered on the site root."""
        view = getMultiAdapter((portal, http_request), name="ai-tools")
        assert view is not None

    def test_restapi_configlet_registered(self, portal, http_request):
        """The plone.restapi configlet adapter is registered for Volto."""
        from plone.restapi.controlpanels.interfaces import IControlpanel

        panel = getMultiAdapter((portal, http_request), IControlpanel, name="ai-tools")
        assert panel.configlet_id == "ai-tools"

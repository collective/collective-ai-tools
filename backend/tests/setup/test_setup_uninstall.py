from collective.aitools import PACKAGE_NAME

import pytest


class TestSetupUninstall:
    @pytest.fixture(autouse=True)
    def uninstalled(self, installer):
        installer.uninstall_product(PACKAGE_NAME)

    def test_addon_uninstalled(self, installer):
        """Test if collective.aitools is uninstalled."""
        assert installer.is_product_installed(PACKAGE_NAME) is False

    def test_browserlayer_not_registered(self, browser_layers):
        """Test that IBrowserLayer is not registered."""
        from collective.aitools.interfaces import IBrowserLayer

        assert IBrowserLayer not in browser_layers

    def test_classic_ui_bundle_removed(self, portal):
        """The Classic UI bundle records are removed on uninstall."""
        from plone import api

        assert (
            api.portal.get_registry_record(
                "plone.bundles/aitools.enabled", default=None
            )
            is None
        )

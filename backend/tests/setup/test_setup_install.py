from collective.aitools import PACKAGE_NAME


class TestSetupInstall:
    def test_addon_installed(self, installer):
        """Test if collective.aitools is installed."""
        assert installer.is_product_installed(PACKAGE_NAME) is True

    def test_browserlayer(self, browser_layers):
        """Test that IBrowserLayer is registered."""
        from collective.aitools.interfaces import IBrowserLayer

        assert IBrowserLayer in browser_layers

    def test_latest_version(self, profile_last_version):
        """Test latest version of default profile."""
        assert profile_last_version(f"{PACKAGE_NAME}:default") == "1000"

    def test_classic_ui_bundle_registered(self, portal):
        """The Classic UI Patternslib bundle is registered and enabled."""
        from plone import api

        prefix = "plone.bundles/aitools"
        assert (
            api.portal.get_registry_record(f"{prefix}.enabled", default=None) is True
        )
        assert api.portal.get_registry_record(
            f"{prefix}.jscompilation", default=""
        ) == "++plone++collective.aitools/aitools-remote.min.js"

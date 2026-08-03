"""Tests for which users a capability is offered to.

``getSecurityManager().checkPermission`` understands Zope permission *titles*
("View"), not the dotted ZCML ids used in ``configure.zcml`` ("zope2.View"). An
unregistered name is not an error — it falls back to the ``('Manager',)``
default roles — so declaring an id silently hid read-only capabilities from
every non-Manager. These tests pin the intended audience of each capability.
"""

from collective.aitools.capabilities import get_capability
from collective.aitools.capabilities import manifest_for
from collective.aitools.capabilities.base import AICapability
from collective.aitools.capabilities.base import _check_permission
from plone import api

import pytest


READ_ONLY = ["search_site"]
EDITOR_ONLY = ["where_to_add", "propose_draft"]


def _names(context):
    return {schema["function"]["name"] for schema in manifest_for(context)}


class TestDeclaredPermissions:
    @pytest.mark.parametrize("name", READ_ONLY + EDITOR_ONLY)
    def test_permission_is_a_registered_title(self, portal, name):
        # A dotted ZCML id would not be registered, and would quietly make the
        # capability Manager-only.
        from AccessControl.Permission import getPermissions

        capability = get_capability(name)
        assert capability.permission in {entry[0] for entry in getPermissions()}


class TestManifestAudience:
    def test_member_gets_the_read_only_capabilities(self, portal):
        # A plain Member can view, so search_site must be offered.
        names = _names(portal)
        assert set(READ_ONLY).issubset(names)

    def test_member_does_not_get_editor_capabilities(self, portal):
        names = _names(portal)
        assert not names.intersection(EDITOR_ONLY)

    def test_editor_gets_everything(self, portal):
        with api.env.adopt_roles(["Editor"]):
            names = _names(portal)
        assert set(READ_ONLY + EDITOR_ONLY).issubset(names)

    def test_anonymous_gets_the_read_only_capabilities(self, portal):
        with api.env.adopt_roles(["Anonymous"]):
            names = _names(portal)
        assert set(READ_ONLY).issubset(names)
        assert not names.intersection(EDITOR_ONLY)


class TestCheckPermission:
    def test_unknown_permission_warns_and_denies(self, portal, caplog):
        class BadCapability(AICapability):
            name = "bad"
            permission = "zope2.View"  # a ZCML id, not a title

        assert BadCapability().allowed_for(portal) is False
        assert "unknown permission 'zope2.View'" in caplog.text

    def test_known_permission_does_not_warn(self, portal, caplog):
        assert _check_permission("View", portal, capability="probe") is True
        assert "unknown permission" not in caplog.text

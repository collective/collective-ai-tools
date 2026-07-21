"""Init and utils."""

from zope.i18nmessageid import MessageFactory

import logging


__version__ = "1.1.2"

PACKAGE_NAME = "collective.aitools"

_ = MessageFactory(PACKAGE_NAME)

logger = logging.getLogger(PACKAGE_NAME)

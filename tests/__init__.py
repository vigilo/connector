from nose.twistedtools import reactor, stop_reactor
from vigilo.common.conf import settings
settings.load_module(__name__)
from vigilo.common.logging import get_logger
LOGGER = get_logger(__name__)

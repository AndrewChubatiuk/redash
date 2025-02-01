import logging
import os
import sys

import redis
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_mail import Mail
from flask_migrate import Migrate
from prometheus_client.bridge.graphite import GraphiteBridge

from redash import settings
from redash.app import create_app  # noqa
from redash.destinations import import_destinations
from redash.query_runner import import_query_runners

__version__ = "25.02.0-dev"


if os.environ.get("REMOTE_DEBUG"):
    import ptvsd

    ptvsd.enable_attach(address=("0.0.0.0", 5678))


def setup_logging():
    handler = logging.StreamHandler(sys.stdout if settings.LOG_STDOUT else sys.stderr)
    formatter = logging.Formatter(settings.LOG_FORMAT)
    handler.setFormatter(formatter)
    logging.getLogger().addHandler(handler)
    logging.getLogger().setLevel(settings.LOG_LEVEL)

    # Make noisy libraries less noisy
    if settings.LOG_LEVEL != "DEBUG":
        for name in [
            "passlib",
            "requests.packages.urllib3",
            "snowflake.connector",
            "apiclient",
        ]:
            logging.getLogger(name).setLevel("ERROR")


setup_logging()

if settings.STATSD_ENABLED:
    gb = GraphiteBridge((settings.STATSD_HOST, settings.STATSD_PORT), tags=settings.STATSD_USE_TAGS)
    gb.start(settings.STATSD_PERIOD, settings.STATSD_PREFIX)

redis_connection = redis.from_url(settings.REDIS_URL)
rq_redis_connection = redis.from_url(settings.RQ_REDIS_URL)
mail = Mail()
migrate = Migrate(compare_type=True)
limiter = Limiter(key_func=get_remote_address, storage_uri=settings.LIMITER_STORAGE)

import_query_runners(settings.QUERY_RUNNERS)
import_destinations(settings.DESTINATIONS)

import datetime

from flask import current_app

from redash import models, utils
from redash.alerts import Alerts
from redash.worker import get_job_logger, job

logger = get_job_logger(__name__)


def notify_subscriptions(alert, new_state, metadata):
    host = utils.base_url(alert.query.org)
    for subscription in alert.subscriptions:
        try:
            subscription.notify(alert, alert.query, subscription.user, new_state, current_app, host, metadata)
        except Exception:
            logger.exception("Error with processing destination")


def should_notify(alert, new_state):
    passed_rearm_threshold = False
    if alert.rearm and alert.last_triggered_at:
        passed_rearm_threshold = alert.last_triggered_at + datetime.timedelta(seconds=alert.rearm) < utils.utcnow()

    return new_state != alert.state or (alert.state == Alerts.TRIGGERED_STATE and passed_rearm_threshold)


@job("default", timeout=300)
def check_alerts_for_query(query_id, metadata):
    logger.debug("Checking query %d for alerts", query_id)

    query = models.db.session.get(models.Query, query_id)

    for alert in query.alerts:
        logger.info("Checking alert (%d) of query %d.", alert.id, query_id)
        new_state = alert.evaluate()

        if should_notify(alert, new_state):
            logger.info("Alert %d new state: %s", alert.id, new_state)
            old_state = alert.state

            alert.state = new_state
            alert.last_triggered_at = utils.utcnow()
            models.db.session.commit()

            if old_state == Alerts.UNKNOWN_STATE and new_state == Alerts.OK_STATE:
                logger.debug("Skipping notification (previous state was unknown and now it's ok).")
                continue

            if alert.muted:
                logger.debug("Skipping notification (alert muted).")
                continue

            notify_subscriptions(alert, new_state, metadata)

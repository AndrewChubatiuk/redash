import logging
import time

from flask import g, has_request_context
from prometheus_client import Histogram
from sqlalchemy.engine import Engine
from sqlalchemy.event import listens_for
from sqlalchemy.sql import Join
from sqlalchemy.sql.selectable import Alias

metrics_logger = logging.getLogger("metrics")

dbActionLatencyHistogram = Histogram(
    "db_action_latency_milliseconds",
    "Database operation duration",
    ["name", "action"],
)


def _table_name_from_select_element(elt):
    t = elt.get_final_froms()[0]

    if isinstance(t, Alias):
        t = t.element

    while isinstance(t, Join):
        t = t.left

    return t.name


@listens_for(Engine, "before_execute")
def before_execute(conn, elt, multiparams, params, opts):
    conn.info.setdefault("query_start_time", []).append(time.time())


@listens_for(Engine, "after_execute")
def after_execute(conn, elt, multiparams, params, opts, result):
    duration = 1000 * (time.time() - conn.info["query_start_time"].pop(-1))
    action = elt.__class__.__name__

    if action == "Select":
        name = "unknown"
        try:
            name = _table_name_from_select_element(elt)
        except Exception:
            logging.exception("Failed finding table name.")
    elif action in ["Update", "Insert", "Delete"]:
        name = elt.table.name
    else:
        # create/drop tables, sqlalchemy internal schema queries, etc
        return

    action = action.lower()

    dbActionLatencyHistogram.labels(name, action).observe(duration)
    metrics_logger.debug("table=%s query=%s duration=%.2f", name, action, duration)

    if has_request_context():
        g.setdefault("queries_count", 0)
        g.setdefault("queries_duration", 0)
        g.queries_count += 1
        g.queries_duration += duration

    return result

import json
import textwrap
from unittest import mock

from redash.alerts import Alerts
from redash.destinations.asana import Asana
from redash.destinations.datadog import Datadog
from redash.destinations.discord import Discord
from redash.destinations.slack import Slack
from redash.destinations.webex import Webex
from redash.models import NotificationDestination, db
from tests import BaseTestCase


class TestDestinationListResource(BaseTestCase):
    def test_get_returns_all_destinations(self):
        self.factory.create_destination()
        self.factory.create_destination()

        rv = self.make_request("get", "/api/destinations", user=self.factory.user)
        self.assertEqual(len(rv.json), 2)

    def test_get_returns_only_destinations_of_current_org(self):
        self.factory.create_destination()
        self.factory.create_destination()
        self.factory.create_destination(org=self.factory.create_org())

        rv = self.make_request("get", "/api/destinations", user=self.factory.user)
        self.assertEqual(len(rv.json), 2)

    def test_post_creates_new_destination(self):
        data = {
            "options": {"addresses": "test@example.com"},
            "name": "Test",
            "type": "email",
        }
        rv = self.make_request("post", "/api/destinations", user=self.factory.create_admin(), data=data)
        self.assertEqual(rv.status_code, 200)
        pass

    def test_post_requires_admin(self):
        data = {
            "options": {"addresses": "test@example.com"},
            "name": "Test",
            "type": "email",
        }
        rv = self.make_request("post", "/api/destinations", user=self.factory.user, data=data)
        self.assertEqual(rv.status_code, 403)

    def test_returns_400_when_name_already_exists(self):
        d1 = self.factory.create_destination()
        data = {
            "options": {"addresses": "test@example.com"},
            "name": d1.name,
            "type": "email",
        }

        rv = self.make_request("post", "/api/destinations", user=self.factory.create_admin(), data=data)
        self.assertEqual(rv.status_code, 400)


class TestDestinationResource(BaseTestCase):
    def test_get(self):
        d = self.factory.create_destination()
        rv = self.make_request("get", "/api/destinations/{}".format(d.id), user=self.factory.create_admin())
        self.assertEqual(rv.status_code, 200)

    def test_delete(self):
        d = self.factory.create_destination()
        rv = self.make_request("delete", "/api/destinations/{}".format(d.id), user=self.factory.create_admin())
        self.assertEqual(rv.status_code, 204)
        self.assertIsNone(db.session.get(NotificationDestination, d.id))

    def test_post(self):
        d = self.factory.create_destination()
        data = {
            "name": "updated",
            "type": d.type,
            "options": {"url": "https://www.slack.com/updated"},
        }

        rv = self.make_request(
            "post", "/api/destinations/{}".format(d.id), user=self.factory.create_admin(), data=data
        )

        self.assertEqual(rv.status_code, 200)

        d = db.session.get(NotificationDestination, d.id)
        self.assertEqual(d.name, data["name"])
        self.assertEqual(d.options["url"], data["options"]["url"])


def test_discord_notify_calls_requests_post():
    alert = mock.Mock(spec_set=["id", "name", "options", "custom_body", "render_template"])
    alert.id = 1
    alert.name = "Test Alert"
    alert.options = {
        "custom_subject": "Test custom subject",
        "custom_body": "Test custom body",
    }
    alert.custom_body = alert.options["custom_body"]
    alert.render_template = mock.Mock(return_value={"Rendered": "template"})
    query = mock.Mock()
    query.id = 1

    user = mock.Mock()
    app = mock.Mock()
    host = "https://localhost:5000"
    options = {"url": "https://discordapp.com/api/webhooks/test"}
    metadata = {"Scheduled": False}
    new_state = Alerts.TRIGGERED_STATE
    destination = Discord(options)

    with mock.patch("redash.destinations.discord.requests.post") as mock_post:
        mock_response = mock.Mock()
        mock_response.status_code = 204
        mock_post.return_value = mock_response

        destination.notify(alert, query, user, new_state, app, host, metadata, options)

        expected_payload = {
            "content": "Test custom subject",
            "embeds": [
                {
                    "color": "12597547",
                    "fields": [
                        {"name": "Query", "value": f"{host}/queries/{query.id}", "inline": True},
                        {"name": "Alert", "value": f"{host}/alerts/{alert.id}", "inline": True},
                        {"name": "Description", "value": "Test custom body"},
                    ],
                }
            ],
        }

        mock_post.assert_called_once_with(
            "https://discordapp.com/api/webhooks/test",
            data=json.dumps(expected_payload),
            headers={"Content-Type": "application/json"},
            timeout=5.0,
        )

        assert mock_response.status_code == 204


def test_asana_notify_calls_requests_post():
    alert = mock.Mock(spec_set=["id", "name", "options", "render_template"])
    alert.id = 1
    alert.name = "Test Alert"
    alert.options = {
        "custom_subject": "Test custom subject",
        "custom_body": "Test custom body",
    }
    alert.render_template = mock.Mock(return_value={"Rendered": "template"})
    query = mock.Mock()
    query.id = 1

    user = mock.Mock()
    app = mock.Mock()
    host = "https://localhost:5000"
    options = {"pat": "abcd", "project_id": "1234"}
    metadata = {"Scheduled": False}

    new_state = Alerts.TRIGGERED_STATE
    destination = Asana(options)

    with mock.patch("redash.destinations.asana.requests.post") as mock_post:
        mock_response = mock.Mock()
        mock_response.status_code = 204
        mock_post.return_value = mock_response

        destination.notify(alert, query, user, new_state, app, host, metadata, options)

        notes = textwrap.dedent(
            f"""
        {alert.name} has TRIGGERED.

        Query: {host}/queries/{query.id}
        Alert: {host}/alerts/{alert.id}
        """
        ).strip()

        expected_payload = {
            "name": f"[Redash Alert] TRIGGERED: {alert.name}",
            "notes": notes,
            "projects": ["1234"],
        }

        mock_post.assert_called_once_with(
            destination.api_base_url,
            data=expected_payload,
            timeout=5.0,
            headers={"Authorization": "Bearer abcd"},
        )

        assert mock_response.status_code == 204


def test_slack_notify_calls_requests_post():
    alert = mock.Mock(spec_set=["id", "name", "custom_subject", "custom_body", "render_template"])
    alert.id = 1
    alert.name = "Test Alert"
    alert.custom_subject = "Test custom subject"
    alert.custom_body = "Test custom body"

    alert.render_template = mock.Mock(return_value={"Rendered": "template"})
    query = mock.Mock()
    query.id = 1

    user = mock.Mock()
    app = mock.Mock()
    host = "https://localhost:5000"
    options = {"url": "https://slack.com/api/api.test"}
    metadata = {"Scheduled": False}

    new_state = Alerts.TRIGGERED_STATE
    destination = Slack(options)

    with mock.patch("redash.destinations.slack.requests.post") as mock_post:
        mock_response = mock.Mock()
        mock_response.status_code = 204
        mock_post.return_value = mock_response

        destination.notify(alert, query, user, new_state, app, host, metadata, options)

        query_link = f"{host}/queries/{query.id}"
        alert_link = f"{host}/alerts/{alert.id}"

        expected_payload = {
            "attachments": [
                {
                    "text": "Test custom subject",
                    "color": "#c0392b",
                    "fields": [
                        {"title": "Query", "type": "mrkdwn", "value": query_link},
                        {"title": "Alert", "type": "mrkdwn", "value": alert_link},
                        {"title": "Description", "value": "Test custom body"},
                    ],
                }
            ]
        }

        mock_post.assert_called_once_with(
            "https://slack.com/api/api.test",
            data=json.dumps(expected_payload).encode(),
            timeout=5.0,
        )

        assert mock_response.status_code == 204


def test_webex_notify_calls_requests_post():
    alert = mock.Mock(spec_set=["id", "name", "custom_subject", "custom_body", "render_template"])
    alert.id = 1
    alert.name = "Test Alert"
    alert.custom_subject = "Test custom subject"
    alert.custom_body = "Test custom body"

    alert.render_template = mock.Mock(return_value={"Rendered": "template"})
    query = mock.Mock()
    query.id = 1

    user = mock.Mock()
    app = mock.Mock()
    host = "https://localhost:5000"
    options = {"webex_bot_token": "abcd", "to_room_ids": "1234"}
    metadata = {"Scheduled": False}

    new_state = Alerts.TRIGGERED_STATE
    destination = Webex(options)

    with mock.patch("redash.destinations.webex.requests.post") as mock_post:
        mock_response = mock.Mock()
        mock_response.status_code = 204
        mock_post.return_value = mock_response

        destination.notify(alert, query, user, new_state, app, host, metadata, options)

        query_link = f"{host}/queries/{query.id}"
        alert_link = f"{host}/alerts/{alert.id}"

        formatted_attachments = Webex.formatted_attachments_template(
            alert.custom_subject, alert.custom_body, query_link, alert_link
        )

        expected_payload = {
            "markdown": alert.custom_subject + "\n" + alert.custom_body,
            "attachments": formatted_attachments,
            "roomId": "1234",
        }

        mock_post.assert_called_once_with(
            destination.api_base_url,
            json=expected_payload,
            headers={"Authorization": "Bearer abcd"},
            timeout=5.0,
        )

        assert mock_response.status_code == 204


def test_datadog_notify_calls_requests_post():
    alert = mock.Mock(spec_set=["id", "name", "custom_subject", "custom_body", "render_template"])
    alert.id = 1
    alert.name = "Test Alert"
    alert.custom_subject = "Test custom subject"
    alert.custom_body = "Test custom body"
    alert.render_template = mock.Mock(return_value={"Rendered": "template"})
    query = mock.Mock()
    query.id = 1

    user = mock.Mock()
    app = mock.Mock()
    host = "https://localhost:5000"
    options = {
        "api_key": "my-api-key",
        "tags": "foo:bar,zoo:baz",
        "priority": "normal",
        "source_type_name": "postgres",
    }
    metadata = {"Scheduled": False}
    new_state = Alerts.TRIGGERED_STATE
    destination = Datadog(options)

    with mock.patch("redash.destinations.datadog.requests.post") as mock_post:
        mock_response = mock.Mock()
        mock_response.status_code = 202
        mock_post.return_value = mock_response

        destination.notify(alert, query, user, new_state, app, host, metadata, options)

        expected_payload = {
            "title": "Test custom subject",
            "text": "Test custom body\nQuery: https://localhost:5000/queries/1\nAlert: https://localhost:5000/alerts/1",
            "alert_type": "error",
            "priority": "normal",
            "source_type_name": "postgres",
            "aggregation_key": "redash:https://localhost:5000/alerts/1",
            "tags": [
                "foo:bar",
                "zoo:baz",
                "redash",
                "query_id:1",
                "alert_id:1",
            ],
        }

        mock_post.assert_called_once_with(
            "https://api.datadoghq.com/api/v1/events",
            data=json.dumps(expected_payload),
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "DD-API-KEY": "my-api-key",
            },
            timeout=5.0,
        )

        assert mock_response.status_code == 202

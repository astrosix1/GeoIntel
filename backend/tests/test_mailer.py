"""Resend mailer: off without config, correct request when on, never raises."""
from unittest.mock import MagicMock, patch

import pytest
import requests

from services import mailer


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    monkeypatch.setenv('RESEND_API_KEY', 're_test_key')
    monkeypatch.setenv('ALERT_FROM_EMAIL', 'GeoIntel <alerts@example.com>')


def test_not_configured_without_key(monkeypatch):
    monkeypatch.delenv('RESEND_API_KEY')
    assert mailer.is_configured() is False


def test_not_configured_without_sender(monkeypatch):
    monkeypatch.delenv('ALERT_FROM_EMAIL')
    assert mailer.is_configured() is False


def test_send_does_nothing_when_unconfigured(monkeypatch):
    monkeypatch.delenv('RESEND_API_KEY')
    with patch.object(mailer.requests, 'post') as post:
        assert mailer.send_email('a@b.co', 's', '<p>h</p>', 't') is False
    post.assert_not_called()


def test_send_posts_the_expected_request():
    with patch.object(mailer.requests, 'post', return_value=MagicMock(raise_for_status=lambda: None)) as post:
        assert mailer.send_email('a@b.co', 'Subject', '<p>h</p>', 'plain') is True
    assert post.call_args.args[0] == 'https://api.resend.com/emails'
    assert post.call_args.kwargs['headers']['Authorization'] == 'Bearer re_test_key'
    assert post.call_args.kwargs['json'] == {
        'from': 'GeoIntel <alerts@example.com>', 'to': ['a@b.co'],
        'subject': 'Subject', 'html': '<p>h</p>', 'text': 'plain',
    }


@pytest.mark.parametrize('error', [requests.ConnectionError('down'), requests.Timeout('slow')])
def test_network_failure_returns_false(error):
    with patch.object(mailer.requests, 'post', side_effect=error):
        assert mailer.send_email('a@b.co', 's', 'h', 't') is False


def test_http_error_returns_false():
    bad = MagicMock()
    bad.raise_for_status.side_effect = requests.HTTPError('422')
    with patch.object(mailer.requests, 'post', return_value=bad):
        assert mailer.send_email('a@b.co', 's', 'h', 't') is False

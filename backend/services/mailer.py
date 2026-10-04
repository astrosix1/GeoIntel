"""Outbound email through Resend's HTTP API.

Needs RESEND_API_KEY and ALERT_FROM_EMAIL (a sender on a domain verified in
Resend, e.g. "GeoIntel <alerts@yourdomain.com>"). When either is missing the
mailer is simply off: callers check is_configured() and in-app alerts carry on.
"""
import logging
import os

import requests

logger = logging.getLogger(__name__)

RESEND_URL = 'https://api.resend.com/emails'
TIMEOUT = 8

_warned = False


def is_configured():
    global _warned
    ok = bool(os.getenv('RESEND_API_KEY', '').strip() and os.getenv('ALERT_FROM_EMAIL', '').strip())
    if not ok and not _warned:
        logger.warning("Email alerts are off: set RESEND_API_KEY and ALERT_FROM_EMAIL to enable them")
        _warned = True
    return ok


def send_email(to, subject, html, text):
    """True if Resend accepted the message. Never raises."""
    if not is_configured():
        return False
    try:
        response = requests.post(
            RESEND_URL,
            headers={'Authorization': f"Bearer {os.getenv('RESEND_API_KEY', '').strip()}"},
            json={
                'from': os.getenv('ALERT_FROM_EMAIL', '').strip(),
                'to': [to],
                'subject': subject,
                'html': html,
                'text': text,
            },
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        return True
    except requests.RequestException as e:
        logger.error(f"Resend send failed: {e}")
        return False

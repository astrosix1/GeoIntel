"""Event comments, display names and moderation, stored in Supabase (see
backend/supabase/003_geointel_comments.sql — RLS on, no policies, so only this
backend's service-role key reaches the tables).

Who may do what is decided by the callers (blueprints/comments.py): reading is
public, posting and reporting need premium, deleting needs only the author's
sign-in. This module scopes every write by the verified user id it is given.

Moderation: a comment is `visible`, `hidden` (auto-hidden once
AUTO_HIDE_THRESHOLD different people report it; shown only to its author and
the admin) or `removed` (never served).
"""
import re
import unicodedata
from datetime import datetime, timezone

from models import Session, Crisis
from services.supabase_rest import SupabaseConflict, check_uuid, rest

AUTO_HIDE_THRESHOLD = 5
MAX_BODY = 1000
PAGE_SIZE = 50
COOLDOWN_SECONDS = 10
MIN_NAME, MAX_NAME = 2, 40
REPORT_REASONS = ('spam', 'abusive', 'misinformation', 'other')

_COMMENT_COLUMNS = 'id,crisis_id,user_id,author_name,body,status,report_count,created_at'
_CRISIS_ID_RE = re.compile(r'^[A-Za-z0-9_.:-]{1,60}$')


class InvalidDisplayName(ValueError):
    pass


class DisplayNameTaken(Exception):
    pass


class InvalidComment(ValueError):
    pass


class ProfileRequired(Exception):
    pass


class TooFast(Exception):
    pass


class CannotReportOwn(Exception):
    pass


class InvalidReport(ValueError):
    pass


def _strip_control(text, keep_newlines=False):
    return ''.join(
        ch for ch in text
        if unicodedata.category(ch) != 'Cc' or (keep_newlines and ch == '\n')
    )


def clean_display_name(raw):
    if not isinstance(raw, str):
        raise InvalidDisplayName('display name must be text')
    name = ' '.join(_strip_control(raw).split())
    if not (MIN_NAME <= len(name) <= MAX_NAME):
        raise InvalidDisplayName(f'display name must be {MIN_NAME}-{MAX_NAME} characters')
    if not any(ch.isalnum() for ch in name):
        raise InvalidDisplayName('display name needs at least one letter or number')
    return name


def clean_body(raw):
    if not isinstance(raw, str):
        raise InvalidComment('empty')
    text = _strip_control(raw.replace('\r\n', '\n').replace('\r', '\n'), keep_newlines=True)
    text = re.sub(r'\n{3,}', '\n\n', text).strip()
    if not text:
        raise InvalidComment('empty')
    if len(text) > MAX_BODY:
        raise InvalidComment('too_long')
    return text


def get_profile(user_id):
    uid = check_uuid(user_id)
    rows = rest('GET', 'geointel_profiles', params={
        'user_id': f'eq.{uid}', 'select': 'display_name', 'limit': '1',
    }).json()
    return rows[0] if rows else None


def set_profile(user_id, raw_name):
    """Create or rename the user's public display name (unique, ignoring case)."""
    uid = check_uuid(user_id)
    name = clean_display_name(raw_name)
    try:
        rest('POST', 'geointel_profiles', params={'on_conflict': 'user_id'},
             json_body=[{'user_id': uid, 'display_name': name}],
             prefer='resolution=merge-duplicates')
    except SupabaseConflict as e:
        raise DisplayNameTaken() from e
    return {'display_name': name}


def _public(row, viewer_id):
    return {
        'id': row['id'],
        'body': row['body'],
        'author_name': row['author_name'],
        'created_at': row['created_at'],
        'mine': viewer_id is not None and row['user_id'] == viewer_id,
        'hidden': row['status'] == 'hidden',
    }


def _valid_cursor(before):
    try:
        datetime.fromisoformat(before.replace('Z', '+00:00'))
        return True
    except (AttributeError, ValueError):
        return False


def list_comments(crisis_id, viewer_id=None, limit=PAGE_SIZE, before=None):
    """Newest first: every visible comment plus the viewer's own hidden ones.
    Returns {'comments': [...], 'next_before': cursor-or-None}."""
    if not _CRISIS_ID_RE.match(crisis_id or ''):
        return {'comments': [], 'next_before': None}
    viewer = check_uuid(viewer_id) if viewer_id else None
    base = {'crisis_id': f'eq.{crisis_id}', 'select': _COMMENT_COLUMNS, 'order': 'created_at.desc'}
    if before and _valid_cursor(before):
        base['created_at'] = f'lt.{before}'

    visible = rest('GET', 'geointel_comments', params={**base, 'status': 'eq.visible', 'limit': str(limit)}).json()
    own_hidden = []
    if viewer:
        own_hidden = rest('GET', 'geointel_comments', params={
            **base, 'user_id': f'eq.{viewer}', 'status': 'eq.hidden', 'limit': str(PAGE_SIZE),
        }).json()

    merged = sorted(visible + own_hidden, key=lambda r: r['created_at'], reverse=True)[:limit]
    next_before = merged[-1]['created_at'] if len(visible) >= limit and merged else None
    return {'comments': [_public(r, viewer) for r in merged], 'next_before': next_before}


def post_comment(user_id, crisis_id, raw_body):
    """The new comment, or None if the crisis doesn't exist. Raises
    InvalidComment, ProfileRequired (no display name yet) or TooFast."""
    uid = check_uuid(user_id)
    session = Session()
    try:
        if not session.query(Crisis.id).filter(Crisis.id == crisis_id).first():
            return None
    finally:
        session.close()
    body = clean_body(raw_body)
    profile = get_profile(uid)
    if not profile:
        raise ProfileRequired()

    latest = rest('GET', 'geointel_comments', params={
        'user_id': f'eq.{uid}', 'select': 'created_at', 'order': 'created_at.desc', 'limit': '1',
    }).json()
    if latest:
        last = datetime.fromisoformat(latest[0]['created_at'].replace('Z', '+00:00'))
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        if (datetime.now(timezone.utc) - last).total_seconds() < COOLDOWN_SECONDS:
            raise TooFast()

    rows = rest('POST', 'geointel_comments', params={'select': _COMMENT_COLUMNS},
                json_body=[{'crisis_id': crisis_id, 'user_id': uid,
                            'author_name': profile['display_name'], 'body': body}],
                prefer='return=representation').json()
    return _public(rows[0], uid)


def delete_own_comment(user_id, comment_id):
    """True if the user's own comment was deleted; False if it doesn't exist
    or isn't theirs."""
    uid = check_uuid(user_id)
    cid = check_uuid(comment_id)
    rows = rest('DELETE', 'geointel_comments', params={'id': f'eq.{cid}', 'user_id': f'eq.{uid}'},
                prefer='return=representation').json()
    return bool(rows)


def report_comment(reporter_id, comment_id, reason):
    """Record a report and auto-hide the comment at AUTO_HIDE_THRESHOLD distinct
    reporters. Returns {'reported': True, 'hidden': bool}, or None if the
    comment doesn't exist (or was removed). Idempotent per reporter."""
    rid = check_uuid(reporter_id)
    cid = check_uuid(comment_id)
    if reason not in REPORT_REASONS:
        raise InvalidReport('unknown reason')
    found = rest('GET', 'geointel_comments', params={
        'id': f'eq.{cid}', 'select': 'id,user_id,status', 'limit': '1',
    }).json()
    if not found or found[0]['status'] == 'removed':
        return None
    if found[0]['user_id'] == rid:
        raise CannotReportOwn()

    rest('POST', 'geointel_comment_reports', params={'on_conflict': 'comment_id,reporter_id'},
         json_body=[{'comment_id': cid, 'reporter_id': rid, 'reason': reason}],
         prefer='resolution=ignore-duplicates')
    reporters = rest('GET', 'geointel_comment_reports', params={
        'comment_id': f'eq.{cid}', 'select': 'reporter_id', 'limit': '1000',
    }).json()
    count = len(reporters)

    update = {'report_count': count}
    hidden = found[0]['status'] == 'hidden'
    if count >= AUTO_HIDE_THRESHOLD and found[0]['status'] == 'visible':
        update['status'] = 'hidden'
        hidden = True
    rest('PATCH', 'geointel_comments', params={'id': f'eq.{cid}'}, json_body=update)
    return {'reported': True, 'hidden': hidden}


# ---- Admin review (callers must have passed services/auth.check_admin_key) ----

def list_reported():
    """Hidden comments plus visible ones that have any reports, newest first."""
    hidden = rest('GET', 'geointel_comments', params={
        'status': 'eq.hidden', 'select': _COMMENT_COLUMNS, 'order': 'created_at.desc', 'limit': '200',
    }).json()
    reported = rest('GET', 'geointel_comments', params={
        'status': 'eq.visible', 'report_count': 'gt.0', 'select': _COMMENT_COLUMNS,
        'order': 'created_at.desc', 'limit': '200',
    }).json()
    return sorted(hidden + reported, key=lambda r: r['created_at'], reverse=True)


def list_reports(comment_id):
    cid = check_uuid(comment_id)
    return rest('GET', 'geointel_comment_reports', params={
        'comment_id': f'eq.{cid}', 'select': 'reporter_id,reason,created_at', 'order': 'created_at.desc',
    }).json()


def restore_comment(comment_id):
    """Make a comment visible again and clear its reports, so it needs a fresh
    AUTO_HIDE_THRESHOLD reports to be hidden again. False if it doesn't exist."""
    cid = check_uuid(comment_id)
    rest('DELETE', 'geointel_comment_reports', params={'comment_id': f'eq.{cid}'})
    rows = rest('PATCH', 'geointel_comments', params={'id': f'eq.{cid}'},
                json_body={'status': 'visible', 'report_count': 0},
                prefer='return=representation').json()
    return bool(rows)


def remove_comment(comment_id):
    """Permanently stop serving a comment (kept in the table for the record)."""
    cid = check_uuid(comment_id)
    rows = rest('PATCH', 'geointel_comments', params={'id': f'eq.{cid}'},
                json_body={'status': 'removed'}, prefer='return=representation').json()
    return bool(rows)

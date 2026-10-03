"""Comments, display names and moderation: the service layer (against an
in-memory fake of the Supabase REST calls) and the HTTP endpoints, including
the auto-hide threshold and admin review."""
import time
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import jwt
import pytest

from cache import cache_delete
from extensions import limiter
from models import Crisis
from services import comments as svc
from services import entitlements, supabase_rest
from services.supabase_rest import SupabaseUnavailable
from supabase_fake import FakePostgrest

SECRET = 'jwt-signing-secret'


@pytest.fixture(autouse=True)
def fresh_limits(app_module):
    limiter.reset()
    yield


@pytest.fixture()
def db(monkeypatch):
    monkeypatch.setenv('SUPABASE_URL', 'https://proj.supabase.co')
    monkeypatch.setenv('SUPABASE_SERVICE_ROLE_KEY', 'service-key')
    fake = FakePostgrest()
    with patch.object(supabase_rest.requests, 'request', fake.request):
        yield fake


@pytest.fixture()
def crisis_id(app_module, client, db_session):
    client.get('/api/health')  # let the app's first-request seeding happen now
    cid = f'cmt-{uuid.uuid4().hex[:8]}'
    db_session.add(Crisis(id=cid, type='conflict', title='Event', country='Testland', latitude=1,
                          longitude=2, severity=50, source='GDELT', is_active=True))
    db_session.commit()
    yield cid
    db_session.query(Crisis).filter(Crisis.id == cid).delete()
    db_session.commit()


def uid():
    return str(uuid.uuid4())


def with_profile(db, user_id, name='Alice'):
    db.add('geointel_profiles', user_id=user_id, display_name=name)
    return user_id


def add_comment(db, crisis, user_id, body='hello', status='visible', author='Alice', **extra):
    return db.add('geointel_comments', crisis_id=crisis, user_id=user_id, author_name=author,
                  body=body, status=status, **extra)


class TestCleaning:
    def test_display_name_is_trimmed_and_collapsed(self):
        assert svc.clean_display_name('  Ada   Lovelace \t') == 'Ada Lovelace'

    def test_display_name_strips_control_characters(self):
        assert svc.clean_display_name('Ada\x00\x07') == 'Ada'

    @pytest.mark.parametrize('bad', ['', 'A', 'x' * 41, '!!!', '   ', None, 5])
    def test_bad_display_names(self, bad):
        with pytest.raises(svc.InvalidDisplayName):
            svc.clean_display_name(bad)

    def test_body_is_normalised(self):
        assert svc.clean_body('  hi\r\n\r\n\r\n\r\nthere\x00  ') == 'hi\n\nthere'

    def test_body_limit_is_inclusive(self):
        assert len(svc.clean_body('a' * 1000)) == 1000
        with pytest.raises(svc.InvalidComment) as exc:
            svc.clean_body('a' * 1001)
        assert str(exc.value) == 'too_long'

    @pytest.mark.parametrize('bad', ['', '   \n  ', '\x00\x01', None, 7])
    def test_empty_or_non_text_body(self, bad):
        with pytest.raises(svc.InvalidComment) as exc:
            svc.clean_body(bad)
        assert str(exc.value) == 'empty'


class TestProfiles:
    def test_create_and_read(self, db):
        user = uid()
        assert svc.set_profile(user, ' Ada  L ') == {'display_name': 'Ada L'}
        assert svc.get_profile(user) == {'display_name': 'Ada L'}

    def test_no_profile_yet(self, db):
        assert svc.get_profile(uid()) is None

    def test_renaming_is_allowed(self, db):
        user = uid()
        svc.set_profile(user, 'First')
        svc.set_profile(user, 'Second')
        assert svc.get_profile(user)['display_name'] == 'Second'

    def test_names_are_unique_ignoring_case(self, db):
        svc.set_profile(uid(), 'Ada')
        with pytest.raises(svc.DisplayNameTaken):
            svc.set_profile(uid(), 'aDa')

    def test_keeping_your_own_name_is_not_a_conflict(self, db):
        user = uid()
        svc.set_profile(user, 'Ada')
        assert svc.set_profile(user, 'ADA') == {'display_name': 'ADA'}


class TestPosting:
    def test_requires_a_profile(self, db, crisis_id):
        with pytest.raises(svc.ProfileRequired):
            svc.post_comment(uid(), crisis_id, 'hello')

    def test_unknown_crisis_returns_none_and_writes_nothing(self, db):
        user = with_profile(db, uid())
        assert svc.post_comment(user, 'does-not-exist', 'hello') is None
        assert ('POST', 'geointel_comments') not in db.calls

    def test_posts_with_a_name_snapshot(self, db, crisis_id):
        user = with_profile(db, uid(), 'Ada')
        comment = svc.post_comment(user, crisis_id, '  first!  ')
        assert comment['body'] == 'first!'
        assert comment['author_name'] == 'Ada'
        assert comment['mine'] is True and comment['hidden'] is False
        assert db.tables['geointel_comments'][0]['user_id'] == user

    def test_old_comments_keep_the_old_name_after_a_rename(self, db, crisis_id):
        user = with_profile(db, uid(), 'Ada')
        svc.post_comment(user, crisis_id, 'hi')
        svc.set_profile(user, 'Ada Renamed')
        assert svc.list_comments(crisis_id)['comments'][0]['author_name'] == 'Ada'

    def test_invalid_body_is_rejected_before_any_write(self, db, crisis_id):
        user = with_profile(db, uid())
        with pytest.raises(svc.InvalidComment):
            svc.post_comment(user, crisis_id, '   ')
        assert ('POST', 'geointel_comments') not in db.calls

    def test_cooldown_blocks_a_rapid_second_comment(self, db, crisis_id):
        user = with_profile(db, uid())
        svc.post_comment(user, crisis_id, 'one')
        with pytest.raises(svc.TooFast):
            svc.post_comment(user, crisis_id, 'two')

    def test_cooldown_expires(self, db, crisis_id):
        user = with_profile(db, uid())
        svc.post_comment(user, crisis_id, 'one')
        db.tables['geointel_comments'][0]['created_at'] = (
            datetime.now(timezone.utc) - timedelta(seconds=svc.COOLDOWN_SECONDS + 1)).isoformat()
        assert svc.post_comment(user, crisis_id, 'two') is not None

    def test_cooldown_is_per_user(self, db, crisis_id):
        a, b = with_profile(db, uid(), 'A1'), with_profile(db, uid(), 'B2')
        svc.post_comment(a, crisis_id, 'one')
        assert svc.post_comment(b, crisis_id, 'two') is not None


class TestListing:
    def test_newest_first_and_visible_only(self, db, crisis_id):
        author = uid()
        add_comment(db, crisis_id, author, 'old')
        add_comment(db, crisis_id, author, 'secret', status='hidden')
        add_comment(db, crisis_id, author, 'gone', status='removed')
        add_comment(db, crisis_id, author, 'new')
        assert [c['body'] for c in svc.list_comments(crisis_id)['comments']] == ['new', 'old']

    def test_author_sees_their_own_hidden_comment_flagged(self, db, crisis_id):
        author, other = uid(), uid()
        add_comment(db, crisis_id, author, 'visible one')
        add_comment(db, crisis_id, author, 'hidden one', status='hidden')
        mine = svc.list_comments(crisis_id, viewer_id=author)['comments']
        assert [(c['body'], c['hidden'], c['mine']) for c in mine] == [
            ('hidden one', True, True), ('visible one', False, True)]
        assert [c['body'] for c in svc.list_comments(crisis_id, viewer_id=other)['comments']] == ['visible one']

    def test_removed_is_never_served_even_to_the_author(self, db, crisis_id):
        author = uid()
        add_comment(db, crisis_id, author, 'gone', status='removed')
        assert svc.list_comments(crisis_id, viewer_id=author)['comments'] == []

    def test_other_events_comments_are_not_included(self, db, crisis_id):
        add_comment(db, 'another-crisis', uid(), 'elsewhere')
        assert svc.list_comments(crisis_id)['comments'] == []

    def test_mine_flag(self, db, crisis_id):
        author, other = uid(), uid()
        add_comment(db, crisis_id, author, 'x')
        assert svc.list_comments(crisis_id, viewer_id=author)['comments'][0]['mine'] is True
        assert svc.list_comments(crisis_id, viewer_id=other)['comments'][0]['mine'] is False
        assert svc.list_comments(crisis_id)['comments'][0]['mine'] is False

    def test_output_hides_internal_fields(self, db, crisis_id):
        add_comment(db, crisis_id, uid(), 'x', report_count=3)
        assert set(svc.list_comments(crisis_id)['comments'][0]) == {
            'id', 'body', 'author_name', 'created_at', 'mine', 'hidden'}

    def test_paging(self, db, crisis_id):
        author = uid()
        for i in range(3):
            add_comment(db, crisis_id, author, f'c{i}')
        first = svc.list_comments(crisis_id, limit=2)
        assert [c['body'] for c in first['comments']] == ['c2', 'c1']
        assert first['next_before'] is not None
        second = svc.list_comments(crisis_id, limit=2, before=first['next_before'])
        assert [c['body'] for c in second['comments']] == ['c0']
        assert second['next_before'] is None

    def test_malformed_crisis_id_is_empty(self, db):
        assert svc.list_comments("x' or 1=1") == {'comments': [], 'next_before': None}
        assert db.calls == []


class TestDelete:
    def test_author_can_delete(self, db, crisis_id):
        author = uid()
        comment = add_comment(db, crisis_id, author)
        assert svc.delete_own_comment(author, comment['id']) is True
        assert svc.list_comments(crisis_id)['comments'] == []

    def test_cannot_delete_someone_elses(self, db, crisis_id):
        comment = add_comment(db, crisis_id, uid())
        assert svc.delete_own_comment(uid(), comment['id']) is False
        assert len(svc.list_comments(crisis_id)['comments']) == 1

    def test_unknown_comment(self, db):
        assert svc.delete_own_comment(uid(), str(uuid.uuid4())) is False

    def test_malformed_id_raises(self, db):
        with pytest.raises(SupabaseUnavailable):
            svc.delete_own_comment(uid(), 'not-a-uuid')

    def test_deleting_removes_its_reports(self, db, crisis_id):
        author = uid()
        comment = add_comment(db, crisis_id, author)
        svc.report_comment(uid(), comment['id'], 'spam')
        svc.delete_own_comment(author, comment['id'])
        assert db.tables['geointel_comment_reports'] == []


class TestReporting:
    def test_unknown_or_removed_comment_is_none(self, db, crisis_id):
        assert svc.report_comment(uid(), str(uuid.uuid4()), 'spam') is None
        removed = add_comment(db, crisis_id, uid(), status='removed')
        assert svc.report_comment(uid(), removed['id'], 'spam') is None

    def test_cannot_report_your_own(self, db, crisis_id):
        author = uid()
        comment = add_comment(db, crisis_id, author)
        with pytest.raises(svc.CannotReportOwn):
            svc.report_comment(author, comment['id'], 'spam')

    def test_unknown_reason_is_rejected(self, db, crisis_id):
        comment = add_comment(db, crisis_id, uid())
        with pytest.raises(svc.InvalidReport):
            svc.report_comment(uid(), comment['id'], 'because')

    def test_same_person_reporting_twice_counts_once(self, db, crisis_id):
        comment = add_comment(db, crisis_id, uid())
        reporter = uid()
        svc.report_comment(reporter, comment['id'], 'spam')
        svc.report_comment(reporter, comment['id'], 'abusive')
        assert comment['report_count'] == 1
        assert len(db.tables['geointel_comment_reports']) == 1

    def test_four_reports_do_not_hide(self, db, crisis_id):
        comment = add_comment(db, crisis_id, uid())
        for _ in range(svc.AUTO_HIDE_THRESHOLD - 1):
            assert svc.report_comment(uid(), comment['id'], 'spam') == {'reported': True, 'hidden': False}
        assert comment['status'] == 'visible'

    def test_fifth_distinct_report_hides(self, db, crisis_id):
        comment = add_comment(db, crisis_id, uid())
        results = [svc.report_comment(uid(), comment['id'], 'abusive') for _ in range(svc.AUTO_HIDE_THRESHOLD)]
        assert results[-1] == {'reported': True, 'hidden': True}
        assert comment['status'] == 'hidden' and comment['report_count'] == 5
        assert svc.list_comments(crisis_id)['comments'] == []

    def test_restored_comment_needs_five_fresh_reports(self, db, crisis_id):
        comment = add_comment(db, crisis_id, uid())
        for _ in range(5):
            svc.report_comment(uid(), comment['id'], 'spam')
        assert svc.restore_comment(comment['id']) is True
        assert comment['status'] == 'visible' and comment['report_count'] == 0
        for _ in range(4):
            svc.report_comment(uid(), comment['id'], 'spam')
        assert comment['status'] == 'visible'
        svc.report_comment(uid(), comment['id'], 'spam')
        assert comment['status'] == 'hidden'


class TestAdminReview:
    def test_list_reported_has_hidden_and_reported_but_not_clean(self, db, crisis_id):
        add_comment(db, crisis_id, uid(), 'clean')
        add_comment(db, crisis_id, uid(), 'auto hidden', status='hidden', report_count=5)
        add_comment(db, crisis_id, uid(), 'flagged', report_count=2)
        add_comment(db, crisis_id, uid(), 'removed already', status='removed', report_count=9)
        assert {c['body'] for c in svc.list_reported()} == {'auto hidden', 'flagged'}

    def test_reports_detail(self, db, crisis_id):
        comment = add_comment(db, crisis_id, uid())
        svc.report_comment(uid(), comment['id'], 'spam')
        assert [r['reason'] for r in svc.list_reports(comment['id'])] == ['spam']

    def test_restore_and_remove(self, db, crisis_id):
        comment = add_comment(db, crisis_id, uid(), status='hidden', report_count=5)
        assert svc.restore_comment(comment['id']) is True
        assert svc.list_comments(crisis_id)['comments'][0]['body'] == 'hello'
        assert svc.remove_comment(comment['id']) is True
        assert svc.list_comments(crisis_id)['comments'] == []

    def test_unknown_comment(self, db):
        assert svc.restore_comment(str(uuid.uuid4())) is False
        assert svc.remove_comment(str(uuid.uuid4())) is False


def token(user_id):
    return jwt.encode({'sub': user_id, 'aud': 'authenticated', 'exp': int(time.time()) + 3600},
                      SECRET, algorithm='HS256')


@pytest.fixture()
def secret(monkeypatch):
    monkeypatch.setenv('SUPABASE_JWT_SECRET', SECRET)


def call(client, method, path, user=None, plan='active', **kwargs):
    headers = dict(kwargs.pop('headers', {}))
    if user:
        headers['Authorization'] = f'Bearer {token(user)}'
    row = {'status': plan} if plan else None
    if user:
        cache_delete(f'plan:{user}')   # each call states its own plan; don't reuse a cached one
    with patch.object(entitlements, '_fetch_subscription', return_value=row):
        return getattr(client, method)(path, headers=headers, **kwargs)


class TestEndpoints:
    def test_anyone_can_read(self, client, secret, db, crisis_id):
        add_comment(db, crisis_id, uid(), 'public note')
        for user, plan in ((None, 'active'), (uid(), None)):   # anonymous, signed-in free
            res = call(client, 'get', f'/api/crises/{crisis_id}/comments', user, plan)
            assert res.status_code == 200
            assert [c['body'] for c in res.get_json()['comments']] == ['public note']

    def test_author_sees_own_hidden_comment_over_http(self, client, secret, db, crisis_id):
        author = uid()
        add_comment(db, crisis_id, author, 'hidden note', status='hidden')
        mine = call(client, 'get', f'/api/crises/{crisis_id}/comments', author).get_json()['comments']
        assert mine[0]['hidden'] is True
        assert call(client, 'get', f'/api/crises/{crisis_id}/comments').get_json()['comments'] == []

    def test_post_gating(self, client, secret, db, crisis_id):
        url = f'/api/crises/{crisis_id}/comments'
        assert call(client, 'post', url, json={'body': 'hi'}).status_code == 401
        free = call(client, 'post', url, uid(), plan=None, json={'body': 'hi'})
        assert free.status_code == 403
        assert db.calls == []

    def test_post_needs_a_profile_then_works(self, client, secret, db, crisis_id):
        user, url = uid(), f'/api/crises/{crisis_id}/comments'
        assert call(client, 'post', url, user, json={'body': 'hi'}).get_json() == {'error': 'profile_required'}
        assert call(client, 'put', '/api/me/profile', user, json={'display_name': 'Ada'}).status_code == 200
        res = call(client, 'post', url, user, json={'body': 'hi'})
        assert res.status_code == 201
        assert res.get_json()['comment']['author_name'] == 'Ada'

    def test_post_validation_and_cooldown(self, client, secret, db, crisis_id):
        user, url = with_profile(db, uid(), 'Ada'), f'/api/crises/{crisis_id}/comments'
        assert call(client, 'post', url, user, json={'body': '   '}).status_code == 400
        assert call(client, 'post', url, user, json={}).status_code == 400
        assert call(client, 'post', url, user, json={'body': 'x' * 1001}).status_code == 400
        assert call(client, 'post', url, user, json={'body': 'ok'}).status_code == 201
        assert call(client, 'post', url, user, json={'body': 'again'}).status_code == 429

    def test_post_to_unknown_crisis_is_404(self, client, secret, db, crisis_id):
        user = with_profile(db, uid())
        assert call(client, 'post', '/api/crises/nope/comments', user, json={'body': 'hi'}).status_code == 404

    def test_delete_needs_only_a_signed_in_author(self, client, secret, db, crisis_id):
        author, other = uid(), uid()
        comment = add_comment(db, crisis_id, author)
        path = f"/api/comments/{comment['id']}"
        assert call(client, 'delete', path).status_code == 401
        assert call(client, 'delete', path, other, plan=None).status_code == 404
        assert call(client, 'delete', path, author, plan=None).status_code == 204   # lapsed premium is fine

    def test_delete_with_a_malformed_id_is_404(self, client, secret, db):
        assert call(client, 'delete', '/api/comments/not-a-uuid', uid()).status_code == 404

    def test_report_gating_and_flow(self, client, secret, db, crisis_id):
        comment = add_comment(db, crisis_id, uid())
        path = f"/api/comments/{comment['id']}/report"
        assert call(client, 'post', path, json={'reason': 'spam'}).status_code == 401
        assert call(client, 'post', path, uid(), plan=None, json={'reason': 'spam'}).status_code == 403
        assert call(client, 'post', path, uid(), json={'reason': 'bogus'}).status_code == 400
        assert call(client, 'post', path, uid(), json={'reason': 'spam'}).get_json() == {'reported': True, 'hidden': False}

    def test_cannot_report_own_over_http(self, client, secret, db, crisis_id):
        author = uid()
        comment = add_comment(db, crisis_id, author)
        res = call(client, 'post', f"/api/comments/{comment['id']}/report", author, json={'reason': 'spam'})
        assert res.status_code == 400 and res.get_json()['error'] == 'cannot_report_own'

    def test_five_reports_hide_it_from_readers(self, client, secret, db, crisis_id):
        comment = add_comment(db, crisis_id, uid())
        for _ in range(5):
            call(client, 'post', f"/api/comments/{comment['id']}/report", uid(), json={'reason': 'abusive'})
        assert call(client, 'get', f'/api/crises/{crisis_id}/comments').get_json()['comments'] == []

    def test_report_unknown_comment_is_404(self, client, secret, db):
        assert call(client, 'post', f'/api/comments/{uuid.uuid4()}/report', uid(), json={'reason': 'spam'}).status_code == 404

    def test_profile_endpoints(self, client, secret, db):
        user = uid()
        assert call(client, 'get', '/api/me/profile', user).get_json() == {'profile': None}
        assert call(client, 'put', '/api/me/profile', user, plan=None, json={'display_name': 'Ada'}).status_code == 403
        assert call(client, 'put', '/api/me/profile', user, json={'display_name': 'Ada'}).get_json() == {'profile': {'display_name': 'Ada'}}
        assert call(client, 'put', '/api/me/profile', uid(), json={'display_name': 'ada'}).status_code == 409
        assert call(client, 'put', '/api/me/profile', uid(), json={'display_name': '!'}).status_code == 400

    def test_supabase_down_is_503(self, client, secret, db, crisis_id):
        db.fail = True
        res = call(client, 'get', f'/api/crises/{crisis_id}/comments')
        assert res.status_code == 503 and res.get_json()['error'] == 'user_data_unavailable'


class TestAdminEndpoints:
    @pytest.fixture(autouse=True)
    def admin_key(self, monkeypatch):
        monkeypatch.setenv('ADMIN_KEY', 'admin-secret')

    ADMIN = {'X-Admin-Key': 'admin-secret'}

    def test_rejects_without_the_admin_key(self, client, db, crisis_id):
        comment = add_comment(db, crisis_id, uid(), status='hidden')
        for method, path in (('get', '/api/admin/comments/reported'),
                             ('get', f"/api/admin/comments/{comment['id']}/reports"),
                             ('post', f"/api/admin/comments/{comment['id']}/restore"),
                             ('post', f"/api/admin/comments/{comment['id']}/remove")):
            assert getattr(client, method)(path).status_code == 401
            assert getattr(client, method)(path, headers={'X-Admin-Key': 'wrong'}).status_code == 401
        assert comment['status'] == 'hidden'

    def test_review_flow(self, client, db, crisis_id):
        comment = add_comment(db, crisis_id, uid(), 'bad one', status='hidden', report_count=5)
        listed = client.get('/api/admin/comments/reported', headers=self.ADMIN).get_json()['comments']
        assert [c['body'] for c in listed] == ['bad one']
        assert client.post(f"/api/admin/comments/{comment['id']}/restore", headers=self.ADMIN).status_code == 200
        assert comment['status'] == 'visible'
        assert client.post(f"/api/admin/comments/{comment['id']}/remove", headers=self.ADMIN).status_code == 200
        assert comment['status'] == 'removed'

    def test_reports_detail_endpoint(self, client, db, crisis_id):
        comment = add_comment(db, crisis_id, uid())
        svc.report_comment(uid(), comment['id'], 'spam')
        res = client.get(f"/api/admin/comments/{comment['id']}/reports", headers=self.ADMIN)
        assert [r['reason'] for r in res.get_json()['reports']] == ['spam']

    def test_unknown_and_malformed_ids_are_404(self, client, db):
        assert client.post(f'/api/admin/comments/{uuid.uuid4()}/restore', headers=self.ADMIN).status_code == 404
        assert client.post('/api/admin/comments/not-a-uuid/remove', headers=self.ADMIN).status_code == 404

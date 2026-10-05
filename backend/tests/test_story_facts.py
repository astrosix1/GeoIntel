"""Story fact extraction: validation, the stored-once rule, and what is retried."""
import json
import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from models import Crisis
from services import story_facts as sf

GOOD = {'place': 'Obuasi gold mine', 'country': 'Ghana', 'is_statement': False, 'event_type': 'accident',
        'killed': 5, 'injured': None, 'scale_cues': ['ongoing'], 'summary': 'A tunnel collapsed.',
        'confidence': 'high'}
PAGE = {'title': 'Tunnel collapse', 'description': 'Five miners died.', 'excerpt': 'Five miners were killed on Monday.'}


@pytest.fixture(autouse=True)
def clean(app_module, db_session):
    db_session.query(Crisis).delete()
    db_session.commit()


def seed(db_session, **extra):
    cid = f'sf-{uuid.uuid4().hex[:8]}'
    db_session.add(Crisis(id=cid, type='conflict', title='Auto title', country='Ghana', latitude=6.2, longitude=-1.7,
                          severity=50, source='GDELT', source_url='https://example.com/a', scope='global',
                          is_active=True, event_kind='physical', **extra))
    db_session.commit()
    return cid


def fresh(db_session, cid):
    db_session.expire_all()
    return db_session.query(Crisis).filter(Crisis.id == cid).first()


class TestValidate:
    def test_good_payload_is_kept(self):
        assert sf.validate(GOOD) == GOOD

    @pytest.mark.parametrize('value', [-1, 10**9, 'five', 5.5, True, None])
    def test_bad_counts_become_null(self, value):
        facts = sf.validate({**GOOD, 'killed': value, 'injured': value})
        assert facts['killed'] is None and facts['injured'] is None

    def test_unknown_lists_are_dropped(self):
        facts = sf.validate({**GOOD, 'event_type': 'zombies', 'scale_cues': ['ongoing', 'nonsense', 'ongoing'],
                             'confidence': 'certain'})
        assert facts['event_type'] == 'other' and facts['scale_cues'] == ['ongoing'] and facts['confidence'] == 'low'

    @pytest.mark.parametrize('payload', [None, [], {}, {'is_statement': 'no'}])
    def test_unusable_payload(self, payload):
        assert sf.validate(payload) is None

    def test_blank_place_is_null_and_long_text_is_trimmed(self):
        facts = sf.validate({**GOOD, 'place': '   ', 'summary': 'x' * 900})
        assert facts['place'] is None and len(facts['summary']) == 300


class TestExtract:
    @staticmethod
    def client(block):
        def create(**kwargs):
            return SimpleNamespace(content=[block])
        return SimpleNamespace(api_key='k', messages=SimpleNamespace(create=create))

    def test_reads_the_forced_tool_output(self):
        block = SimpleNamespace(type='tool_use', input=GOOD)
        with patch.object(sf, 'anthropic_client', self.client(block)):
            assert sf.extract_facts('text') == (GOOD, False)

    def test_no_tool_output_is_nothing_usable_not_a_failure(self):
        with patch.object(sf, 'anthropic_client', self.client(SimpleNamespace(type='text'))):
            assert sf.extract_facts('text') == (None, False)

    def test_no_key_is_a_failure_to_retry(self):
        with patch.object(sf, 'anthropic_client', None):
            assert sf.extract_facts('text') == (None, True)

    def test_model_error_is_a_failure_to_retry(self):
        def boom(**kwargs):
            raise RuntimeError('down')
        bad = SimpleNamespace(api_key='k', messages=SimpleNamespace(create=boom))
        with patch.object(sf, 'anthropic_client', bad):
            assert sf.extract_facts('text') == (None, True)


class TestEnsureFacts:
    @staticmethod
    def run(cid, page=PAGE, result=(GOOD, False), available=True):
        with patch.object(sf, 'facts_available', return_value=available), \
                patch.object(sf, 'fetch_real_page_metadata', return_value=page) as fetch, \
                patch.object(sf, 'extract_facts', return_value=result) as extract:
            return sf.ensure_facts(cid), fetch, extract

    def test_extracts_and_stores_once(self, db_session):
        cid = seed(db_session)
        out, _, _ = self.run(cid)
        assert out == {'status': 'done', 'facts': GOOD}
        row = fresh(db_session, cid)
        assert json.loads(row.facts) == GOOD and row.facts_extracted_at is not None
        assert row.article_excerpt == PAGE['excerpt']
        out, fetch, extract = self.run(cid)
        assert out['status'] == 'done' and fetch.call_count == 0 and extract.call_count == 0

    def test_unknown_story(self):
        assert sf.ensure_facts('nope') == {'status': 'not_found'}

    def test_no_key_is_unavailable_and_not_recorded(self, db_session):
        cid = seed(db_session)
        out, fetch, _ = self.run(cid, available=False)
        assert out['status'] == 'unavailable' and fetch.call_count == 0
        assert fresh(db_session, cid).facts_extracted_at is None

    def test_model_outage_is_retried_later(self, db_session):
        cid = seed(db_session)
        out, _, _ = self.run(cid, result=(None, True))
        assert out == {'status': 'unavailable', 'reason': 'ai_failed'}
        assert fresh(db_session, cid).facts_extracted_at is None

    def test_nothing_usable_is_recorded_and_never_repeated(self, db_session):
        cid = seed(db_session)
        out, _, _ = self.run(cid, result=(None, False))
        assert out == {'status': 'none'}
        assert fresh(db_session, cid).facts_extracted_at is not None
        _, _, extract = self.run(cid)
        assert extract.call_count == 0

    @pytest.mark.parametrize('page', [None, {'title': 'T', 'description': None, 'excerpt': None}])
    def test_dead_page_is_a_definite_none_without_a_model_call(self, db_session, page):
        cid = seed(db_session)
        out, _, extract = self.run(cid, page=page)
        assert out == {'status': 'none'} and extract.call_count == 0
        assert fresh(db_session, cid).facts_extracted_at is not None

    def test_a_saved_excerpt_is_not_fetched_again(self, db_session):
        cid = seed(db_session, article_excerpt='Five miners were killed on Monday.')
        _, fetch, extract = self.run(cid)
        assert fetch.call_count == 0 and extract.call_count == 1

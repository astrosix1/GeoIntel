"""A small in-memory stand-in for the PostgREST calls GeoIntel makes to its own
Supabase tables (services/supabase_rest.rest), for tests. Supports eq/lt/gt/gte/
in/is.null filters, order, limit, select, upsert (merge / ignore duplicates),
PATCH and DELETE, default column values, cascading deletes, and the unique
rules the real tables have (display name; watch-place name per user)."""
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import requests

RESERVED = {'select', 'order', 'limit', 'on_conflict'}

KEYS = {
    'geointel_profiles': ('user_id',),
    'geointel_comments': ('id',),
    'geointel_comment_reports': ('comment_id', 'reporter_id'),
    'geointel_watch_places': ('id',),
    'geointel_alerts': ('place_id', 'hazard_key'),
    'geointel_user_prefs': ('user_id',),
    'geointel_cascades': ('id',),
}


class FakePostgrest:
    def __init__(self):
        self.tables = {name: [] for name in KEYS}
        self.calls = []
        self.fail = False
        self._tick = 0

    # -- helpers ---------------------------------------------------------
    def now(self):
        """Strictly increasing timestamps, so ordering is deterministic."""
        self._tick += 1
        return (datetime.now(timezone.utc) + timedelta(microseconds=self._tick)).isoformat()

    def add(self, table, **row):
        """Insert a row directly (for test setup), applying column defaults."""
        row = self._with_defaults(table, row)
        self.tables[table].append(row)
        return row

    def _with_defaults(self, table, row):
        row = dict(row)
        if table == 'geointel_comments':
            row.setdefault('id', str(uuid.uuid4()))
            row.setdefault('status', 'visible')
            row.setdefault('report_count', 0)
            row.setdefault('created_at', self.now())
        elif table == 'geointel_comment_reports':
            row.setdefault('created_at', self.now())
        elif table == 'geointel_profiles':
            row.setdefault('created_at', self.now())
        elif table == 'geointel_watch_places':
            row.setdefault('id', str(uuid.uuid4()))
            row.setdefault('created_at', self.now())
        elif table == 'geointel_alerts':
            row.setdefault('id', str(uuid.uuid4()))
            row.setdefault('created_at', self.now())
            row.setdefault('read_at', None)
            row.setdefault('emailed_at', None)
        elif table == 'geointel_cascades':
            row.setdefault('id', str(uuid.uuid4()))
            row.setdefault('created_at', self.now())
        elif table == 'geointel_user_prefs':
            row.setdefault('hidden_outlets', [])
            row.setdefault('alert_email', True)
            row.setdefault('alert_min_level', 'orange')
            row.setdefault('alert_conditions', {})
        return row

    @staticmethod
    def _matches(row, params):
        for column, expr in params.items():
            if column in RESERVED:
                continue
            op, _, value = expr.partition('.')
            actual = row.get(column)
            if op == 'eq':
                if str(actual) != value:
                    return False
            elif op == 'lt':
                if not (actual is not None and str(actual) < value):
                    return False
            elif op in ('gt', 'gte'):
                if actual is None:
                    return False
                try:
                    a, b = float(actual), float(value)
                except ValueError:
                    a, b = str(actual), value  # timestamps compare as ISO strings
                if not (a > b if op == 'gt' else a >= b):
                    return False
            elif op == 'in':
                if str(actual) not in value.strip('()').split(','):
                    return False
            elif op == 'is':
                if value == 'null' and actual is not None:
                    return False
            else:
                raise AssertionError(f'unsupported filter {expr}')
        return True

    @staticmethod
    def _project(row, params):
        select = params.get('select')
        return {c: row.get(c) for c in select.split(',')} if select else dict(row)

    def _unique_name_taken(self, table, row, ignore_user=None):
        if table == 'geointel_watch_places':
            return any(
                o['user_id'] == row['user_id'] and o['name'].lower() == row['name'].lower() and o is not row
                for o in self.tables[table]
            )
        if table != 'geointel_profiles':
            return False
        return any(
            other['display_name'].lower() == row['display_name'].lower() and other['user_id'] != ignore_user
            for other in self.tables[table]
        )

    # -- the requests.request replacement -------------------------------------
    def request(self, method, url, params=None, json=None, headers=None, timeout=None):
        table = url.rsplit('/', 1)[-1]
        self.calls.append((method, table))
        if self.fail:
            raise requests.ConnectionError('supabase down')
        params = params or {}
        prefer = (headers or {}).get('Prefer', '')
        rows = self.tables[table]
        data = []

        if method == 'GET':
            found = [r for r in rows if self._matches(r, params)]
            order = params.get('order')
            if order:
                column, _, direction = order.partition('.')
                found.sort(key=lambda r: r[column], reverse=(direction == 'desc'))
            if 'limit' in params:
                found = found[:int(params['limit'])]
            data = [self._project(r, params) for r in found]

        elif method == 'POST':
            for incoming in json:
                keys = KEYS[table]
                existing = next((r for r in rows if all(r.get(k) == incoming.get(k) for k in keys)
                                 and all(k in incoming for k in keys)), None)
                if existing is not None:
                    if 'ignore-duplicates' in prefer:
                        continue
                    if self._unique_name_taken(table, {**existing, **incoming}, ignore_user=existing['user_id']):
                        raise self._conflict()
                    existing.update(incoming)
                    data.append(self._project(existing, params))
                    continue
                row = self._with_defaults(table, incoming)
                if self._unique_name_taken(table, row):
                    raise self._conflict()
                rows.append(row)
                data.append(self._project(row, params))

        elif method == 'PATCH':
            for row in [r for r in rows if self._matches(r, params)]:
                row.update(json)
                data.append(self._project(row, params))

        elif method == 'DELETE':
            doomed = [r for r in rows if self._matches(r, params)]
            self.tables[table] = [r for r in rows if r not in doomed]
            data = [self._project(r, params) for r in doomed]
            # cascade, as the real foreign keys do
            if table == 'geointel_watch_places':
                gone = {r['id'] for r in doomed}
                self.tables['geointel_alerts'] = [
                    r for r in self.tables['geointel_alerts'] if r['place_id'] not in gone
                ]
            if table == 'geointel_comments':
                gone = {r['id'] for r in doomed}
                self.tables['geointel_comment_reports'] = [
                    r for r in self.tables['geointel_comment_reports'] if r['comment_id'] not in gone
                ]
        else:
            raise AssertionError(method)

        returns_rows = method == 'GET' or 'return=representation' in prefer
        payload = data if returns_rows else []
        return SimpleNamespace(json=lambda: payload, raise_for_status=lambda: None, status_code=200)

    @staticmethod
    def _conflict():
        return requests.HTTPError('duplicate key value', response=SimpleNamespace(status_code=409))

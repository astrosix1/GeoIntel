"""The cascade simulator API (premium): what can be asked, and running a trigger. See docs/cascade-plan.md.

The country graph takes about a minute to build, so it is warmed at start-up and daily; a request that arrives before it is ready gets a
503 "cascade_warming" and starts the build rather than making the visitor wait.
"""
import logging

from flask import Blueprint, g, jsonify, request

from extensions import limiter
from models import Crisis, Session
from services import cascade_saved, cascade_trade
from services.cascade_narrative import NarrativeUnavailable, narrate
from services.supabase_rest import SupabaseUnavailable
from services.cascade_engine import UnknownCountry
from services.cascade_graph import cached_graph, warm_graph_async
from services.cascade_triggers import BadTrigger, options, run_template, trigger_for_event
from services.event_analysis import _iso2_for
from services.gating import require_premium
from services.stories import canonical_id

logger = logging.getLogger(__name__)

cascade_bp = Blueprint('cascade', __name__, url_prefix='/api/cascade')


def _warming():
    warm_graph_async()
    return jsonify({'error': 'cascade_warming', 'message': 'The cascade data is being prepared. Try again in a minute.'}), 503


@cascade_bp.route('/options', methods=['GET'])
@limiter.limit("60 per minute")
@require_premium
def get_options():
    graph = cached_graph()
    if graph is None:
        return _warming()
    countries = sorted(({'iso': iso, 'name': c['name']} for iso, c in graph['countries'].items()), key=lambda c: c['name'])
    return jsonify({**options(), 'countries': countries})


def _compute(body):
    """Runs the trigger in a request body. Returns (result, None) or (None, an error response)."""
    if not isinstance(body, dict):
        return None, (jsonify({'error': 'invalid_trigger', 'message': 'expected a JSON object'}), 400)
    graph = cached_graph()
    if graph is None:
        return None, _warming()
    note = None
    template, country, commodity = body.get('template'), body.get('country'), body.get('commodity')
    chokepoint = body.get('chokepoint')
    if body.get('crisis_id') is not None:
        session = Session()
        try:
            crisis = session.query(Crisis).filter(Crisis.id == canonical_id(str(body['crisis_id']))).first()
            event = crisis and {'type': crisis.type, 'country': crisis.country}
        finally:
            session.close()
        if not event:
            return None, (jsonify({'error': 'Crisis not found'}), 404)
        country = _iso2_for(event['country'])
        if not country:
            return None, (jsonify({'error': 'invalid_trigger', 'message': f"No country data for {event['country']}."}), 400)
        template, note = trigger_for_event(event['type'], country)
        commodity = None
    if template == 'chokepoint':
        country = country if isinstance(country, str) else 'XX'      # a chokepoint trigger has no country
    if not isinstance(template, str) or not isinstance(country, str) or not (commodity is None or isinstance(commodity, str)) \
            or not (chokepoint is None or isinstance(chokepoint, str)):
        return None, (jsonify({'error': 'invalid_trigger', 'message': 'template and country are required'}), 400)
    try:
        result = run_template(graph, template, country.upper(), commodity or None, cascade_trade.load(), chokepoint)
    except UnknownCountry as e:                     # a ValueError too, so it must come first
        return None, (jsonify({'error': 'invalid_trigger', 'message': str(e)}), 404)
    except (BadTrigger, ValueError) as e:
        return None, (jsonify({'error': 'invalid_trigger', 'message': str(e)}), 400)
    if note:
        result['started_from'] = note
    return result, None


def _request_of(result):
    """The resolved trigger of a result, in the form /run accepts, so a saved scenario can be run again exactly."""
    t = result['trigger']
    out = {'template': t['template']}
    if t.get('country'):
        out['country'] = t['country']
    if t.get('commodity'):
        out['commodity'] = t['commodity']
    if t.get('chokepoint'):
        out['chokepoint'] = t['chokepoint']
    return out


def _data_failed(e):
    if e.reason == 'bad_id':
        return jsonify({'error': 'Not found'}), 404
    return jsonify({'error': 'user_data_unavailable', 'reason': e.reason}), 503


@cascade_bp.route('/run', methods=['POST'])
@limiter.limit("20 per minute")
@require_premium
def post_run():
    """Body: {template, country, commodity?} or {crisis_id} to start from an event or situation."""
    result, error = _compute(request.get_json(silent=True))
    return error if error else jsonify(result)


@cascade_bp.route('/narrative', methods=['POST'])
@limiter.limit("6 per minute")
@require_premium
def post_narrative():
    """A written summary of a trigger's result, from the computed facts only. 503 when no model is configured or its text cannot be grounded."""
    result, error = _compute(request.get_json(silent=True))
    if error:
        return error
    try:
        return jsonify(narrate(result))
    except NarrativeUnavailable as e:
        return jsonify({'error': 'narrative_unavailable', 'reason': e.reason}), 503


@cascade_bp.route('/saved', methods=['GET'])
@limiter.limit("60 per minute")
@require_premium
def get_saved():
    try:
        return jsonify({'scenarios': cascade_saved.list_saved(g.user['id']), 'limit': cascade_saved.MAX_SAVED})
    except SupabaseUnavailable as e:
        return _data_failed(e)


@cascade_bp.route('/saved', methods=['POST'])
@limiter.limit("20 per minute")
@require_premium
def post_saved():
    """Body: {name, template, country?, commodity?, chokepoint?}. The server runs the trigger itself and stores that result."""
    body = request.get_json(silent=True)
    result, error = _compute(body)
    if error:
        return error
    try:
        saved = cascade_saved.save(g.user['id'], body.get('name'), _request_of(result), result)
    except cascade_saved.InvalidScenario as e:
        return jsonify({'error': 'invalid_scenario', 'message': str(e)}), 400
    except cascade_saved.ScenarioLimitReached:
        return jsonify({'error': 'scenario_limit_reached', 'limit': cascade_saved.MAX_SAVED}), 409
    except SupabaseUnavailable as e:
        return _data_failed(e)
    return jsonify({'scenario': saved}), 201


@cascade_bp.route('/saved/<scenario_id>', methods=['GET'])
@limiter.limit("60 per minute")
@require_premium
def get_saved_one(scenario_id):
    try:
        found = cascade_saved.get(g.user['id'], scenario_id)
    except SupabaseUnavailable as e:
        return _data_failed(e)
    return (jsonify({'scenario': found}), 200) if found else (jsonify({'error': 'Not found'}), 404)


@cascade_bp.route('/saved/<scenario_id>', methods=['DELETE'])
@limiter.limit("60 per minute")
@require_premium
def delete_saved(scenario_id):
    try:
        cascade_saved.delete(g.user['id'], scenario_id)
    except SupabaseUnavailable as e:
        return _data_failed(e)
    return '', 204

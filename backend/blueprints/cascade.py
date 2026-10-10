"""The cascade simulator API (premium): what can be asked, and running a trigger. See docs/cascade-plan.md.

The country graph takes about a minute to build, so it is warmed at start-up and daily; a request that arrives before it is ready gets a
503 "cascade_warming" and starts the build rather than making the visitor wait.
"""
import logging

from flask import Blueprint, jsonify, request

from extensions import limiter
from models import Crisis, Session
from services import cascade_trade
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


@cascade_bp.route('/run', methods=['POST'])
@limiter.limit("20 per minute")
@require_premium
def post_run():
    """Body: {template, country, commodity?} or {crisis_id} to start from an event or situation."""
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({'error': 'invalid_trigger', 'message': 'expected a JSON object'}), 400
    graph = cached_graph()
    if graph is None:
        return _warming()
    note = None
    template, country, commodity = body.get('template'), body.get('country'), body.get('commodity')
    if body.get('crisis_id') is not None:
        session = Session()
        try:
            crisis = session.query(Crisis).filter(Crisis.id == canonical_id(str(body['crisis_id']))).first()
            event = crisis and {'type': crisis.type, 'country': crisis.country}
        finally:
            session.close()
        if not event:
            return jsonify({'error': 'Crisis not found'}), 404
        country = _iso2_for(event['country'])
        if not country:
            return jsonify({'error': 'invalid_trigger', 'message': f"No country data for {event['country']}."}), 400
        template, note = trigger_for_event(event['type'], country)
        commodity = None
    if not isinstance(template, str) or not isinstance(country, str) or not (commodity is None or isinstance(commodity, str)):
        return jsonify({'error': 'invalid_trigger', 'message': 'template and country are required'}), 400
    try:
        result = run_template(graph, template, country.upper(), commodity or None, cascade_trade.load())
    except UnknownCountry as e:                     # a ValueError too, so it must come first
        return jsonify({'error': 'invalid_trigger', 'message': str(e)}), 404
    except (BadTrigger, ValueError) as e:
        return jsonify({'error': 'invalid_trigger', 'message': str(e)}), 400
    if note:
        result['started_from'] = note
    return jsonify(result)

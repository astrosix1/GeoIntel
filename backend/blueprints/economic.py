"""
Economic data endpoints. Kept as its own small, standalone blueprint
(rather than folded into crises) because it will be reused by the
not-yet-built `countries` blueprint in a later phase.
"""
import logging

from flask import Blueprint, jsonify

from models import Session, EconomicData

logger = logging.getLogger(__name__)

economic_bp = Blueprint('economic', __name__, url_prefix='/api/economic')


@economic_bp.route('/<country_code>', methods=['GET'])
def get_economic_data(country_code):
    """Get economic indicators for a country"""
    try:
        session = Session()

        data = session.query(EconomicData).filter(
            EconomicData.country_code == country_code.upper()
        ).order_by(EconomicData.year.desc()).limit(10).all()

        result = [d.to_dict() for d in data]

        session.close()

        return jsonify({
            'country': country_code.upper(),
            'count': len(result),
            'data': result
        })

    except Exception as e:
        logger.error(f"Error fetching economic data: {e}")
        return jsonify({'error': 'An internal error occurred. Please try again.'}), 500

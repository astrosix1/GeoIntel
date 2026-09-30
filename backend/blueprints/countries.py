"""
Country-profile endpoint for the Analysis sidebar's country-click view
(step 4 of the rewrite plan). Real demographics (REST Countries or
WorldBank fallback) + real trade/export facts (OEC or honest-unavailable +
WorldBank) + an AI-or-honest-static narrative — assembled in
services/country_profile.py, this blueprint just serves it as JSON.
"""
import logging

from flask import Blueprint, jsonify

from services.country_profile import get_country_profile

logger = logging.getLogger(__name__)

countries_bp = Blueprint('countries', __name__, url_prefix='/api/countries')


@countries_bp.route('/<country_code>', methods=['GET'])
def get_country(country_code):
    """Get the assembled real country profile for a given ISO alpha-2 code."""
    try:
        if not country_code or len(country_code) > 3:
            return jsonify({'error': 'country_code must be a short ISO country code'}), 400

        profile = get_country_profile(country_code)
        if not profile:
            return jsonify({'error': 'Could not assemble a profile for this country code'}), 404

        return jsonify(profile)
    except Exception as e:
        logger.error(f"Error fetching country profile for {country_code}: {e}")
        return jsonify({'error': 'An internal error occurred. Please try again.'}), 500

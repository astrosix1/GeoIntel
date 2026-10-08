"""
Country-profile endpoint for the Analysis sidebar's country-click view
(step 4 of the rewrite plan). Real demographics (REST Countries or
WorldBank fallback) + real trade/export facts (OEC or honest-unavailable +
WorldBank) + an AI-or-honest-static narrative — assembled in
services/country_profile.py, this blueprint just serves it as JSON.
"""
import logging

from flask import Blueprint, jsonify

from services.country_detail import get_country_detail
from services.country_profile import get_country_profile
from services.country_analyst import AnalystUnavailable, read
from services.country_tabs import TABS, get_country_tab
from extensions import limiter
from services.gating import require_premium_feature

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


@countries_bp.route('/<country_code>/detail', methods=['GET'])
@require_premium_feature
def get_country_more(country_code):
    """Premium: government, people, migration, economy, infrastructure and security for a country."""
    try:
        if not country_code or len(country_code) > 3:
            return jsonify({'error': 'country_code must be a short ISO country code'}), 400
        detail = get_country_detail(country_code)
        if not detail:
            return jsonify({'error': 'No detail is available for this country'}), 404
        return jsonify(detail)
    except Exception as e:
        logger.error(f"Error fetching country detail for {country_code}: {e}")
        return jsonify({'error': 'An internal error occurred. Please try again.'}), 500


@countries_bp.route('/<country_code>/tab/<tab>', methods=['GET'])
@require_premium_feature
def get_country_tab_data(country_code, tab):
    """Premium: the data for one country tab (government, people, migration, economy, security, geography)."""
    try:
        if not country_code or len(country_code) > 3:
            return jsonify({'error': 'country_code must be a short ISO country code'}), 400
        if tab not in TABS:
            return jsonify({'error': 'unknown tab'}), 404
        data = get_country_tab(country_code, tab)
        if not data:
            return jsonify({'error': 'No data is available for this country and tab'}), 404
        return jsonify(data)
    except Exception as e:
        logger.error(f"Error fetching country tab {tab} for {country_code}: {e}")
        return jsonify({'error': 'An internal error occurred. Please try again.'}), 500


@countries_bp.route('/<country_code>/tab/<tab>/read', methods=['GET'])
@limiter.limit("10 per minute")
@require_premium_feature
def get_country_tab_read(country_code, tab):
    """Premium: a short AI-written read of one country tab, from that tab's own figures only. Asked for on demand; 503 when no
    model is configured or it fails, because there is no static fallback."""
    try:
        if not country_code or len(country_code) > 3:
            return jsonify({'error': 'country_code must be a short ISO country code'}), 400
        if tab not in TABS:
            return jsonify({'error': 'unknown tab'}), 404
        data = get_country_tab(country_code, tab)
        if not data:
            return jsonify({'error': 'No data is available for this country and tab'}), 404
        name = (get_country_profile(country_code) or {}).get('demographics', {}).get('name')
        return jsonify(read(country_code.upper(), name, tab, data))
    except AnalystUnavailable as e:
        status = 404 if e.reason == 'no_data' else 503
        return jsonify({'error': 'read_unavailable', 'reason': e.reason}), status
    except Exception as e:
        logger.error(f"Error writing the {tab} read for {country_code}: {e}")
        return jsonify({'error': 'An internal error occurred. Please try again.'}), 500

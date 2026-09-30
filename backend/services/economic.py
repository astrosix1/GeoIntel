"""Economic impact analysis for a crisis."""
from models import Session, Crisis, EconomicData


def get_economic_impact(crisis_id):
    """
    Get economic impact data for a crisis based on affected countries.
    """
    session = Session()
    try:
        crisis = session.query(Crisis).filter(Crisis.id == crisis_id).first()
        if not crisis:
            return None

        affected_countries = [crisis.country]

        # Get economic data for affected countries
        economic_impact = {}
        for country_code in affected_countries:
            country_name = crisis.country
            econ_data = session.query(EconomicData).filter(
                EconomicData.country_code == country_code.upper()[:2]
            ).order_by(EconomicData.year.desc()).first()

            if econ_data:
                economic_impact[country_name] = econ_data.to_dict()

        # Estimate impact severity based on crisis severity and economic size
        impact_severity = 'moderate'
        if crisis.severity > 80:
            impact_severity = 'severe'
        elif crisis.severity > 60:
            impact_severity = 'significant'
        elif crisis.severity > 40:
            impact_severity = 'moderate'
        else:
            impact_severity = 'minor'

        # No time-series economic-disruption data exists anywhere in this
        # app, so a headline "trade disruption %" would still be an invented
        # metric regardless of the arithmetic behind it. economic_profile is
        # instead a real ratio computed from the actual WorldBank-sourced
        # EconomicData row already fetched above — None when no real
        # economic data exists for this country, never a fabricated stand-in.
        econ = economic_impact.get(crisis.country)
        economic_profile = None
        if econ and econ.get('gdp'):
            exports = econ.get('exports') or 0
            imports = econ.get('imports') or 0
            trade_openness_percent_of_gdp = round((exports + imports) / econ['gdp'] * 100, 1)
            economic_profile = {
                'trade_openness_percent_of_gdp': trade_openness_percent_of_gdp,
                'gdp_growth': econ.get('gdp_growth'),
                'trade_balance': econ.get('trade_balance'),
                'unemployment': econ.get('unemployment'),
                'inflation': econ.get('inflation'),
            }

        return {
            'impact_severity': impact_severity,
            'affected_countries': affected_countries,
            'economic_data': economic_impact,
            'economic_profile': economic_profile,
            # A category lookup by crisis type, not this crisis's measured
            # exposure — named to be honest about that distinction.
            'sectors_typically_exposed': estimate_affected_sectors(crisis),
        }
    finally:
        session.close()


def estimate_affected_sectors(crisis):
    """
    Estimate which industry sectors are affected based on crisis type and severity.
    """
    sectors = {
        'conflict': ['Energy', 'Defense', 'Shipping'],
        'military': ['Defense', 'Energy', 'Aviation'],
        'diplomatic': ['Trade', 'Finance', 'Technology'],
        'economic': ['Finance', 'Energy', 'Manufacturing'],
        'resource': ['Energy', 'Agriculture', 'Mining'],
        'technology': ['Technology', 'Semiconductors', 'Software'],
        'proxy': ['Defense', 'Shipping', 'Energy'],
        'alliance': ['Trade', 'Defense', 'Technology']
    }

    base_sectors = sectors.get(crisis.type, ['General Economy'])

    # Add more sectors if severe
    if crisis.severity > 80:
        base_sectors.extend(['Finance', 'Aviation'])

    return list(set(base_sectors))[:5]  # Return top 5

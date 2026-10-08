import type { CountryDetail as Detail, CountryProfile } from '../../../api/types';
import { formatNumber } from './chart';
import { Fact } from './shared';
import { StatList } from './Stat';
import { Unavailable } from './shared';
import eventStyles from '../EventAnalysis.module.css';
import countryStyles from '../CountryAnalysis.module.css';
import styles from '../CountryDetail.module.css';


const ALERT_CLASS: Record<string, string> = { Red: 'advisoryMax', Orange: 'advisoryHigh', Green: 'advisoryNone' };

function Block({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className={styles.group}>
      <div className={styles.groupTitle}>{title}</div>
      {children}
    </div>
  );
}

// The premium geography: figures with rank and trend, then the Factbook's own account of the land, climate, water and hazards.
function GeographyFacts({ detail }: { detail: Detail }) {
  const geo = detail.geography;
  const hazards = detail.hazards?.items ?? [];
  const longest = geo?.borders.countries?.[0]?.km ?? 1;
  return (
    <>
      {detail.stats && detail.stats.length > 0 && (
        <Block title="Land and environment in figures">
          <StatList stats={detail.stats} />
        </Block>
      )}
      {hazards.length > 0 && (
        <Block title="Hazards active now">
          {hazards.map((h) => (
            <div key={`${h.name}-${h.from_date}`} className={`${styles.advisory} ${styles[(ALERT_CLASS[h.alert_level ?? ''] ?? 'advisoryNone') as keyof typeof styles]}`}>
              <div className={styles.text}>{h.hazard}{h.name ? `: ${h.name}` : ''}{h.alert_level ? ` (${h.alert_level} alert)` : ''}</div>
              {h.description && <div className={styles.asOf}>{h.description}</div>}
              {h.report_url && <div className={styles.asOf}><a href={h.report_url} target="_blank" rel="noopener noreferrer">GDACS report</a></div>}
            </div>
          ))}
          <div className={styles.asOf}>Live from GDACS (UN and European Commission), which this app reads for its Weather mode.</div>
        </Block>
      )}
      {geo && (
        <>
          <Block title="Location and size">
            <div className={countryStyles.factsGrid}>
              <Fact label="Where">{geo.location}</Fact>
              <Fact label="Coordinates">{geo.coordinates}</Fact>
              <Fact label="Total area">{geo.area.total}</Fact>
              <Fact label="Land">{geo.area.land}</Fact>
              <Fact label="Water">{geo.area.water}</Fact>
              <Fact label="In comparison">{geo.area.comparative}</Fact>
              <Fact label="Population spread">{geo.population_distribution}</Fact>
            </div>
          </Block>
          {geo.borders.countries && (
            <Block title={`Land borders${geo.borders.total ? ` (${geo.borders.total} in all)` : ''}`}>
              {geo.borders.countries.map((b) => (
                <div key={b.name} className={styles.share}>
                  <div className={styles.shareHead}><span>{b.name}</span><span className={styles.shareValue}>{formatNumber(b.km, 0)} km</span></div>
                  <div className={styles.bar} aria-hidden="true"><div className={styles.fill} style={{ width: `${(b.km / longest) * 100}%` }} /></div>
                </div>
              ))}
            </Block>
          )}
          {(geo.coastline || geo.maritime_claims) && (
            <Block title="Coast and sea">
              <div className={countryStyles.factsGrid}>
                <Fact label="Coastline">{geo.coastline}</Fact>
                {geo.maritime_claims && Object.entries(geo.maritime_claims).map(([k, v]) => <Fact key={k} label={k.charAt(0).toUpperCase() + k.slice(1)}>{v}</Fact>)}
              </div>
            </Block>
          )}
          <Block title="Climate, terrain and elevation">
            <div className={countryStyles.factsGrid}>
              <Fact label="Climate">{geo.climate}</Fact>
              <Fact label="Terrain">{geo.terrain}</Fact>
              <Fact label="Highest point">{geo.elevation.highest}</Fact>
              <Fact label="Lowest point">{geo.elevation.lowest}</Fact>
              <Fact label="Average height">{geo.elevation.mean}</Fact>
              <Fact label="Natural hazards">{geo.natural_hazards}</Fact>
            </div>
          </Block>
          {geo.land_use && (
            <Block title="How the land is used">
              {geo.land_use.items.map((item) => (
                <div key={item.label} className={`${styles.share} ${item.sub ? styles.child : ''}`}>
                  <div className={styles.shareHead}><span>{item.label}</span><span className={styles.shareValue}>{item.percent}%</span></div>
                  <div className={`${styles.bar} ${item.sub ? styles.childBar : ''}`} aria-hidden="true"><div className={styles.fill} style={{ width: `${Math.min(item.percent, 100)}%` }} /></div>
                </div>
              ))}
              {geo.land_use.as_of && <div className={styles.asOf}>Share of the land, {geo.land_use.as_of}.</div>}
            </Block>
          )}
          <Block title="Water and environment">
            <div className={countryStyles.factsGrid}>
              <Fact label="Major rivers">{geo.rivers}</Fact>
              <Fact label="Major lakes">{geo.lakes}</Fact>
              <Fact label="Irrigated land">{geo.irrigated_land}</Fact>
              <Fact label="Renewable water">{geo.renewable_water}</Fact>
              {geo.water_withdrawal && Object.entries(geo.water_withdrawal).map(([k, v]) => <Fact key={k} label={`Water used: ${k}`}>{v}</Fact>)}
              <Fact label="Environmental issues">{geo.environmental_issues}</Fact>
              <Fact label="Carbon dioxide">{geo.co2_total}</Fact>
              <Fact label="Waste recycled">{geo.waste_recycled}</Fact>
              <Fact label="Note">{geo.note}</Fact>
            </div>
          </Block>
        </>
      )}
      {detail.intro && (
        <Block title="Background">
          <div className={styles.text}>{detail.intro.extract}</div>
          <div className={styles.asOf}>
            From <a href={detail.intro.url} target="_blank" rel="noopener noreferrer">{detail.intro.title}</a> on Wikipedia, licensed{' '}
            <a href={detail.intro.license_url} target="_blank" rel="noopener noreferrer">{detail.intro.license}</a>.
          </div>
        </Block>
      )}
    </>
  );
}

export function Geography({ profile, detail }: { profile: CountryProfile; detail?: Detail }) {
  const { demographics, demographics_source, narrative } = profile;
  const isAiGenerated = narrative.model !== 'static-facts-only';
  return (
    <>
      <div className={styles.group}>
        <div className={styles.groupTitle}>Land</div>
        <div className={countryStyles.factsGrid}>
          <span className={countryStyles.factLabel}>Area</span>
          <span className={countryStyles.factValue}>
            {demographics.area_km2 ? `${Math.round(demographics.area_km2).toLocaleString()} km²` : 'unavailable'}
          </span>
          {demographics.borders && demographics.borders.length > 0 && (
            <>
              <span className={countryStyles.factLabel}>Borders</span>
              <span className={countryStyles.factValue}>{demographics.borders.join(', ')}</span>
            </>
          )}
        </div>
        <div className={styles.asOf}>Source: {demographics_source}</div>
      </div>
      <div className={styles.group}>
        <div className={styles.groupTitle}>Geography and infrastructure</div>
        <span className={`${countryStyles.narrativeBadge} ${isAiGenerated ? countryStyles.aiBadge : countryStyles.staticBadge}`}>
          {isAiGenerated ? 'AI-generated' : 'Real facts, no narrative'}
        </span>
        {narrative.geography_infrastructure ? (
          <div className={eventStyles.briefingText}>{narrative.geography_infrastructure}</div>
        ) : (
          <Unavailable>No AI key is configured in this environment, so no generated narrative is shown here.</Unavailable>
        )}
      </div>
      {detail && <GeographyFacts detail={detail} />}
    </>
  );
}

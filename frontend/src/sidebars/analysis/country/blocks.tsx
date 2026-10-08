import type { AgeBand, CityItem, CountryDemocracy, CountryDetail, CountryEnergy, CountryHdi, CountryMineral, CountryStat } from '../../../api/types';
import { changeText, formatNumber } from './chart';
import Sparkline from './Sparkline';
import { Unavailable } from './shared';
import statStyles from './Stat.module.css';
import styles from '../CountryDetail.module.css';

// The Human Development Index (0 to 1): life expectancy, schooling and income combined, with its tier and rank.
export function HdiBlock({ hdi }: { hdi: CountryHdi | null | undefined }) {
  if (!hdi) return null;
  const change = changeText(hdi.series, '', 3);
  return (
    <div className={styles.group}>
      <div className={styles.groupTitle}>Human development</div>
      <div className={statStyles.stat}>
        <span className={statStyles.label}>Human Development Index</span>
        <span className={statStyles.value}>{formatNumber(hdi.value, 3)}<span className={statStyles.unit}>{hdi.tier}</span></span>
        <div className={statStyles.meta}>
          <span>{hdi.year}</span>
          <span className={statStyles.rank}>#{hdi.rank} of {hdi.of}</span>
          {change && <span>{change}</span>}
          <Sparkline points={hdi.series} label={`Human Development Index, ${hdi.series[0][0]} to ${hdi.year}`} />
        </div>
      </div>
      <div className={styles.asOf}>Source: {hdi.source}. Combines life expectancy, years of schooling and income per person.</div>
    </div>
  );
}

// Males and females side by side for each age group, with the Factbook's own counts.
export function Pyramid({ bands }: { bands: AgeBand[] | null | undefined }) {
  const rows = (bands ?? []).filter((b) => b.male != null && b.female != null);
  if (rows.length === 0) return null;
  const widest = Math.max(...rows.flatMap((b) => [b.male as number, b.female as number]));
  return (
    <div className={styles.group}>
      <div className={styles.groupTitle}>Males and females by age</div>
      {rows.map((band) => (
        <div key={band.band} className={styles.pyramidRow}>
          <div className={styles.pyramidSide} aria-hidden="true">
            <div className={styles.pyramidBarLeft} style={{ width: `${((band.male as number) / widest) * 100}%` }} />
          </div>
          <div className={styles.pyramidLabel}>{band.band}</div>
          <div className={styles.pyramidSide} aria-hidden="true">
            <div className={styles.pyramidBarRight} style={{ width: `${((band.female as number) / widest) * 100}%` }} />
          </div>
          <div className={`${styles.pyramidCount} ${styles.pyramidCountLeft}`}>{(band.male as number).toLocaleString()} males</div>
          <div />
          <div className={styles.pyramidCount}>{(band.female as number).toLocaleString()} females</div>
        </div>
      ))}
    </div>
  );
}

export function CitiesBlock({ cities }: { cities: { items: CityItem[]; as_of: number | null } | null | undefined }) {
  if (!cities) return null;
  return (
    <div className={styles.group}>
      <div className={styles.groupTitle}>Largest cities</div>
      {cities.items.map((city) => (
        <div key={city.name} className={styles.shareHead}>
          <span>{city.name}{city.capital ? ' (capital)' : ''}</span>
          <span className={styles.shareValue}>{city.population.toLocaleString()}</span>
        </div>
      ))}
      {cities.as_of && <div className={styles.asOf}>Urban area populations, {cities.as_of}.</div>}
    </div>
  );
}

// Agriculture, industry and services as shares of the economy, from three World Bank figures.
export function SectorsBlock({ sectors }: { sectors: CountryStat[] | undefined }) {
  if (!sectors || sectors.length === 0) return null;
  return (
    <div className={styles.group}>
      <div className={styles.groupTitle}>What the economy is made of</div>
      {sectors.map((sector) => (
        <div key={sector.code} className={styles.share}>
          <div className={styles.shareHead}>
            <span>{sector.label}</span>
            <span className={styles.shareValue}>{formatNumber(sector.value, 1)}% ({sector.year})</span>
          </div>
          <div className={styles.bar} aria-hidden="true">
            <div className={styles.fill} style={{ width: `${Math.min(Math.max(sector.value, 0), 100)}%` }} />
          </div>
        </div>
      ))}
      <div className={styles.asOf}>Share of GDP (value added). Source: {sectors[0].source}.</div>
    </div>
  );
}

export function EnergyBlock({ energy }: { energy: CountryEnergy | null | undefined }) {
  if (!energy) return null;
  return (
    <div className={styles.group}>
      <div className={styles.groupTitle}>Electricity: where it comes from</div>
      {energy.mix.map((source) => (
        <div key={source.name} className={styles.share}>
          <div className={styles.shareHead}>
            <span>{source.name}</span>
            <span className={styles.shareValue}>{formatNumber(source.percent, 1)}%</span>
          </div>
          <div className={styles.bar} aria-hidden="true">
            <div className={styles.fill} style={{ width: `${Math.min(source.percent, 100)}%` }} />
          </div>
        </div>
      ))}
      <div className={styles.asOf}>
        {energy.low_carbon_share != null && `${formatNumber(energy.low_carbon_share, 1)}% low-carbon. `}
        {energy.carbon_intensity != null && `${formatNumber(energy.carbon_intensity, 0)} g CO2 per kWh. `}
        {energy.generation_twh != null && `${formatNumber(energy.generation_twh, 1)} TWh generated. `}
        {energy.year}. Source: {energy.source}.
      </div>
    </div>
  );
}

function amount(value: number, unit: string): string {
  return `${formatNumber(value, value < 10 ? 1 : 0)} ${unit}`;
}

// What the country produces and holds in the ground (USGS), critical minerals first. Production rank is among the producers
// the USGS lists for that mineral, not among all countries.
export function MineralsBlock({ minerals }: { minerals: { items: CountryMineral[]; source: string } | null | undefined }) {
  if (!minerals || minerals.items.length === 0) {
    return <Unavailable>The USGS lists no mineral production or reserves for this country.</Unavailable>;
  }
  const critical = minerals.items.filter((m) => m.critical);
  const others = minerals.items.filter((m) => !m.critical);
  const render = (title: string, items: CountryMineral[]) =>
    items.length > 0 && (
      <div className={styles.group}>
        <div className={styles.groupTitle}>{title}</div>
        {items.map((m) => (
          <div key={m.commodity} className={styles.mineral}>
            <div className={styles.shareHead}>
              <span>{m.commodity}</span>
              <span className={styles.shareValue}>
                {m.production != null ? amount(m.production, m.unit) : m.capacity != null ? `capacity ${amount(m.capacity, m.unit)}` : ''}
              </span>
            </div>
            <div className={styles.asOf}>
              {m.rank != null && `#${m.rank} of ${m.producers} producers`}
              {m.world_share != null && `${m.rank != null ? ', ' : ''}${m.world_share === 0 ? 'under 0.1' : m.world_share}% of world output`}
              {m.year != null && ` (${m.year})`}
              {m.reserves != null && `${m.rank != null ? '. ' : ''}Reserves ${amount(m.reserves, m.unit)}${m.reserves_share != null ? ` (${m.reserves_share}% of world)` : ''}`}
            </div>
          </div>
        ))}
      </div>
    );
  return (
    <>
      {render('Critical and strategic minerals', critical)}
      {render('Other minerals and materials', others)}
      <div className={styles.asOf}>Production and reserves as published by the {minerals.source}; estimates, in the units shown.</div>
    </>
  );
}

const KIND_TITLE = { security: 'Security and arms control', political: 'Political', economic: 'Economic', other: 'Other' } as const;

export function Memberships({ memberships }: { memberships: NonNullable<CountryDetail['memberships']> }) {
  const kinds = (['security', 'political', 'economic', 'other'] as const).filter((k) => memberships.some((m) => m.kind === k));
  return (
    <div className={styles.group}>
      <div className={styles.groupTitle}>Alliances and groupings</div>
      {kinds.map((kind) => (
        <div key={kind} className={styles.chipBlock}>
          <div className={styles.asOf}>{KIND_TITLE[kind]}</div>
          <div className={styles.chips}>
            {memberships.filter((m) => m.kind === kind).map((m) => (
              <span key={m.abbr} className={styles.chip} title={`${m.name}${m.note ? ` (${m.note})` : ''}`}>
                {m.abbr}
                {m.note ? ` (${m.note})` : ''}
              </span>
            ))}
          </div>
        </div>
      ))}
      <div className={styles.asOf}>As listed by the CIA World Factbook. Hover a badge for the full name; unlisted abbreviations are shown as written.</div>
    </div>
  );
}


// How democratic the country is (0 to 1), where it ranks, and which kind of regime it is, with the trend since 1950.
export function DemocracyBlock({ democracy }: { democracy: CountryDemocracy | null | undefined }) {
  if (!democracy) return null;
  const change = changeText(democracy.series, '', 3);
  return (
    <div className={styles.group}>
      <div className={styles.groupTitle}>How democratic</div>
      <div className={statStyles.stat}>
        <span className={statStyles.label}>Electoral democracy index</span>
        <span className={statStyles.value}>
          {formatNumber(democracy.value, 3)}
          {democracy.regime?.label && <span className={statStyles.unit}>{democracy.regime.label}</span>}
        </span>
        <div className={statStyles.meta}>
          <span>{democracy.year}</span>
          <span className={statStyles.rank}>#{democracy.rank} of {democracy.of}</span>
          {change && <span>{change}</span>}
          <Sparkline points={democracy.series} label={`Electoral democracy index, ${democracy.series[0][0]} to ${democracy.year}`} />
        </div>
      </div>
      <div className={styles.asOf}>
        0 is no real electoral competition, 1 is fully free and fair elections.
        {democracy.regime && ` Classed as a ${democracy.regime.label?.toLowerCase()} since ${democracy.regime.since}.`} Source: {democracy.source}.
      </div>
    </div>
  );
}

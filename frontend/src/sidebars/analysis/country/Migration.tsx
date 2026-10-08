import type { CountryDetail as Detail, CountryStat, MigrationFlow, RefugeePartner, RefugeeRow } from '../../../api/types';
import { rate } from './format';
import { Fact, Unavailable } from './shared';
import Stat, { StatList } from './Stat';
import styles from '../CountryDetail.module.css';
import countryStyles from '../CountryAnalysis.module.css';

const countryName = (code: string) => {
  try {
    return new Intl.DisplayNames(['en'], { type: 'region' }).of(code) ?? code;
  } catch {
    return code;
  }
};

// A figure the server gave as a series becomes the same Stat row the World Bank figures use (no rank: these are not ranked).
function seriesStat(code: string, label: string, unit: string, decimals: number, series: [number, number][] | undefined, source: string): CountryStat | null {
  if (!series || series.length === 0) return null;
  const [year, value] = series[series.length - 1];
  return { code, label, unit, decimals, value, year, series, source, rank: null, of: null };
}

function unhcrSeries(rows: RefugeeRow[], field: keyof RefugeeRow): [number, number][] {
  return rows.filter((r) => typeof r[field] === 'number').map((r) => [r.year, r[field] as number]);
}

function Partners({ rows, total, caption }: { rows: { country_code: string; count: number; percent?: number | null }[]; total?: number; caption: string }) {
  const largest = rows[0]?.count ?? 1;
  return (
    <div className={styles.group}>
      <div className={styles.groupTitle}>{caption}</div>
      {rows.map((row) => (
        <div key={row.country_code} className={styles.share}>
          <div className={styles.shareHead}>
            <span>{countryName(row.country_code)}</span>
            <span className={styles.shareValue}>
              {row.count.toLocaleString()}
              {row.percent != null && ` · ${row.percent}%`}
            </span>
          </div>
          <div className={styles.bar} aria-hidden="true">
            <div className={styles.fill} style={{ width: `${(row.count / largest) * 100}%` }} />
          </div>
        </div>
      ))}
      {total != null && total > 0 && <div className={styles.asOf}>All other countries combined: {total.toLocaleString()}.</div>}
    </div>
  );
}

function Flow({ flow, who, partners }: { flow: MigrationFlow; who: string; partners: 'origins' | 'destinations' }) {
  const stock = seriesStat(`${who}-stock`, who === 'immigrants' ? 'Born abroad, living here' : 'Born here, living abroad', '', 0, flow.series, flow.source);
  const share = seriesStat(`${who}-share`, 'Share of the population', '% of people', 1, flow.share_series, flow.source);
  const rows = (partners === 'origins' ? flow.origins : flow.destinations) ?? [];
  return (
    <>
      <div className={styles.group}>
        <div className={styles.groupTitle}>{who === 'immigrants' ? 'Immigrants' : 'Emigrants'}</div>
        {stock && <Stat stat={stock} />}
        {share && share.series.length > 1 ? <Stat stat={share} /> : flow.share_of_population != null && <Fact label="Share of the population">{`${flow.share_of_population}%`}</Fact>}
        <div className={styles.asOf}>Source: {flow.source}. Counts are for 1990, 1995, 2000, 2005, 2010, 2015, 2020 and {flow.year}.</div>
      </div>
      {rows.length > 0 && (
        <Partners
          rows={rows}
          total={flow.other_count}
          caption={who === 'immigrants' ? 'Where they come from' : 'Where they live'}
        />
      )}
    </>
  );
}

function Refugees({ detail }: { detail: Detail }) {
  const r = detail.refugees;
  if (!r) return <Unavailable>UNHCR publishes no refugee or displacement figures for this country.</Unavailable>;
  const src = r.source;
  const hosted = r.hosted;
  const from = r.from_here;
  const hostedStats = hosted
    ? [
        seriesStat('hosted-refugees', 'Refugees living here', '', 0, unhcrSeries(hosted.series, 'refugees'), src),
        seriesStat('hosted-asylum', 'Asylum seekers waiting here', '', 0, unhcrSeries(hosted.series, 'asylum_seekers'), src),
        seriesStat('hosted-stateless', 'Stateless people here', '', 0, unhcrSeries(hosted.series, 'stateless'), src),
      ].filter((s): s is CountryStat => s !== null)
    : [];
  const fromStats = from
    ? [
        seriesStat('from-refugees', 'Refugees from here, living abroad', '', 0, unhcrSeries(from.series, 'refugees'), src),
        seriesStat('from-asylum', 'Asylum seekers from here', '', 0, unhcrSeries(from.series, 'asylum_seekers'), src),
        seriesStat('from-idps', 'Displaced inside the country', '', 0, unhcrSeries(from.series, 'idps'), src),
      ].filter((s): s is CountryStat => s !== null)
    : [];
  const asRows = (rows: RefugeePartner[] | null | undefined) => (rows ?? []).map((p) => ({ country_code: p.country_code, count: p.total, percent: null }));
  return (
    <>
      {hostedStats.length > 0 && (
        <div className={styles.group}>
          <div className={styles.groupTitle}>Refugees and asylum seekers hosted</div>
          <StatList stats={hostedStats} source={src} />
        </div>
      )}
      {hosted?.by_origin && <Partners rows={asRows(hosted.by_origin)} caption={`Where they come from (${hosted.latest.year})`} />}
      {fromStats.length > 0 && (
        <div className={styles.group}>
          <div className={styles.groupTitle}>People who have fled or are displaced</div>
          <StatList stats={fromStats} source={src} />
        </div>
      )}
      {from?.by_destination && <Partners rows={asRows(from.by_destination)} caption={`Where refugees from here now live (${from.latest.year})`} />}
      <div className={styles.asOf}>Refugees and asylum seekers combined in the bars. The latest year can be a mid-year count.</div>
    </>
  );
}

export function Migration({ detail }: { detail: Detail }) {
  const empty = !detail.immigrants && !detail.emigrants && !detail.refugees && !(detail.stats && detail.stats.length);
  if (empty) return <Unavailable>Migration figures are unavailable for this country.</Unavailable>;
  const remittances = (detail.stats ?? []).filter((s) => s.code.includes('TRF'));
  const flows = (detail.stats ?? []).filter((s) => !s.code.includes('TRF'));
  return (
    <>
      {detail.immigrants && <Flow flow={detail.immigrants} who="immigrants" partners="origins" />}
      {detail.emigrants && <Flow flow={detail.emigrants} who="emigrants" partners="destinations" />}
      {(flows.length > 0 || detail.net_migration_rate) && (
        <div className={styles.group}>
          <div className={styles.groupTitle}>Net movement</div>
          {flows.length > 0 && <StatList stats={flows} />}
          <div className={countryStyles.factsGrid}>
            <Fact label="Net migration rate">{rate(detail.net_migration_rate, 'per 1,000 people')}</Fact>
          </div>
        </div>
      )}
      <Refugees detail={detail} />
      {remittances.length > 0 && (
        <div className={styles.group}>
          <div className={styles.groupTitle}>Money sent home</div>
          <StatList stats={remittances} />
        </div>
      )}
    </>
  );
}

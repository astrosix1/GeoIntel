import type { Chamber, CountryDetail as Detail, OfficeHolder } from '../../../api/types';
import { DemocracyBlock, Memberships } from './blocks';
import { Fact, Unavailable } from './shared';
import countryStyles from '../CountryAnalysis.module.css';
import styles from '../CountryDetail.module.css';

const yearOf = (date: string | null) => (date ? date.slice(0, 4) : '');

function Previous({ title, holders }: { title: string; holders: OfficeHolder[] | undefined }) {
  const past = (holders ?? []).filter((h) => h.end).slice(0, 5);
  if (past.length === 0) return null;
  return (
    <div className={styles.chipBlock}>
      <div className={styles.asOf}>{title}</div>
      {past.map((h) => (
        <div key={`${h.name}-${h.start}`} className={styles.shareHead}>
          <span>{h.name}</span>
          <span className={styles.shareValue}>{yearOf(h.start)}{h.start || h.end ? ' to ' : ''}{yearOf(h.end)}</span>
        </div>
      ))}
    </div>
  );
}

function ChamberCard({ chamber }: { chamber: Chamber }) {
  return (
    <div className={styles.mineral}>
      <div className={styles.groupTitle}>{chamber.name ?? chamber.label}</div>
      <div className={countryStyles.factsGrid}>
        <Fact label="Seats">{chamber.seats}</Fact>
        <Fact label="Elected by">{chamber.electoral_system}</Fact>
        <Fact label="Renewal">{chamber.scope}</Fact>
        <Fact label="Term">{chamber.term}</Fact>
        <Fact label="Women">{chamber.women_percent}</Fact>
        <Fact label="Last election">{chamber.last_election}</Fact>
        <Fact label="Next election">{chamber.next_election}</Fact>
        <Fact label="Seats by party">{chamber.parties}</Fact>
      </div>
    </div>
  );
}

function PowerPoint({ label, text }: { label: string; text: string | null | undefined }) {
  if (!text) return null;
  return (
    <div className={styles.mineral}>
      <div className={styles.shareHead}><span>{label}</span></div>
      <div className={styles.text}>{text}</div>
    </div>
  );
}

export function Government({ detail }: { detail: Detail }) {
  const gov = detail.government;
  if (!gov && !detail.democracy && !detail.intro) return <Unavailable>Government facts are unavailable for this country.</Unavailable>;
  const power = detail.power;
  const leaders = detail.leaders;
  return (
    <>
      {gov && (
        <div className={styles.group}>
          <div className={styles.groupTitle}>Leadership</div>
          <div className={countryStyles.factsGrid}>
            <Fact label="System">{gov.type}</Fact>
            <Fact label="Head of state">{gov.chief_of_state?.text}</Fact>
            <Fact label="Head of government">{gov.head_of_government?.text}</Fact>
            <Fact label="Cabinet">{gov.cabinet}</Fact>
            <Fact label="How chosen">{gov.election_process}</Fact>
            <Fact label="Last election">{gov.last_election}</Fact>
            <Fact label="Next election">{gov.next_election}</Fact>
          </div>
          <Previous title="Previous heads of state (Wikidata)" holders={leaders?.head_of_state} />
          <Previous title="Previous heads of government (Wikidata)" holders={leaders?.head_of_government} />
        </div>
      )}
      {power && Object.values(power).some(Boolean) && (
        <div className={styles.group}>
          <div className={styles.groupTitle}>How power works</div>
          <PowerPoint label="Head of state" text={power.head_of_state} />
          <PowerPoint label="Government" text={power.government} />
          <PowerPoint label="Legislature" text={power.legislature} />
          <PowerPoint label="Courts" text={power.courts} />
          <PowerPoint label="Constitution" text={power.constitution} />
          <div className={styles.asOf}>Written by an AI model from the Factbook text in the sections below, and nothing else. Check it against that text.</div>
        </div>
      )}
      <DemocracyBlock democracy={detail.democracy} />
      {gov?.legislature && (
        <div className={styles.group}>
          <div className={styles.groupTitle}>Legislature{gov.legislature.structure ? ` (${gov.legislature.structure})` : ''}</div>
          {gov.legislature.name && <div className={styles.text}>{gov.legislature.name}</div>}
          {gov.legislature.chambers.map((chamber) => <ChamberCard key={chamber.label} chamber={chamber} />)}
        </div>
      )}
      {gov?.judiciary && (
        <div className={styles.group}>
          <div className={styles.groupTitle}>Courts</div>
          <div className={countryStyles.factsGrid}>
            <Fact label="Highest courts">{gov.judiciary.highest_courts}</Fact>
            <Fact label="Judges chosen by">{gov.judiciary.selection}</Fact>
            <Fact label="Lower courts">{gov.judiciary.subordinate_courts}</Fact>
          </div>
        </div>
      )}
      {gov && (
        <div className={styles.group}>
          <div className={styles.groupTitle}>Constitution and the state</div>
          <div className={countryStyles.factsGrid}>
            <Fact label="Constitution">{gov.constitution.history}</Fact>
            <Fact label="Amending it">{gov.constitution.amendment}</Fact>
            <Fact label="Legal system">{gov.legal_system}</Fact>
            <Fact label="Voting">{gov.suffrage}</Fact>
            <Fact label="Independence">{gov.independence}</Fact>
            <Fact label="National day">{gov.national_holiday}</Fact>
            <Fact label="Divisions">{gov.administrative_divisions}</Fact>
            {gov.citizenship && Object.entries(gov.citizenship).map(([k, v]) => <Fact key={k} label={k.charAt(0).toUpperCase() + k.slice(1)}>{v}</Fact>)}
          </div>
        </div>
      )}
      {gov?.parties && gov.parties.length > 0 && (
        <div className={styles.group}>
          <div className={styles.groupTitle}>Political parties</div>
          <div className={styles.chips}>
            {gov.parties.map((party) => (party.endsWith(':') ? <div key={party} className={styles.asOf}>{party}</div> : <span key={party} className={styles.chip}>{party}</span>))}
          </div>
        </div>
      )}
      {detail.memberships && detail.memberships.length > 0 && <Memberships memberships={detail.memberships} />}
      {detail.intro && (
        <div className={styles.group}>
          <div className={styles.groupTitle}>Background</div>
          <div className={styles.text}>{detail.intro.extract}</div>
          <div className={styles.asOf}>
            From <a href={detail.intro.url} target="_blank" rel="noopener noreferrer">{detail.intro.title}</a> on Wikipedia, licensed{' '}
            <a href={detail.intro.license_url} target="_blank" rel="noopener noreferrer">{detail.intro.license}</a>.
          </div>
        </div>
      )}
      <div className={styles.asOf}>Leaders and offices are as of the Factbook&apos;s last update and can lag recent changes.</div>
    </>
  );
}

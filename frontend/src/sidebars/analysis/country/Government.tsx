import type { CountryDetail as Detail } from '../../../api/types';
import { Unavailable, Fact } from './shared';
import countryStyles from '../CountryAnalysis.module.css';
import styles from '../CountryDetail.module.css';

export function Government({ detail }: { detail: Detail }) {
  const gov = detail.government;
  if (!gov) return <Unavailable>Government facts are unavailable for this country.</Unavailable>;
  return (
    <>
      <div className={styles.group}>
        <div className={styles.groupTitle}>Leadership</div>
        <div className={countryStyles.factsGrid}>
          <Fact label="System">{gov.type}</Fact>
          <Fact label="Head of state">{gov.chief_of_state?.text}</Fact>
          <Fact label="Head of government">{gov.head_of_government?.text}</Fact>
          <Fact label="Cabinet">{gov.cabinet}</Fact>
          <Fact label="How chosen">{gov.election_process}</Fact>
        </div>
      </div>
      <div className={styles.group}>
        <div className={styles.groupTitle}>Constitution and powers</div>
        <div className={countryStyles.factsGrid}>
          <Fact label="Constitution">{gov.constitution.history}</Fact>
          <Fact label="Amending it">{gov.constitution.amendment}</Fact>
          <Fact label="Legislature">{gov.legislative}</Fact>
          <Fact label="Courts">{gov.judicial}</Fact>
          <Fact label="Legal system">{gov.legal_system}</Fact>
          <Fact label="Voting">{gov.suffrage}</Fact>
          <Fact label="Parties">{gov.parties}</Fact>
        </div>
      </div>
      <div className={styles.asOf}>Leaders are as of the Factbook&apos;s last update and can lag recent changes.</div>
    </>
  );
}

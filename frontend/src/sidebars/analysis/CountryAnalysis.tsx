import { useEffect, useState } from 'react';
import { useCountryProfileQuery } from '../../state/queries';
import CountryDetail from './CountryDetail';
import eventStyles from './EventAnalysis.module.css';
import styles from './CountryAnalysis.module.css';

export default function CountryAnalysis({ countryCode }: { countryCode: string }) {
  const { data: profile, isLoading, isError } = useCountryProfileQuery(countryCode);
  const [imageFailed, setImageFailed] = useState(false);

  useEffect(() => {
    setImageFailed(false);
  }, [profile?.image?.src]);

  if (isLoading) {
    return <div className={eventStyles.loading}>Loading country profile…</div>;
  }
  if (isError || !profile) {
    return <div className={eventStyles.error}>Failed to load country profile.</div>;
  }

  const { demographics } = profile;

  return (
    <div>
      {demographics.flag_svg && (
        <img className={styles.flag} src={demographics.flag_svg} alt={`Flag of ${demographics.name}`} />
      )}
      <h2 className={eventStyles.title}>{demographics.name ?? profile.country_code}</h2>

      {profile.image && !imageFailed && (
        <div className={eventStyles.section}>
          <img
            className={eventStyles.media}
            src={profile.image.src}
            alt={profile.image.caption || demographics.name || profile.country_code}
            onError={() => setImageFailed(true)}
          />
          {profile.image.caption && (
            <div className={eventStyles.mediaCaption}>{profile.image.caption}</div>
          )}
        </div>
      )}
      <div className={eventStyles.metaRow}>
        {demographics.region && <span className={eventStyles.badge}>{demographics.region}</span>}
        {demographics.capital && <span className={eventStyles.badge}>Capital: {demographics.capital}</span>}
      </div>

      <CountryDetail countryCode={countryCode} profile={profile} />
    </div>
  );
}

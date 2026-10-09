import type { SituationView } from '../../api/types';
import { Section } from '../../ui/Display';
import { useUiStore } from '../../state/uiStore';
import styles from './EventAnalysis.module.css';

const KIND_TEXT = { killed: 'killed', injured: 'injured' } as const;

function span(first: string, last: string): string {
  const a = new Date(first);
  const b = new Date(last);
  const hours = Math.max(1, Math.round((b.getTime() - a.getTime()) / 3_600_000));
  return hours < 48 ? `${hours} hour${hours === 1 ? '' : 's'}` : `${Math.round(hours / 24)} days`;
}

// A situation: several stories about one development, summarised from the reporting itself. Everything here is quoted or counted
// from the stories; nothing is generated, so it works without a model.
export default function SituationBlock({ situation, currentId }: { situation: SituationView; currentId: string }) {
  const selectCrisis = useUiStore((s) => s.selectCrisis);
  const others = situation.stories.filter((s) => s.id !== currentId);
  return (
    <>
      <Section title={`This is one of ${situation.story_count} stories on the same development`}>
        <div className={styles.briefingText}>
          {situation.story_count} stories from {situation.outlet_count} outlet{situation.outlet_count === 1 ? '' : 's'} over {span(situation.first_at, situation.last_at)}. Most reported: {situation.title}
        </div>
        {situation.angles.length > 0 && (
          <>
            <div className={styles.mediaCaption}>Other angles</div>
            <ul className={styles.sourceList}>
              {situation.angles.map((a) => (
                <li key={a.id}>
                  {a.headline}
                  {a.outlet && <span className={styles.sourceOutlet}>{a.outlet}</span>}
                </li>
              ))}
            </ul>
          </>
        )}
      </Section>
      {situation.figures.length > 0 && (
        <Section title="Figures stated in the reporting">
          <ul className={styles.sourceList}>
            {situation.figures.map((f) => (
              <li key={`${f.kind}-${f.count}`}>
                {f.count} {KIND_TEXT[f.kind]}: {f.snippet}
                <span className={styles.sourceOutlet}>stated by {f.stated_by} stor{f.stated_by === 1 ? 'y' : 'ies'}</span>
              </li>
            ))}
          </ul>
          <div className={styles.mediaCaption}>Each figure is quoted from the reporting with the words around it. They are not added up, and a figure for one place is not a total.</div>
        </Section>
      )}
      {situation.key_sentences.length > 0 && (
        <Section title="What the outlets repeat">
          <ul className={styles.sourceList}>
            {situation.key_sentences.map((k) => (
              <li key={k.text}>
                &ldquo;{k.text}&rdquo;
                <span className={styles.sourceOutlet}>
                  {k.url ? (
                    <a className={styles.sourceLink} href={k.url} target="_blank" rel="noopener noreferrer">
                      {k.outlet}
                    </a>
                  ) : (
                    k.outlet
                  )}
                  {k.echoed_by > 0 ? `, echoed by ${k.echoed_by} other${k.echoed_by === 1 ? '' : 's'}` : ''}
                </span>
              </li>
            ))}
          </ul>
          <div className={styles.mediaCaption}>Quoted from the articles, not rewritten.</div>
        </Section>
      )}
      {others.length > 0 && (
        <Section title={`Stories in this situation (${situation.story_count})`}>
          <ul className={styles.sourceList}>
            {others.map((s) => (
              <li key={s.id}>
                <button type="button" className={`${styles.sourceLink} ${styles.linkButton}`} onClick={() => selectCrisis(s)}>
                  {s.headline}
                </button>
                <span className={styles.sourceOutlet}>
                  {s.outlet ?? s.country}, {(s.date ?? '').slice(0, 10)}
                </span>
              </li>
            ))}
          </ul>
        </Section>
      )}
    </>
  );
}

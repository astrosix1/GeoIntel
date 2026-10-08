import type { Briefing } from '../../api/types';
import { Badge, Section } from '../../ui/Display';
import styles from './EventAnalysis.module.css';

const CUE_LABELS: Record<string, string> = {
  mass_casualty: 'Mass casualties',
  infrastructure: 'Infrastructure hit',
  chemical_bio_nuclear: 'Chemical, biological or nuclear',
  state_actors: 'State actors involved',
  ongoing: 'Ongoing',
};

function Cites({ numbers, briefing }: { numbers: number[]; briefing: Briefing }) {
  return (
    <>
      {numbers.map((n) => {
        const source = briefing.sources.find((s) => s.n === n);
        return (
          <sup key={n}>
            {source?.url ? (
              <a href={source.url} target="_blank" rel="noopener noreferrer" title={`${source.source}: ${source.title}`} aria-label={`Source ${n}: ${source.source}`}>
                [{n}]
              </a>
            ) : (
              `[${n}]`
            )}
          </sup>
        );
      })}
    </>
  );
}

// The structured briefing: summary, key points that cite their sources, and what the sources do not say.
// Facts are what the article states.
export function BriefingBlocks({ briefing }: { briefing: Briefing }) {
  const s = briefing.structured;
  const facts = briefing.facts;
  const chips: string[] = [];
  if (facts) {
    if (facts.killed != null) chips.push(`${facts.killed} killed`);
    if (facts.injured != null) chips.push(`${facts.injured} injured`);
    if (facts.place) chips.push(facts.place);
    for (const cue of facts.scale_cues) if (CUE_LABELS[cue]) chips.push(CUE_LABELS[cue]);
  }
  return (
    <>
      <Section title="What we know">
        {s ? (
          <>
            <div className={styles.briefingText}>{s.summary}</div>
            <ul className={styles.sourceList}>
              {s.key_points.map((p, i) => (
                <li key={i}>
                  {p.text} <Cites numbers={p.sources} briefing={briefing} />
                </li>
              ))}
            </ul>
          </>
        ) : (
          <div className={styles.briefingText}>{briefing.briefing}</div>
        )}
      </Section>
      {s && s.unknowns.length > 0 && (
        <Section title="What is not known">
          <ul className={styles.sourceList}>
            {s.unknowns.map((u, i) => (
              <li key={i}>{u}</li>
            ))}
          </ul>
        </Section>
      )}
      {chips.length > 0 && (
        <Section title="Facts from the reporting">
          <div>
            {chips.map((c) => (
              <Badge key={c}>{c}</Badge>
            ))}
          </div>
          <div className={styles.mediaCaption}>Stated in the article; nothing is estimated.</div>
        </Section>
      )}
    </>
  );
}

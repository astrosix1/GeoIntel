import { useRunCascadeMutation, useEntitlements } from '../../state/queries';
import { Section } from '../../ui/Display';
import Button from '../../ui/Button';
import CascadeResult from '../../components/CascadeResult';
import { CASCADE_ABOUT, cascadeErrorText } from '../../components/CascadeWorkspace';
import styles from './EventAnalysis.module.css';

// "Run a cascade from this": who is exposed if this event plays out as its type suggests. Premium; the trigger it assumed is shown
// at the top of the result so it can be changed in the Cascade workspace.
export default function EventCascade({ crisisId }: { crisisId: string }) {
  const { premium } = useEntitlements();
  const run = useRunCascadeMutation();
  return (
    <Section title="Cascade">
      {!premium ? (
        <div className={styles.mediaCaption}>
          <strong>This feature is for premium subscribers only.</strong> {CASCADE_ABOUT}
        </div>
      ) : (
        <>
          {!run.data && (
            <div className={styles.mediaCaption}>Who is exposed if this plays out? Follows trade and energy links, with the evidence for each country.</div>
          )}
          <Button size="sm" disabled={run.isPending} onClick={() => run.mutate({ crisis_id: crisisId })}>
            {run.isPending ? 'Running…' : run.data ? 'Run again' : 'Run a cascade from this'}
          </Button>
          {run.error && <div className={styles.error}>{cascadeErrorText(run.error)}</div>}
          {run.data && <CascadeResult result={run.data} />}
        </>
      )}
    </Section>
  );
}

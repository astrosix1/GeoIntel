import { UserDataError } from '../api/client';
import { useEntitlements, useSaveEventMutation, useSavedEventsQuery } from '../state/queries';
import PremiumGate from './PremiumGate';
import styles from './SaveButton.module.css';

// Save / unsave an event to the user's dashboard (premium). Non-premium
// visitors get the usual locked control.
export default function SaveButton({ crisisId }: { crisisId: string }) {
  const { premium } = useEntitlements();
  const { data: saved } = useSavedEventsQuery();
  const mutation = useSaveEventMutation();
  const isSaved = !!saved?.some((event) => event.crisis_id === crisisId);

  const button = (
    <button
      type="button"
      className={`${styles.button} ${isSaved ? styles.saved : ''}`}
      aria-pressed={isSaved}
      disabled={mutation.isPending}
      onClick={() => premium && mutation.mutate({ id: crisisId, save: !isSaved })}
    >
      {isSaved ? '★ Saved' : '☆ Save'}
    </button>
  );

  const errorKind = mutation.error instanceof UserDataError ? mutation.error.kind : mutation.error ? 'error' : null;

  return (
    <>
      {premium ? button : <PremiumGate feature="Saved events">{button}</PremiumGate>}
      {errorKind && (
        <span className={styles.error}>
          {errorKind === 'limit_reached'
            ? "You've reached the saved-event limit."
            : errorKind === 'unavailable'
              ? "Saving isn't available right now."
              : "Couldn't save. Please try again."}
        </span>
      )}
    </>
  );
}

import { useState } from 'react';
import { CommentsError } from '../../api/client';
import type { EventComment, ReportReason } from '../../api/types';
import PremiumGate from '../../components/PremiumGate';
import { timeAgo } from '../../lib/time';
import {
  useCommentsQuery,
  useDeleteCommentMutation,
  useEntitlements,
  usePostCommentMutation,
  useProfileQuery,
  useReportCommentMutation,
  useSaveProfileMutation,
} from '../../state/queries';
import styles from './Comments.module.css';

const MAX_LENGTH = 1000;

const REASONS: { value: ReportReason; label: string }[] = [
  { value: 'spam', label: 'Spam' },
  { value: 'abusive', label: 'Abusive or hateful' },
  { value: 'misinformation', label: 'Misinformation' },
  { value: 'other', label: 'Something else' },
];

function kindOf(error: unknown) {
  return error instanceof CommentsError ? error.kind : 'error';
}

function DisplayNameForm() {
  const [name, setName] = useState('');
  const save = useSaveProfileMutation();
  const kind = save.error ? kindOf(save.error) : null;

  return (
    <form
      className={styles.composer}
      onSubmit={(e) => {
        e.preventDefault();
        if (name.trim().length >= 2) save.mutate(name);
      }}
    >
      <div className={styles.formTitle}>Choose a display name to comment</div>
      <div className={styles.hint}>Shown next to your comments. 2&ndash;40 characters, and it must be unique.</div>
      <input
        className={styles.input}
        value={name}
        maxLength={40}
        placeholder="Display name"
        onChange={(e) => setName(e.target.value)}
      />
      <button type="submit" className={styles.primary} disabled={save.isPending || name.trim().length < 2}>
        Save name
      </button>
      {kind && (
        <div className={styles.error}>
          {kind === 'name_taken'
            ? 'That name is taken. Try another.'
            : kind === 'invalid'
              ? 'Names need 2-40 characters and at least one letter or number.'
              : kind === 'unavailable'
                ? "Couldn't save your name right now."
                : "Couldn't save your name. Please try again."}
        </div>
      )}
    </form>
  );
}

function postErrorText(kind: string): string {
  if (kind === 'slow_down') return "You're posting too fast. Try again in a few seconds.";
  if (kind === 'invalid') return `Write something (up to ${MAX_LENGTH} characters).`;
  if (kind === 'unavailable') return "Comments aren't available right now.";
  if (kind === 'not_found') return 'This event is no longer available.';
  return "Couldn't post your comment. Please try again.";
}

function Composer({ crisisId }: { crisisId: string }) {
  const { premium } = useEntitlements();
  const profile = useProfileQuery();
  const post = usePostCommentMutation(crisisId);
  const [body, setBody] = useState('');

  // Free and anonymous visitors can read; commenting is the premium part.
  if (!premium) {
    return (
      <PremiumGate feature="Commenting" block>
        <div className={styles.composer}>
          <textarea className={styles.textarea} rows={3} disabled placeholder="Share your thoughts…" />
          <button type="button" className={styles.primary} disabled>
            Post
          </button>
        </div>
      </PremiumGate>
    );
  }

  if (profile.isLoading) return <div className={styles.status}>Loading…</div>;

  const postKind = post.error ? kindOf(post.error) : null;
  if (!profile.data || postKind === 'profile_required') return <DisplayNameForm />;

  return (
    <form
      className={styles.composer}
      onSubmit={(e) => {
        e.preventDefault();
        if (body.trim()) post.mutate(body, { onSuccess: () => setBody('') });
      }}
    >
      <textarea
        className={styles.textarea}
        rows={3}
        maxLength={MAX_LENGTH}
        value={body}
        placeholder="Share your thoughts…"
        onChange={(e) => setBody(e.target.value)}
      />
      <div className={styles.composerFooter}>
        <span className={styles.hint}>
          Posting as <strong>{profile.data.display_name}</strong> &middot; {body.length}/{MAX_LENGTH}
        </span>
        <button type="submit" className={styles.primary} disabled={post.isPending || !body.trim()}>
          {post.isPending ? 'Posting…' : 'Post'}
        </button>
      </div>
      {postKind && <div className={styles.error}>{postErrorText(postKind)}</div>}
    </form>
  );
}

function CommentItem({ comment, crisisId, canReport }: { comment: EventComment; crisisId: string; canReport: boolean }) {
  const remove = useDeleteCommentMutation(crisisId);
  const report = useReportCommentMutation();
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [reporting, setReporting] = useState(false);
  const [reason, setReason] = useState<ReportReason>('spam');

  return (
    <div className={styles.item}>
      <div className={styles.itemHeader}>
        <span className={styles.author}>{comment.author_name}</span>
        <span className={styles.time}>{timeAgo(comment.created_at)}</span>
      </div>
      {comment.hidden && <div className={styles.hiddenNote}>Hidden pending review &mdash; only you can see this.</div>}
      <div className={styles.body}>{comment.body}</div>

      <div className={styles.actions}>
        {comment.mine ? (
          confirmingDelete ? (
            <>
              <span className={styles.hint}>Delete this comment?</span>
              <button type="button" className={styles.linkDanger} disabled={remove.isPending} onClick={() => remove.mutate(comment.id)}>
                Yes, delete
              </button>
              <button type="button" className={styles.link} onClick={() => setConfirmingDelete(false)}>
                Cancel
              </button>
            </>
          ) : (
            <button type="button" className={styles.link} onClick={() => setConfirmingDelete(true)}>
              Delete
            </button>
          )
        ) : (
          canReport &&
          (report.isSuccess ? (
            <span className={styles.hint}>Reported &mdash; thanks.</span>
          ) : reporting ? (
            <>
              <select className={styles.select} value={reason} onChange={(e) => setReason(e.target.value as ReportReason)}>
                {REASONS.map((r) => (
                  <option key={r.value} value={r.value}>
                    {r.label}
                  </option>
                ))}
              </select>
              <button type="button" className={styles.linkDanger} disabled={report.isPending} onClick={() => report.mutate({ commentId: comment.id, reason })}>
                Send report
              </button>
              <button type="button" className={styles.link} onClick={() => setReporting(false)}>
                Cancel
              </button>
            </>
          ) : (
            <button type="button" className={styles.link} onClick={() => setReporting(true)}>
              Report
            </button>
          ))
        )}
      </div>
      {remove.isError && <div className={styles.error}>Couldn&apos;t delete that comment. Please try again.</div>}
      {report.isError && <div className={styles.error}>Couldn&apos;t send the report. Please try again.</div>}
    </div>
  );
}

// The "Comments" tab of an event's Analysis. Anyone can read; premium members
// can post and report. Everything is plain text.
export default function Comments({ crisisId }: { crisisId: string }) {
  const { premium } = useEntitlements();
  const query = useCommentsQuery(crisisId);
  const comments = query.data?.pages.flatMap((page) => page.comments) ?? [];

  return (
    <div>
      <Composer crisisId={crisisId} />

      {query.isLoading && <div className={styles.status}>Loading comments…</div>}
      {query.isError && (
        <div className={styles.status}>
          Comments aren&apos;t available right now.{' '}
          <button type="button" className={styles.link} onClick={() => query.refetch()}>
            Try again
          </button>
        </div>
      )}
      {query.data && comments.length === 0 && (
        <div className={styles.status}>No comments yet.{premium ? ' Be the first.' : ''}</div>
      )}

      {comments.map((comment) => (
        <CommentItem key={comment.id} comment={comment} crisisId={crisisId} canReport={premium} />
      ))}

      {query.hasNextPage && (
        <button type="button" className={styles.more} disabled={query.isFetchingNextPage} onClick={() => query.fetchNextPage()}>
          {query.isFetchingNextPage ? 'Loading…' : 'Show older comments'}
        </button>
      )}
    </div>
  );
}

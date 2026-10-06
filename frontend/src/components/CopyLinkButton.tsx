import { useState } from 'react';
import type { ShareTarget } from '../lib/shareLink';
import { buildShareUrl } from '../lib/shareLink';
import Button from '../ui/Button';
import styles from './CopyLinkButton.module.css';

// Copies a link to this hazard or place. If the clipboard is blocked, shows the link to copy by hand.
export default function CopyLinkButton({ target, className }: { target: ShareTarget; className?: string }) {
  const [state, setState] = useState<'idle' | 'copied' | 'manual'>('idle');
  const url = buildShareUrl(target);

  async function copy() {
    try {
      await navigator.clipboard.writeText(url);
      setState('copied');
      window.setTimeout(() => setState('idle'), 2500);
    } catch {
      setState('manual');
    }
  }

  return (
    <>
      <Button size="sm" icon={state === 'copied' ? 'check' : 'link'} className={className} onClick={copy}>
        {state === 'copied' ? 'Link copied' : 'Copy link'}
      </Button>
      {state === 'manual' && (
        <input
          readOnly
          value={url}
          aria-label="Link to copy"
          onFocus={(e) => e.currentTarget.select()}
          className={styles.manual}
        />
      )}
    </>
  );
}

import { useState } from 'react';
import type { ShareTarget } from '../lib/shareLink';
import { buildShareUrl } from '../lib/shareLink';

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
      <button type="button" className={className} onClick={copy}>
        {state === 'copied' ? 'Link copied' : 'Copy link'}
      </button>
      {state === 'manual' && (
        <input
          readOnly
          value={url}
          aria-label="Link to copy"
          onFocus={(e) => e.currentTarget.select()}
          style={{ width: '100%', marginTop: 6, fontSize: 12 }}
        />
      )}
    </>
  );
}

'use client';

import { useRouter } from 'next/navigation';
import { type ReactElement, useState } from 'react';

/**
 * The care-use declaration.
 *
 * Deliberately not a one-click button. The wording is shown in full, the
 * confirmation is a separate deliberate act, and the consequence (every record
 * you open is logged against your name) is stated before the choice rather than
 * in small print after it. A gate that can be cleared without reading it
 * records only that somebody clicked, which is worth nothing to the person
 * whose data is behind it.
 */
export function AttestForm({ text }: { text: string }): ReactElement {
  const router = useRouter();
  const [checked, setChecked] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(): Promise<void> {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch('/api/organisation/attestation', { method: 'POST' });
      if (!res.ok) {
        setError('Could not record the confirmation. Please try again.');
        setBusy(false);
        return;
      }
      router.refresh();
    } catch {
      setError('Could not record the confirmation. Please try again.');
      setBusy(false);
    }
  }

  return (
    <div className="rounded-[var(--radius-control)] border border-brand-200 bg-white p-6">
      <h2 className="text-lg font-semibold tracking-tight text-brand-950">
        Confirm how you will use this list
      </h2>
      <p className="mt-2 max-w-2xl text-sm text-brand-700">
        This page names individual members. Before it opens, confirm the purpose
        below. Your confirmation is recorded against your name and lasts 90 days.
      </p>

      <blockquote className="mt-4 max-w-2xl border-l-2 border-brand-300 pl-4 text-sm leading-relaxed text-brand-800">
        {text}
      </blockquote>

      <label
        htmlFor="care-use-confirm"
        className="mt-5 flex max-w-2xl items-start gap-3 text-sm text-brand-900"
      >
        <input
          id="care-use-confirm"
          type="checkbox"
          checked={checked}
          onChange={(e) => setChecked(e.target.checked)}
          className="mt-1 h-4 w-4 rounded border-brand-300 text-brand-700 focus-visible:ring-2 focus-visible:ring-brand-500"
        />
        <span>I confirm the above.</span>
      </label>

      {error ? <p className="mt-4 text-sm text-red-700">{error}</p> : null}

      <button
        type="button"
        onClick={submit}
        disabled={!checked || busy}
        className="mt-5 rounded-full bg-brand-700 px-5 py-2.5 text-sm font-medium text-white transition hover:bg-brand-800 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-700"
      >
        {busy ? 'Recording…' : 'Confirm and open the list'}
      </button>
    </div>
  );
}

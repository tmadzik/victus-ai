'use client';

import { useCallback, useEffect, useState } from 'react';

import {
  type KioskResultPayload,
  KioskResultPayloadSchema,
  TriageState,
} from '@victus/contracts';

type Phase = 'loading' | 'otp' | 'result' | 'invalid' | 'consumed' | 'locked';

interface ErrorBody {
  error?: { code?: string; message?: string; attempts_remaining?: number };
}

const STATE_STYLES: Record<TriageState, { band: string; label: string }> = {
  [TriageState.GREEN]: {
    band: 'bg-[color:var(--color-state-green-ring)]',
    label: 'No urgent concerns detected',
  },
  [TriageState.YELLOW]: {
    band: 'bg-[color:var(--color-state-yellow-ring)]',
    label: 'Some readings to review',
  },
  [TriageState.RED]: {
    band: 'bg-[color:var(--color-state-red-ring)]',
    label: 'Please seek care soon',
  },
};

export function ResultPortal({ token }: { token: string }): React.ReactElement {
  const [phase, setPhase] = useState<Phase>('loading');
  const [otp, setOtp] = useState('');
  const [attemptsLeft, setAttemptsLeft] = useState<number | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [payload, setPayload] = useState<KioskResultPayload | null>(null);

  // Probe the link on mount so we can show the right state before any OTP try.
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const res = await fetch(`/api/kiosk/results/${encodeURIComponent(token)}`, {
          cache: 'no-store',
        });
        if (cancelled) return;
        if (res.ok) {
          const gate = (await res.json()) as { attempts_remaining?: number; locked?: boolean };
          setAttemptsLeft(gate.attempts_remaining ?? null);
          setPhase(gate.locked ? 'locked' : 'otp');
        } else if (res.status === 409) {
          setPhase('consumed');
        } else {
          setPhase('invalid');
        }
      } catch {
        if (!cancelled) setPhase('invalid');
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token]);

  const submit = useCallback(
    async (e: React.FormEvent): Promise<void> => {
      e.preventDefault();
      if (otp.length !== 4 || submitting) return;
      setSubmitting(true);
      setMessage(null);
      try {
        const res = await fetch(
          `/api/kiosk/results/${encodeURIComponent(token)}/unlock`,
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ otp }),
          },
        );
        if (res.ok) {
          setPayload(KioskResultPayloadSchema.parse(await res.json()));
          setPhase('result');
          return;
        }
        const body = (await res.json().catch(() => ({}))) as ErrorBody;
        const remaining = body.error?.attempts_remaining ?? null;
        setAttemptsLeft(remaining);
        setOtp('');
        if (res.status === 403) {
          setPhase('locked');
        } else if (res.status === 410) {
          setPhase('invalid');
        } else if (res.status === 409) {
          setPhase('consumed');
        } else {
          setMessage(
            remaining !== null
              ? `Incorrect code. ${remaining} ${remaining === 1 ? 'try' : 'tries'} left.`
              : 'Incorrect code.',
          );
        }
      } catch {
        setMessage('Something went wrong. Please try again.');
      } finally {
        setSubmitting(false);
      }
    },
    [otp, submitting, token],
  );

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-md flex-col justify-center gap-6 px-5 py-10">
      <header className="text-center">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/victus-logo.svg" alt="Victus AI" className="mx-auto h-10 w-auto" />
        <h1 className="mt-4 text-2xl font-semibold text-brand-950">
          Your wellness summary
        </h1>
      </header>

      {phase === 'loading' ? <Centered>Checking your link…</Centered> : null}

      {phase === 'otp' ? (
        <form
          onSubmit={submit}
          className="rounded-3xl border border-brand-200 bg-white p-6 shadow-sm"
        >
          <p className="text-sm text-brand-700">
            Enter the 4-digit code we sent to your WhatsApp to view your summary.
          </p>
          <input
            inputMode="numeric"
            autoComplete="one-time-code"
            pattern="\d{4}"
            maxLength={4}
            value={otp}
            onChange={(e) => setOtp(e.target.value.replace(/\D/g, '').slice(0, 4))}
            aria-label="4-digit code"
            className="mt-4 w-full rounded-2xl border border-brand-300 bg-brand-50 px-4 py-4 text-center font-mono text-3xl tracking-[0.5em] text-brand-950 outline-none focus:border-brand-600"
            placeholder="––––"
          />
          {message ? <p className="mt-3 text-sm text-red-600">{message}</p> : null}
          {attemptsLeft !== null && !message ? (
            <p className="mt-3 text-xs text-brand-500">
              {attemptsLeft} {attemptsLeft === 1 ? 'attempt' : 'attempts'} remaining.
            </p>
          ) : null}
          <button
            type="submit"
            disabled={otp.length !== 4 || submitting}
            className="mt-5 w-full rounded-2xl bg-brand-700 px-4 py-4 text-lg font-semibold text-white transition hover:bg-brand-800 disabled:opacity-50"
          >
            {submitting ? 'Unlocking…' : 'View my summary'}
          </button>
          <p className="mt-4 text-center text-xs text-brand-500">
            This link can be opened once and expires 24 hours after it was sent.
          </p>
        </form>
      ) : null}

      {phase === 'result' && payload ? <ResultView payload={payload} /> : null}

      {phase === 'locked' ? (
        <Notice
          title="Link locked"
          body="Too many incorrect codes were entered. For your security this link is now locked. Please request a new check-up at the kiosk."
        />
      ) : null}
      {phase === 'consumed' ? (
        <Notice
          title="Already viewed"
          body="This summary has already been opened. For your privacy each link works only once."
        />
      ) : null}
      {phase === 'invalid' ? (
        <Notice
          title="Link unavailable"
          body="This link is invalid or has expired. Links expire 24 hours after they are sent."
        />
      ) : null}
    </main>
  );
}

function ResultView({ payload }: { payload: KioskResultPayload }): React.ReactElement {
  const state = payload.triage_state ?? null;
  const style = state ? STATE_STYLES[state] : null;
  const vitals = Object.entries(payload.vitals ?? {});
  return (
    <div className="overflow-hidden rounded-3xl border border-brand-200 bg-white shadow-sm">
      {style ? (
        <div className={`${style.band} px-6 py-4`}>
          <p className="text-sm font-semibold uppercase tracking-wider text-white/90">
            {state}
          </p>
          <p className="text-lg font-semibold text-white">{style.label}</p>
        </div>
      ) : null}
      <div className="space-y-4 p-6">
        <div>
          <h2 className="text-xl font-semibold text-brand-950">{payload.headline}</h2>
          <p className="mt-1 text-brand-700">{payload.body}</p>
        </div>

        {vitals.length > 0 ? (
          <dl className="grid grid-cols-2 gap-3">
            {vitals.map(([key, value]) => (
              <div key={key} className="rounded-2xl border border-brand-100 p-3">
                <dt className="text-xs uppercase tracking-wider text-brand-500">
                  {key.replace(/_/g, ' ')}
                </dt>
                <dd className="mt-1 font-mono text-lg text-brand-900">
                  {String(value)}
                </dd>
              </div>
            ))}
          </dl>
        ) : null}

        <p className="rounded-2xl bg-brand-50 p-4 text-sm leading-relaxed text-brand-700">
          {payload.disclaimer}
        </p>
      </div>
    </div>
  );
}

function Notice({ title, body }: { title: string; body: string }): React.ReactElement {
  return (
    <div className="rounded-3xl border border-brand-200 bg-white p-6 text-center shadow-sm">
      <h2 className="text-xl font-semibold text-brand-950">{title}</h2>
      <p className="mt-2 text-brand-700">{body}</p>
    </div>
  );
}

function Centered({ children }: { children: React.ReactNode }): React.ReactElement {
  return <p className="text-center text-brand-600">{children}</p>;
}

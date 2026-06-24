'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

import {
  type KioskCaptureRequest,
  type KioskSessionResponse,
  KioskSessionResponseSchema,
  KioskSessionStatusResponseSchema,
} from '@victus/contracts';

import { QrPanel } from './qr-panel';
import { KioskCapture } from './kiosk-capture';

type Screen = 'welcome' | 'linking' | 'capture' | 'submitting' | 'done' | 'error';

// The spec's inactivity purge: wipe local state + camera if abandoned.
const INACTIVITY_MS = 30_000;
const POLL_MS = 2_500;

export function KioskClient(): React.ReactElement {
  const [screen, setScreen] = useState<Screen>('welcome');
  const [session, setSession] = useState<KioskSessionResponse | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const screenRef = useRef<Screen>('welcome');
  const inactivityRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const setScreenBoth = useCallback((s: Screen) => {
    screenRef.current = s;
    setScreen(s);
  }, []);

  /** Full local purge — return to the welcome screen, drop the session. The
   *  KioskCapture unmount stops the camera + releases the MediaStream. */
  const purge = useCallback(() => {
    setSession(null);
    setErrorMessage(null);
    setScreenBoth('welcome');
  }, [setScreenBoth]);

  const resetInactivity = useCallback(() => {
    if (inactivityRef.current) clearTimeout(inactivityRef.current);
    // Active measurement isn't "inactivity"; pause the timer during capture.
    if (screenRef.current === 'capture' || screenRef.current === 'submitting') return;
    if (screenRef.current === 'welcome') return;
    inactivityRef.current = setTimeout(() => purge(), INACTIVITY_MS);
  }, [purge]);

  // Reset the inactivity timer on any interaction with the terminal.
  useEffect(() => {
    const onActivity = (): void => resetInactivity();
    const events: (keyof WindowEventMap)[] = [
      'pointerdown',
      'touchstart',
      'keydown',
      'mousemove',
    ];
    events.forEach((e) => window.addEventListener(e, onActivity, { passive: true }));
    return () => {
      events.forEach((e) => window.removeEventListener(e, onActivity));
      if (inactivityRef.current) clearTimeout(inactivityRef.current);
    };
  }, [resetInactivity]);

  const startSession = useCallback(async (): Promise<void> => {
    setErrorMessage(null);
    try {
      const res = await fetch('/api/kiosk/sessions', { method: 'POST' });
      if (!res.ok) throw new Error('Could not start a session.');
      const parsed = KioskSessionResponseSchema.parse(await res.json());
      setSession(parsed);
      setScreenBoth('linking');
      resetInactivity();
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : 'Something went wrong.');
      setScreenBoth('error');
    }
  }, [resetInactivity, setScreenBoth]);

  // Poll session status while linking, until the participant consents on WhatsApp.
  useEffect(() => {
    if (screen !== 'linking' || !session) return;
    let cancelled = false;
    const id = setInterval(async () => {
      try {
        const res = await fetch(`/api/kiosk/sessions/${session.id}`, { cache: 'no-store' });
        if (!res.ok) return;
        const status = KioskSessionStatusResponseSchema.parse(await res.json());
        if (cancelled) return;
        if (status.consented) {
          resetInactivity();
          setScreenBoth('capture');
        } else if (
          status.status === 'EXPIRED' ||
          status.status === 'ABORTED'
        ) {
          purge();
        } else if (status.linked) {
          // Progress — the participant is mid-flow; keep the session alive.
          resetInactivity();
        }
      } catch {
        /* transient poll error — keep trying until the session expires */
      }
    }, POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [screen, session, purge, resetInactivity, setScreenBoth]);

  const handleCapture = useCallback(
    async (capture: KioskCaptureRequest): Promise<void> => {
      if (!session) return;
      setScreenBoth('submitting');
      try {
        const res = await fetch(`/api/kiosk/sessions/${session.id}/capture`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(capture),
        });
        if (!res.ok) throw new Error('Could not submit your capture.');
        setScreenBoth('done');
        // Auto-reset for the next person.
        setTimeout(() => purge(), 12_000);
      } catch (err) {
        setErrorMessage(err instanceof Error ? err.message : 'Submission failed.');
        setScreenBoth('error');
      }
    },
    [session, purge, setScreenBoth],
  );

  return (
    <main className="flex min-h-dvh w-full max-w-2xl flex-col items-center justify-center gap-8 px-6 py-10 text-center">
      {screen === 'welcome' ? (
        <WelcomeScreen onStart={() => void startSession()} />
      ) : null}

      {screen === 'linking' && session ? (
        <LinkingScreen session={session} onCancel={purge} />
      ) : null}

      {screen === 'capture' ? <KioskCapture onComplete={handleCapture} /> : null}

      {screen === 'submitting' ? (
        <Status title="Processing…" body="Analysing your readings. This takes a moment." />
      ) : null}

      {screen === 'done' ? (
        <Status
          title="All done ✅"
          body="Your secure results link and a 4-digit code are on their way to your WhatsApp. Open the link on your phone to view your summary."
          tone="success"
        />
      ) : null}

      {screen === 'error' ? (
        <div className="space-y-5">
          <Status title="Something went wrong" body={errorMessage ?? 'Please try again.'} tone="error" />
          <BigButton onClick={purge}>Start over</BigButton>
        </div>
      ) : null}
    </main>
  );
}

function WelcomeScreen({ onStart }: { onStart: () => void }): React.ReactElement {
  return (
    <div className="space-y-8">
      <div className="space-y-3">
        <h1 className="text-balance text-4xl font-semibold tracking-tight text-brand-50 sm:text-5xl">
          Free contactless wellness check-up
        </h1>
        <p className="mx-auto max-w-md text-balance text-lg text-brand-300">
          A quick face scan estimates your vitals. This is a wellness screening,
          not a medical diagnosis. No photo or video is ever stored.
        </p>
      </div>
      <BigButton onClick={onStart}>Tap to begin</BigButton>
    </div>
  );
}

function LinkingScreen({
  session,
  onCancel,
}: {
  session: KioskSessionResponse;
  onCancel: () => void;
}): React.ReactElement {
  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h2 className="text-3xl font-semibold text-brand-50">Scan to connect</h2>
        <p className="mx-auto max-w-md text-brand-300">
          Open WhatsApp and scan this code with your phone, then reply{' '}
          <span className="font-semibold text-brand-100">YES</span> to consent.
        </p>
      </div>
      <div className="flex justify-center">
        <QrPanel value={session.whatsapp_deep_link ?? session.qr_text} />
      </div>
      <p className="font-mono text-sm text-brand-400">{session.qr_text}</p>
      <button onClick={onCancel} className="text-sm text-brand-400 underline">
        Cancel
      </button>
    </div>
  );
}

function Status({
  title,
  body,
  tone = 'neutral',
}: {
  title: string;
  body: string;
  tone?: 'neutral' | 'success' | 'error';
}): React.ReactElement {
  const titleColor =
    tone === 'success'
      ? 'text-emerald-400'
      : tone === 'error'
        ? 'text-red-400'
        : 'text-brand-50';
  return (
    <div className="space-y-3">
      <h2 className={`text-3xl font-semibold ${titleColor}`}>{title}</h2>
      <p className="mx-auto max-w-md text-balance text-lg text-brand-300">{body}</p>
    </div>
  );
}

function BigButton({
  onClick,
  children,
}: {
  onClick: () => void;
  children: React.ReactNode;
}): React.ReactElement {
  return (
    <button
      onClick={onClick}
      className="rounded-full bg-emerald-500 px-12 py-5 text-2xl font-semibold text-brand-950 shadow-lg transition hover:bg-emerald-400 active:scale-[0.98]"
    >
      {children}
    </button>
  );
}

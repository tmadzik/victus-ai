'use client';

import Link from 'next/link';
import { useActionState, useRef, type ReactElement } from 'react';
import { useFormStatus } from 'react-dom';

import { Button } from '@victus/ui';

import { requestPilot, type PilotRequestState } from '@/app/actions';

const INITIAL_STATE: PilotRequestState = { status: 'idle', message: '' };

function SubmitButton(): ReactElement {
  const { pending } = useFormStatus();
  return (
    <Button type="submit" size="lg" disabled={pending} className="shrink-0 rounded-full">
      {pending ? 'Sending…' : 'Request Pilot'}
    </Button>
  );
}

export function LeadCapture(): ReactElement {
  const [state, formAction] = useActionState(requestPilot, INITIAL_STATE);
  // Captured once on mount; the server rejects sub-2s submissions as bots.
  const renderedAt = useRef(Date.now());

  return (
    <section id="request-pilot" className="scroll-mt-24 px-4 py-20 sm:py-28">
      <div className="mx-auto flex max-w-2xl flex-col items-center gap-6 text-center">
        <h2 className="text-brand-950 text-3xl font-semibold tracking-tighter text-balance sm:text-4xl">
          Start Managing Population Risk.
        </h2>
        <p className="text-brand-700 text-lg text-pretty">
          Deploy the Victus platform for your healthcare fund.
        </p>

        {state.status === 'success' ? (
          <p
            role="status"
            className="bg-brand-50 text-brand-900 ring-brand-200 rounded-full px-6 py-3 text-sm font-medium ring-1 ring-inset"
          >
            {state.message}
          </p>
        ) : (
          <form action={formAction} className="w-full max-w-md">
            <div className="ring-brand-200 focus-within:ring-brand-500 flex items-center gap-1.5 rounded-full bg-white p-1.5 ring-1 transition-shadow ring-inset focus-within:ring-2">
              <label htmlFor="pilot-email" className="sr-only">
                Work email
              </label>
              <input
                id="pilot-email"
                name="email"
                type="email"
                required
                autoComplete="email"
                placeholder="Enter your work email"
                className="text-brand-950 placeholder:text-brand-400 h-11 w-full min-w-0 flex-1 bg-transparent px-4 text-sm focus:outline-none"
              />
              <SubmitButton />
            </div>

            {/* Honeypot — invisible to humans, irresistible to bots. */}
            <input
              type="text"
              name="company_website"
              tabIndex={-1}
              autoComplete="off"
              aria-hidden="true"
              className="absolute -left-[9999px] size-px opacity-0"
            />
            <input type="hidden" name="rendered_at" value={renderedAt.current} />

            {state.status === 'error' ? (
              <p role="alert" className="mt-3 text-sm text-[color:var(--color-state-red-fg)]">
                {state.message}
              </p>
            ) : null}

            <p className="text-grey-500 mt-4 text-xs text-pretty">
              By submitting, you consent to Victus contacting you about the platform. See our{' '}
              <Link href="/privacy" className="hover:text-brand-900 underline underline-offset-2">
                Privacy Policy
              </Link>
              .
            </p>
          </form>
        )}
      </div>
    </section>
  );
}

'use client';

import Link from 'next/link';
import { useActionState, useRef, type ReactElement } from 'react';
import { useFormStatus } from 'react-dom';

import { Button } from '@victus/ui';

import { requestPilot, type PilotRequestState } from '@/app/actions';
import { ENQUIRY_COUNTRIES, ENQUIRY_ROLES } from '@/lib/enquiry';

const INITIAL_STATE: PilotRequestState = { status: 'idle', message: '' };

const fieldClass =
  'h-11 w-full rounded-[var(--radius-control)] bg-white px-3.5 text-sm text-brand-950 ' +
  'ring-1 ring-brand-200 ring-inset placeholder:text-brand-400 ' +
  'focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:outline-none';

const labelClass = 'text-sm font-medium text-white/90';

function SubmitButton(): ReactElement {
  const { pending } = useFormStatus();
  return (
    <Button type="submit" size="lg" disabled={pending} className="w-full rounded-full sm:w-auto">
      {pending ? 'Sending…' : 'Book a Demo'}
    </Button>
  );
}

export function LeadCapture(): ReactElement {
  const [state, formAction] = useActionState(requestPilot, INITIAL_STATE);
  // Captured once on mount; the server rejects sub-2s submissions as bots.
  const renderedAt = useRef(Date.now());

  return (
    <section id="book-demo" className="bg-brand-950 scroll-mt-24 px-4 py-20 text-white sm:py-28">
      <div className="mx-auto max-w-2xl">
        <div className="text-center">
          <h2 className="text-3xl font-semibold tracking-tighter text-balance sm:text-4xl">
            See Victus on your own numbers.
          </h2>
          <p className="mt-4 text-lg text-pretty text-white/80">
            Tell us about your team and we&rsquo;ll walk you through the platform and scope a pilot
            with you.
          </p>
        </div>

        {state.status === 'success' ? (
          <p
            role="status"
            className="bg-brand-50 text-brand-900 ring-brand-200 mx-auto mt-10 max-w-md rounded-[var(--radius-card)] px-6 py-5 text-center font-medium ring-1 ring-inset"
          >
            {state.message}
          </p>
        ) : (
          <form action={formAction} className="mt-10 flex flex-col gap-5">
            <div className="grid gap-5 sm:grid-cols-2">
              <div className="flex flex-col gap-1.5">
                <label htmlFor="lead-name" className={labelClass}>
                  Full name
                </label>
                <input
                  id="lead-name"
                  name="full_name"
                  required
                  autoComplete="name"
                  className={fieldClass}
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <label htmlFor="lead-email" className={labelClass}>
                  Work email
                </label>
                <input
                  id="lead-email"
                  name="email"
                  type="email"
                  required
                  autoComplete="email"
                  className={fieldClass}
                />
              </div>
            </div>

            <div className="flex flex-col gap-1.5">
              <label htmlFor="lead-org" className={labelClass}>
                Organisation
              </label>
              <input
                id="lead-org"
                name="organisation"
                required
                autoComplete="organization"
                className={fieldClass}
              />
            </div>

            <div className="grid gap-5 sm:grid-cols-2">
              <div className="flex flex-col gap-1.5">
                <label htmlFor="lead-role" className={labelClass}>
                  Which best describes you?
                </label>
                <select id="lead-role" name="role" required defaultValue="" className={fieldClass}>
                  <option value="" disabled>
                    Select one…
                  </option>
                  {ENQUIRY_ROLES.map((role) => (
                    <option key={role} value={role}>
                      {role}
                    </option>
                  ))}
                </select>
              </div>
              <div className="flex flex-col gap-1.5">
                <label htmlFor="lead-country" className={labelClass}>
                  Country <span className="font-normal text-white/50">(optional)</span>
                </label>
                <select id="lead-country" name="country" defaultValue="" className={fieldClass}>
                  <option value="">Select…</option>
                  {ENQUIRY_COUNTRIES.map((country) => (
                    <option key={country} value={country}>
                      {country}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="flex flex-col gap-1.5">
              <label htmlFor="lead-message" className={labelClass}>
                What would you like to cover?{' '}
                <span className="font-normal text-white/50">(optional)</span>
              </label>
              <textarea
                id="lead-message"
                name="message"
                rows={3}
                className={`${fieldClass} h-auto py-2.5`}
              />
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
              <p role="alert" className="text-sm text-red-300">
                {state.message}
              </p>
            ) : null}

            <div className="flex flex-col items-start gap-4 sm:flex-row sm:items-center">
              <SubmitButton />
              <p className="text-xs text-pretty text-white/60">
                By submitting, you consent to Victus contacting you about the platform. See our{' '}
                <Link href="/privacy" className="underline underline-offset-2 hover:text-white">
                  Privacy Policy
                </Link>
                .
              </p>
            </div>
          </form>
        )}
      </div>
    </section>
  );
}

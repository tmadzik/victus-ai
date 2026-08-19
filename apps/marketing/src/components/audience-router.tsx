import { Building2, Stethoscope, Truck, type LucideIcon } from 'lucide-react';
import type { Route } from 'next';
import Link from 'next/link';
import type { ReactElement } from 'react';

interface Audience {
  role: string;
  title: string;
  pitch: string;
  points: string[];
  icon: LucideIcon;
  href: string;
  /** Defaults to "Sign in" for the roles that have an application login. */
  ctaLabel?: string;
}

const AUDIENCES: Audience[] = [
  {
    role: 'clinician',
    title: 'Clinicians & care teams',
    pitch: 'See who needs you first, and act on it in the same visit.',
    points: [
      'A clear low / watch / urgent result per person',
      'One record with their full screening history',
      'Raise a referral and export a PDF for the file',
    ],
    icon: Stethoscope,
    href: '/for/clinicians',
    ctaLabel: 'For clinicians',
  },
  {
    role: 'insurer',
    title: 'Health insurers & funders',
    pitch: 'Find rising risk in your member base before it becomes a claim.',
    points: [
      'Screen members in the community, without a clinic visit',
      'Route flagged members into wellness or care',
      'Track referrals and follow-up over time',
    ],
    icon: Building2,
    // Funder access is arranged with us directly — there is no self-serve
    // insurer login today, so this routes to the demo rather than a dead end.
    href: '/#book-demo',
    ctaLabel: 'Book a demo',
  },
  {
    role: 'kiosk',
    title: 'Community & mobile clinics',
    pitch: 'Bring screening to where people already are.',
    points: [
      'A self-service kiosk — nothing for people to install',
      'Consent captured over WhatsApp before any capture',
      'Private results delivered straight to their phone',
    ],
    icon: Truck,
    href: '/for/kiosk',
    ctaLabel: 'For community clinics',
  },
];

export function AudienceRouter(): ReactElement {
  return (
    <section id="who-its-for" className="scroll-mt-24 px-4 py-20 sm:py-28">
      <div className="mx-auto max-w-6xl">
        <div className="max-w-2xl">
          <h2 className="text-brand-950 text-3xl font-semibold tracking-tighter text-balance sm:text-4xl">
            Built for your team.
          </h2>
          <p className="text-brand-700 mt-4 text-lg text-pretty">
            One platform, three ways in — whether you see patients, carry the risk, or take
            screening out into the community.
          </p>
        </div>

        <div className="mt-12 grid gap-4 lg:grid-cols-3">
          {AUDIENCES.map((audience) => (
            <div
              key={audience.role}
              className="ring-brand-100 hover:ring-brand-300 flex flex-col rounded-[var(--radius-card)] bg-white p-8 shadow-sm ring-1 transition-shadow ring-inset hover:shadow-md"
            >
              <span className="bg-brand-100 text-brand-700 flex size-12 items-center justify-center rounded-xl">
                <audience.icon aria-hidden="true" className="size-6" />
              </span>
              <h3 className="text-brand-950 mt-6 text-xl font-semibold tracking-tight">
                {audience.title}
              </h3>
              <p className="text-brand-700 mt-2 text-pretty">{audience.pitch}</p>
              <ul className="mt-5 flex flex-1 flex-col gap-2.5">
                {audience.points.map((point) => (
                  <li key={point} className="flex gap-2.5 text-sm leading-relaxed">
                    <span
                      aria-hidden="true"
                      className="bg-brand-400 mt-2 size-1.5 shrink-0 rounded-full"
                    />
                    <span className="text-brand-700 text-pretty">{point}</span>
                  </li>
                ))}
              </ul>
              <Link
                href={audience.href as Route}
                className="text-brand-700 hover:text-brand-950 mt-7 text-sm font-semibold transition-colors"
              >
                {audience.ctaLabel ?? 'Sign in'} <span aria-hidden="true">→</span>
              </Link>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

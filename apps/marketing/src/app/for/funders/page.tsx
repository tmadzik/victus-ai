import {
  Building2,
  ClipboardCheck,
  HeartPulse,
  Route as RouteIcon,
  ScanLine,
  ShieldCheck,
} from 'lucide-react';
import type { Metadata } from 'next';
import type { ReactElement } from 'react';

import { RoleLanding } from '@/components/role-landing';

export const metadata: Metadata = {
  title: 'For health insurers & funders',
  description:
    'Victus for funders: screen members in the community without a clinic visit, see a population view that cannot identify anyone, route flagged members into care, and follow each referral through to an outcome.',
  alternates: { canonical: '/for/funders' },
};

/**
 * The funder pathway.
 *
 * Every claim on this page is bounded by two documents, deliberately:
 *
 * * `docs/MODEL_DATA_ARCHITECTURE.md` §4.1 — the model is cross-sectional, so
 *   it detects disease already present. Nothing here says "predict", "early
 *   detection", or anything about reducing claims or cost. That last one is
 *   barred from marketing and contracts alike until a counterfactual design is
 *   agreed with a funder's own actuary.
 * * `docs/ENROLLMENT_DPIA.md` §7.6 — the training extract is **de-identified**,
 *   not anonymous, until a re-identification risk assessment is signed. This
 *   page uses that word and no stronger one, and says why.
 *
 * The honest version is not the weaker pitch. What a funder actually wants to
 * know is whether the people you flag reach care, and that is the one thing
 * here which is genuinely built, measured and reportable today.
 */
const WAYS_OF_WORKING = [
  {
    title: 'On our platform',
    body: 'Your own team screens members using Victus software, on your own deployment.',
  },
  {
    title: 'At our facilities',
    body: 'Members are screened at a Victus wellness facility, as a benefit you offer them.',
  },
  {
    title: 'At your site',
    body: 'We come to you — screening days on your premises, with consultation and wellness alongside.',
  },
];

export default function FundersPage(): ReactElement {
  return (
    <RoleLanding
      eyebrow="For health insurers & funders"
      title="Find the disease already in your member base."
      intro="Most non-communicable disease in a member population is present and undiagnosed long before anyone hears about it. Victus screens for it in the community — no bloods, no clinic visit — routes the people it flags into care, and shows you how many of them actually got there."
      features={[
        {
          title: 'Screen without a clinic visit',
          description:
            'A few tape-measure readings and questions, or a short face-video capture on a phone. Members are screened where they already are, including at a self-service kiosk with consent taken over WhatsApp first.',
          icon: ScanLine,
        },
        {
          title: 'A population view that names nobody',
          description:
            'Your cohort dashboard reports how members distribute across low, watch and urgent. Any group too small to be safe is withheld — and where withholding one group would let its size be worked out by subtraction, a second goes too.',
          icon: ShieldCheck,
        },
        {
          title: 'Route the people who need it',
          description:
            'Care managers open a named list of flagged members and follow up — a wellness referral, a call, a clinic appointment. That view is theirs alone, and opening it is logged.',
          icon: RouteIcon,
        },
        {
          title: 'Follow it through to an outcome',
          description:
            'Referral, attended, confirmed, treatment started — the loop is tracked and reported as rates, not anecdotes. This is the number we would put in front of you first.',
          icon: HeartPulse,
        },
        {
          title: 'Your deployment, your database',
          description:
            'Each organisation runs on its own instance with its own database. There is no shared system with another funder’s members in it, so there is no query that could cross between you.',
          icon: Building2,
        },
        {
          title: 'Underwriting is designed out',
          description:
            'Individual member risk opens only for a care manager who has confirmed on the record that they are routing people into care, not rating them. It protects your members — and it protects you, if you are ever asked to show that.',
          icon: ClipboardCheck,
        },
      ]}
      primary={{ label: 'Book a demo', href: '/#book-demo' }}
      secondary={{
        label: 'Talk to us',
        note: 'Funder deployments are set up with us directly — there is no self-serve sign-up. Tell us about your member base and we will scope a pilot.',
      }}
      extra={
        <>
          <section className="px-4 py-20 sm:py-24">
            <div className="mx-auto max-w-5xl">
              <h2 className="text-brand-950 text-3xl font-semibold tracking-tighter text-balance sm:text-4xl">
                Three ways to run it.
              </h2>
              <p className="text-brand-700 mt-4 max-w-2xl text-lg text-pretty">
                Screening can sit with your team, with ours, or come to your
                premises. The reporting is the same in all three.
              </p>
              <div className="mt-10 grid gap-4 sm:grid-cols-3">
                {WAYS_OF_WORKING.map((way) => (
                  <div
                    key={way.title}
                    className="ring-brand-100 rounded-[var(--radius-card)] p-7 ring-1 ring-inset"
                  >
                    <h3 className="text-brand-950 font-semibold tracking-tight">
                      {way.title}
                    </h3>
                    <p className="text-brand-700 mt-1.5 text-sm leading-relaxed text-pretty">
                      {way.body}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          </section>

          <section className="bg-brand-950 px-4 py-20 text-white sm:py-24">
            <div className="mx-auto max-w-3xl">
              <h2 className="text-3xl font-semibold tracking-tighter text-balance sm:text-4xl">
                What we ask of your data, and what we don’t.
              </h2>
              <div className="mt-8 space-y-5 text-white/80">
                <p className="text-pretty">
                  Nothing leaves your deployment unless you agree that it can,
                  under a named version of an agreement. Withdrawing that
                  agreement stops it.
                </p>
                <p className="text-pretty">
                  What may leave is a de-identified extract used to improve the
                  models: no names, no member identifiers, no organisation
                  identifier, and every group too small to be safe removed
                  entirely rather than thinned.
                </p>
                <p className="text-pretty">
                  We call that <strong className="text-white">de-identified</strong>,
                  not anonymous. A formal re-identification assessment has not
                  been signed off yet, and until it has, the stronger word would
                  be doing work the evidence does not support. Once records are
                  pooled they carry nothing that ties them back to you — though a
                  file arriving from your deployment is of course identifiable as
                  yours until a pooling arrangement is in place.
                </p>
              </div>
              <p className="mt-8 text-sm text-white/50 text-pretty">
                Victus is a research demonstrator preparing pilots in Zimbabwe and
                Nigeria. Screening indicates who may need attention; it is not a
                diagnosis, and it is not a basis for any decision about a
                member’s cover.
              </p>
            </div>
          </section>
        </>
      }
    />
  );
}

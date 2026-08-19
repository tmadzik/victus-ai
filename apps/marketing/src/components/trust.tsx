import { FileCheck2, Fingerprint, ScrollText, ShieldCheck, type LucideIcon } from 'lucide-react';
import type { ReactElement } from 'react';

interface Pillar {
  title: string;
  description: string;
  icon: LucideIcon;
}

const PILLARS: Pillar[] = [
  {
    title: 'Consent-first enrollment',
    description:
      'Every participant completes explicit, granular consent before any screening. Identifiers are minimised and the external patient ID is stored only as a salted hash — the plaintext is never kept.',
    icon: Fingerprint,
  },
  {
    title: 'Jurisdiction-aware',
    description:
      'Each deployment is stamped with its country and honours the local regime — POPIA in South Africa, the Cyber & Data Protection Act in Zimbabwe, the NDPA in Nigeria — including data residency.',
    icon: ShieldCheck,
  },
  {
    title: 'Audited & erasable',
    description:
      'Every access to an identified record is logged and role-restricted. A right-to-erasure path removes personal data while preserving de-identified research strata, and each deployment carries a Data Protection Impact Assessment.',
    icon: ScrollText,
  },
  {
    title: 'Secure by construction',
    description:
      'argon2id password hashing, short-lived rotating tokens, HTTPS-only sessions, and per-site deployment so clinical data stays within each pilot’s boundary.',
    icon: FileCheck2,
  },
];

export function Trust(): ReactElement {
  return (
    <section id="trust" className="bg-brand-50 scroll-mt-24 px-4 py-20 sm:py-28">
      <div className="mx-auto max-w-6xl">
        <div className="max-w-2xl">
          <h2 className="text-brand-950 text-3xl font-semibold tracking-tighter text-balance sm:text-4xl">
            Built compliance-first.
          </h2>
          <p className="text-brand-700 mt-4 text-lg text-pretty">
            Population health runs on trust. Victus is engineered around consent, data-protection
            law, and auditability from the very first screen.
          </p>
        </div>

        <div className="mt-12 grid gap-4 sm:grid-cols-2">
          {PILLARS.map((pillar) => (
            <div
              key={pillar.title}
              className="ring-brand-100 flex gap-5 rounded-[var(--radius-card)] bg-white p-6 ring-1 ring-inset sm:p-8"
            >
              <span className="bg-brand-100 text-brand-700 flex size-11 shrink-0 items-center justify-center rounded-lg">
                <pillar.icon aria-hidden="true" className="size-5" />
              </span>
              <div>
                <h3 className="text-brand-950 font-semibold tracking-tight">{pillar.title}</h3>
                <p className="text-brand-700 mt-1.5 text-sm leading-relaxed text-pretty">
                  {pillar.description}
                </p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

import { LockKeyhole, QrCode, ShieldCheck, type LucideIcon } from 'lucide-react';
import type { ReactElement } from 'react';

interface Step {
  step: string;
  title: string;
  description: string;
  icon: LucideIcon;
}

const STEPS: Step[] = [
  {
    step: '01',
    title: 'Approach & consent',
    description:
      'A face-capture kiosk shows a QR code. The participant scans it into WhatsApp and gives explicit consent before anything is captured.',
    icon: QrCode,
  },
  {
    step: '02',
    title: 'Derived signals only',
    description:
      'The camera extracts rPPG signals in memory. Raw face frames are never stored — only derived measurements and quality metadata, encrypted at rest.',
    icon: ShieldCheck,
  },
  {
    step: '03',
    title: 'Private result',
    description:
      'The screening summary is delivered to the participant’s own phone behind a one-time passcode, framed as a non-diagnostic result.',
    icon: LockKeyhole,
  },
];

export function Gateway(): ReactElement {
  return (
    <section id="gateway" className="bg-brand-50 scroll-mt-24 px-4 py-20 sm:py-28">
      <div className="mx-auto max-w-6xl">
        <div className="max-w-2xl">
          <p className="text-brand-500 text-xs font-semibold tracking-wider uppercase">
            Mobile Clinic Gateway
          </p>
          <h2 className="text-brand-950 mt-2 text-3xl font-semibold tracking-tighter text-balance sm:text-4xl">
            Screening that meets people where they are.
          </h2>
          <p className="text-brand-700 mt-4 text-lg text-pretty">
            A public-kiosk rail that brings Victus screening to mobile clinics and community sites —
            no app to install, and privacy-minimal by design.
          </p>
        </div>

        <ol className="mt-12 grid gap-4 md:grid-cols-3">
          {STEPS.map((item) => (
            <li
              key={item.step}
              className="ring-brand-100 rounded-[var(--radius-card)] bg-white p-8 ring-1 ring-inset"
            >
              <div className="flex items-center justify-between">
                <span className="bg-brand-100 text-brand-700 flex size-11 items-center justify-center rounded-lg">
                  <item.icon aria-hidden="true" className="size-5" />
                </span>
                <span className="text-brand-400 font-mono text-xs tabular-nums">{item.step}</span>
              </div>
              <h3 className="text-brand-950 mt-6 text-lg font-semibold tracking-tight">
                {item.title}
              </h3>
              <p className="text-brand-700 mt-2 text-sm leading-relaxed text-pretty">
                {item.description}
              </p>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}

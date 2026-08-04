import { Ruler, ScanFace, type LucideIcon } from 'lucide-react';
import type { ReactElement } from 'react';

import { Badge } from '@victus/ui';

interface Pathway {
  eyebrow: string;
  title: string;
  icon: LucideIcon;
  body: string;
  points: string[];
}

const PATHWAYS: Pathway[] = [
  {
    eyebrow: 'Pathway A',
    title: '3B-Triage',
    icon: Ruler,
    body: 'Non-invasive screening for the risk of obesity, hypertension and diabetes from tape-measure and symptom inputs — no bloods, no clinic required.',
    points: [
      'An evidential model reports its own uncertainty and resolves each person to a GREEN / YELLOW / RED referral state.',
      'A domain-adversarial design makes community-health-worker measurements behave like clinical-grade ones by construction.',
      'Deterministic red-flag rules escalate danger signs regardless of what the model predicts.',
    ],
  },
  {
    eyebrow: 'Pathway B',
    title: 'Transdermal Optical Imaging',
    icon: ScanFace,
    body: 'A short face-video capture reads vital signs from skin colour changes (rPPG) using CHROM / POS pipelines — a camera, not a cuff.',
    points: [
      'Reports heart rate and respiratory rate, the outputs Victus validates today.',
      'A learned corrector removes skin-tone bias, tuned across Fitzpatrick III–VI.',
      'Further biomarkers stay out of scope until they have validated, single-camera ground truth.',
    ],
  },
];

export function Pathways(): ReactElement {
  return (
    <section id="pathways" className="scroll-mt-24 px-4 py-20 sm:py-28">
      <div className="mx-auto max-w-6xl">
        <div className="max-w-2xl">
          <h2 className="text-brand-950 text-3xl font-semibold tracking-tighter text-balance sm:text-4xl">
            Two screening pathways, one risk picture.
          </h2>
          <p className="text-brand-700 mt-4 text-lg text-pretty">
            Victus screens for non-communicable disease risk two complementary ways, each built to
            work in real Sub-Saharan settings — from a community health worker with a tape measure
            to a phone camera.
          </p>
          <div className="mt-5 flex flex-wrap gap-2" aria-label="Triage states">
            <Badge tone="green">GREEN — Low risk</Badge>
            <Badge tone="yellow">YELLOW — Audit required</Badge>
            <Badge tone="red">RED — Urgent referral</Badge>
          </div>
        </div>

        <div className="mt-12 grid gap-4 lg:grid-cols-2">
          {PATHWAYS.map((pathway) => (
            <div
              key={pathway.title}
              className="ring-brand-100 flex flex-col rounded-[var(--radius-card)] bg-white p-8 ring-1 ring-inset sm:p-10"
            >
              <div className="flex items-center gap-4">
                <span className="bg-brand-100 text-brand-700 flex size-11 items-center justify-center rounded-lg">
                  <pathway.icon aria-hidden="true" className="size-5" />
                </span>
                <div>
                  <p className="text-brand-500 text-xs font-semibold tracking-wider uppercase">
                    {pathway.eyebrow}
                  </p>
                  <h3 className="text-brand-950 text-lg font-semibold tracking-tight">
                    {pathway.title}
                  </h3>
                </div>
              </div>
              <p className="text-brand-700 mt-5 text-pretty">{pathway.body}</p>
              <ul className="mt-4 flex flex-col gap-3">
                {pathway.points.map((point) => (
                  <li key={point} className="flex gap-3 text-sm leading-relaxed">
                    <span
                      aria-hidden="true"
                      className="bg-brand-400 mt-2 size-1.5 shrink-0 rounded-full"
                    />
                    <span className="text-brand-700 text-pretty">{point}</span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

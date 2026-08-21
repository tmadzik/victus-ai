import type { ReactElement } from 'react';

interface Stage {
  step: string;
  title: string;
  description: string;
}

const STAGES: Stage[] = [
  {
    step: '01',
    title: 'Enrol & consent',
    description:
      'A participant gives granular consent and completes a short intake. Demographics are minimal, the patient ID is stored only as a salted hash, and enrolment is adults-only by design.',
  },
  {
    step: '02',
    title: 'Screen',
    description:
      'They are screened through Pathway A (3B-Triage), Pathway B (Transdermal Optical Imaging), or the Mobile Clinic Gateway kiosk — each resolving to a GREEN / YELLOW / RED state.',
  },
  {
    step: '03',
    title: 'Clinician review',
    description:
      'A clinician reviews the identified record against a longitudinal history of that participant’s previous assessments across both pathways.',
  },
  {
    step: '04',
    title: 'Refer or enrol',
    description:
      'The clinician raises a referral — with urgency and a tracked status — to a Victus facility or a partner or public clinic, or enrols the member in a structured wellness programme.',
  },
  {
    step: '05',
    title: 'Track & document',
    description:
      'Outcomes are followed over time and fed back to keep the models calibrated to local populations. The full record can be exported as a PDF for the care team.',
  },
];

export function ClosedLoop(): ReactElement {
  return (
    <section id="closed-loop" className="scroll-mt-24 px-4 py-20 sm:py-28">
      <div className="mx-auto max-w-4xl">
        <div className="max-w-2xl">
          <h2 className="text-brand-950 text-3xl font-semibold tracking-tighter text-balance sm:text-4xl">
            One closed loop, from screen to outcome.
          </h2>
          <p className="text-brand-700 mt-4 text-lg text-pretty">
            A screening result only matters if it changes what happens next. Victus connects screening to a
            clinician, a referral, and a tracked outcome — as one auditable pathway.
          </p>
        </div>

        <ol className="mt-12 flex flex-col">
          {STAGES.map((stage, i) => (
            <li key={stage.step} className="flex gap-5">
              <div className="flex flex-col items-center">
                <span className="bg-brand-100 text-brand-800 flex size-10 shrink-0 items-center justify-center rounded-full font-mono text-sm font-semibold tabular-nums">
                  {stage.step}
                </span>
                {i < STAGES.length - 1 ? (
                  <span aria-hidden="true" className="bg-brand-100 my-1 w-px flex-1" />
                ) : null}
              </div>
              <div className={i < STAGES.length - 1 ? 'pb-8' : ''}>
                <h3 className="text-brand-950 text-lg font-semibold tracking-tight">
                  {stage.title}
                </h3>
                <p className="text-brand-700 mt-1.5 text-pretty">{stage.description}</p>
              </div>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}

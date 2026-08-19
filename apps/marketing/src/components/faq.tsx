import type { ReactElement } from 'react';

interface QA {
  q: string;
  a: string;
}

const FAQS: QA[] = [
  {
    q: 'Do we need blood tests or lab equipment?',
    a: 'No. Screening runs on tape-measure readings and a short symptom questionnaire, or on a face-video capture from an ordinary phone or tablet camera. That is the whole point — it works where labs are far away or expensive.',
  },
  {
    q: 'Is a Victus result a diagnosis?',
    a: 'No. Victus is deployed today as a research demonstrator: results are screening signals that help a clinician decide who to see first, not clinical diagnoses. The platform enforces that framing in software until the models complete prospective clinical validation.',
  },
  {
    q: 'What does the camera actually measure?',
    a: 'Heart rate and respiratory rate — the two outputs Victus validates today. Anything without solid single-camera evidence, such as blood pressure from video, is deliberately not produced.',
  },
  {
    q: 'Does it work across different skin tones?',
    a: 'That is a first-class design requirement, not an afterthought. The camera pipeline is tuned across Fitzpatrick III–VI, and agreement is measured and reported by skin tone as a precondition to any clinical claim.',
  },
  {
    q: 'How is personal health data protected?',
    a: 'Consent is captured before any screening, identifiers are minimised, every access to an identified record is logged, and there is a right-to-erasure path. Each deployment honours its local regime — POPIA in South Africa, the NDPA in Nigeria, the Cyber & Data Protection Act in Zimbabwe — and keeps data in-country.',
  },
  {
    q: 'What does a pilot involve?',
    a: 'We scope it with you: which sites, which population, which pathway, and what success looks like. Each pilot is its own jurisdiction-aware deployment. Book a demo and we will walk you through it.',
  },
];

export function Faq(): ReactElement {
  return (
    <section id="faq" className="bg-brand-50 scroll-mt-24 px-4 py-20 sm:py-28">
      <div className="mx-auto max-w-3xl">
        <h2 className="text-brand-950 text-3xl font-semibold tracking-tighter text-balance sm:text-4xl">
          Questions we get asked.
        </h2>

        <div className="mt-10 flex flex-col gap-3">
          {FAQS.map((item) => (
            <details
              key={item.q}
              className="ring-brand-100 group rounded-[var(--radius-card)] bg-white px-6 ring-1 ring-inset open:shadow-sm"
            >
              <summary className="text-brand-950 flex cursor-pointer list-none items-center justify-between gap-4 py-5 font-semibold tracking-tight marker:content-none focus-visible:outline-none">
                {item.q}
                <span
                  aria-hidden="true"
                  className="text-brand-500 shrink-0 text-xl transition-transform group-open:rotate-45"
                >
                  +
                </span>
              </summary>
              <p className="text-brand-700 pb-5 leading-relaxed text-pretty">{item.a}</p>
            </details>
          ))}
        </div>
      </div>
    </section>
  );
}

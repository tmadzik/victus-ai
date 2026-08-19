import type { ReactElement } from 'react';

import { Button } from '@victus/ui';

export function Hero(): ReactElement {
  return (
    <section id="top" className="relative isolate overflow-hidden">
      {/* Pre-sized WebP variants (13–48 KB) rather than next/image, so the
          cPanel bundle stays free of the sharp native binary. */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src="/hero-screening-1920.webp"
        srcSet="/hero-screening-800.webp 800w, /hero-screening-1280.webp 1280w, /hero-screening-1920.webp 1920w"
        sizes="100vw"
        alt=""
        aria-hidden="true"
        fetchPriority="high"
        className="absolute inset-0 -z-20 size-full object-cover object-center sm:object-[62%_center]"
      />
      {/* Two-layer scrim: a flat wash guarantees a contrast floor, the
          directional gradient keeps the subject readable on the right. */}
      <div aria-hidden="true" className="bg-brand-950/25 absolute inset-0 -z-10" />
      <div
        aria-hidden="true"
        className="from-brand-950 via-brand-950/80 to-brand-950/70 absolute inset-0 -z-10 bg-gradient-to-b from-10% via-55% sm:bg-gradient-to-r sm:via-50% sm:to-transparent"
      />

      <div className="mx-auto max-w-6xl px-4 pt-36 pb-20 sm:pt-44 sm:pb-28 lg:pt-52 lg:pb-36">
        <div className="max-w-xl">
          <p className="text-brand-200 text-sm font-medium tracking-wide">
            Non-communicable disease screening, built for Africa
          </p>
          <h1 className="mt-4 text-4xl font-semibold tracking-tighter text-balance text-white sm:text-5xl lg:text-6xl">
            Predict NCD risk. Prevent avoidable claims.
          </h1>
          <p className="mt-5 text-lg leading-relaxed text-pretty text-white/85">
            Screen people for diabetes, hypertension and obesity risk with nothing more than a tape
            measure or a phone camera — then route them to care and track what actually changes.
          </p>

          <div className="mt-8 flex flex-wrap items-center gap-4">
            <Button asChild size="lg" className="rounded-full">
              <a href="#book-demo">Book a Demo</a>
            </Button>
            <Button
              asChild
              size="lg"
              variant="ghost"
              className="rounded-full text-white hover:bg-white/10 hover:text-white active:bg-white/15"
            >
              <a href="#how-it-works">See how it works</a>
            </Button>
          </div>

          <p className="mt-8 flex items-center gap-2 text-sm text-white/75">
            <span aria-hidden="true" className="bg-brand-400 size-1.5 rounded-full" />
            Research demonstrator · preparing pilots in Zimbabwe and Nigeria
          </p>
        </div>
      </div>
    </section>
  );
}

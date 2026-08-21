import type { LucideIcon } from 'lucide-react';
import type { Route } from 'next';
import Link from 'next/link';
import type { ReactElement } from 'react';

import { Button } from '@victus/ui';

import { SiteFooter } from '@/components/site-footer';
import { SiteHeader } from '@/components/site-header';

export interface RoleLandingProps {
  eyebrow: string;
  title: string;
  intro: string;
  features: { title: string; description: string; icon: LucideIcon }[];
  /** Primary action — leaves this domain for the application. */
  primary: { label: string; href: string };
  /** How someone without access gets it. Always the demo form. */
  secondary: { label: string; note: string };
}

export function RoleLanding({
  eyebrow,
  title,
  intro,
  features,
  primary,
  secondary,
}: RoleLandingProps): ReactElement {
  return (
    <>
      <SiteHeader />
      <main>
        <section className="px-4 pt-36 pb-16 sm:pt-44">
          <div className="mx-auto max-w-3xl">
            <p className="text-brand-500 text-xs font-semibold tracking-wider uppercase">
              {eyebrow}
            </p>
            <h1 className="text-brand-950 mt-2 text-4xl font-semibold tracking-tighter text-balance sm:text-5xl">
              {title}
            </h1>
            <p className="text-brand-700 mt-4 text-lg leading-relaxed text-pretty">{intro}</p>

            <div className="mt-8 flex flex-wrap items-center gap-4">
              <Button asChild size="lg" className="rounded-full">
                <a href={primary.href}>{primary.label}</a>
              </Button>
              <Button asChild size="lg" variant="outline" className="rounded-full">
                <Link href={'/#book-demo' as Route}>{secondary.label}</Link>
              </Button>
            </div>
            <p className="text-grey-500 mt-4 text-sm text-pretty">{secondary.note}</p>
          </div>
        </section>

        <section className="bg-brand-50 px-4 py-20 sm:py-24">
          <div className="mx-auto grid max-w-5xl gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {features.map((feature) => (
              <div
                key={feature.title}
                className="ring-brand-100 rounded-[var(--radius-card)] bg-white p-7 ring-1 ring-inset"
              >
                <span className="bg-brand-100 text-brand-700 flex size-11 items-center justify-center rounded-xl">
                  <feature.icon aria-hidden="true" className="size-5" />
                </span>
                <h2 className="text-brand-950 mt-5 font-semibold tracking-tight">
                  {feature.title}
                </h2>
                <p className="text-brand-700 mt-1.5 text-sm leading-relaxed text-pretty">
                  {feature.description}
                </p>
              </div>
            ))}
          </div>
        </section>
      </main>
      <SiteFooter />
    </>
  );
}

import type { ReactElement, ReactNode } from 'react';

import { SiteFooter } from '@/components/site-footer';
import { SiteHeader } from '@/components/site-header';

export function LegalPage({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}): ReactElement {
  return (
    <>
      <SiteHeader />
      <main className="px-4 pt-32 pb-20 sm:pt-40">
        <article className="mx-auto max-w-2xl">
          <h1 className="text-brand-950 text-3xl font-semibold tracking-tighter text-balance sm:text-4xl">
            {title}
          </h1>
          <div className="text-brand-700 mt-6 flex flex-col gap-4 leading-relaxed text-pretty">
            {children}
          </div>
        </article>
      </main>
      <SiteFooter />
    </>
  );
}

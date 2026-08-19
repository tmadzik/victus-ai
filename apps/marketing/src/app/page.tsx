import type { ReactElement } from 'react';

import { AudienceRouter } from '@/components/audience-router';
import { Efficacy } from '@/components/efficacy';
import { Faq } from '@/components/faq';
import { Gateway } from '@/components/gateway';
import { Hero } from '@/components/hero';
import { HowItWorks } from '@/components/how-it-works';
import { LeadCapture } from '@/components/lead-capture';
import { SiteFooter } from '@/components/site-footer';
import { SiteHeader } from '@/components/site-header';
import { Trust } from '@/components/trust';
import { TrustStrip } from '@/components/trust-strip';
import { ValidationStatus } from '@/components/validation-status';

export default function HomePage(): ReactElement {
  return (
    <>
      <SiteHeader />
      <main>
        <Hero />
        <TrustStrip />
        <AudienceRouter />
        <HowItWorks />
        <Gateway />
        <Trust />
        <ValidationStatus />
        <Efficacy />
        <Faq />
        <LeadCapture />
      </main>
      <SiteFooter />
    </>
  );
}

import type { ReactElement } from 'react';

import { ClinicalApproach } from '@/components/clinical-approach';
import { Efficacy } from '@/components/efficacy';
import { Hero } from '@/components/hero';
import { LeadCapture } from '@/components/lead-capture';
import { Mechanism } from '@/components/mechanism';
import { PhysicalNetwork } from '@/components/physical-network';
import { SiteFooter } from '@/components/site-footer';
import { SiteHeader } from '@/components/site-header';

export default function HomePage(): ReactElement {
  return (
    <>
      <SiteHeader />
      <main>
        <Hero />
        <Mechanism />
        <PhysicalNetwork />
        <ClinicalApproach />
        <Efficacy />
        <LeadCapture />
      </main>
      <SiteFooter />
    </>
  );
}

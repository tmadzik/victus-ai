import type { ReactElement } from 'react';

import { Efficacy } from '@/components/efficacy';
import { Gateway } from '@/components/gateway';
import { Hero } from '@/components/hero';
import { LeadCapture } from '@/components/lead-capture';
import { Mechanism } from '@/components/mechanism';
import { Pathways } from '@/components/pathways';
import { PhysicalNetwork } from '@/components/physical-network';
import { SiteFooter } from '@/components/site-footer';
import { SiteHeader } from '@/components/site-header';
import { Trust } from '@/components/trust';
import { ValidationStatus } from '@/components/validation-status';

export default function HomePage(): ReactElement {
  return (
    <>
      <SiteHeader />
      <main>
        <Hero />
        <Pathways />
        <Mechanism />
        <Gateway />
        <PhysicalNetwork />
        <Trust />
        <ValidationStatus />
        <Efficacy />
        <LeadCapture />
      </main>
      <SiteFooter />
    </>
  );
}

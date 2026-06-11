import type { Metadata } from 'next';
import type { ReactElement } from 'react';

import { LegalPage } from '@/components/legal-page';
import { LEGAL_NAME } from '@/lib/site';

export const metadata: Metadata = {
  title: 'Privacy Policy',
  description: `How ${LEGAL_NAME} collects, processes and protects personal information under POPIA.`,
};

export default function Page(): ReactElement {
  return (
    <LegalPage title="Privacy Policy">
      <p>
        {LEGAL_NAME} processes personal information in accordance with the Protection of Personal
        Information Act, 2013 (POPIA). The full policy — covering what we collect, why, how long we
        retain it, and how to exercise your rights as a data subject — is being finalised and will
        be published here ahead of platform launch.
      </p>
      <p>
        Email addresses submitted through the pilot request form are used solely to contact you
        about the Victus platform, on the basis of the consent you give when submitting the form.
      </p>
      <p>
        To exercise your rights or ask questions, contact our information officer at{' '}
        <a href="mailto:privacy@victusdata.com" className="underline underline-offset-2">
          privacy@victusdata.com
        </a>
        .
      </p>
    </LegalPage>
  );
}

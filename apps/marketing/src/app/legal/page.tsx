import type { Metadata } from 'next';
import type { ReactElement } from 'react';

import { LegalPage } from '@/components/legal-page';
import { LEGAL_NAME } from '@/lib/site';

export const metadata: Metadata = {
  title: 'Legal',
  description: `Legal notices and terms for ${LEGAL_NAME}.`,
};

export default function Page(): ReactElement {
  return (
    <LegalPage title="Legal">
      <p>
        Terms of service and legal notices for {LEGAL_NAME} are being finalised and will be
        published here ahead of platform launch.
      </p>
      <p>
        For legal enquiries in the interim, contact us at{' '}
        <a href="mailto:legal@victusdata.com" className="underline underline-offset-2">
          legal@victusdata.com
        </a>
        .
      </p>
    </LegalPage>
  );
}

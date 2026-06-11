import type { Metadata } from 'next';
import type { ReactElement } from 'react';

import { LegalPage } from '@/components/legal-page';
import { LEGAL_NAME } from '@/lib/site';

export const metadata: Metadata = {
  title: 'PAIA Manual',
  description: `Promotion of Access to Information Act manual for ${LEGAL_NAME}.`,
};

export default function Page(): ReactElement {
  return (
    <LegalPage title="PAIA Manual">
      <p>
        The {LEGAL_NAME} manual prepared in terms of section 51 of the Promotion of Access to
        Information Act, 2000 (PAIA) will be published here.
      </p>
      <p>
        Requests for access to records may be directed to our information officer at{' '}
        <a href="mailto:privacy@victusdata.com" className="underline underline-offset-2">
          privacy@victusdata.com
        </a>
        .
      </p>
    </LegalPage>
  );
}

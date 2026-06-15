import type { Metadata } from 'next';
import type { ReactElement } from 'react';

import { LegalPage } from '@/components/legal-page';
import { LEGAL_NAME } from '@/lib/site';

// DRAFT — prepared for legal review before launch. Confirm the company
// registration details, record categories and fee schedule with counsel, and
// update the "Last updated" date on sign-off.

export const metadata: Metadata = {
  title: 'PAIA Manual',
  description: `Promotion of Access to Information Act manual for ${LEGAL_NAME}.`,
};

const heading = 'text-brand-950 mt-4 text-xl font-semibold tracking-tight';

export default function Page(): ReactElement {
  return (
    <LegalPage title="PAIA Manual">
      <p className="text-grey-500 text-sm">Last updated: 15 June 2026</p>

      <p>
        This manual is published by {LEGAL_NAME} in terms of section 51 of the Promotion of Access
        to Information Act, 2000 (PAIA). It describes the records held by {LEGAL_NAME} and how to
        request access to them.
      </p>

      <h2 className={heading}>Responsible party and Information Officer</h2>
      <p>
        Requests and enquiries under PAIA may be directed to our Information Officer at{' '}
        <a href="mailto:privacy@victusdata.com" className="underline underline-offset-2">
          privacy@victusdata.com
        </a>
        . Full company registration and contact particulars are available on request.
      </p>

      <h2 className={heading}>The PAIA Guide</h2>
      <p>
        The Information Regulator has compiled a guide on how to use PAIA. It is available from the
        Information Regulator &mdash; enquiries:{' '}
        <a href="mailto:enquiries@inforegulator.org.za" className="underline underline-offset-2">
          enquiries@inforegulator.org.za
        </a>
        .
      </p>

      <h2 className={heading}>Records held by Victus</h2>
      <p>
        The following broad categories of records may be held. Access to a record is subject to the
        grounds for refusal set out in PAIA and may require protection of third-party information.
      </p>
      <ul className="flex list-disc flex-col gap-2 pl-5">
        <li>Company and statutory records (incorporation, governance and regulatory records);</li>
        <li>Financial and tax records;</li>
        <li>Personnel and employment records;</li>
        <li>Contracts with suppliers, operators and partners;</li>
        <li>
          Customer, enquiry and marketing records, including pilot requests submitted through the
          Site;
        </li>
        <li>Information technology, security and website operation records.</li>
      </ul>

      <h2 className={heading}>Records held under other legislation</h2>
      <p>
        Certain records are kept in accordance with other laws, which may include the Companies Act,
        the Income Tax Act and Value-Added Tax Act, the Labour Relations Act and Basic Conditions of
        Employment Act, and POPIA.
      </p>

      <h2 className={heading}>How to request access</h2>
      <p>
        A requester must complete the prescribed request form and submit it to the Information
        Officer at the address above, identifying the record sought and the form of access required.
        A prescribed request fee and access fee may be payable in accordance with the PAIA
        regulations. We will respond within the timeframes set by PAIA.
      </p>

      <h2 className={heading}>Grounds for refusal</h2>
      <p>
        Access to a record may be refused on the grounds set out in Chapter 4 of PAIA, including the
        mandatory protection of the privacy of third parties, commercial information of third
        parties, and other interests protected by the Act.
      </p>

      <h2 className={heading}>Remedies</h2>
      <p>
        If a request is refused, the requester may lodge a complaint with the Information Regulator
        or apply to a court, as provided for in PAIA. Complaints to the Information Regulator:{' '}
        <a
          href="mailto:PAIAComplaints@inforegulator.org.za"
          className="underline underline-offset-2"
        >
          PAIAComplaints@inforegulator.org.za
        </a>
        .
      </p>

      <h2 className={heading}>Availability of this manual</h2>
      <p>
        This manual is available on this page and on request from the Information Officer. We may
        update it from time to time; the revision date is shown above.
      </p>
    </LegalPage>
  );
}

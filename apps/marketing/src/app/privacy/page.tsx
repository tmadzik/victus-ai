import type { Metadata } from 'next';
import type { ReactElement } from 'react';

import { LegalPage } from '@/components/legal-page';
import { LEGAL_NAME } from '@/lib/site';

// DRAFT — prepared for legal review before launch. Confirm processor list,
// cross-border transfers, and retention periods with counsel and update the
// "Last updated" date on sign-off.

export const metadata: Metadata = {
  title: 'Privacy Policy',
  description: `How ${LEGAL_NAME} collects, processes and protects personal information under POPIA.`,
};

const heading = 'text-brand-950 mt-4 text-xl font-semibold tracking-tight';

export default function Page(): ReactElement {
  return (
    <LegalPage title="Privacy Policy">
      <p className="text-grey-500 text-sm">Last updated: 15 June 2026</p>

      <p>
        This Privacy Policy explains how {LEGAL_NAME} (&ldquo;Victus&rdquo;, &ldquo;we&rdquo;,
        &ldquo;us&rdquo;) collects, uses, shares and protects personal information when you visit{' '}
        www.victusdata.com (the &ldquo;Site&rdquo;) or submit a pilot request. We process personal
        information in accordance with the Protection of Personal Information Act, 2013 (POPIA). The
        Victus platform (app.victusdata.com) is governed by a separate notice provided within that
        environment.
      </p>

      <h2 className={heading}>Responsible party and Information Officer</h2>
      <p>
        {LEGAL_NAME} is the responsible party for the personal information described here. You can
        reach our Information Officer at{' '}
        <a href="mailto:privacy@victusdata.com" className="underline underline-offset-2">
          privacy@victusdata.com
        </a>
        .
      </p>

      <h2 className={heading}>Personal information we collect</h2>
      <ul className="flex list-disc flex-col gap-2 pl-5">
        <li>
          <strong>Information you give us.</strong> When you submit the pilot request form, we
          collect the work email address you provide.
        </li>
        <li>
          <strong>Information collected automatically.</strong> Our hosting infrastructure records
          standard server logs (such as IP address, browser type and request timestamps) for
          security and to operate the Site. The Site does not use advertising cookies or third-party
          tracking.
        </li>
      </ul>

      <h2 className={heading}>Why we process it, and our lawful basis</h2>
      <ul className="flex list-disc flex-col gap-2 pl-5">
        <li>
          To respond to your pilot request and contact you about the Victus platform — on the basis
          of your consent, which you give when you submit the form, and our legitimate interest in
          responding to enquiries.
        </li>
        <li>
          To secure, maintain and improve the Site, and to detect and prevent abuse — on the basis
          of our legitimate interest and applicable legal obligations.
        </li>
      </ul>

      <h2 className={heading}>Consent and direct communications</h2>
      <p>
        By submitting the form you consent to us contacting you about the Victus platform. You may
        withdraw your consent at any time by emailing{' '}
        <a href="mailto:privacy@victusdata.com" className="underline underline-offset-2">
          privacy@victusdata.com
        </a>
        . Withdrawing consent does not affect processing carried out before the withdrawal.
      </p>

      <h2 className={heading}>Who we share it with</h2>
      <p>
        We share personal information only with operators (processors) that help us run the Site and
        respond to you — for example our email delivery provider and, where used, our
        customer-relationship management system. These operators process personal information on our
        instructions and under a duty of confidentiality. We do not sell your personal information.
      </p>

      <h2 className={heading}>Cross-border transfers</h2>
      <p>
        Where an operator processes personal information outside South Africa, we take reasonable
        steps to ensure it receives a level of protection consistent with POPIA, as required by
        section 72.
      </p>

      <h2 className={heading}>Retention</h2>
      <p>
        We keep the information you submit only for as long as necessary to act on your request and
        to maintain a record of your consent, after which it is deleted or de-identified, unless a
        longer period is required or permitted by law.
      </p>

      <h2 className={heading}>How we protect it</h2>
      <p>
        We apply appropriate technical and organisational measures to safeguard personal
        information, including encryption in transit (HTTPS) and access controls. No method of
        transmission or storage is completely secure, but we work to protect your information and to
        address incidents promptly.
      </p>

      <h2 className={heading}>Your rights</h2>
      <p>Subject to POPIA, you have the right to:</p>
      <ul className="flex list-disc flex-col gap-2 pl-5">
        <li>request access to the personal information we hold about you;</li>
        <li>request that we correct or delete personal information;</li>
        <li>object to the processing of your personal information;</li>
        <li>withdraw any consent you have given; and</li>
        <li>lodge a complaint with the Information Regulator.</li>
      </ul>
      <p>
        To exercise any of these rights, contact{' '}
        <a href="mailto:privacy@victusdata.com" className="underline underline-offset-2">
          privacy@victusdata.com
        </a>
        .
      </p>

      <h2 className={heading}>Information Regulator</h2>
      <p>
        You may lodge a complaint with the Information Regulator (South Africa). Enquiries:{' '}
        <a href="mailto:enquiries@inforegulator.org.za" className="underline underline-offset-2">
          enquiries@inforegulator.org.za
        </a>
        . Complaints:{' '}
        <a
          href="mailto:POPIAComplaints@inforegulator.org.za"
          className="underline underline-offset-2"
        >
          POPIAComplaints@inforegulator.org.za
        </a>
        .
      </p>

      <h2 className={heading}>Changes to this policy</h2>
      <p>
        We may update this Privacy Policy from time to time. The current version is always available
        on this page, with the revision date shown above.
      </p>
    </LegalPage>
  );
}

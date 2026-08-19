import { LockKeyhole, MonitorSmartphone, QrCode, ShieldCheck, Timer, Truck } from 'lucide-react';
import type { Metadata } from 'next';
import type { ReactElement } from 'react';

import { RoleLanding } from '@/components/role-landing';
import { APP_URL } from '@/lib/site';

export const metadata: Metadata = {
  title: 'For community & mobile clinics',
  description:
    'The Victus Mobile Clinic Gateway: a self-service screening kiosk for community sites and mobile clinics — consent first, derived signals only, private results to the participant’s phone.',
  alternates: { canonical: '/for/kiosk' },
};

export default function KioskPage(): ReactElement {
  return (
    <RoleLanding
      eyebrow="For community & mobile clinics"
      title="Bring screening to where people already are."
      intro="The Mobile Clinic Gateway turns a tablet at a community site into a self-service screening station — nothing for people to install, consent taken before anything is captured, and results delivered privately to their own phone."
      features={[
        {
          title: 'Nothing to install',
          description:
            'A participant walks up, scans a QR code with the phone already in their pocket, and starts. No app, no account, no queue at a desk.',
          icon: QrCode,
        },
        {
          title: 'Consent before capture',
          description:
            'The conversation starts on WhatsApp and explicit consent is taken there — before the camera records anything at all.',
          icon: ShieldCheck,
        },
        {
          title: 'Derived signals only',
          description:
            'The capture is processed in memory and only derived measurements and quality metadata are kept, encrypted at rest. Raw face frames are never stored.',
          icon: MonitorSmartphone,
        },
        {
          title: 'Private results',
          description:
            'The screening summary goes to the participant’s own phone behind a one-time passcode — never displayed on the shared kiosk screen.',
          icon: LockKeyhole,
        },
        {
          title: 'Nothing left behind',
          description:
            'Sessions clear themselves after inactivity and abandoned ones expire automatically, so the next person never sees the last person’s data.',
          icon: Timer,
        },
        {
          title: 'Authorised as a device',
          description:
            'Each terminal is provisioned with its own device credentials by us — there is no personal login to share, lose, or leave signed in.',
          icon: Truck,
        },
      ]}
      primary={{ label: 'Open kiosk mode', href: `${APP_URL}/kiosk` }}
      secondary={{
        label: 'Request a kiosk',
        note: 'Kiosks are authorised per device, not per person — we provision each terminal with you before it goes live.',
      }}
    />
  );
}

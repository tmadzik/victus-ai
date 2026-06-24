import { KioskClient } from './kiosk-client';

// Always dynamic: this terminal surface holds no cacheable content.
export const dynamic = 'force-dynamic';

export default function KioskPage(): React.ReactElement {
  return <KioskClient />;
}

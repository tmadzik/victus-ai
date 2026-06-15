import type { ReactElement } from 'react';

import { TriageState } from '@victus/contracts';
import { Badge, type BadgeProps } from '@victus/ui';

export { Badge, badgeVariants, type BadgeProps } from '@victus/ui';

const STATE_TONE: Record<TriageState, NonNullable<BadgeProps['tone']>> = {
  [TriageState.GREEN]: 'green',
  [TriageState.YELLOW]: 'yellow',
  [TriageState.RED]: 'red',
};

const STATE_LABEL: Record<TriageState, string> = {
  [TriageState.GREEN]: 'Low risk',
  [TriageState.YELLOW]: 'Uncertain — audit required',
  [TriageState.RED]: 'Urgent clinical referral',
};

export function TriageStateBadge({ state }: { state: TriageState }): ReactElement {
  return (
    <Badge tone={STATE_TONE[state]} aria-label={`Triage state: ${STATE_LABEL[state]}`}>
      <span aria-hidden="true">{state}</span>
      <span className="sr-only">{STATE_LABEL[state]}</span>
    </Badge>
  );
}

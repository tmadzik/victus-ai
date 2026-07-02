'use server';

import { redirect } from 'next/navigation';

import type { EnrollmentRequest } from '@victus/contracts';

import { ApiError, apiClient } from '@/lib/api-client';
import { auth } from '@/lib/auth';

export type EnrollState = { ok: boolean; error?: string };

/**
 * Capture the participant's enrollment (identified demographics + consent) for
 * the signed-in user, then send them into the platform. Consent to both pathways
 * is mandatory; the API re-validates everything server-side.
 */
export async function enrollAction(
  _prev: EnrollState,
  formData: FormData,
): Promise<EnrollState> {
  const session = await auth();
  if (!session?.user) {
    return { ok: false, error: 'Your session has expired — please sign in again.' };
  }

  const race = String(formData.get('race_ethnicity') ?? '').trim();
  const payload = {
    full_name: String(formData.get('full_name') ?? '').trim(),
    email: String(formData.get('email') ?? '').trim(),
    patient_id: String(formData.get('patient_id') ?? '').trim(),
    age_range: String(formData.get('age_range') ?? ''),
    biological_sex: String(formData.get('biological_sex') ?? ''),
    region: String(formData.get('region') ?? ''),
    race_ethnicity: race || null,
    consent_triage: formData.get('consent_triage') === 'on',
    consent_toi_imaging: formData.get('consent_toi_imaging') === 'on',
    consent_research: formData.get('consent_research') === 'on',
  } as EnrollmentRequest;

  if (!payload.consent_triage || !payload.consent_toi_imaging) {
    return {
      ok: false,
      error:
        'You must consent to both the triage and TOI-imaging pathways to continue.',
    };
  }

  try {
    await apiClient.enroll(session.accessToken, payload);
  } catch (err) {
    if (err instanceof ApiError) return { ok: false, error: err.message };
    return { ok: false, error: 'Could not complete enrollment. Please try again.' };
  }

  redirect('/dashboard');
}

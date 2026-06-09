'use client';

import Link from 'next/link';
import { useActionState } from 'react';

import { UserRole } from '@victus/contracts';

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { registerAction, type ActionState } from '@/server/auth-actions';

const initialState: ActionState = { ok: true };

const SELF_REGISTRABLE_ROLES: { value: UserRole; label: string }[] = [
  { value: UserRole.PATIENT, label: 'Patient' },
  { value: UserRole.CHW, label: 'Community Health Worker' },
  { value: UserRole.CLINICIAN, label: 'Clinician' },
];

export function RegisterForm(): React.ReactElement {
  const [state, formAction, isPending] = useActionState(registerAction, initialState);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Create account</CardTitle>
        <CardDescription>
          A 12+ character password with upper, lower, and digit is required.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {state.error ? (
          <Alert tone="danger" className="mb-4">
            <AlertTitle>Registration failed</AlertTitle>
            <AlertDescription>{state.error}</AlertDescription>
          </Alert>
        ) : null}

        <form action={formAction} className="space-y-4" noValidate>
          <div className="space-y-1.5">
            <Label htmlFor="full_name">Full name</Label>
            <Input
              id="full_name"
              name="full_name"
              type="text"
              autoComplete="name"
              required
              minLength={2}
              aria-invalid={Boolean(state.fieldErrors?.full_name)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="email">Email</Label>
            <Input
              id="email"
              name="email"
              type="email"
              autoComplete="email"
              required
              aria-invalid={Boolean(state.fieldErrors?.email)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="password">Password</Label>
            <Input
              id="password"
              name="password"
              type="password"
              autoComplete="new-password"
              required
              minLength={12}
              aria-invalid={Boolean(state.fieldErrors?.password)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="role">I am a…</Label>
            <select
              id="role"
              name="role"
              required
              defaultValue={UserRole.PATIENT}
              className="flex h-10 w-full rounded-[var(--radius-control)] border border-brand-200 bg-white px-3 py-2 text-sm text-brand-950 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2"
            >
              {SELF_REGISTRABLE_ROLES.map((r) => (
                <option key={r.value} value={r.value}>
                  {r.label}
                </option>
              ))}
            </select>
          </div>

          <Button type="submit" size="lg" className="w-full" disabled={isPending}>
            {isPending ? 'Creating account…' : 'Create account'}
          </Button>
        </form>

        <p className="mt-6 text-center text-sm text-brand-700">
          Already registered?{' '}
          <Link href="/login" className="font-semibold text-brand-900 underline">
            Sign in
          </Link>
        </p>
      </CardContent>
    </Card>
  );
}

'use client';

import Link from 'next/link';
import { useActionState } from 'react';

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { registerAction, type ActionState } from '@/server/auth-actions';

const initialState: ActionState = { ok: true };

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
          <p className="text-sm text-brand-700">
            Creating an account registers you as a participant. Clinician and community-health-worker
            access is arranged by your organisation.
          </p>

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

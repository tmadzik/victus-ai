'use client';

import Link from 'next/link';
import { useActionState } from 'react';

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { loginAction, type ActionState } from '@/server/auth-actions';

const initialState: ActionState = { ok: true };

export function LoginForm({
  initialMessage,
}: {
  initialMessage: string | null;
}): React.ReactElement {
  const [state, formAction, isPending] = useActionState(loginAction, initialState);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Sign in</CardTitle>
        <CardDescription>
          Access your Victus AI account to begin a triage or TOI session.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {initialMessage ? (
          <Alert tone="warning" className="mb-4">
            <AlertTitle>Session expired</AlertTitle>
            <AlertDescription>{initialMessage}</AlertDescription>
          </Alert>
        ) : null}

        {state.error ? (
          <Alert tone="danger" className="mb-4">
            <AlertTitle>Sign-in failed</AlertTitle>
            <AlertDescription>{state.error}</AlertDescription>
          </Alert>
        ) : null}

        <form action={formAction} className="space-y-4" noValidate>
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
              autoComplete="current-password"
              required
              minLength={1}
              aria-invalid={Boolean(state.fieldErrors?.password)}
            />
          </div>

          <Button type="submit" size="lg" className="w-full" disabled={isPending}>
            {isPending ? 'Signing in…' : 'Sign in'}
          </Button>
        </form>

        <p className="mt-6 text-center text-sm text-brand-700">
          New to Victus AI?{' '}
          <Link href="/register" className="font-semibold text-brand-900 underline">
            Create an account
          </Link>
        </p>
      </CardContent>
    </Card>
  );
}

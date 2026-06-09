'use server';

import { AuthError } from 'next-auth';
import { redirect } from 'next/navigation';

import { LoginRequestSchema, RegisterRequestSchema } from '@victus/contracts';

import { apiClient, ApiError } from '@/lib/api-client';
import { signIn, signOut } from '@/lib/auth';

export interface ActionState {
  ok: boolean;
  error?: string;
  fieldErrors?: Record<string, string[]>;
}

const GENERIC_AUTH_ERROR = 'Invalid email or password.';

export async function loginAction(_: ActionState, formData: FormData): Promise<ActionState> {
  const parsed = LoginRequestSchema.safeParse({
    email: formData.get('email'),
    password: formData.get('password'),
  });
  if (!parsed.success) {
    return {
      ok: false,
      error: 'Please correct the highlighted fields.',
      fieldErrors: parsed.error.flatten().fieldErrors,
    };
  }

  try {
    await signIn('credentials', {
      email: parsed.data.email,
      password: parsed.data.password,
      redirect: false,
    });
  } catch (err) {
    if (err instanceof AuthError) {
      return { ok: false, error: GENERIC_AUTH_ERROR };
    }
    throw err;
  }

  redirect('/dashboard');
}

export async function registerAction(_: ActionState, formData: FormData): Promise<ActionState> {
  const parsed = RegisterRequestSchema.safeParse({
    email: formData.get('email'),
    password: formData.get('password'),
    full_name: formData.get('full_name'),
    role: formData.get('role') ?? 'PATIENT',
  });
  if (!parsed.success) {
    return {
      ok: false,
      error: 'Please correct the highlighted fields.',
      fieldErrors: parsed.error.flatten().fieldErrors,
    };
  }

  try {
    await apiClient.register(parsed.data);
  } catch (err) {
    if (err instanceof ApiError) {
      if (err.code === 'email_already_registered') {
        return { ok: false, error: 'An account with this email already exists.' };
      }
      return { ok: false, error: err.message };
    }
    throw err;
  }

  try {
    await signIn('credentials', {
      email: parsed.data.email,
      password: parsed.data.password,
      redirect: false,
    });
  } catch (err) {
    if (err instanceof AuthError) {
      return { ok: false, error: 'Account created — please sign in to continue.' };
    }
    throw err;
  }

  redirect('/dashboard');
}

export async function logoutAction(): Promise<void> {
  await signOut({ redirect: false });
  redirect('/login');
}

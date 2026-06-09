import type { Metadata } from 'next';

import { RegisterForm } from './register-form';

export const metadata: Metadata = { title: 'Create account' };

export default function RegisterPage(): React.ReactElement {
  return <RegisterForm />;
}

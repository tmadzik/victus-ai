import Link from 'next/link';
import { redirect } from 'next/navigation';

import { Button } from '@/components/ui/button';
import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { auth } from '@/lib/auth';

export default async function HomePage(): Promise<React.ReactElement> {
  const session = await auth();
  if (session?.user) {
    redirect('/dashboard');
  }

  return (
    <main className="mx-auto flex min-h-dvh max-w-5xl flex-col items-center justify-center gap-10 px-6 py-12">
      <header className="text-center">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src="/victus-logo.svg"
          alt="Victus AI"
          className="mx-auto h-20 w-auto"
        />
        <h1 className="mt-6 text-balance text-4xl font-semibold tracking-tight text-brand-950 sm:text-5xl">
          Precision NCD screening, calibrated for African contexts.
        </h1>
        <p className="mx-auto mt-4 max-w-2xl text-balance text-brand-700">
          Dual-pathway risk prediction with explicit uncertainty quantification and
          melanin-robust transdermal optical imaging.
        </p>
      </header>

      <section className="grid w-full gap-6 sm:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>3B-Triage</CardTitle>
            <CardDescription>
              Evidential Deep Learning over tape-measure + symptom inputs. Surfaces
              epistemic and aleatoric uncertainty as a strict GREEN / YELLOW / RED
              referral state.
            </CardDescription>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>TOI Biomarkers</CardTitle>
            <CardDescription>
              Camera-based rPPG with CHROM / POS chrominance pipelines tuned for
              Fitzpatrick III–VI skin types. HR, RR, BP, HRV, stress and CVD risk.
            </CardDescription>
          </CardHeader>
        </Card>
      </section>

      <div className="flex items-center gap-4">
        <Button asChild size="lg">
          <Link href="/login">Sign in</Link>
        </Button>
        <Button asChild size="lg" variant="outline">
          <Link href="/register">Create account</Link>
        </Button>
      </div>
    </main>
  );
}

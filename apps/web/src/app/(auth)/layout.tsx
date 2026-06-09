import Link from 'next/link';

export default function AuthLayout({
  children,
}: {
  children: React.ReactNode;
}): React.ReactElement {
  return (
    <main className="grid min-h-dvh place-items-center bg-brand-50 px-4 py-12">
      <div className="w-full max-w-md">
        <Link href="/" className="block" aria-label="Victus AI">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src="/victus-logo.svg"
            alt="Victus AI"
            className="mx-auto h-16 w-auto"
          />
        </Link>
        <div className="mt-6">{children}</div>
      </div>
    </main>
  );
}

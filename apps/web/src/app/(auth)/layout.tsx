import Link from 'next/link';

export default function AuthLayout({
  children,
}: {
  children: React.ReactNode;
}): React.ReactElement {
  return (
    <main className="grid min-h-dvh place-items-center bg-brand-50 px-4 py-12">
      <div className="w-full max-w-md">
        <Link
          href="/"
          className="block text-center text-xs font-semibold uppercase tracking-[0.2em] text-brand-700"
        >
          Victus AI
        </Link>
        <div className="mt-6">{children}</div>
      </div>
    </main>
  );
}

"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export function JudgeDemo() {
  const pathname = usePathname();
  // These values are intentionally public. Configure only a dedicated synthetic
  // account, never a personal account, provider key, or production password.
  const email = process.env.NEXT_PUBLIC_DEMO_EMAIL;
  const password = process.env.NEXT_PUBLIC_DEMO_PASSWORD;
  if (!email || !password || !["/login", "/signup"].includes(pathname)) return null;

  return (
    <aside aria-label="Judge demo access" className="mb-5 rounded-2xl border border-brand/30 bg-brand/5 p-5 text-sm">
      <h2 className="font-medium">Judges: try the demo</h2>
      <p className="mt-2 text-fg-muted">Use this shared test account to explore the dashboard and financial features. No signup needed.</p>
      <dl className="mt-3 space-y-2">
        <div><dt className="text-xs text-fg-muted">Email</dt><dd className="break-all select-all font-mono">{email}</dd></div>
        <div><dt className="text-xs text-fg-muted">Password</dt><dd className="break-all select-all font-mono">{password}</dd></div>
      </dl>
      <p className="mt-3 text-xs text-fg-muted">Synthetic finances and PayPal sandbox only. Do not connect personal bank accounts or enter private information.</p>
      <Link className="mt-3 inline-block text-brand underline" href={`/login?email=${encodeURIComponent(email)}`}>Sign in with the demo account</Link>
    </aside>
  );
}

import Link from "next/link";
import { ArrowLeft, ShieldCheck } from "lucide-react";
import { Logo } from "@/components/brand/logo";
import { ThemeToggle } from "@/components/ui/theme-toggle";
import { JudgeDemo } from "@/components/auth/judge-demo";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="relative flex min-h-dvh flex-col">
      <header className="flex items-center justify-between px-5 py-5 sm:px-8">
        <Link href="/" aria-label="MoneyWealth AI home">
          <Logo />
        </Link>
        <div className="flex items-center gap-1.5">
          <ThemeToggle className="size-9" />
          <Link
            href="/"
            className="inline-flex items-center gap-1.5 text-sm text-fg-muted transition-colors hover:text-fg"
          >
            <ArrowLeft className="size-4" /> Back home
          </Link>
        </div>
      </header>

      <main id="main-content" className="flex flex-1 items-center justify-center px-5 py-8">
        <div className="w-full max-w-md animate-[rise_0.5s_ease-out_both]">
          <JudgeDemo />
          {children}
        </div>
      </main>

      <footer className="flex items-center justify-center gap-1.5 px-5 py-6 text-xs text-fg-subtle">
        <ShieldCheck className="size-3.5 text-brand" />
        Encrypted, read-only access. We never move your money.
      </footer>
    </div>
  );
}

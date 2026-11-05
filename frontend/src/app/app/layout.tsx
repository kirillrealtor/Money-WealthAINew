"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";
import { useAuth } from "@/lib/auth/context";
import { Sidebar } from "@/components/shell/sidebar";
import { Topbar } from "@/components/shell/topbar";
import { Mark } from "@/components/brand/logo";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { status, user } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (status === "unauthenticated") router.replace("/login");
  }, [status, router]);

  if (status !== "authenticated") {
    return (
      <div className="grid min-h-dvh place-items-center">
        <div className="flex flex-col items-center gap-3 text-fg-muted">
          <Mark className="size-9 animate-[float_8s_ease-in-out_infinite]" />
          <Loader2 className="size-5 animate-spin text-brand" />
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-dvh">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar />
        <main id="main-content" className="flex-1 px-4 py-6 sm:px-6 lg:px-8">
          <div className="mx-auto max-w-6xl">
            {user?.is_demo && <div role="status" className="mb-5 rounded-xl border border-warning/40 bg-warning/10 p-3 text-sm">
              Synthetic demo finances. These accounts and transactions were seeded locally, not imported from Plaid.
            </div>}
            {children}
          </div>
        </main>
      </div>
    </div>
  );
}

"use client";

/**
 * The signed-in application shell. Every route in this group requires a
 * session: without an identity, no action could be attributed in the audit
 * trail, so nothing here renders for an anonymous visitor.
 */

import * as React from "react";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { Sidebar } from "@/components/layout/sidebar";
import { Header } from "@/components/layout/header";
import { Workspace } from "@/components/layout/workspace";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { session } = useAuth();
  const router = useRouter();

  React.useEffect(() => {
    if (session === null) router.replace("/login");
  }, [session, router]);

  if (!session) {
    return (
      <div className="flex h-screen items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-brand-700" aria-hidden />
      </div>
    );
  }

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-slate-50">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <Header />
        <main className="flex-1 overflow-hidden px-6 py-6 md:px-6 md:py-6 sm:px-4 sm:py-4 animate-float-in">
          <div className="h-full w-full overflow-y-auto">
            <Workspace>{children}</Workspace>
          </div>
        </main>
      </div>
    </div>
  );
}

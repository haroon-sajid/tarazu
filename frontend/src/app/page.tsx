"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";

/** Signed in → the dashboard. Signed out → the login screen. */
export default function Home() {
  const { session } = useAuth();
  const router = useRouter();

  React.useEffect(() => {
    if (session === undefined) return; // still reading storage
    router.replace(session ? "/dashboard" : "/login");
  }, [session, router]);

  return null;
}

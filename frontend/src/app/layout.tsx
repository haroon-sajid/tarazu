import type { Metadata } from "next";
import { AuthProvider } from "@/lib/auth";
import "./globals.css";

export const metadata: Metadata = {
  title: "Tarazu — AI Audit Assistant",
  description:
    "The AI weighs the evidence, the auditor delivers the verdict. Upload, review, and sign off with a full audit trail.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      {/* suppressHydrationWarning: browser extensions (ColorZilla's
          cz-shortcut-listen, Grammarly, password managers) inject attributes
          into <body> before React hydrates, tripping a false mismatch. The
          suppression is attribute-only and applies to this element alone —
          real hydration bugs in children still surface. */}
      <body className="min-h-screen" suppressHydrationWarning>
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}

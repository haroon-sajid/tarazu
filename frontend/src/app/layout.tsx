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
      <body className="min-h-screen">
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}

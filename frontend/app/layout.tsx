import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";

import { LogoutButton } from "@/components/audit/LogoutButton";
import { hasSession } from "@/lib/auth";

import "./globals.css";

export const metadata: Metadata = {
  title: "CCPA Dark Pattern Auditor",
  description: "Review dark-pattern findings against India's 2023 dark pattern guidelines.",
  robots: { index: false, follow: false },
};

export default async function RootLayout({ children }: { children: ReactNode }) {
  const signedIn = await hasSession();
  return (
    <html lang="en">
      <body className="min-h-screen">
        <header className="border-b border-line bg-surface">
          <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
            <Link href="/" className="text-base font-semibold">
              CCPA Dark Pattern Auditor
            </Link>
            {signedIn ? <LogoutButton /> : null}
          </div>
        </header>
        <main className="mx-auto max-w-6xl px-4 py-6">{children}</main>
      </body>
    </html>
  );
}

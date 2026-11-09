import { redirect } from "next/navigation";

import { LoginForm } from "@/components/audit/LoginForm";
import { hasSession } from "@/lib/auth";
import { checkConfig } from "@/lib/config";

export const dynamic = "force-dynamic";

export default async function LoginPage() {
  const check = checkConfig();
  if (!check.ok) {
    return (
      <section className="mx-auto max-w-lg rounded-lg border border-line bg-surface p-6">
        <h1 className="text-lg font-semibold">The dashboard is not configured</h1>
        <p className="mt-2 text-sm text-muted">
          Set these in <code>frontend/.env.local</code>, then restart the dashboard:
        </p>
        <ul className="mt-3 list-disc space-y-1 pl-5 text-sm">
          {check.problems.map((problem) => (
            <li key={problem}>{problem}</li>
          ))}
        </ul>
      </section>
    );
  }
  if (await hasSession()) redirect("/");
  return (
    <section className="mx-auto max-w-sm rounded-lg border border-line bg-surface p-6">
      <h1 className="text-lg font-semibold">Sign in</h1>
      <p className="mt-1 text-sm text-muted">Enter the dashboard password.</p>
      <LoginForm />
    </section>
  );
}

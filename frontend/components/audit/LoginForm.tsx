"use client";

import { useState, type FormEvent } from "react";

import { INPUT_CLASS, buttonClass } from "@/components/ui/styles";

export function LoginForm() {
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const response = await fetch("/api/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
      });
      if (response.ok) {
        window.location.assign("/");
        return;
      }
      const data: unknown = await response.json().catch(() => null);
      const message =
        typeof data === "object" && data !== null && "error" in data
          ? String((data as { error: unknown }).error)
          : "Could not sign in.";
      setError(message);
    } catch {
      setError("Could not reach the dashboard server.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="mt-4 space-y-3">
      <label className="block text-sm font-medium" htmlFor="password">
        Password
      </label>
      <input
        id="password"
        type="password"
        autoComplete="current-password"
        className={INPUT_CLASS}
        value={password}
        onChange={(event) => setPassword(event.target.value)}
        required
      />
      <p role="alert" className="min-h-5 text-sm text-bad">
        {error}
      </p>
      <button type="submit" className={buttonClass("primary")} disabled={busy || password === ""}>
        {busy ? "Signing in..." : "Sign in"}
      </button>
    </form>
  );
}

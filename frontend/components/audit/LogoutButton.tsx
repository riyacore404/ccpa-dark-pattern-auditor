"use client";

import { useState } from "react";

import { buttonClass } from "@/components/ui/styles";

export function LogoutButton() {
  const [busy, setBusy] = useState(false);

  async function logout() {
    setBusy(true);
    try {
      await fetch("/api/logout", { method: "POST" });
    } finally {
      window.location.assign("/login");
    }
  }

  return (
    <button type="button" className={buttonClass("secondary")} onClick={logout} disabled={busy}>
      Sign out
    </button>
  );
}

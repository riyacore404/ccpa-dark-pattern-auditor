import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { checkConfig } from "@/lib/config";
import { SESSION_COOKIE, verifySessionToken } from "@/lib/session";

export async function hasSession(): Promise<boolean> {
  const check = checkConfig();
  if (!check.ok) return false;
  const store = await cookies();
  const token = store.get(SESSION_COOKIE)?.value;
  if (!token) return false;
  return verifySessionToken(token, check.config.sessionSecret);
}

/** For pages: send a signed-out visitor to the login page. */
export async function requireSession(): Promise<void> {
  if (!(await hasSession())) redirect("/login");
}

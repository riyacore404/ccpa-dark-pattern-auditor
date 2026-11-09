import { NextResponse } from "next/server";

import { problem } from "@/lib/apiRoute";
import { isSameOrigin } from "@/lib/origin";
import { SESSION_COOKIE } from "@/lib/session";

export async function POST(request: Request): Promise<Response> {
  if (!isSameOrigin(request)) return problem(403, "Cross-origin request refused.");
  const response = NextResponse.json({ ok: true }, { headers: { "Cache-Control": "no-store" } });
  response.cookies.set(SESSION_COOKIE, "", {
    httpOnly: true,
    sameSite: "strict",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: 0,
  });
  return response;
}

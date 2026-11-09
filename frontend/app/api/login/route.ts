import { NextResponse } from "next/server";

import { errorResponse, problem, readJson } from "@/lib/apiRoute";
import { checkConfig } from "@/lib/config";
import { loginLimiter } from "@/lib/loginLimiter";
import { isSameOrigin } from "@/lib/origin";
import {
  SESSION_COOKIE,
  SESSION_MAX_AGE_SECONDS,
  createSessionToken,
  passwordMatches,
} from "@/lib/session";

export async function POST(request: Request): Promise<Response> {
  try {
    if (!isSameOrigin(request)) return problem(403, "Cross-origin request refused.");

    const check = checkConfig();
    if (!check.ok) return problem(500, "The dashboard is not configured.");

    if (loginLimiter.isBlocked()) {
      return problem(429, "Too many failed attempts. Try again in a few minutes.");
    }

    const body = await readJson(request);
    const password =
      typeof body === "object" && body !== null && "password" in body
        ? (body as { password: unknown }).password
        : undefined;
    if (typeof password !== "string" || password.length > 256) {
      return problem(400, "Enter the dashboard password.");
    }

    if (!passwordMatches(password, check.config.dashboardPassword)) {
      loginLimiter.recordFailure();
      return problem(401, "Incorrect password.");
    }

    loginLimiter.reset();
    const response = NextResponse.json({ ok: true }, { headers: { "Cache-Control": "no-store" } });
    response.cookies.set(SESSION_COOKIE, createSessionToken(check.config.sessionSecret), {
      httpOnly: true,
      sameSite: "strict",
      secure: process.env.NODE_ENV === "production",
      path: "/",
      maxAge: SESSION_MAX_AGE_SECONDS,
    });
    return response;
  } catch (error) {
    return errorResponse(error);
  }
}

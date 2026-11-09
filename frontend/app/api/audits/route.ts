import { errorResponse, guard, jsonResponse, problem, readJson } from "@/lib/apiRoute";
import { createAudit } from "@/lib/backend";
import { parseAuditUrl } from "@/lib/validate";

export async function POST(request: Request): Promise<Response> {
  const denied = await guard(request, true);
  if (denied) return denied;
  try {
    const body = await readJson(request);
    const raw =
      typeof body === "object" && body !== null && "url" in body
        ? (body as { url: unknown }).url
        : undefined;
    const parsed = parseAuditUrl(raw);
    if (!parsed.ok) return problem(422, parsed.error);
    const created = await createAudit(parsed.value);
    return jsonResponse({ session_id: created.session_id, status: created.status }, 202);
  } catch (error) {
    return errorResponse(error);
  }
}

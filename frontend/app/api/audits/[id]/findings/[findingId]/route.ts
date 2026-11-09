import { errorResponse, guard, jsonResponse, problem, readJson } from "@/lib/apiRoute";
import { reviewFinding } from "@/lib/backend";
import { parseReviewInput } from "@/lib/validate";

export async function PATCH(
  request: Request,
  context: { params: Promise<{ id: string; findingId: string }> },
): Promise<Response> {
  const denied = await guard(request, true);
  if (denied) return denied;
  try {
    const parsed = parseReviewInput(await readJson(request));
    if (!parsed.ok) return problem(422, parsed.error);
    const { id, findingId } = await context.params;
    return jsonResponse(await reviewFinding(id, findingId, parsed.value));
  } catch (error) {
    return errorResponse(error);
  }
}

import { errorResponse, guard, jsonResponse } from "@/lib/apiRoute";
import { cancelAudit } from "@/lib/backend";

export async function POST(
  request: Request,
  context: { params: Promise<{ id: string }> },
): Promise<Response> {
  const denied = await guard(request, true);
  if (denied) return denied;
  try {
    const { id } = await context.params;
    return jsonResponse(await cancelAudit(id));
  } catch (error) {
    return errorResponse(error);
  }
}

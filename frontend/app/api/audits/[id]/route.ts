import { errorResponse, guard, jsonResponse } from "@/lib/apiRoute";
import { getAuditDetail } from "@/lib/backend";

export const dynamic = "force-dynamic";

export async function GET(
  request: Request,
  context: { params: Promise<{ id: string }> },
): Promise<Response> {
  const denied = await guard(request, false);
  if (denied) return denied;
  try {
    const { id } = await context.params;
    return jsonResponse(await getAuditDetail(id));
  } catch (error) {
    return errorResponse(error);
  }
}

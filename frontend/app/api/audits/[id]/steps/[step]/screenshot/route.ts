import { errorResponse, guard, problem } from "@/lib/apiRoute";
import { fetchScreenshot } from "@/lib/backend";
import { parseStepNumber } from "@/lib/ids";

export const dynamic = "force-dynamic";

export async function GET(
  request: Request,
  context: { params: Promise<{ id: string; step: string }> },
): Promise<Response> {
  const denied = await guard(request, false);
  if (denied) return denied;
  try {
    const { id, step } = await context.params;
    const stepNumber = parseStepNumber(step);
    if (stepNumber === null) return problem(404, "No screenshot for this step.");
    const image = await fetchScreenshot(id, stepNumber);
    return new Response(image.body, {
      headers: {
        "Content-Type": image.contentType,
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'",
      },
    });
  } catch (error) {
    return errorResponse(error);
  }
}

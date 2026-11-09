import { notFound } from "next/navigation";

import { AuditView } from "@/components/audit/AuditView";
import { requireSession } from "@/lib/auth";
import { BackendError, getAuditDetail } from "@/lib/backend";
import { describeError } from "@/lib/errors";
import { isUuid } from "@/lib/ids";

export const dynamic = "force-dynamic";

export default async function AuditPage({ params }: { params: Promise<{ id: string }> }) {
  await requireSession();
  const { id } = await params;
  if (!isUuid(id)) notFound();

  try {
    const detail = await getAuditDetail(id);
    return <AuditView initial={detail} />;
  } catch (error) {
    if (error instanceof BackendError && error.status === 404) notFound();
    return (
      <p role="alert" className="rounded-md border border-bad bg-bad-soft p-3 text-sm text-bad">
        {describeError(error)}
      </p>
    );
  }
}

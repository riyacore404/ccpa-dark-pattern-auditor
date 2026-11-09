import { AuditTable } from "@/components/audit/AuditTable";
import { AutoRefresh } from "@/components/audit/AutoRefresh";
import { NewAuditForm } from "@/components/audit/NewAuditForm";
import { requireSession } from "@/lib/auth";
import { listAudits } from "@/lib/backend";
import { describeError } from "@/lib/errors";
import { isActiveStatus, type AuditSummary } from "@/types/api";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  await requireSession();

  let audits: AuditSummary[] = [];
  let error: string | null = null;
  try {
    audits = await listAudits(50);
  } catch (caught) {
    error = describeError(caught);
  }

  return (
    <div className="space-y-8">
      <section>
        <h1 className="text-xl font-semibold">Start an audit</h1>
        <NewAuditForm />
      </section>
      <section>
        <h2 className="mb-3 text-lg font-semibold">Recent audits</h2>
        {error ? (
          <p role="alert" className="rounded-md border border-bad bg-bad-soft p-3 text-sm text-bad">
            {error}
          </p>
        ) : (
          <>
            <AutoRefresh active={audits.some((audit) => isActiveStatus(audit.status))} />
            <AuditTable audits={audits} />
          </>
        )}
      </section>
    </div>
  );
}

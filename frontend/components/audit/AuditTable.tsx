import Link from "next/link";

import { AuditStatusBadge } from "@/components/ui/StatusBadge";
import { formatDateTime } from "@/lib/format";
import type { AuditSummary } from "@/types/api";

export function AuditTable({ audits }: { audits: AuditSummary[] }) {
  if (audits.length === 0) {
    return (
      <p className="rounded-md border border-line bg-surface p-4 text-sm text-muted">
        No audits yet. Start one above.
      </p>
    );
  }
  return (
    <div className="overflow-x-auto rounded-lg border border-line bg-surface">
      <table className="w-full text-left text-sm">
        <thead className="border-b border-line text-xs uppercase tracking-wide text-muted">
          <tr>
            <th className="px-4 py-2 font-medium">Site</th>
            <th className="px-4 py-2 font-medium">Status</th>
            <th className="px-4 py-2 font-medium">Findings</th>
            <th className="px-4 py-2 font-medium">Steps</th>
            <th className="px-4 py-2 font-medium">Started</th>
          </tr>
        </thead>
        <tbody>
          {audits.map((audit) => (
            <tr key={audit.id} className="border-b border-line last:border-b-0">
              <td className="px-4 py-3">
                <Link href={`/audits/${audit.id}`} className="font-medium text-accent hover:underline">
                  {audit.domain}
                </Link>
              </td>
              <td className="px-4 py-3">
                <AuditStatusBadge status={audit.status} />
              </td>
              <td className="px-4 py-3">{audit.finding_count}</td>
              <td className="px-4 py-3">{audit.step_count}</td>
              <td className="px-4 py-3 text-muted">{formatDateTime(audit.started_at ?? audit.created_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

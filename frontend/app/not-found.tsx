import Link from "next/link";

export default function NotFound() {
  return (
    <section className="rounded-lg border border-line bg-surface p-6">
      <h1 className="text-lg font-semibold">Not found</h1>
      <p className="mt-1 text-sm text-muted">That audit does not exist.</p>
      <Link href="/" className="mt-3 inline-block text-sm text-accent hover:underline">
        Back to audits
      </Link>
    </section>
  );
}

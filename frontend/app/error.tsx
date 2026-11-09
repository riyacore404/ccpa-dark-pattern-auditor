"use client";

export default function ErrorPage({ reset }: { error: Error; reset: () => void }) {
  return (
    <section className="rounded-lg border border-bad bg-bad-soft p-6">
      <h1 className="text-lg font-semibold text-bad">Something went wrong</h1>
      <p className="mt-1 text-sm">The page could not be loaded.</p>
      <button
        type="button"
        onClick={reset}
        className="mt-3 rounded-md border border-bad px-3 py-1.5 text-sm text-bad"
      >
        Try again
      </button>
    </section>
  );
}

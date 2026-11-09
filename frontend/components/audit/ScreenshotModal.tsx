"use client";

import { useEffect, useRef } from "react";

import { buttonClass } from "@/components/ui/styles";

interface Props {
  auditId: string;
  step: number;
  onClose: () => void;
}

export function ScreenshotModal({ auditId, step, onClose }: Props) {
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={`Screenshot for step ${step}`}
      className="fixed inset-0 z-50 flex flex-col bg-black/70 p-4"
      onClick={onClose}
    >
      <div className="mb-2 flex justify-end">
        <button ref={closeRef} type="button" className={buttonClass("secondary")} onClick={onClose}>
          Close
        </button>
      </div>
      <div className="min-h-0 flex-1 overflow-auto rounded-md bg-surface" onClick={(event) => event.stopPropagation()}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={`/api/audits/${auditId}/steps/${step}/screenshot`}
          alt={`Full screenshot at step ${step}`}
          className="mx-auto block max-w-full"
        />
      </div>
    </div>
  );
}

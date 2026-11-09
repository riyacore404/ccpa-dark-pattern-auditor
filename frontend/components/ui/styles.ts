export type ButtonVariant = "primary" | "secondary" | "danger";

const BASE =
  "inline-flex items-center justify-center rounded-md px-3.5 py-2 text-sm font-medium transition-opacity disabled:cursor-not-allowed disabled:opacity-50";

const VARIANTS: Record<ButtonVariant, string> = {
  primary: "bg-accent text-accent-ink hover:opacity-90",
  secondary: "border border-line bg-surface text-ink hover:bg-neutral-soft",
  danger: "border border-bad text-bad hover:bg-bad-soft",
};

export function buttonClass(variant: ButtonVariant = "primary"): string {
  return `${BASE} ${VARIANTS[variant]}`;
}

export const INPUT_CLASS =
  "w-full rounded-md border border-line bg-surface px-3 py-2 text-sm text-ink placeholder:text-muted";

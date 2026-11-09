const LABELS: Record<string, string> = {
  FALSE_URGENCY: "False urgency",
  BASKET_SNEAKING: "Basket sneaking",
  CONFIRM_SHAMING: "Confirm shaming",
  FORCED_ACTION: "Forced action",
  SUBSCRIPTION_TRAP: "Subscription trap",
  INTERFACE_INTERFERENCE: "Interface interference",
  BAIT_AND_SWITCH: "Bait and switch",
  DRIP_PRICING: "Drip pricing",
  DISGUISED_ADVERTISEMENT: "Disguised advertisement",
  NAGGING: "Nagging",
  TRICK_QUESTION: "Trick question",
  SAAS_BILLING: "SaaS billing",
  ROGUE_MALWARE: "Rogue malware",
};

export function categoryLabel(category: string): string {
  const known = LABELS[category];
  if (known) return known;
  const words = category.toLowerCase().replace(/_/g, " ").trim();
  return words ? words.charAt(0).toUpperCase() + words.slice(1) : "Unknown";
}

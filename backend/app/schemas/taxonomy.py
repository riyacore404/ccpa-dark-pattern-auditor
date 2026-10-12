"""The 13-category dark pattern taxonomy.

Category values mirror the Postgres enum public.ccpa_dark_pattern_category
in database/migrations/001_initial_schema.sql. A test keeps the two in sync.

A category is a classification label. Matching a category identifies a
potential dark pattern for human review; it is never a legal conclusion.

OWNER REVIEW REQUIRED: the `summary` strings below are short working
descriptions used only to guide the model. They are paraphrased, not quoted
from the official text. Verify them against the Guidelines for Prevention and
Regulation of Dark Patterns, 2023 before relying on them.
"""

from dataclasses import dataclass
from enum import StrEnum

TAXONOMY_VERSION = "CCPA-2023"

GUIDELINES_CITATION = (
    "Guidelines for Prevention and Regulation of Dark Patterns, 2023 "
    "(Central Consumer Protection Authority, India)"
)


class DarkPatternCategory(StrEnum):
    FALSE_URGENCY = "FALSE_URGENCY"
    BASKET_SNEAKING = "BASKET_SNEAKING"
    CONFIRM_SHAMING = "CONFIRM_SHAMING"
    FORCED_ACTION = "FORCED_ACTION"
    SUBSCRIPTION_TRAP = "SUBSCRIPTION_TRAP"
    INTERFACE_INTERFERENCE = "INTERFACE_INTERFERENCE"
    BAIT_AND_SWITCH = "BAIT_AND_SWITCH"
    DRIP_PRICING = "DRIP_PRICING"
    DISGUISED_ADVERTISEMENT = "DISGUISED_ADVERTISEMENT"
    NAGGING = "NAGGING"
    TRICK_QUESTION = "TRICK_QUESTION"
    SAAS_BILLING = "SAAS_BILLING"
    ROGUE_MALWARE = "ROGUE_MALWARE"


@dataclass(frozen=True)
class CategoryInfo:
    category: DarkPatternCategory
    display_name: str
    annexure_number: int
    summary: str


TAXONOMY: dict[DarkPatternCategory, CategoryInfo] = {
    info.category: info
    for info in (
        CategoryInfo(
            DarkPatternCategory.FALSE_URGENCY,
            "False Urgency",
            1,
            "Falsely stating or implying urgency or scarcity to push a "
            "user into an immediate purchase or action.",
        ),
        CategoryInfo(
            DarkPatternCategory.BASKET_SNEAKING,
            "Basket Sneaking",
            2,
            "Adding items, services, payments or donations at checkout "
            "without the user's explicit consent, raising the total above "
            "what the user chose.",
        ),
        CategoryInfo(
            DarkPatternCategory.CONFIRM_SHAMING,
            "Confirm Shaming",
            3,
            "Wording, audio, video or other means that create fear, shame, "
            "ridicule or guilt to nudge the user into buying a product or "
            "continuing a subscription, for commercial gain.",
        ),
        CategoryInfo(
            DarkPatternCategory.FORCED_ACTION,
            "Forced Action",
            4,
            "Forcing the user to take an unrelated action, such as buying "
            "more, subscribing, or sharing personal information, in order "
            "to complete what they set out to do.",
        ),
        CategoryInfo(
            DarkPatternCategory.SUBSCRIPTION_TRAP,
            "Subscription Trap",
            5,
            "Making cancellation or opting out hidden, complex or "
            "impossible, or demanding payment details for a free offer, or "
            "using ambiguous subscription instructions.",
        ),
        CategoryInfo(
            DarkPatternCategory.INTERFACE_INTERFERENCE,
            "Interface Interference",
            6,
            "Design that emphasizes some options and obscures others to "
            "steer the user away from the choice they would otherwise make.",
        ),
        CategoryInfo(
            DarkPatternCategory.BAIT_AND_SWITCH,
            "Bait and Switch",
            7,
            "Advertising one outcome but delivering a different, less "
            "favorable one after the user acts.",
        ),
        CategoryInfo(
            DarkPatternCategory.DRIP_PRICING,
            "Drip Pricing",
            8,
            "Price elements that are not disclosed upfront or are revealed "
            "later, such as a higher amount charged after checkout than was "
            "shown, a product advertised as free that needs in-app "
            "purchases to keep using it, or a paid-for service withheld "
            "until the user buys something extra.",
        ),
        CategoryInfo(
            DarkPatternCategory.DISGUISED_ADVERTISEMENT,
            "Disguised Advertisement",
            9,
            "Presenting advertising as other content, such as editorial, "
            "reviews or user content, so the user does not recognize it "
            "as an advertisement.",
        ),
        CategoryInfo(
            DarkPatternCategory.NAGGING,
            "Nagging",
            10,
            "Repeatedly and persistently disrupting the user with requests, "
            "information, options or interruptions to push a transaction "
            "for commercial gain, unless the user has specifically "
            "permitted it.",
        ),
        CategoryInfo(
            DarkPatternCategory.TRICK_QUESTION,
            "Trick Question",
            11,
            "Deliberately confusing or vague wording, such as double "
            "negatives, used to steer the user away from the action they "
            "want or into a particular response.",
        ),
        CategoryInfo(
            DarkPatternCategory.SAAS_BILLING,
            "SaaS Billing",
            12,
            "In software-as-a-service billing, exploiting recurring "
            "subscription payment loops to collect money from the user as "
            "discreetly as possible.",
        ),
        CategoryInfo(
            DarkPatternCategory.ROGUE_MALWARE,
            "Rogue Malware",
            13,
            "Using ransomware or scareware to falsely convince the user "
            "that their device has a virus or is compromised, so they pay "
            "for or install a supposed removal tool.",
        ),
    )
}


def legal_reference(category: DarkPatternCategory) -> str:
    """Citation string stored with each finding. Points to the guideline
    item; it does not assert that a violation occurred."""
    info = TAXONOMY[category]
    return (
        f"{GUIDELINES_CITATION}, Annexure 1, item {info.annexure_number} "
        f"({info.display_name})"
    )

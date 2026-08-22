"""Is this skill mine to share?

The safety scanner answers a different question - whether a package is
dangerous to run. This one answers whether it is the owner's to give away, and
the two are independent: a completely inert skill can still be the most private
thing on the machine.

The case that shaped this module: a skill named `pawtold-scriptwriter`, where
"pawtold" is the owner's client and "scriptwriter" is genuinely good craft
worth sharing. Publishing it whole leaks a client relationship. Refusing it
entirely throws away the part the town wants. Neither is right, so there is a
third verdict - REWRITE - which says the skill has a shareable core wearing a
private coat, and names the coat so it can be taken off.

Three verdicts, and a citizen must be able to explain which it got and why:

  shareable - nothing in it belongs to anyone in particular. Deposit it.
  rewrite   - there is craft here worth having, wrapped around a private
              subject. Generalise it first and deposit the generalised skill.
  private   - it is about someone, or it carries their secrets. It never
              leaves the machine, and the agent does not argue about it.

Everything here is deterministic. No model is asked to judge what is private,
because a model that is wrong once has already published the thing.
"""
from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

# Craft words: the part of a name that describes what a skill DOES. A name that
# is "<something> <craft>" is the shape a private wrapper takes, because the
# something is almost always a client, a product, or a person.
CRAFT_WORDS = frozenset({
    # The -ing forms matter as much as the agent nouns: people name a skill
    # "channel-a-scriptwriting" at least as often as "channel-a-scriptwriter".
    #
    # Kept deliberately narrow. The first draft of this list also held
    # "analysis", "research", "design", "strategy" and a dozen more, and those
    # are the ordinary tail of perfectly innocent compound names -
    # competitor-analysis and keyword-research were promptly accused of being
    # somebody's private client work. A craft word here has to be one that
    # almost never appears as the second half of a general skill name.
    "scriptwriting", "copywriting", "ghostwriting", "proofreading",
    "transcription", "narration",
    "scriptwriter", "writer", "copywriter", "ghostwriter", "editor", "proofreader",
    "researcher", "analyst", "reviewer", "auditor", "planner", "scheduler",
    "designer", "illustrator", "animator", "producer", "director",
    "developer", "engineer", "architect", "tester", "debugger", "refactorer",
    "translator", "summarizer", "summariser", "transcriber", "narrator",
    "marketer", "strategist", "consultant", "coach", "trainer", "tutor",
    "assistant", "helper", "generator", "builder", "formatter", "converter",
    "scraper", "crawler", "reporter", "publisher", "moderator", "curator",
})

# Words that are generic on their own, so "<word>-<craft>" is not a private
# wrapper. "python-developer" names a craft twice; it names nobody.
GENERIC_HEADS = frozenset({
    "ai", "api", "auto", "basic", "blog", "book", "brand", "code", "content",
    "core", "daily", "data", "deep", "doc", "docs", "email", "fast", "film",
    "general", "generic", "git", "image", "java", "js", "json", "long", "meta",
    "music", "news", "note", "notes", "open", "paper", "pdf", "photo", "podcast",
    "post", "product", "python", "quick", "react", "report", "research", "rust",
    "script", "seo", "short", "simple", "smart", "social", "song", "sql", "story",
    "tech", "test", "text", "ts", "ui", "unit", "ux", "video", "web", "youtube",
})

# Text that says, in words, that something is not for sharing. An owner who
# wrote one of these into their own skill has already given the answer.
PRIVACY_PHRASES = (
    (re.compile(r"\bdo not (share|publish|distribute|redistribute)\b", re.I), "the skill says not to share it"),
    (re.compile(r"\b(confidential|proprietary|classified)\b", re.I), "marked confidential"),
    (re.compile(r"\b(nda|non-disclosure)\b", re.I), "mentions an NDA"),
    (re.compile(r"\binternal (use|only)\b", re.I), "marked internal use"),
    (re.compile(r"\bclient[- ]specific\b", re.I), "described as client-specific"),
    (re.compile(r"\bprivate\s+(client|customer|project|repo)\b", re.I), "names a private client or project"),
)

# A live credential is never shareable and never fixable by editing prose: if
# it has leaked into a skill the answer is to rotate it, not to publish the
# file. These are the only content findings that refuse outright.
SECRETS = (
    (re.compile(r"(?i)\b(?:sk|pk|ghp|gho|xox[abps])[-_][A-Za-z0-9_-]{16,}"), "something shaped like a live credential"),
    (re.compile(r"(?i)\b(?:api[_-]?key|secret|password|token)\s*[:=]\s*[\"']?[A-Za-z0-9_\-]{12,}"), "an assigned secret"),
)

# Traces of a particular person or machine. These are real - a skill should not
# ship somebody's address or a path through their home directory - but they are
# lines to fix, not reasons to withhold the craft. Blocking on them refused
# nine perfectly good skills on the first real machine this ran against,
# because dev docs cite an author and every tutorial mentions a dev server.
SCRUBBABLE = (
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]{2,}"), "an email address"),
    (re.compile(r"(?i)\b[A-Z]:\\Users\\[^\\\s\"']+"), "a path inside somebody's Windows account"),
    (re.compile(r"/(?:home|Users)/[A-Za-z0-9._-]+/"), "a path inside somebody's home directory"),
    (re.compile(r"(?i)\bhttps?://(?:192\.168\.|10\.)[^\s\"']*"), "an address on somebody's private network"),
)
# Deliberately absent: localhost and 127.0.0.1. Every tutorial ever written
# mentions a dev server, and treating that as a privacy leak is just noise.


@dataclass
class Shareability:
    """One reproducible answer, with the reasons that produced it."""

    verdict: str
    reasons: list[str] = field(default_factory=list)
    subject: str | None = None
    generic_name: str | None = None
    subject_mentions: int = 0

    @property
    def may_deposit(self) -> bool:
        return self.verdict == "shareable"

    def explain(self) -> str:
        if self.verdict == "shareable":
            return "nothing in this belongs to anyone in particular"
        if self.verdict == "private":
            return "; ".join(self.reasons) or "this is about someone"
        if self.subject:
            return (f"the craft here is worth sharing, but it is written around "
                    f"'{self.subject}' ({self.subject_mentions} mention(s))")
        return "the craft here is worth sharing once " + "; ".join(self.reasons) + " is taken out"

    def as_dict(self) -> dict:
        return {"verdict": self.verdict, "reasons": self.reasons, "subject": self.subject,
                "genericName": self.generic_name, "subjectMentions": self.subject_mentions}


def split_private_wrapper(name: str) -> tuple[str, str] | None:
    """Split `pawtold-scriptwriter` into its subject and its craft.

    Returns None when the name names a craft and nobody in particular, which is
    the common and happy case.
    """
    parts = [part for part in re.split(r"[-_\s]+", name.strip().lower()) if part]
    if len(parts) < 2:
        return None
    craft = parts[-1]
    if craft not in CRAFT_WORDS:
        return None
    head = parts[:-1]
    # Every leading word generic? Then the name describes work, not a person.
    if all(word in GENERIC_HEADS for word in head):
        return None
    subject = "-".join(word for word in head if word not in GENERIC_HEADS)
    return (subject, craft) if subject else None


def _unique(values: list[str]) -> list[str]:
    seen: list[str] = []
    for value in values:
        if value not in seen:
            seen.append(value)
    return seen


def assess(name: str, text: str) -> Shareability:
    """Judge one skill from its name and its own words."""
    # The owner saying no, and a leaked credential, both end it here.
    refusals = [why for pattern, why in PRIVACY_PHRASES if pattern.search(text)]
    refusals += [f"it contains {why}" for pattern, why in SECRETS if pattern.search(text)]
    if refusals:
        return Shareability(verdict="private", reasons=_unique(refusals))

    # Everything below is fixable, so the verdict is rewrite: the craft is
    # worth having and the citizen is told exactly what to take out first.
    fixes = [f"it contains {why}" for pattern, why in SCRUBBABLE if pattern.search(text)]
    wrapper = split_private_wrapper(name)
    if wrapper:
        subject, craft = wrapper
        mentions = len(re.findall(re.escape(subject), text, re.I))
        return Shareability(
            verdict="rewrite", subject=subject, generic_name=craft, subject_mentions=mentions,
            reasons=_unique([f"the name is built around '{subject}', which names a subject rather than a craft", *fixes]),
        )
    if fixes:
        return Shareability(verdict="rewrite", reasons=_unique(fixes))
    return Shareability(verdict="shareable")


def assess_folder(name: str, folder: str | Path) -> Shareability:
    """Judge a skill from every markdown and text file it ships."""
    root = Path(folder)
    collected: list[str] = []
    if root.is_file():
        collected.append(_read(root))
    else:
        for path in sorted(root.rglob("*")):
            if path.is_file() and path.suffix.lower() in {".md", ".markdown", ".txt", ".yml", ".yaml", ".json"}:
                collected.append(_read(path))
            if len(collected) >= 60:
                break
    return assess(name, "\n".join(collected))


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:200_000]
    except OSError:
        return ""


def rewrite_guidance(result: Shareability) -> list[str]:
    """What the citizen has to actually do before this can be deposited."""
    if result.verdict != "rewrite":
        return []
    if not result.subject:
        # Nothing wrong with the craft or its name - only lines to scrub.
        return [f"Remove {reason.removeprefix('it contains ')} from the skill text."
                for reason in result.reasons] + [
            "Then deposit it: Earth deposit-skill <name>",
        ]
    return [
        f"Rename the skill to '{result.generic_name}' - keep the craft, drop the subject.",
        f"Remove or generalise all {result.subject_mentions} mention(s) of '{result.subject}'.",
        "Replace client-specific examples with invented ones that teach the same thing.",
        "Strip any brand voice, tone guide, or house style that is not yours to give away.",
        f"Deposit the generalised skill. The original '{result.subject}-{result.generic_name}' stays on this machine.",
    ]


# ── Families: one craft, many private variants ────────────────────────────────
#
# A machine that does scriptwriting for two channels tends to hold three skills:
# `scriptwriting`, `channel-a-scriptwriting` and `channel-b-scriptwriting`. Only
# the first is anybody else's business. Depositing all three publishes the same
# craft three times AND leaks two client relationships doing it, which is the
# worst of both outcomes.
#
# The craft is the family name. Skills whose name is nothing but the craft are
# parents; skills that wrap the craft in a subject are that parent's daughters.


@dataclass
class SkillFamily:
    """One craft, and every local skill built around it."""

    craft: str
    parent: str | None
    daughters: list[str] = field(default_factory=list)

    @property
    def needs_a_parent(self) -> bool:
        """Daughters with nobody to generalise into."""
        return self.parent is None and bool(self.daughters)


def group_families(names: Iterable[str]) -> dict[str, SkillFamily]:
    """Sort skill names into families keyed by the craft they share."""
    families: dict[str, SkillFamily] = {}
    for name in names:
        wrapper = split_private_wrapper(name)
        if wrapper:
            subject, craft = wrapper
            family = families.setdefault(craft, SkillFamily(craft=craft, parent=None))
            family.daughters.append(name)
            continue
        # A name that IS the craft, with nothing wrapped around it, is a parent.
        parts = [part for part in re.split(r"[-_\s]+", name.strip().lower()) if part]
        if len(parts) == 1 and parts[0] in CRAFT_WORDS:
            family = families.setdefault(parts[0], SkillFamily(craft=parts[0], parent=None))
            family.parent = name
    return {craft: family for craft, family in families.items() if family.daughters or family.parent}


@dataclass
class DepositPlan:
    """What to deposit, what to hold back, and what still has to be written."""

    deposit: list[str] = field(default_factory=list)
    covered_by_parent: dict[str, str] = field(default_factory=dict)
    write_parent_first: dict[str, list[str]] = field(default_factory=dict)

    def reason_for(self, name: str) -> str | None:
        parent = self.covered_by_parent.get(name)
        if parent:
            return (f"the craft in this is already going up as '{parent}'. Depositing this too "
                    f"publishes the same craft twice and leaks the subject it is written around.")
        return None


def plan_deposits(
    names: Iterable[str],
    shareable: Iterable[str] | None = None,
    wrappers: Iterable[str] | None = None,
) -> DepositPlan:
    """Decide which of a machine's skills should actually reach the Bank.

    `shareable` is the subset that passed the privacy check. `wrappers` is the
    subset the privacy check judged to be craft wrapped around a private subject
    - the only skills for which "go and write the general version" is sound
    advice.

    That second argument matters more than it looks. A name alone is far too
    weak a signal to demand somebody write a parent skill: `competitor-analysis`
    and `keyword-research` have exactly the shape of `pawtold-scriptwriter`, and
    they are ordinary standalone skills whose leading word describes the work
    rather than naming a client. Holding a daughter back because its parent
    genuinely exists on this machine is safe and needs no such judgement.
    Telling someone to invent a parent, on the evidence of a hyphen, is not.
    """
    all_names = list(names)
    allowed = set(shareable) if shareable is not None else set(all_names)
    private_wrappers = set(wrappers) if wrappers is not None else set()
    families = group_families(all_names)
    plan = DepositPlan()
    spoken_for: set[str] = set()

    for family in families.values():
        if family.parent and family.daughters:
            # The parent carries the craft; the daughters stay home. This needs
            # no guesswork: the general version is right there on the machine.
            for daughter in family.daughters:
                plan.covered_by_parent[daughter] = family.parent
                spoken_for.add(daughter)
        elif family.needs_a_parent:
            # Only for skills the privacy check already found a subject inside.
            wrapped = sorted(d for d in family.daughters if d in private_wrappers)
            if not wrapped:
                continue
            plan.write_parent_first[family.craft] = wrapped
            spoken_for.update(wrapped)

    for name in all_names:
        if name in spoken_for or name not in allowed:
            continue
        plan.deposit.append(name)
    plan.deposit.sort()
    return plan


def parent_guidance(craft: str, daughters: list[str]) -> list[str]:
    """What to tell a citizen holding daughters and no parent."""
    return [
        f"Write '{craft}' first: the general craft, with no client, channel or product in it.",
        f"Take what is genuinely reusable from {', '.join(daughters)} - structure, pacing, checklists.",
        "Replace every specific example with an invented one that teaches the same thing.",
        f"Deposit '{craft}'. The variants stay on this machine and keep working as they are.",
    ]

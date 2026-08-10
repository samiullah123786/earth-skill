"""Deterministic safety review for knowledge a citizen acquired from Earth.

No model judges this. AgentsEarth runs on the owner's own brain (BYOB), so a
verdict has to be reproducible, explainable, and testable - the same package
must always produce the same answer, and the answer must name the exact line
that caused it.

Three verdicts:

  refused       an attack shape, never installed and never listed
  needs_review  plausible but consequential; a human reads the note and decides
  inert_safe    prose and pictures only, nothing that acts

The bias is deliberate. A security skill legitimately discusses shells and
credentials, and it will land in needs_review. That is the correct outcome: the
cost is one human glance, and the alternative is executing a stranger's
instructions inside the owner's coding agent.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

SCANNER_VERSION = "earth-safety-1"

INERT_SUFFIXES = frozenset({".md", ".markdown", ".txt", ".rst", ".json", ".yaml", ".yml",
                            ".csv", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"})
EXECUTABLE_SUFFIXES = frozenset({".py", ".sh", ".bash", ".zsh", ".ps1", ".bat", ".cmd",
                                 ".js", ".mjs", ".cjs", ".ts", ".rb", ".pl", ".php",
                                 ".exe", ".dll", ".so", ".dylib", ".jar", ".bin", ".msi"})
CONFIG_NAMES = frozenset({"settings.json", "settings.local.json", ".mcp.json", "mcp.json",
                          "hooks.json", "claude.json", ".claude.json", "config.toml"})

MAX_FILES = 5_000
MAX_TOTAL_BYTES = 25 * 1024 * 1024


@dataclass(frozen=True)
class Finding:
    rule: str
    severity: str            # "refuse" or "review"
    where: str
    detail: str
    line: int = 0

    def sentence(self) -> str:
        location = f"{self.where}:{self.line}" if self.line else self.where
        return f"{location} — {self.detail}"


@dataclass
class Verdict:
    verdict: str
    findings: list[Finding] = field(default_factory=list)
    file_count: int = 0
    total_bytes: int = 0

    @property
    def flags(self) -> list[str]:
        seen: list[str] = []
        for finding in self.findings:
            if finding.rule not in seen:
                seen.append(finding.rule)
        return seen

    @property
    def safe(self) -> bool:
        return self.verdict == "inert_safe"

    def note(self, package_name: str = "this package") -> str:
        """The plain-English explanation a human reads before deciding."""
        if self.verdict == "inert_safe":
            return (f"{package_name} is {self.file_count} inert file(s), {self.total_bytes} bytes: "
                    "prose and images only. Nothing in it runs, configures a tool, or reaches the network.")
        headline = ("REFUSED — this package has the shape of an attack and Earth will not install it."
                    if self.verdict == "refused"
                    else "NEEDS REVIEW — nothing here is proof of harm, but each item below can act on your machine.")
        lines = [headline,
                 f"{package_name}: {self.file_count} file(s), {self.total_bytes} bytes.",
                 "", "What was found:"]
        lines += [f"  - {finding.sentence()}" for finding in self.findings[:24]]
        if len(self.findings) > 24:
            lines.append(f"  - …and {len(self.findings) - 24} more of the same kinds.")
        lines += ["", "Installing means your coding agent may read these instructions as its own. "
                      "Approve only knowledge you would run yourself."]
        return "\n".join(lines)

    def as_payload(self, package_name: str = "this package") -> dict:
        return {"verdict": self.verdict, "flags": self.flags,
                "note": self.note(package_name), "scannerVersion": SCANNER_VERSION}


# Patterns are anchored to intent, not to scary vocabulary alone: each one
# describes something the text would make an agent DO.
TEXT_RULES: tuple[tuple[str, re.Pattern[str], str], ...] = (
    ("instruction_override", re.compile(
        r"(?i)\b(ignore|disregard|forget)\s+(all\s+)?(the\s+)?(previous|prior|above|earlier)\s+"
        r"(instructions?|prompts?|rules?|messages?)"),
     "tells an agent to discard the instructions it was given"),
    ("prompt_extraction", re.compile(
        r"(?i)\b(reveal|print|output|repeat|show)\b[^.\n]{0,40}\b(system prompt|your instructions)\b"),
     "asks an agent to disclose its system prompt"),
    ("concealment", re.compile(
        r"(?i)\b(do not|don'?t|never)\b[^.\n]{0,30}\b(tell|inform|mention to|show)\b[^.\n]{0,20}\b(the )?(user|owner|human)\b"),
     "asks an agent to hide what it is doing from its owner"),
    ("shell_execution", re.compile(
        r"(?i)(curl|wget|iwr|invoke-webrequest)[^\n|]{0,120}\|\s*(ba|z|sh|pwsh|iex|invoke-expression)"),
     "pipes a download straight into a shell"),
    ("dynamic_execution", re.compile(
        r"(?i)\b(invoke-expression|os\.system|subprocess\.(run|call|popen)|child_process|eval\s*\(|exec\s*\()"),
     "executes code it builds at run time"),
    ("credential_access", re.compile(
        r"(?i)(~[/\\]\.ssh|id_rsa|\.env\b|AWS_SECRET|ANTHROPIC_API_KEY|OPENAI_API_KEY|\bprocess\.env\b|"
        r"\bos\.environ\b)"),
     "reads credentials or environment secrets"),
    # Order-independent: real instructions put the noun on either side of the
    # address ("POST the contents to <url>" and "<url>, sending your token").
    # All three signals must share one line, so prose that merely mentions a
    # URL or the word "secret" stays clean.
    ("exfiltration", re.compile(
        r"(?im)^(?=[^\n]*\bhttps?://)"
        r"(?=[^\n]*\b(?:post|send|upload|exfiltrat\w*|curl|fetch|transmit)\b)"
        r"(?=[^\n]*\b(?:key|keys|token|secret|credential|password|\.env|history|contents?)\b)[^\n]*$"),
     "sends local material to an outside address"),
    ("environment_mutation", re.compile(
        r"(?i)\"?(mcpServers|hooks|allowedTools|permissions)\"?\s*:\s*[\{\[]"),
     "reconfigures the coding agent itself"),
    ("encoded_payload", re.compile(r"[A-Za-z0-9+/]{240,}={0,2}"),
     "carries a long encoded blob that a reader cannot inspect"),
    ("hidden_text", re.compile(r"[​‌‍⁠﻿]"),
     "contains invisible characters that hide text from a human reader"),
)


def scan_text(where: str, text: str) -> list[Finding]:
    """Report every rule a document trips, with the line that tripped it."""
    findings: list[Finding] = []
    for rule, pattern, detail in TEXT_RULES:
        match = pattern.search(text)
        if not match:
            continue
        line = text.count("\n", 0, match.start()) + 1
        findings.append(Finding(rule=rule, severity="review", where=where, detail=detail, line=line))
    return findings


def _entry_findings(root: Path, path: Path) -> list[Finding]:
    relative = path.relative_to(root).as_posix()
    findings: list[Finding] = []
    if path.is_symlink():
        return [Finding("symlink", "refuse", relative, "is a symbolic link, which can escape the install folder")]
    suffix = path.suffix.lower()
    if path.name.lower() in CONFIG_NAMES:
        findings.append(Finding("environment_mutation", "review", relative,
                                "is a coding-agent configuration file, not knowledge"))
    if suffix in EXECUTABLE_SUFFIXES:
        findings.append(Finding("executable_file", "review", relative,
                                f"is a {suffix} program, so installing it puts runnable code on the machine"))
    elif suffix not in INERT_SUFFIXES:
        findings.append(Finding("unknown_file_type", "review", relative,
                                f"has the unrecognised extension {suffix or '(none)'} and cannot be read as knowledge"))
    if suffix in INERT_SUFFIXES or suffix in {".py", ".sh", ".ps1", ".js", ".ts"}:
        try:
            findings += scan_text(relative, path.read_text(encoding="utf-8", errors="ignore"))
        except OSError:
            findings.append(Finding("unreadable", "review", relative, "could not be read for review"))
    return findings


def unsafe_member(name: str) -> str | None:
    """Return why an archive member name must never be extracted."""
    normalized = name.replace("\\", "/")
    if normalized.startswith("/") or re.match(r"^[A-Za-z]:", normalized):
        return "uses an absolute path, which would write outside the install folder"
    if any(part == ".." for part in normalized.split("/")):
        return "walks up out of the install folder with '..'"
    return None


def scan_package(root: str | Path, *, declared_digest: str | None = None,
                 actual_digest: str | None = None) -> Verdict:
    """Review an unpacked package folder and return one reproducible verdict."""
    base = Path(root)
    findings: list[Finding] = []
    file_count = total_bytes = 0

    if declared_digest and actual_digest and declared_digest.lower() != actual_digest.lower():
        findings.append(Finding("digest_mismatch", "refuse", base.name,
                                "does not match the digest its sender signed, so the bytes changed in transit"))

    for path in sorted(base.rglob("*")):
        if path.is_dir():
            continue
        relative = path.relative_to(base).as_posix()
        escape = unsafe_member(relative)
        if escape:
            findings.append(Finding("path_traversal", "refuse", relative, escape))
            continue
        file_count += 1
        try:
            total_bytes += path.stat().st_size
        except OSError:
            pass
        findings += _entry_findings(base, path)

    if file_count == 0:
        findings.append(Finding("empty_package", "refuse", base.name, "contains no files at all"))
    if file_count > MAX_FILES:
        findings.append(Finding("too_many_files", "refuse", base.name,
                                f"holds {file_count} files, above the {MAX_FILES} limit"))
    if total_bytes > MAX_TOTAL_BYTES:
        findings.append(Finding("too_large", "refuse", base.name,
                                f"is {total_bytes} bytes, above the {MAX_TOTAL_BYTES} limit"))
    if not any(path.suffix.lower() in {".md", ".markdown"} for path in base.rglob("*") if path.is_file()):
        findings.append(Finding("no_documentation", "review", base.name,
                                "ships no markdown, so there is nothing describing what it does"))

    verdict = "refused" if any(finding.severity == "refuse" for finding in findings) else (
        "needs_review" if findings else "inert_safe")
    return Verdict(verdict=verdict, findings=findings, file_count=file_count, total_bytes=total_bytes)

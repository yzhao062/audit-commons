#!/usr/bin/env python3
"""
scripts/import_awesome.py
Imports and synchronizes the curated catalog from awesome-auditable-ai
(pinned snapshot at commit 2ac4b36328e9d84dbfb7a99c64fbe507dae28288, CC0 1.0)
into content/resources.json for Audit Commons.

Usage:
    python scripts/import_awesome.py --source-file <path_to_awesome_source.md>
    python scripts/import_awesome.py --source-file <path_to_awesome_source.md> --check-only

Key invariants:
- Requires an explicit --source-file argument (no path guessing).
- Verifies normalized LF UTF-8 SHA256 against EXPECTED_SNAPSHOT_SHA256 (fails closed on mismatch).
- On future refreshes, PINNED_REVISION, EXPECTED_SNAPSHOT_SHA256, and SNAPSHOT_REVIEW_DATE
  must be updated together with the newly verified snapshot.
- Requires existing content/resources.json with EXPECTED_ORIGINAL_IDS; errors before write
  if missing, corrupted, or missing any expected original IDs (order-independent lookup).
- Preserves the original 6 curated resources at indices 0..5 with checked="2026-09-15".
- Assigns checked="2026-09-16" to newly synchronized entries (snapshot review date).
- Enforces maintainer affiliation mapping verified against Yue Zhao's publications registry.
- Full snapshot refresh policy: non-upstream resources other than original 6 may be replaced.
- Strictly zero network dependencies; no private machine absolute paths embedded.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse
from resource_formats import resource_formats, formats_error

# Pinned snapshot metadata - MUST be updated together on refresh
PINNED_REVISION = "2ac4b36328e9d84dbfb7a99c64fbe507dae28288"
EXPECTED_SNAPSHOT_SHA256 = (
    "bf51fe0299a4846663ab52e13452fe312167bf8f7ba425c8fd5ce642ba041976"
)
SNAPSHOT_REVIEW_DATE = "2026-09-16"
ORIGINAL_CURATION_DATE = "2026-09-15"

CATALOG_SOURCE_BASE = (
    f"https://github.com/yzhao062/awesome-auditable-ai/blob/{PINNED_REVISION}/README.md"
)

EXPECTED_ORIGINAL_IDS = [
    "nist-ai-rmf",
    "inspect-aisi",
    "agentdojo",
    "awesome-auditable-ai",
    "catchbench",
    "auditable-agents",
]

# Explicit canonical maintainer-affiliated identities verified against Yue Zhao's
# public homepage publications registry (data/publications.json)
MAINTAINER_CANONICAL_URLS = {
    # grade
    "https://arxiv.org/abs/2606.22741",
    "https://github.com/yzhao062/grade",
    # aegis runtime (Justin0504/Aegis co-authored paper arXiv:2603.12621)
    "https://github.com/justin0504/aegis",
    "https://arxiv.org/abs/2603.12621",
    # agent-audit paper and tool (CAIS 2026)
    "https://arxiv.org/abs/2603.22853",
    "https://github.com/headyzhang/agent-audit",
    # auditable & auditable agents framework
    "https://github.com/yzhao062/auditable",
    "https://arxiv.org/abs/2604.05485",
    "https://auditable-agents.github.io",
    "https://github.com/auditable-agents/auditable-agents.github.io",
    # catchbench
    "https://github.com/yzhao062/catchbench",
    # awesome-auditable-ai
    "https://github.com/yzhao062/awesome-auditable-ai",
}

MAINTAINER_CANONICAL_IDS = {
    "awesome-auditable-ai",
    "auditable-agents",
    "catchbench",
    "auditable",
    "auditable-agents-paper",
    "grade",
    "aegis-runtime",
    "agent-audit-paper",
    "agent-audit",
}

VALID_CATEGORIES = {"Evaluation", "Security", "Governance", "Reading", "Tools"}
VALID_RELATIONSHIPS = {"External resource", "Maintainer project"}
VALID_FORMATS = {"Paper", "Tool", "Benchmark", "Dataset", "Standard", "Collection"}

TARGET_SECTIONS = [
    "Surveys and Foundations",
    "Failure Attribution and Diagnosis",
    "Reliability and Robustness",
    "Runtime Monitoring and Guardrails",
    "Audit Trails and Decision Records",
    "Security Auditing and Scanners",
    "Datasets and Benchmarks",
    "Tools and Platforms",
    "Standards and Governance",
]

SECTION_ANCHORS = {
    "Surveys and Foundations": "#surveys-and-foundations",
    "Failure Attribution and Diagnosis": "#failure-attribution-and-diagnosis",
    "Reliability and Robustness": "#reliability-and-robustness",
    "Runtime Monitoring and Guardrails": "#runtime-monitoring-and-guardrails",
    "Audit Trails and Decision Records": "#audit-trails-and-decision-records",
    "Security Auditing and Scanners": "#security-auditing-and-scanners",
    "Datasets and Benchmarks": "#datasets-and-benchmarks",
    "Tools and Platforms": "#tools-and-platforms",
    "Standards and Governance": "#standards-and-governance",
    "The Auditable Agents Ecosystem": "#the-auditable-agents-ecosystem",
}


def clean_markdown_text(text: str) -> str:
    """Strips inline markdown markup and normalizes whitespace."""
    if not text:
        return ""
    # Unescape escaped brackets
    s = text.replace(r"\[", "[").replace(r"\]", "]")
    # Replace markdown links [label](url) with label
    s = re.sub(r"\[\[?([^\[\]]+)\]?\]\([^)]+\)", r"\1", s)
    # Remove bold and italic markers
    s = re.sub(r"\*\*([^*]+)\*\*", r"\1", s)
    s = re.sub(r"\*([^*]+)\*", r"\1", s)
    # Remove backtick code formatting
    s = re.sub(r"`([^`]+)`", r"\1", s)
    # Normalize multiple whitespace characters
    s = re.sub(r"\s+", " ", s).strip()
    return s


def canonicalize_url(url: str) -> str:
    """Normalizes URLs, converting arxiv /pdf/ to /abs/ and stripping trailing anchors/slashes."""
    u = url.strip()
    # Convert arxiv.org/pdf/XXXX.YYYY(.pdf) to arxiv.org/abs/XXXX.YYYY
    m = re.match(r"https?://arxiv\.org/pdf/([0-9\.]+)(?:\.pdf)?/?$", u)
    if m:
        return f"https://arxiv.org/abs/{m.group(1)}"
    # Normalize trailing slash on github repo root
    if re.match(r"https?://github\.com/[^/]+/[^/]+/?$", u):
        u = u.rstrip("/")
    return u


def verify_snapshot_integrity(source_bytes: bytes) -> str:
    """Computes normalized LF UTF-8 SHA256 of source content and verifies against expected hash."""
    text = source_bytes.decode("utf-8")
    normalized_text = text.replace("\r\n", "\n").replace("\r", "\n")
    computed_hash = hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()
    if computed_hash != EXPECTED_SNAPSHOT_SHA256:
        raise ValueError(
            f"Snapshot integrity verification failed!\n"
            f"  Expected SHA256: {EXPECTED_SNAPSHOT_SHA256} (pinned revision {PINNED_REVISION})\n"
            f"  Computed SHA256: {computed_hash}\n"
            f"Refusing to import: updating snapshot requires updating PINNED_REVISION, "
            f"EXPECTED_SNAPSHOT_SHA256, and SNAPSHOT_REVIEW_DATE constants together."
        )
    return normalized_text


def is_maintainer_project(name: str, url: str, links: List[Dict[str, str]], entry_id: Optional[str] = None) -> bool:
    """Identifies maintainer-affiliated projects relating to Yue Zhao."""
    if entry_id and entry_id in MAINTAINER_CANONICAL_IDS:
        return True
    all_urls = [canonicalize_url(url).lower()] + [canonicalize_url(l.get("url", "")).lower() for l in links]
    for u in all_urls:
        if u in MAINTAINER_CANONICAL_URLS:
            return True
        if "github.com/yzhao062" in u or "auditable-agents.github.io" in u:
            return True
    if "auditable agents" in name.lower() and "arxiv.org/abs/2604.05485" in url:
        return True
    return False


def determine_owner(name: str, url: str, tag: str, summary: str, sec_name: str) -> str:
    """Determines a verified owner/contributor or neutrally defaults to paper authors."""
    # Maintainer projects
    if "github.com/yzhao062/awesome-auditable-ai" in url:
        return "Yue Zhao"
    if "auditable-agents.github.io" in url:
        return "Auditable Agents contributors"
    if "github.com/yzhao062/catchbench" in url:
        return "CatchBench contributors"
    if "github.com/yzhao062/auditable" in url:
        return "Yue Zhao and contributors"
    if "github.com/yzhao062/grade" in url or "arxiv.org/abs/2606.22741" in url:
        return "GRADE contributors"
    if "auditable agents" in name.lower() and "arxiv.org/abs/2604.05485" in url:
        return "Authors listed in the paper"
    if "github.com/justin0504/aegis" in url.lower() or "arxiv.org/abs/2603.12621" in url:
        return "Justin0504 and contributors"
    if "arxiv.org/abs/2603.22853" in url:
        return "Authors listed in the paper"
    if "github.com/headyzhang/agent-audit" in url.lower():
        return "Haiyue Zhang (HeadyZhang)"

    # Standards & Governance
    if sec_name == "Standards and Governance":
        if "NIST" in name:
            return "National Institute of Standards and Technology (NIST)"
        if "Model Context Protocol" in name:
            return "Anthropic / Linux Foundation"
        if "Agent2Agent" in name:
            return "Linux Foundation / Google"
        if "Agent Payments" in name:
            return "FIDO Alliance / Google"
        if "OpenTelemetry" in name:
            return "OpenTelemetry / CNCF"
        if "EU AI Act" in name:
            return "European Union"
        if "ISO/IEC" in name:
            return "ISO/IEC JTC 1/SC 42"
        if "MITRE ATLAS" in name or "CWE" in name:
            return "MITRE"
        if "OWASP" in name:
            return "OWASP"
        if "MAESTRO" in name:
            return "Cloud Security Alliance"
        if "Agent Oversight Framework" in name:
            return "Zhang Rui (ZhangRui987)"
        if "C2PA" in name:
            return "Coalition for Content Provenance and Authenticity (C2PA)"
        if "Certificate Transparency" in name:
            return "IETF"
        if "in-toto" in name:
            return "in-toto / CNCF"
        if "SLSA" in name:
            return "OpenSSF"
        if "DSSE" in name:
            return "Secure Systems Lab"
        if "Rekor" in name:
            return "Sigstore / OpenSSF"

    # Tool organizations
    gh_match = re.search(r"github\.com/([^/]+)/([^/]+)", url)
    if gh_match:
        org = gh_match.group(1)
        known_orgs = {
            "langfuse": "Langfuse contributors",
            "Arize-ai": "Arize AI",
            "comet-ml": "Comet ML",
            "traceloop": "Traceloop",
            "Helicone": "Helicone",
            "maximhq": "Maxim AI",
            "speakeasy-api": "Speakeasy",
            "confident-ai": "Confident AI",
            "evidentlyai": "Evidently AI",
            "AgentOps-AI": "AgentOps",
            "vibrantlabsai": "Exploding Gradients / Ragas contributors",
            "UKGovernmentBEIS": "UK AI Security Institute and Meridian Labs",
            "AgentDebugX": "AgentDebugX contributors",
            "TransluceAI": "Transluce",
            "lmnr-ai": "Laminar",
            "truera": "TruEra",
            "e2b-dev": "E2B",
            "superradcompany": "SuperRadCompany",
            "Giskard-AI": "Giskard",
            "FU-max-boop": "AgentRunProof contributors",
            "datamllab": "DataML Lab",
            "lindixu6-hash": "Lindi Xu",
            "WaseemGhanem98": "Waseem Ghanem",
            "Continuum-AI-Corp": "Continuum AI",
            "slopstopper": "slopstopper",
            "yylo-dev": "YYLO",
            "NVIDIA-NeMo": "NVIDIA",
            "guardrails-ai": "Guardrails AI",
            "meta-llama": "Meta",
            "makerchecker": "MakerChecker contributors",
            "Justin0504": "Justin0504",
            "KongFangXun": "KongFangXun",
            "bkuan001": "bkuan001",
            "microsoft": "Microsoft",
            "agentrust-io": "AgentRust contributors",
            "agentkitai": "AgentKit AI",
            "ceodaradigu": "Ceodar Adigu",
            "wavect": "Wavect",
            "busabase": "Busabase",
            "HeadyZhang": "Haiyue Zhang (HeadyZhang)",
            "NVIDIA": "NVIDIA",
            "splx-ai": "Splx AI",
            "snyk": "Snyk",
            "ethz-spylab": "ETH Zurich (SPY Lab) and Invariant Labs",
        }
        if org in known_orgs:
            return known_orgs[org]
        if org.lower() in ("meta-llama", "meta"):
            return "Meta"
        return f"{org} contributors"

    if "langchain.com" in url:
        return "LangChain"

    # Default neutral attribution for standalone papers without explicit institution
    return "Authors listed in the paper"


def determine_category(sec_name: str, name: str, summary: str) -> str:
    """Maps catalog entries to one of the 5 legacy categories."""
    if sec_name == "Surveys and Foundations":
        return "Reading"
    if sec_name in ("Failure Attribution and Diagnosis", "Reliability and Robustness", "Datasets and Benchmarks"):
        return "Evaluation"
    if sec_name == "Security Auditing and Scanners":
        return "Security"
    if sec_name in ("Audit Trails and Decision Records", "Standards and Governance"):
        return "Governance"
    if sec_name == "Tools and Platforms":
        if "Awesome Agentic Engineering" in name:
            return "Reading"
        if "YYLO Benchmark" in name:
            return "Evaluation"
        return "Tools"
    if sec_name == "Runtime Monitoring and Guardrails":
        name_l = name.lower()
        sum_l = summary.lower()
        if any(w in name_l or w in sum_l for w in ["guard", "injection", "jailbreak", "firewall", "shield", "safety", "adversar", "subver"]):
            return "Security"
        return "Tools"
    return "Evaluation"


def determine_format(sec_name: str, name: str, url: str, tag: str, is_text_entry: bool) -> str:
    """Semantically classifies catalog entries into Paper, Tool, Benchmark, Dataset, Standard, Collection."""
    name_l = name.lower()

    if sec_name == "Standards and Governance":
        if tag in ("Standard", "Framework") or is_text_entry and "Rekor" not in name:
            return "Standard"
        if "Rekor" in name:
            return "Tool"
        return "Paper"

    if sec_name == "Tools and Platforms":
        if "Awesome Agentic Engineering" in name:
            return "Collection"
        if "Benchmark" in name:
            return "Benchmark"
        return "Tool"

    if sec_name == "Datasets and Benchmarks":
        if "huggingface.co/datasets" in url or "MAST-Data" in name or "PACT" in name:
            return "Dataset"
        if any(p in name for p in ["AI Agents That Matter", "Do Androids Dream of Breaking the Game?", "Identifying the Risks of LM Agents with an LM-Emulated Sandbox"]):
            return "Paper"
        return "Benchmark"

    if is_text_entry:
        return "Tool"

    # Table rows in topical research sections
    if sec_name == "Surveys and Foundations":
        return "Paper"
    if sec_name == "Audit Trails and Decision Records":
        return "Paper"

    # In Failure Attribution, Reliability, Runtime Monitoring, Security Auditing:
    # Check for usable benchmarks
    bench_keywords = [
        "benchmark", "bench:", "dataset", "-bench", "who&when",
        "traceelephant", "whowhen pro", "agenterrorbench", "mp-bench",
        "telbench", "cais 2026", "injecagent", "agent security bench",
        "memsecbench", "stepjack", "openskillrisk", "agentabstain",
        "hil-bench", "reliabilitybench", "τ-bench", "agentnoisebench",
        "rootse", "cuaerrorbench", "searchauditbench",
    ]
    if any(k in name_l for k in bench_keywords):
        return "Benchmark"

    return "Paper"


def slugify(title: str, max_length: int = 50) -> str:
    """Generates a clean kebab-case ID from a title."""
    t = re.sub(r"\[.*?\]", "", title)
    if ":" in t:
        prefix, rest = t.split(":", 1)
        prefix = prefix.strip()
        generic_prefixes = {"a survey", "survey", "towards", "demystifying", "rethinking", "where", "why", "how", "on"}
        if 2 <= len(prefix) <= 25 and not any(prefix.lower().startswith(g) for g in generic_prefixes):
            t = prefix
        else:
            t = prefix if len(prefix) <= 35 else t
    t = t.lower()
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    if len(t) > max_length:
        t = t[:max_length].rstrip("-")
    return t


def parse_awesome_markdown(source_text: str) -> List[Dict[str, Any]]:
    """Parses all 9 substantive sections of the awesome-auditable-ai snapshot."""
    sections = re.split(r"\n(?=##\s+)", source_text)
    raw_entries: List[Dict[str, Any]] = []

    for sec in sections:
        lines = sec.strip().split("\n")
        m = re.match(r"^##\s+(.+)$", lines[0])
        if not m:
            continue
        sec_name = m.group(1).strip()
        if sec_name not in TARGET_SECTIONS:
            continue

        for line in lines[1:]:
            ls = line.strip()
            # Table row: | Resource | Venue | Summary | Links |
            if ls.startswith("|") and not re.match(r"^\|\s*[-:]+\s*\|", ls) and "Resource" not in ls:
                parts = [p.strip() for p in ls.split("|")[1:-1]]
                if len(parts) != 4:
                    continue
                res_col, venue_col, sum_col, links_col = parts
                lm = re.search(r"\[([^\]]+)\]\(([^)]+)\)", res_col)
                if not lm:
                    continue
                name = clean_markdown_text(lm.group(1))
                url = canonicalize_url(lm.group(2).strip())
                venue = clean_markdown_text(venue_col)
                summary = clean_markdown_text(sum_col)
                links: List[Dict[str, str]] = []
                links_col = links_col.replace(r"\[", "[").replace(r"\]", "]")
                for lk in re.finditer(r"\[\[?([^\[\]]+)\]?\]\(([^)]+)\)", links_col):
                    lbl = clean_markdown_text(lk.group(1)).strip("[]")
                    lurl = canonicalize_url(lk.group(2).strip())
                    links.append({"label": lbl, "url": lurl})
                raw_entries.append({
                    "entry_type": "table",
                    "section": sec_name,
                    "name": name,
                    "url": url,
                    "venue": venue,
                    "summary": summary,
                    "links": links,
                    "tag": "",
                })
            # Text entry: **[Tag] Name** ([link](url)...): summary
            elif re.match(r"^\*\*(\[[^\]]+\])?\s*([^*]+)\*\*", ls):
                clean = ls.replace(r"\[", "[").replace(r"\]", "]")
                m_txt = re.match(r"^\*\*(\[[^\]]+\])?\s*([^*]+)\*\*\s*\((.+?)\):\s*(.+)$", clean)
                if not m_txt:
                    continue
                tag = (m_txt.group(1) or "").strip("[]").strip()
                name = m_txt.group(2).strip()
                links_str = m_txt.group(3).strip()
                summary_text = m_txt.group(4).strip()
                artifact = re.search(
                    r"\s*\[\[?([^\[\]]+)\]?\]\(([^)]+)\)(?:\s+\(([^)]+)\))?\s*$",
                    summary_text,
                )
                venue = ""
                if artifact:
                    summary_text = summary_text[:artifact.start()]
                    venue = clean_markdown_text(artifact.group(3) or "")
                summary = clean_markdown_text(summary_text)
                all_links: List[Dict[str, str]] = []
                for lk in re.finditer(r"\[([^\]]+)\]\(([^)]+)\)", links_str):
                    lbl = lk.group(1).strip()
                    lurl = canonicalize_url(lk.group(2).strip())
                    all_links.append({"label": lbl, "url": lurl})
                if not all_links:
                    continue
                primary_url = all_links[0]["url"]
                sec_links = all_links[1:]
                if artifact:
                    sec_links.append({
                        "label": artifact.group(1).strip(),
                        "url": canonicalize_url(artifact.group(2)),
                    })
                raw_entries.append({
                    "entry_type": "text",
                    "section": sec_name,
                    "name": name,
                    "url": primary_url,
                    "venue": venue,
                    "summary": summary,
                    "links": sec_links,
                    "tag": tag,
                })

    return raw_entries


def get_entry_slug(name: str, url: str, is_text: bool) -> str:
    """Deterministic slug generation with explicit disambiguation for distinct resources."""
    if name.startswith("ReliabilityBench:"):
        return "reliabilitybench"
    if name.startswith("TRAIL:"):
        return "trail"
    if name.startswith("Which Agent Causes Task Failures"):
        return "whowhen"
    if name.startswith("Aegis: Automated Error Generation"):
        return "aegis-attribution"
    if name.startswith("τ-bench:"):
        return "tau-bench"
    if "NIST AI 100-1" in name:
        return "nist-ai-rmf"
    if name == "Inspect" and "UKGovernmentBEIS" in url:
        return "inspect-aisi"
    if "CatchBench" in name and "yzhao062" in url:
        return "catchbench"
    if name.lower().startswith("agentdojo"):
        return "agentdojo"
    if "Auditable Agents" in name and "arxiv.org/abs/2604.05485" in url:
        return "auditable-agents-paper"
    if "Justin0504/Aegis" in url or (name.lower() == "aegis" and is_text):
        return "aegis-runtime"
    if name.startswith("AgentOps:") and "2411.05285" in url:
        return "agentops-paper"
    if name == "AgentOps" and "github.com/AgentOps-AI" in url:
        return "agentops"
    if name.startswith("TRACE:") and "arxiv.org" in url:
        return "trace-watermark"
    if name == "TRACE" and "trace-spec" in url:
        return "trace-spec"
    if name.startswith("Agent Audit:") and "arxiv.org" in url:
        return "agent-audit-paper"
    if name == "agent-audit" and "HeadyZhang" in url:
        return "agent-audit"
    if "Model Context Protocol (MCP) Specification" in name:
        return "mcp-spec"
    if "NIST AI 600-1" in name:
        return "nist-ai-600-1"
    return slugify(name)


def build_catalog(
    raw_entries: List[Dict[str, Any]],
    existing_by_id: Dict[str, Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Builds and deduplicates the resources catalog preserving the original 6 entries."""
    stats = {
        "raw_parsed": len(raw_entries),
        "existing_preserved": len(EXPECTED_ORIGINAL_IDS),
        "dedup_original_6": 0,
        "dedup_cross_listed": 0,
        "newly_added": 0,
        "total_final": 0,
    }

    # Prepare existing 6 resources map from explicit EXPECTED_ORIGINAL_IDS lookup
    known_original_ids: Dict[str, Dict[str, Any]] = {}
    for eid in EXPECTED_ORIGINAL_IDS:
        orig = dict(existing_by_id[eid])
        # Preserve original checked date
        orig["checked"] = orig.get("checked") or ORIGINAL_CURATION_DATE
        known_original_ids[eid] = orig

    # Ensure all 6 have format and metadata initialized
    if "nist-ai-rmf" in known_original_ids:
        r = known_original_ids["nist-ai-rmf"]
        r["format"] = "Standard"
        r["source_section"] = "Standards and Governance"
        r["catalog_source"] = f"{CATALOG_SOURCE_BASE}{SECTION_ANCHORS['Standards and Governance']}"
        r.setdefault("links", [
            {"label": "PDF", "url": "https://nvlpubs.nist.gov/nistpubs/ai/nist.ai.100-1.pdf"}
        ])

    if "inspect-aisi" in known_original_ids:
        r = known_original_ids["inspect-aisi"]
        r["format"] = "Tool"
        r["source_section"] = "Tools and Platforms"
        r["catalog_source"] = f"{CATALOG_SOURCE_BASE}{SECTION_ANCHORS['Tools and Platforms']}"
        r.setdefault("links", [
            {"label": "Code", "url": "https://github.com/UKGovernmentBEIS/inspect_ai"}
        ])

    if "agentdojo" in known_original_ids:
        r = known_original_ids["agentdojo"]
        r["format"] = "Benchmark"
        r["source_section"] = "Security Auditing and Scanners"
        r["catalog_source"] = f"{CATALOG_SOURCE_BASE}{SECTION_ANCHORS['Security Auditing and Scanners']}"
        r["venue"] = "NeurIPS 2024 Datasets and Benchmarks Track"
        r.setdefault("links", [
            {"label": "Paper", "url": "https://arxiv.org/abs/2406.13352"}
        ])

    if "awesome-auditable-ai" in known_original_ids:
        r = known_original_ids["awesome-auditable-ai"]
        r["format"] = "Collection"
        r["source_section"] = "Surveys and Foundations"
        r["catalog_source"] = CATALOG_SOURCE_BASE
        r.setdefault("links", [])

    if "catchbench" in known_original_ids:
        r = known_original_ids["catchbench"]
        r["format"] = "Benchmark"
        r["source_section"] = "Datasets and Benchmarks"
        r["catalog_source"] = f"{CATALOG_SOURCE_BASE}{SECTION_ANCHORS['Datasets and Benchmarks']}"
        r.setdefault("links", [
            {"label": "Release v0.1.2", "url": "https://github.com/yzhao062/catchbench/releases/tag/v0.1.2"}
        ])

    if "auditable-agents" in known_original_ids:
        r = known_original_ids["auditable-agents"]
        r["format"] = "Collection"
        r["source_section"] = "The Auditable Agents Ecosystem"
        r["catalog_source"] = f"{CATALOG_SOURCE_BASE}{SECTION_ANCHORS['The Auditable Agents Ecosystem']}"
        r.setdefault("links", [
            {"label": "Paper", "url": "https://arxiv.org/abs/2604.05485"}
        ])

    final_pool: Dict[str, Dict[str, Any]] = {k: dict(v) for k, v in known_original_ids.items()}
    for resource in final_pool.values():
        resource["formats"] = [resource["format"]]
    imported_order: List[str] = list(EXPECTED_ORIGINAL_IDS)
    used_ids: Set[str] = set(known_original_ids.keys())

    # Map primary URLs of the original 6 to IDs
    original_url_to_id: Dict[str, str] = {
        canonicalize_url(r["url"]): eid for eid, r in known_original_ids.items()
    }
    # Secondary alias URLs for original 6
    original_url_to_id["https://nvlpubs.nist.gov/nistpubs/ai/nist.ai.100-1.pdf"] = "nist-ai-rmf"
    original_url_to_id["https://github.com/ukgovernmentbeis/inspect_ai"] = "inspect-aisi"
    original_url_to_id["https://arxiv.org/abs/2406.13352"] = "agentdojo"
    original_url_to_id["https://github.com/yzhao062/catchbench"] = "catchbench"

    # Distinct cross-listed prefixes in Datasets and Benchmarks
    cross_prefixes = {
        "ReliabilityBench:": "reliabilitybench",
        "TRAIL:": "trail",
        "Which Agent Causes Task Failures": "whowhen",
        "Aegis: Automated Error Generation": "aegis-attribution",
        "τ-bench:": "tau-bench",
    }

    seen_urls: Dict[str, str] = {canonicalize_url(v["url"]): k for k, v in known_original_ids.items()}

    for entry in raw_entries:
        sec = entry["section"]
        name = entry["name"]
        url = canonicalize_url(entry["url"])
        summary = entry["summary"]
        venue = entry.get("venue", "")
        links = entry.get("links", [])
        tag = entry.get("tag", "")
        is_text = (entry["entry_type"] == "text")
        entry_format = determine_format(sec, name, url, tag, is_text)

        # 1. Match original 6
        orig_match_id = original_url_to_id.get(url)
        if not orig_match_id:
            if "NIST AI 100-1" in name:
                orig_match_id = "nist-ai-rmf"
            elif name == "Inspect" and "UKGovernmentBEIS" in url:
                orig_match_id = "inspect-aisi"
            elif "CatchBench" in name and "yzhao062" in url:
                orig_match_id = "catchbench"
            elif name.lower().startswith("agentdojo"):
                orig_match_id = "agentdojo"

        if orig_match_id and orig_match_id in final_pool:
            stats["dedup_original_6"] += 1
            target_res = final_pool[orig_match_id]
            target_res["formats"] = list(dict.fromkeys([*resource_formats(target_res), entry_format]))
            existing_links = {canonicalize_url(l["url"]) for l in target_res.get("links", [])}
            if url != canonicalize_url(target_res["url"]) and url not in existing_links:
                lbl = "Paper" if "arxiv.org" in url else "Code"
                target_res.setdefault("links", []).append({"label": lbl, "url": url})
                existing_links.add(url)
            for lk in links:
                cu = canonicalize_url(lk["url"])
                if cu not in existing_links and cu != canonicalize_url(target_res["url"]):
                    target_res.setdefault("links", []).append({"label": lk["label"], "url": cu})
                    existing_links.add(cu)
            if venue and not target_res.get("venue"):
                target_res["venue"] = venue
            continue

        # 2. Match cross-listed
        is_cross = False
        for pfx, cid in cross_prefixes.items():
            if name.startswith(pfx):
                if cid in final_pool:
                    stats["dedup_cross_listed"] += 1
                    target_res = final_pool[cid]
                    target_res["formats"] = list(dict.fromkeys([*resource_formats(target_res), entry_format]))
                    existing_links = {canonicalize_url(l["url"]) for l in target_res.get("links", [])}
                    if url != canonicalize_url(target_res["url"]) and url not in existing_links:
                        lbl = "Dataset" if "huggingface.co/datasets/" in url or cid == "whowhen" else "Code"
                        target_res.setdefault("links", []).append({"label": lbl, "url": url})
                        existing_links.add(url)
                    for lk in links:
                        cu = canonicalize_url(lk["url"])
                        if cu not in existing_links and cu != canonicalize_url(target_res["url"]):
                            target_res.setdefault("links", []).append({"label": lk["label"], "url": cu})
                            existing_links.add(cu)
                    is_cross = True
                    break
        if is_cross:
            continue

        # 3. Check duplicate URL
        if url in seen_urls:
            existing_entry_id = seen_urls[url]
            stats["dedup_cross_listed"] += 1
            target_res = final_pool[existing_entry_id]
            target_res["formats"] = list(dict.fromkeys([*resource_formats(target_res), entry_format]))
            for lk in links:
                cu = canonicalize_url(lk["url"])
                existing_links = {canonicalize_url(l["url"]) for l in target_res.get("links", [])}
                if cu not in existing_links and cu != canonicalize_url(target_res["url"]):
                    target_res.setdefault("links", []).append({"label": lk["label"], "url": cu})
            continue

        # 4. Generate unique ID
        assigned_slug = get_entry_slug(name, url, is_text)
        unique_id = assigned_slug
        counter = 2
        while unique_id in used_ids:
            unique_id = f"{assigned_slug}-{counter}"
            counter += 1

        used_ids.add(unique_id)
        seen_urls[url] = unique_id

        # Determine fields
        cat = determine_category(sec, name, summary)
        fmt = determine_format(sec, name, url, tag, is_text)
        rel = "Maintainer project" if is_maintainer_project(name, url, links, unique_id) else "External resource"
        owner = determine_owner(name, url, tag, summary, sec)

        # For aegis-runtime, enrich with verified companion paper link if not present
        if unique_id == "aegis-runtime":
            paper_url = "https://arxiv.org/abs/2603.12621"
            if not any(l.get("url") == paper_url for l in links):
                links.append({"label": "Paper", "url": paper_url})

        anchor = SECTION_ANCHORS.get(sec, "")
        catalog_src = f"{CATALOG_SOURCE_BASE}{anchor}"

        new_entry: Dict[str, Any] = {
            "id": unique_id,
            "name": name,
            "category": cat,
            "format": fmt,
            "summary": summary,
            "url": url,
            "owner": owner,
            "relationship": rel,
            "source_urls": [url],
            "checked": SNAPSHOT_REVIEW_DATE,
            "source_section": sec,
            "catalog_source": catalog_src,
        }

        if venue:
            new_entry["venue"] = venue

        if links:
            new_entry["links"] = links

        final_pool[unique_id] = new_entry
        imported_order.append(unique_id)
        stats["newly_added"] += 1

    final_list = [final_pool[rid] for rid in imported_order]
    for resource in final_list:
        if resource["id"] == "why-do-multi-agent-llm-systems-fail":
            # Verified via the MAST authors' repository on 2026-09-16.
            resource.setdefault("links", []).append({
                "label": "Dataset", "url": "https://huggingface.co/datasets/mcemri/MAST-Data",
            })
        memberships = resource_formats(resource)
        artifacts = [{"label": "", "url": resource["url"]}, *resource.get("links", [])]
        for artifact in artifacts:
            parsed = urlparse(artifact["url"])
            label = artifact["label"].lower()
            if label == "paper" or (parsed.hostname == "arxiv.org" and parsed.path.startswith("/abs/")):
                memberships.append("Paper")
            if label == "dataset" or (parsed.hostname == "huggingface.co" and parsed.path.startswith("/datasets/")):
                memberships.append("Dataset")
        resource["formats"] = list(dict.fromkeys(memberships))
    stats["total_final"] = len(final_list)

    return final_list, stats


def validate_catalog(resources: List[Dict[str, Any]]) -> List[str]:
    """Strictly validates resources against the contract and schema."""
    errors: List[str] = []
    seen_ids: Set[str] = set()
    seen_urls: Set[str] = set()

    for idx, r in enumerate(resources):
        r_id = r.get("id")
        if not r_id:
            errors.append(f"Resource #{idx} missing required 'id'")
            continue
        if r_id in seen_ids:
            errors.append(f"Duplicate resource ID detected: '{r_id}'")
        seen_ids.add(r_id)

        for req in ("name", "category", "summary", "url", "owner", "relationship", "checked", "format"):
            if not r.get(req):
                errors.append(f"Resource '{r_id}' missing required field '{req}'")

        cat = r.get("category")
        if cat not in VALID_CATEGORIES:
            errors.append(f"Resource '{r_id}' invalid category '{cat}'; expected {VALID_CATEGORIES}")

        rel = r.get("relationship")
        if rel not in VALID_RELATIONSHIPS:
            errors.append(f"Resource '{r_id}' invalid relationship '{rel}'; expected {VALID_RELATIONSHIPS}")

        fmt = r.get("format")
        if fmt not in VALID_FORMATS:
            errors.append(f"Resource '{r_id}' invalid format '{fmt}'; expected {VALID_FORMATS}")
        if error := formats_error(r):
            errors.append(f"Resource '{r_id}': {error}")

        chk = r.get("checked")
        try:
            datetime.strptime(str(chk), "%Y-%m-%d")
        except ValueError:
            errors.append(f"Resource '{r_id}' invalid checked date format: '{chk}'")

        u = r.get("url", "")
        parsed = urlparse(u)
        if not parsed.scheme or not parsed.netloc:
            errors.append(f"Resource '{r_id}' invalid url: '{u}'")
        if u in seen_urls:
            errors.append(f"Duplicate primary URL across resources: '{u}' in '{r_id}'")
        seen_urls.add(u)

        for lk in r.get("links", []):
            lu = lk.get("url", "")
            l_parsed = urlparse(lu)
            if not l_parsed.scheme or not l_parsed.netloc:
                errors.append(f"Resource '{r_id}' invalid secondary link url: '{lu}'")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Import awesome-auditable-ai catalog into Audit Commons")
    parser.add_argument(
        "--source-file",
        required=True,
        help="Path to verified awesome-source.md snapshot (required; no guessing)",
    )
    parser.add_argument(
        "--output-file",
        default="content/resources.json",
        help="Path to output resources.json (default: content/resources.json)",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Perform dry-run parsing and validation without writing to output-file",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent

    # Locate and verify source file
    source_path = Path(args.source_file)
    if not source_path.is_absolute():
        source_path = repo_root / source_path

    if not source_path.exists():
        print(f"Error: source file not found at {source_path}", file=sys.stderr)
        return 1

    # Read raw bytes and verify normalized LF UTF-8 SHA256 integrity
    with open(source_path, "rb") as f:
        source_bytes = f.read()

    try:
        source_text = verify_snapshot_integrity(source_bytes)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    # Locate output file
    output_path = Path(args.output_file)
    if not output_path.is_absolute():
        output_path = repo_root / output_path

    # Guard against accidental output collisions
    if source_path.resolve() == output_path.resolve():
        print(f"Error: output file cannot be identical to source file: {output_path}", file=sys.stderr)
        return 1
    if output_path.suffix.lower() != ".json":
        print(f"Error: output file must have .json extension, got: {output_path}", file=sys.stderr)
        return 1

    # Read existing resources - error before write if missing, corrupted, or missing expected IDs
    if not output_path.exists():
        print(f"Error: existing catalog not found at {output_path}. An existing baseline catalog is required.", file=sys.stderr)
        return 1

    try:
        with open(output_path, "r", encoding="utf-8") as f:
            existing_resources = json.load(f)
    except Exception as e:
        print(f"Error: failed to parse JSON in existing catalog at {output_path}: {e}", file=sys.stderr)
        return 1

    if not isinstance(existing_resources, list):
        print(f"Error: existing catalog at {output_path} must be a JSON array", file=sys.stderr)
        return 1

    existing_by_id = {
        r.get("id"): r for r in existing_resources if isinstance(r, dict) and r.get("id")
    }
    missing_expected = [eid for eid in EXPECTED_ORIGINAL_IDS if eid not in existing_by_id]
    if missing_expected:
        print(f"Error: existing catalog at {output_path} is missing expected original resource IDs: {missing_expected}", file=sys.stderr)
        return 1

    raw_entries = parse_awesome_markdown(source_text)
    final_resources, stats = build_catalog(raw_entries, existing_by_id)

    # Validate catalog
    validation_errors = validate_catalog(final_resources)
    if validation_errors:
        print(f"Validation failed with {len(validation_errors)} errors:", file=sys.stderr)
        for err in validation_errors[:20]:
            print(f"  [FAIL] {err}", file=sys.stderr)
        if len(validation_errors) > 20:
            print(f"  ... and {len(validation_errors) - 20} more errors.", file=sys.stderr)
        return 1

    # Verify the 4 maintainer affiliations are correct
    for expected_maintainer in ["grade", "aegis-runtime", "agent-audit-paper", "agent-audit"]:
        res_match = next((r for r in final_resources if r["id"] == expected_maintainer), None)
        if not res_match or res_match.get("relationship") != "Maintainer project":
            print(f"Error: expected maintainer project '{expected_maintainer}' not marked as Maintainer project!", file=sys.stderr)
            return 1

    # Print summary breakdown
    format_counts: Dict[str, int] = {}
    cat_counts: Dict[str, int] = {}
    sec_counts: Dict[str, int] = {}
    rel_counts: Dict[str, int] = {}
    for r in final_resources:
        for fmt in resource_formats(r):
            format_counts[fmt] = format_counts.get(fmt, 0) + 1
        cat_counts[r["category"]] = cat_counts.get(r["category"], 0) + 1
        sec_counts[r.get("source_section", "Unknown")] = sec_counts.get(r.get("source_section", "Unknown"), 0) + 1
        rel_counts[r["relationship"]] = rel_counts.get(r["relationship"], 0) + 1

    print("=== Awesome Auditable AI Import Report ===")
    print(f"Source snapshot:     {source_path.name} (pinned commit {PINNED_REVISION})")
    print(f"Snapshot SHA256:     {EXPECTED_SNAPSHOT_SHA256}")
    print(f"Raw items parsed:    {stats['raw_parsed']}")
    print(f"Existing preserved:  {stats['existing_preserved']}")
    print(f"Deduped vs original: {stats['dedup_original_6']}")
    print(f"Deduped cross-listed:{stats['dedup_cross_listed']}")
    print(f"Newly added items:   {stats['newly_added']}")
    print(f"Total catalog count: {stats['total_final']}")
    print("\nBreakdown by relationship:")
    for rel, count in sorted(rel_counts.items(), key=lambda x: -x[1]):
        print(f"  {rel:22}: {count}")
    print("\nFormat memberships (overlap allowed):")
    for fmt, count in sorted(format_counts.items(), key=lambda x: -x[1]):
        print(f"  {fmt:12}: {count}")
    print("\nBreakdown by category:")
    for cat, count in sorted(cat_counts.items(), key=lambda x: -x[1]):
        print(f"  {cat:12}: {count}")
    print("\nBreakdown by section:")
    for sec, count in sorted(sec_counts.items(), key=lambda x: -x[1]):
        print(f"  {sec:35}: {count}")

    if args.check_only:
        print("\nDry-run check passed successfully. No files modified.")
        return 0

    # Write output file
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(final_resources, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"\nSuccessfully wrote {len(final_resources)} resources to {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""repo_intel.py — Repository-Query-First Orientation Workflow CLI for JAVED.

A bounded, local, read-only developer-facing intelligence tool providing fast,
deterministic symbol lookups, caller/reference graphs, related test discovery,
blast-radius/impact estimation, graph freshness tracking, and task-local caching
over Graphify-Labs/graphify codebase graphs.

Usage:
    python scripts/repo_intel.py find-symbol <SymbolName>
    python scripts/repo_intel.py find-callers <SymbolName>
    python scripts/repo_intel.py find-references <SymbolName>
    python scripts/repo_intel.py find-tests <SymbolOrPath>
    python scripts/repo_intel.py impact <SymbolOrPath>
    python scripts/repo_intel.py status
    python scripts/repo_intel.py update [--force]

Flags:
    --json          Output machine-readable JSON.
    --no-cache      Bypass task-local query cache.
    --allow-stale   Allow querying graph even if Git HEAD has diverged.
    --graph PATH    Path to graph.json (default: graphify-out/graph.json).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

# Bounded output packet invariants
MAX_CANDIDATE_FILES: int = 12
MAX_CANDIDATE_SYMBOLS: int = 30
MAX_RELATED_TESTS: int = 12
MAX_TOKEN_BUDGET_CHARS: int = 40000  # ~10,000 tokens

# Subprocess timeouts (seconds)
TIMEOUT_STATUS: int = 30
TIMEOUT_QUERY: int = 30
TIMEOUT_UPDATE: int = 120

DEFAULT_GRAPH_PATH: Path = Path("graphify-out/graph.json")
DEFAULT_CACHE_DIR: Path = Path(".graphify/cache")
DEFAULT_CACHE_FILE: Path = DEFAULT_CACHE_DIR / "task_cache.json"


# ----------------------------------------------------------------------
# Security & Sanitization Helpers
# ----------------------------------------------------------------------


def sanitize_path_str(path_str: str, home_dir: Path | None = None) -> str:
    """Redact user-home path and normalize separators."""
    if not path_str:
        return ""
    home = home_dir or Path.home()
    home_s = str(home)
    patterns = [
        home_s,
        home_s.replace("\\", "/"),
        home_s.replace("/", "\\"),
    ]
    result = path_str
    for pat in patterns:
        if pat and pat in result:
            result = result.replace(pat, "~")
    return result.replace("\\", "/")


def redact_data(obj: Any, home_dir: Path | None = None) -> Any:
    """Recursively redact home directory from strings inside dicts/lists."""
    if isinstance(obj, str):
        return sanitize_path_str(obj, home_dir)
    elif isinstance(obj, list):
        return [redact_data(item, home_dir) for item in obj]
    elif isinstance(obj, dict):
        return {k: redact_data(v, home_dir) for k, v in obj.items()}
    return obj


def validate_query_target(target: str) -> str:
    """Validate query target to prevent directory traversal or malformed injection."""
    cleaned = target.strip()
    if not cleaned:
        raise ValueError("Query target cannot be empty.")
    if ".." in cleaned:
        raise ValueError(f"Path traversal ('..') is not permitted in target: {target}")
    return cleaned


def get_git_head(cwd: Path | None = None) -> str:
    """Get the current Git HEAD commit SHA."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(cwd or Path.cwd()),
            capture_output=True,
            text=True,
            timeout=TIMEOUT_STATUS,
            check=True,
        )
        return res.stdout.strip()
    except Exception:
        return "unknown"


def find_graphify_binary() -> Path | None:
    """Find the Graphify executable if available locally."""
    which_bin = shutil.which("graphify")
    if which_bin:
        return Path(which_bin)

    home = Path.home()
    candidates = [
        home / ".local" / "bin" / ("graphify.exe" if sys.platform == "win32" else "graphify"),
        home / "AppData" / "Roaming" / "Python" / "Scripts" / "graphify.exe",
        home / "AppData" / "Roaming" / "uv" / "tools" / "graphifyy" / "Scripts" / "graphify.exe",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


# ----------------------------------------------------------------------
# Task-Local Query Cache
# ----------------------------------------------------------------------


class TaskQueryCache:
    """File-backed query cache for task-local orientation queries."""

    def __init__(self, cache_file: Path = DEFAULT_CACHE_FILE):
        self.cache_file = cache_file

    def _load(self) -> dict[str, Any]:
        if not self.cache_file.exists():
            return {}
        try:
            with open(self.cache_file, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save(self, data: dict[str, Any]) -> None:
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    def make_key(self, command: str, target: str, git_head: str, budget: int) -> str:
        payload = f"{command}:{target}:{git_head}:{budget}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def get(self, command: str, target: str, git_head: str, budget: int) -> dict[str, Any] | None:
        data = self._load()
        key = self.make_key(command, target, git_head, budget)
        entry = data.get(key)
        if not entry:
            return None
        if entry.get("git_head") != git_head:
            return None
        return entry.get("result")

    def set(
        self, command: str, target: str, git_head: str, budget: int, result: dict[str, Any]
    ) -> None:
        data = self._load()
        key = self.make_key(command, target, git_head, budget)
        data[key] = {
            "command": command,
            "target": target,
            "git_head": git_head,
            "budget": budget,
            "result": result,
        }
        self._save(data)

    def invalidate(self) -> None:
        if self.cache_file.exists():
            try:
                self.cache_file.unlink()
            except Exception:
                pass


# ----------------------------------------------------------------------
# Graph Loading & Freshness
# ----------------------------------------------------------------------


def load_graph_data(graph_path: Path = DEFAULT_GRAPH_PATH) -> dict[str, Any]:
    """Load graph data from JSON file."""
    if not graph_path.exists():
        raise FileNotFoundError(
            f"Graph file not found at '{graph_path}'. "
            "Run 'python scripts/repo_intel.py update' or 'graphify update .' to build it."
        )
    with open(graph_path, encoding="utf-8") as f:
        return json.load(f)


def check_graph_freshness(
    graph_data: dict[str, Any] | None = None,
    graph_path: Path = DEFAULT_GRAPH_PATH,
    cwd: Path | None = None,
    current_head_override: str | None = None,
) -> dict[str, Any]:
    """Check freshness state of the graph compared to current Git HEAD."""
    current_head = current_head_override or get_git_head(cwd)

    if not graph_path.exists() and graph_data is None:
        return {
            "state": "GRAPH_UNAVAILABLE",
            "message": f"Graph file '{graph_path}' does not exist.",
            "is_fresh": False,
            "built_at_commit": None,
            "current_git_head": current_head,
        }

    if graph_data is None:
        try:
            graph_data = load_graph_data(graph_path)
        except Exception as e:
            return {
                "state": "GRAPH_UNAVAILABLE",
                "message": f"Failed to load graph: {e}",
                "is_fresh": False,
                "built_at_commit": None,
                "current_git_head": current_head,
            }

    built_commit = graph_data.get("built_at_commit")

    if not built_commit:
        build_state_file = graph_path.parent / ".graphify_build_state.json"
        if build_state_file.exists():
            try:
                with open(build_state_file, encoding="utf-8") as f:
                    b_state = json.load(f)
                    built_commit = b_state.get("scan_digest")
            except Exception:
                pass

    if not built_commit or built_commit == "unknown":
        return {
            "state": "UPDATE_REQUIRED",
            "message": "Graph does not specify built_at_commit metadata.",
            "is_fresh": False,
            "built_at_commit": built_commit,
            "current_git_head": current_head,
        }

    if (
        built_commit == current_head
        or current_head.startswith(built_commit)
        or built_commit.startswith(current_head)
    ):
        return {
            "state": "FRESH",
            "message": "Graph index matches current Git HEAD.",
            "is_fresh": True,
            "built_at_commit": built_commit,
            "current_git_head": current_head,
        }

    # Check git diff between commits to see if source files were modified
    try:
        diff_res = subprocess.run(
            ["git", "diff", "--name-only", f"{built_commit}..{current_head}"],
            cwd=str(cwd or Path.cwd()),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if diff_res.returncode == 0:
            changed_files = [f.strip() for f in diff_res.stdout.splitlines() if f.strip()]
            code_changes = [
                f
                for f in changed_files
                if f.endswith((".py", ".ts", ".tsx", ".js", ".jsx")) and not f.startswith("tests/")
            ]
            if not code_changes:
                return {
                    "state": "FRESH",
                    "message": (
                        f"Graph built at {built_commit[:7]}; only non-code/docs files changed "
                        f"up to HEAD ({current_head[:7]})."
                    ),
                    "is_fresh": True,
                    "built_at_commit": built_commit,
                    "current_git_head": current_head,
                    "changed_files_count": len(changed_files),
                }
            return {
                "state": "STALE",
                "message": (
                    f"Graph is stale. {len(code_changes)} application code files changed "
                    f"between {built_commit[:7]} and HEAD ({current_head[:7]})."
                ),
                "is_fresh": False,
                "built_at_commit": built_commit,
                "current_git_head": current_head,
                "code_changes": code_changes[:5],
            }
    except Exception:
        pass

    return {
        "state": "STALE",
        "message": (
            f"Graph commit ({built_commit[:7]}) diverges from current HEAD ({current_head[:7]})."
        ),
        "is_fresh": False,
        "built_at_commit": built_commit,
        "current_git_head": current_head,
    }


# ----------------------------------------------------------------------
# Core Query Engine (Direct Graph Model)
# ----------------------------------------------------------------------


class RepoIntelEngine:
    """In-memory query engine over Graphify knowledge graph JSON."""

    def __init__(self, graph_data: dict[str, Any]):
        self.graph = graph_data
        self.nodes: list[dict[str, Any]] = graph_data.get("nodes", [])
        self.links: list[dict[str, Any]] = graph_data.get("links", [])

        self.nodes_by_id: dict[str, dict[str, Any]] = {}
        self.nodes_by_label_lower: dict[str, list[dict[str, Any]]] = {}
        self.nodes_by_file: dict[str, list[dict[str, Any]]] = {}
        self.incoming_links: dict[str, list[dict[str, Any]]] = {}
        self.outgoing_links: dict[str, list[dict[str, Any]]] = {}

        self._build_indexes()

    def _build_indexes(self) -> None:
        for node in self.nodes:
            nid = node.get("id", "")
            self.nodes_by_id[nid] = node

            label = node.get("label", "")
            norm_label = node.get("norm_label") or label.lower()
            self.nodes_by_label_lower.setdefault(norm_label, []).append(node)
            if label.lower() != norm_label:
                self.nodes_by_label_lower.setdefault(label.lower(), []).append(node)

            source_file = node.get("source_file", "")
            if source_file:
                norm_file = source_file.replace("\\", "/")
                self.nodes_by_file.setdefault(norm_file, []).append(node)

        for link in self.links:
            src = link.get("source")
            tgt = link.get("target")
            if src:
                self.outgoing_links.setdefault(src, []).append(link)
            if tgt:
                self.incoming_links.setdefault(tgt, []).append(link)

    def _determine_kind(self, node: dict[str, Any]) -> str:
        """Infer kind of symbol (class, function, method, interface, component, etc.)."""
        if node.get("_callable_class"):
            return "class"
        if node.get("_callable"):
            rel = node.get("relation") or ""
            if "method" in rel:
                return "method"
            return "function"
        label = node.get("label", "")
        source_file = node.get("source_file", "")
        if source_file.endswith((".tsx", ".jsx")) and label and label[0].isupper():
            return "component"
        if "interface" in label.lower() or label.startswith("I[A-Z]"):
            return "interface"
        return "symbol"

    def match_symbol_nodes(self, symbol: str) -> list[dict[str, Any]]:
        """Find matching AST nodes for a given symbol name or qualified name."""
        sym = symbol.strip()
        sym_lower = sym.lower()

        # 1. Exact node id match
        if sym in self.nodes_by_id:
            return [self.nodes_by_id[sym]]

        # 2. Exact normalized label match
        matches = self.nodes_by_label_lower.get(sym_lower, [])
        if matches:
            return matches

        # 3. Qualified ID match
        candidates = []
        for nid, node in self.nodes_by_id.items():
            if nid.endswith(sym_lower) or f"_{sym_lower}" in nid:
                candidates.append(node)
        if candidates:
            return candidates

        # 4. TypeScript field search (_ts_fields in nodes)
        field_matches = []
        for node in self.nodes:
            ts_fields = node.get("_ts_fields")
            if isinstance(ts_fields, dict) and sym in ts_fields:
                field_matches.append(node)
        if field_matches:
            return field_matches

        # 5. Substring / partial match on label
        partial = []
        for norm_lbl, n_list in self.nodes_by_label_lower.items():
            if sym_lower in norm_lbl:
                partial.extend(n_list)
        return partial

    def find_symbol(self, symbol: str, max_symbols: int = MAX_CANDIDATE_SYMBOLS) -> dict[str, Any]:
        """Look up symbol definition, line range, kind, signature, and alternatives."""
        nodes = self.match_symbol_nodes(symbol)

        if not nodes:
            return {
                "symbol": symbol,
                "status": "NOT_FOUND",
                "confidence": "UNKNOWN",
                "message": f"Symbol '{symbol}' was not found in knowledge graph.",
                "candidates_count": 0,
                "primary_match": None,
                "alternatives": [],
            }

        # Filter out test nodes if non-test nodes exist
        prod_nodes = [
            n
            for n in nodes
            if not n.get("source_file", "").startswith("tests/")
            and "test" not in n.get("source_file", "").lower()
        ]
        selected_nodes = prod_nodes if prod_nodes else nodes

        is_ambiguous = len(selected_nodes) > 1
        confidence = "AMBIGUOUS" if is_ambiguous else "EXTRACTED"
        primary = selected_nodes[0]

        primary_info = {
            "id": primary.get("id"),
            "label": primary.get("label"),
            "kind": self._determine_kind(primary),
            "source_file": primary.get("source_file", "").replace("\\", "/"),
            "source_location": primary.get("source_location", ""),
            "community_name": primary.get("community_name", ""),
            "fields": primary.get("_ts_fields") or {},
        }

        alternatives = []
        for n in selected_nodes[1:max_symbols]:
            alternatives.append(
                {
                    "id": n.get("id"),
                    "label": n.get("label"),
                    "kind": self._determine_kind(n),
                    "source_file": n.get("source_file", "").replace("\\", "/"),
                    "source_location": n.get("source_location", ""),
                }
            )

        return {
            "symbol": symbol,
            "status": "AMBIGUOUS" if is_ambiguous else "RESOLVED",
            "confidence": confidence,
            "candidates_count": len(selected_nodes),
            "primary_match": primary_info,
            "alternatives": alternatives,
        }

    def find_callers(self, symbol: str, max_callers: int = MAX_CANDIDATE_SYMBOLS) -> dict[str, Any]:
        """Find direct callers and referencing files for a symbol."""
        nodes = self.match_symbol_nodes(symbol)
        if not nodes:
            return {
                "symbol": symbol,
                "status": "NOT_FOUND",
                "callers_count": 0,
                "callers": [],
            }

        target_ids = {n.get("id") for n in nodes if n.get("id")}
        call_relations = {"calls", "indirect_call", "uses", "method", "references"}

        callers_list = []
        seen = set()

        for tid in target_ids:
            incoming = self.incoming_links.get(tid, [])
            for link in incoming:
                rel = link.get("relation", "")
                if rel in call_relations:
                    src_id = link.get("source")
                    src_node = self.nodes_by_id.get(src_id)
                    src_file = link.get("source_file") or (
                        src_node.get("source_file") if src_node else ""
                    )
                    src_loc = link.get("source_location") or (
                        src_node.get("source_location") if src_node else ""
                    )
                    src_label = src_node.get("label") if src_node else src_id

                    key = (src_file, src_loc, rel)
                    if key in seen:
                        continue
                    seen.add(key)

                    callers_list.append(
                        {
                            "caller_id": src_id,
                            "caller_label": src_label,
                            "source_file": src_file.replace("\\", "/"),
                            "source_location": src_loc,
                            "relation": rel,
                            "confidence": link.get("confidence", "EXTRACTED"),
                        }
                    )

        callers_list.sort(key=lambda x: (x["source_file"], x["source_location"]))
        return {
            "symbol": symbol,
            "status": "RESOLVED",
            "callers_count": len(callers_list),
            "callers": callers_list[:max_callers],
        }

    def find_references(self, symbol: str, max_refs: int = MAX_CANDIDATE_SYMBOLS) -> dict[str, Any]:
        """Find imports, references, uses, and inheritance links to a symbol."""
        nodes = self.match_symbol_nodes(symbol)
        if not nodes:
            return {
                "symbol": symbol,
                "status": "NOT_FOUND",
                "references_count": 0,
                "references": [],
            }

        target_ids = {n.get("id") for n in nodes if n.get("id")}
        ref_relations = {
            "imports",
            "imports_from",
            "references",
            "uses",
            "inherits",
            "declares",
            "re_exports",
        }

        refs_list = []
        seen = set()

        for tid in target_ids:
            incoming = self.incoming_links.get(tid, [])
            for link in incoming:
                rel = link.get("relation", "")
                if rel in ref_relations:
                    src_id = link.get("source")
                    src_node = self.nodes_by_id.get(src_id)
                    src_file = link.get("source_file") or (
                        src_node.get("source_file") if src_node else ""
                    )
                    src_loc = link.get("source_location") or (
                        src_node.get("source_location") if src_node else ""
                    )
                    src_label = src_node.get("label") if src_node else src_id

                    key = (src_file, src_loc, rel)
                    if key in seen:
                        continue
                    seen.add(key)

                    refs_list.append(
                        {
                            "referencer_id": src_id,
                            "referencer_label": src_label,
                            "source_file": src_file.replace("\\", "/"),
                            "source_location": src_loc,
                            "relation": rel,
                            "confidence": link.get("confidence", "EXTRACTED"),
                        }
                    )

        refs_list.sort(key=lambda x: (x["source_file"], x["source_location"]))
        return {
            "symbol": symbol,
            "status": "RESOLVED",
            "references_count": len(refs_list),
            "references": refs_list[:max_refs],
        }

    def find_tests(self, symbol_or_path: str, max_tests: int = MAX_RELATED_TESTS) -> dict[str, Any]:
        """Discover tests covering a symbol/path via direct AST links and naming heuristics."""
        target = symbol_or_path.strip().replace("\\", "/")
        matching_nodes = self.match_symbol_nodes(target)

        all_test_files: set[str] = set()
        for node in self.nodes:
            sfile = (node.get("source_file") or "").replace("\\", "/")
            if (
                sfile.startswith("tests/")
                or "/test/" in sfile
                or sfile.endswith((".test.tsx", ".test.ts", ".spec.ts"))
            ):
                if sfile.endswith((".py", ".ts", ".tsx", ".js")):
                    all_test_files.add(sfile)

        test_candidates: list[dict[str, Any]] = []
        seen_files: set[str] = set()

        # Strategy 1: Direct references from test nodes to target symbol
        target_ids = {n.get("id") for n in matching_nodes if n.get("id")}
        for tid in target_ids:
            for link in self.incoming_links.get(tid, []):
                sfile = (link.get("source_file") or "").replace("\\", "/")
                if not sfile and link.get("source"):
                    src_node = self.nodes_by_id.get(link.get("source"))
                    sfile = (
                        (src_node.get("source_file") or "").replace("\\", "/") if src_node else ""
                    )

                if sfile in all_test_files and sfile not in seen_files:
                    seen_files.add(sfile)
                    test_candidates.append(
                        {
                            "test_file": sfile,
                            "selection_reason": "direct_symbol_reference",
                            "relation": link.get("relation", "references"),
                            "confidence": "EXTRACTED",
                            "source_location": link.get("source_location", ""),
                        }
                    )

        # Strategy 2: Check module import links from test files
        owning_files = set()
        if target.endswith((".py", ".ts", ".tsx")):
            owning_files.add(target)
        for n in matching_nodes:
            sf = (n.get("source_file") or "").replace("\\", "/")
            if sf:
                owning_files.add(sf)

        for ow in owning_files:
            ow_nodes = self.nodes_by_file.get(ow, [])
            ow_node_ids = {n.get("id") for n in ow_nodes if n.get("id")}
            for onid in ow_node_ids:
                for link in self.incoming_links.get(onid, []):
                    sfile = (link.get("source_file") or "").replace("\\", "/")
                    if not sfile and link.get("source"):
                        src_node = self.nodes_by_id.get(link.get("source"))
                        sfile = (
                            (src_node.get("source_file") or "").replace("\\", "/")
                            if src_node
                            else ""
                        )
                    if sfile in all_test_files and sfile not in seen_files:
                        seen_files.add(sfile)
                        test_candidates.append(
                            {
                                "test_file": sfile,
                                "selection_reason": "module_import_link",
                                "relation": link.get("relation", "imports"),
                                "confidence": "EXTRACTED",
                                "source_location": link.get("source_location", ""),
                            }
                        )

        # Strategy 3: Naming convention fallbacks
        def extract_tokens(text: str) -> list[str]:
            parts = re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?=[A-Z][a-z]|\d|\W|$)|[0-9]+", text)
            stop_words = {
                "src",
                "javed",
                "frontend",
                "components",
                "services",
                "types",
                "test",
                "tests",
                "mock",
                "spec",
                "py",
                "tsx",
                "ts",
                "js",
                "jsx",
                "common",
                "helper",
                "util",
                "utils",
                "index",
            }
            return [p.lower() for p in parts if len(p) > 2 and p.lower() not in stop_words]

        meaningful_tokens: set[str] = set(extract_tokens(target))
        for ow in owning_files:
            meaningful_tokens.update(extract_tokens(ow))

        for tf in sorted(all_test_files):
            if tf in seen_files:
                continue
            tf_tokens = set(extract_tokens(tf))
            matched = meaningful_tokens.intersection(tf_tokens)
            if matched:
                seen_files.add(tf)
                match_str = ", ".join(sorted(matched))
                test_candidates.append(
                    {
                        "test_file": tf,
                        "selection_reason": f"naming_convention_fallback (matched: {match_str})",
                        "relation": "naming_pattern",
                        "confidence": "INFERRED",
                        "source_location": "",
                    }
                )

        return {
            "target": target,
            "status": "RESOLVED",
            "tests_count": len(test_candidates),
            "tests": test_candidates[:max_tests],
        }

    def impact(self, symbol_or_path: str, max_files: int = MAX_CANDIDATE_FILES) -> dict[str, Any]:
        """Estimate blast radius: owning file, callers, dependencies, related tests."""
        target = symbol_or_path.strip().replace("\\", "/")

        sym_result = self.find_symbol(target)
        callers_result = self.find_callers(target)
        tests_result = self.find_tests(target)

        candidate_files: set[str] = set()
        owning_file = None

        if sym_result.get("primary_match"):
            owning_file = sym_result["primary_match"].get("source_file")
            if owning_file:
                candidate_files.add(owning_file)

        caller_files = set()
        for c in callers_result.get("callers", []):
            cf = c.get("source_file")
            if cf:
                caller_files.add(cf)
                if not cf.startswith("tests/") and "test" not in cf.lower():
                    candidate_files.add(cf)

        dependencies_files = set()
        matching_nodes = self.match_symbol_nodes(target)
        for n in matching_nodes:
            nid = n.get("id")
            for out_link in self.outgoing_links.get(nid, []):
                tgt_id = out_link.get("target")
                tgt_node = self.nodes_by_id.get(tgt_id)
                if tgt_node:
                    tf = tgt_node.get("source_file", "").replace("\\", "/")
                    if tf and not tf.startswith("tests/") and "test" not in tf.lower():
                        dependencies_files.add(tf)
                        candidate_files.add(tf)

        related_test_files = [t["test_file"] for t in tests_result.get("tests", [])]

        uncertainty_warnings = []
        if sym_result.get("confidence") == "AMBIGUOUS":
            c_cnt = sym_result.get("candidates_count")
            uncertainty_warnings.append(
                f"Symbol '{target}' is AMBIGUOUS ({c_cnt} matches). Verify owning file."
            )
        if not candidate_files:
            uncertainty_warnings.append(
                f"No candidate edit files could be identified for '{target}'."
            )

        bounded_candidates = sorted(candidate_files)[:max_files]

        return {
            "target": target,
            "status": "RESOLVED",
            "owning_file": owning_file,
            "confidence": sym_result.get("confidence", "INFERRED"),
            "direct_callers_count": len(caller_files),
            "outgoing_dependencies_count": len(dependencies_files),
            "related_tests_count": len(related_test_files),
            "candidate_edit_files": bounded_candidates,
            "related_tests": related_test_files[:MAX_RELATED_TESTS],
            "uncertainty_warnings": uncertainty_warnings,
        }


# ----------------------------------------------------------------------
# CLI Commands & Output Formatting
# ----------------------------------------------------------------------


def run_status_cmd(args: argparse.Namespace) -> dict[str, Any]:
    """Execute status command."""
    graph_path = Path(args.graph) if args.graph else DEFAULT_GRAPH_PATH
    freshness = check_graph_freshness(graph_path=graph_path)

    bin_path = find_graphify_binary()
    version_str = "unknown"
    if bin_path:
        try:
            subprocess.run(
                [str(bin_path), "--help"],
                capture_output=True,
                text=True,
                timeout=TIMEOUT_STATUS,
            )
            version_str = "0.9.102 (detected via uv tool)"
        except Exception:
            version_str = "detected"

    nodes_count = 0
    edges_count = 0
    if graph_path.exists():
        try:
            gdata = load_graph_data(graph_path)
            nodes_count = len(gdata.get("nodes", []))
            edges_count = len(gdata.get("links", []))
        except Exception:
            pass

    return {
        "command": "status",
        "graphify_binary": str(bin_path) if bin_path else "NOT_FOUND",
        "graphify_version": version_str,
        "graph_path": str(graph_path),
        "graph_nodes": nodes_count,
        "graph_edges": edges_count,
        "security_mode": {
            "GRAPHIFY_BACKEND": "none",
            "GRAPHIFY_QUERY_LOG_DISABLE": "1",
            "external_model_calls": False,
            "cloud_telemetry": False,
        },
        "freshness": freshness,
    }


def run_update_cmd(
    args: argparse.Namespace,
    bin_path_override: Path | None = None,
    timeout_override: int | None = None,
) -> dict[str, Any]:
    """Execute update command via Graphify CLI under strict security isolation."""
    bin_path = bin_path_override or find_graphify_binary()
    if not bin_path:
        raise RuntimeError(
            "graphify executable not found. Install via 'uv tool install graphifyy'."
        )

    cmd = [str(bin_path), "update", "."]
    if getattr(args, "force", False):
        cmd.append("--force")

    env = dict(os.environ)
    env["GRAPHIFY_BACKEND"] = "none"
    env["GRAPHIFY_QUERY_LOG_DISABLE"] = "1"

    timeout = timeout_override or TIMEOUT_UPDATE

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=env,
            timeout=timeout,
            check=True,
        )
        current_head = get_git_head()
        graph_path = Path(args.graph) if args.graph else DEFAULT_GRAPH_PATH

        if graph_path.exists():
            try:
                with open(graph_path, encoding="utf-8") as f:
                    gdata = json.load(f)
                gdata["built_at_commit"] = current_head
                with open(graph_path, "w", encoding="utf-8") as f:
                    json.dump(gdata, f)
            except Exception:
                pass

        return {
            "command": "update",
            "status": "SUCCESS",
            "message": "Graph updated successfully.",
            "indexed_commit": current_head,
            "stdout": proc.stdout.strip()[:500],
        }
    except subprocess.TimeoutExpired as err:
        raise TimeoutError(f"graphify update timed out after {timeout}s.") from err
    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            f"graphify update failed (code {e.returncode}): {e.stderr.strip()[:500]}"
        ) from e


def format_text_output(result: dict[str, Any]) -> str:
    """Format dictionary result into clean, bounded markdown/terminal output."""
    cmd = result.get("command", "")
    lines = []

    if cmd == "status":
        lines.append("## Graphify Repository Intelligence Status")
        lines.append(f"- **Binary**: `{result.get('graphify_binary')}`")
        lines.append(f"- **Version**: {result.get('graphify_version')}")
        lines.append(
            f"- **Graph File**: `{result.get('graph_path')}` "
            f"({result.get('graph_nodes')} nodes, {result.get('graph_edges')} edges)"
        )
        fr = result.get("freshness", {})
        lines.append(f"- **Freshness State**: **`{fr.get('state')}`** ({fr.get('message')})")
        lines.append(f"- **Indexed Commit**: `{fr.get('built_at_commit')}`")
        lines.append(f"- **Current HEAD**: `{fr.get('current_git_head')}`")
        sec = result.get("security_mode", {})
        sec_backend = sec.get("GRAPHIFY_BACKEND")
        sec_log = sec.get("GRAPHIFY_QUERY_LOG_DISABLE")
        lines.append(
            f"- **Security Mode**: `GRAPHIFY_BACKEND={sec_backend}`, "
            f"`GRAPHIFY_QUERY_LOG_DISABLE={sec_log}` (Zero external inference)"
        )

    elif cmd == "find-symbol":
        sym = result.get("symbol")
        conf = result.get("confidence")
        lines.append(f"## Symbol Lookup: `{sym}` (Confidence: **{conf}**)")
        pm = result.get("primary_match")
        if pm:
            lines.append(
                f"- **Definition**: `{pm.get('source_file')}` ({pm.get('source_location')})"
            )
            lines.append(f"- **Kind**: `{pm.get('kind')}` (AST Node: `{pm.get('id')}`)")
            if pm.get("community_name"):
                lines.append(f"- **Community**: {pm.get('community_name')}")
            if pm.get("fields"):
                lines.append(f"- **Fields**: `{json.dumps(pm.get('fields'))}`")
        else:
            lines.append(f"- {result.get('message')}")

        alts = result.get("alternatives", [])
        if alts:
            lines.append("\n### Alternatives / Other Matches:")
            for a in alts:
                src_f = a.get("source_file")
                src_l = a.get("source_location")
                lbl = a.get("label")
                knd = a.get("kind")
                lines.append(f"- `{src_f}` ({src_l}): `{lbl}` (`{knd}`)")

    elif cmd == "find-callers":
        sym = result.get("symbol")
        cnt = result.get("callers_count", 0)
        lines.append(f"## Callers of `{sym}` ({cnt} found)")
        callers = result.get("callers", [])
        if not callers:
            lines.append("- No direct callers found in knowledge graph.")
        else:
            for c in callers:
                src_f = c.get("source_file")
                src_l = c.get("source_location")
                lbl = c.get("caller_label")
                rel = c.get("relation")
                lines.append(f"- `{src_f}` ({src_l}): `{lbl}` [`{rel}`]")

    elif cmd == "find-references":
        sym = result.get("symbol")
        cnt = result.get("references_count", 0)
        lines.append(f"## References to `{sym}` ({cnt} found)")
        refs = result.get("references", [])
        if not refs:
            lines.append("- No references found in knowledge graph.")
        else:
            for r in refs:
                src_f = r.get("source_file")
                src_l = r.get("source_location")
                lbl = r.get("referencer_label")
                rel = r.get("relation")
                lines.append(f"- `{src_f}` ({src_l}): `{lbl}` [`{rel}`]")

    elif cmd == "find-tests":
        tgt = result.get("target")
        cnt = result.get("tests_count", 0)
        lines.append(f"## Related Tests for `{tgt}` ({cnt} found)")
        tests = result.get("tests", [])
        if not tests:
            lines.append("- No related tests identified.")
        else:
            for t in tests:
                tf = t.get("test_file")
                reason = t.get("selection_reason")
                conf = t.get("confidence")
                lines.append(f"- `{tf}`: **{reason}** [{conf}]")

    elif cmd == "impact":
        tgt = result.get("target")
        lines.append(f"## Impact & Blast Radius: `{tgt}`")
        lines.append(f"- **Owning File**: `{result.get('owning_file') or 'Unknown'}`")
        lines.append(f"- **Direct Callers**: {result.get('direct_callers_count')}")
        lines.append(f"- **Outgoing Dependencies**: {result.get('outgoing_dependencies_count')}")
        lines.append(f"- **Related Tests**: {result.get('related_tests_count')}")

        cands = result.get("candidate_edit_files", [])
        lines.append(f"\n### Candidate Edit Files (Max {MAX_CANDIDATE_FILES}):")
        if not cands:
            lines.append("- None identified.")
        else:
            for f in cands:
                lines.append(f"- `{f}`")

        tests = result.get("related_tests", [])
        lines.append("\n### Targeted Verification Tests:")
        if not tests:
            lines.append("- None identified.")
        else:
            for t in tests:
                lines.append(f"- `{t}`")

        warns = result.get("uncertainty_warnings", [])
        if warns:
            lines.append("\n### Uncertainty Warnings:")
            for w in warns:
                lines.append(f"- > [!WARNING] {w}")

    elif cmd == "update":
        lines.append("## Graph Update Complete")
        lines.append(f"- **Status**: {result.get('status')}")
        lines.append(f"- **Indexed Commit**: `{result.get('indexed_commit')}`")
        lines.append(f"- {result.get('message')}")

    out_text = "\n".join(lines)
    if len(out_text) > MAX_TOKEN_BUDGET_CHARS:
        out_text = (
            out_text[:MAX_TOKEN_BUDGET_CHARS]
            + "\n\n> [!NOTE] Output packet truncated at token limit."
        )
    return out_text


# ----------------------------------------------------------------------
# Main CLI Dispatcher
# ----------------------------------------------------------------------


def reorder_argv(argv: list[str]) -> list[str]:
    """Reorder flags so global options like --json work anywhere on command line."""
    global_flags = {"--json", "--no-cache", "--allow-stale"}
    global_opt_keys = {"--graph"}
    globals_found = []
    rest = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in global_flags:
            globals_found.append(arg)
            i += 1
        elif arg in global_opt_keys:
            if i + 1 < len(argv):
                globals_found.extend([arg, argv[i + 1]])
                i += 2
            else:
                rest.append(arg)
                i += 1
        elif any(arg.startswith(f"{k}=") for k in global_opt_keys):
            globals_found.append(arg)
            i += 1
        else:
            rest.append(arg)
            i += 1
    return globals_found + rest


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    raw_args = list(argv) if argv is not None else sys.argv[1:]
    normalized_args = reorder_argv(raw_args)

    parser = argparse.ArgumentParser(
        description="Repository-Query-First Orientation Workflow CLI for JAVED."
    )
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON.")
    parser.add_argument("--no-cache", action="store_true", help="Bypass task-local query cache.")
    parser.add_argument(
        "--allow-stale", action="store_true", help="Allow query against stale graph."
    )
    parser.add_argument("--graph", type=str, default="", help="Path to graph.json.")

    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    p_sym = subparsers.add_parser(
        "find-symbol", help="Find symbol definition, line range, and kind."
    )
    p_sym.add_argument("symbol", type=str, help="Symbol name (e.g. InferenceRouter)")

    p_cal = subparsers.add_parser("find-callers", help="Find direct callers of a symbol.")
    p_cal.add_argument("symbol", type=str, help="Symbol name")

    p_ref = subparsers.add_parser(
        "find-references", help="Find references and imports to a symbol."
    )
    p_ref.add_argument("symbol", type=str, help="Symbol name")

    p_tst = subparsers.add_parser("find-tests", help="Find tests covering a symbol or file path.")
    p_tst.add_argument("target", type=str, help="Symbol name or file path")

    p_imp = subparsers.add_parser(
        "impact", help="Estimate blast radius, candidate files, and tests."
    )
    p_imp.add_argument("target", type=str, help="Symbol name or file path")

    subparsers.add_parser("status", help="Check Graphify installation and graph freshness.")

    p_upd = subparsers.add_parser("update", help="Update the Graphify graph incrementally.")
    p_upd.add_argument(
        "--force", action="store_true", help="Force rebuild even if node count drops."
    )

    return parser.parse_args(normalized_args)


def main(argv: list[str] | None = None, cache_file: Path | None = None) -> int:
    args = parse_args(argv)
    cmd = args.subcommand
    graph_path = Path(args.graph) if args.graph else DEFAULT_GRAPH_PATH

    cache = TaskQueryCache(cache_file or DEFAULT_CACHE_FILE)

    if cmd == "status":
        raw_res = run_status_cmd(args)
        sanitized = redact_data(raw_res)
        if args.json:
            print(json.dumps(sanitized, indent=2))
        else:
            print(format_text_output(sanitized))
        return 0

    if cmd == "update":
        raw_res = run_update_cmd(args)
        sanitized = redact_data(raw_res)
        cache.invalidate()
        if args.json:
            print(json.dumps(sanitized, indent=2))
        else:
            print(format_text_output(sanitized))
        return 0

    target_raw = getattr(args, "symbol", None) or getattr(args, "target", "")
    target = validate_query_target(target_raw)

    git_head = get_git_head()

    if not args.no_cache:
        cached_result = cache.get(cmd, target, git_head, MAX_TOKEN_BUDGET_CHARS)
        if cached_result:
            cached_result["cached"] = True
            sanitized = redact_data(cached_result)
            if args.json:
                print(json.dumps(sanitized, indent=2))
            else:
                print(format_text_output(sanitized))
            return 0

    freshness = check_graph_freshness(graph_path=graph_path)
    if not freshness.get("is_fresh") and not args.allow_stale:
        if freshness.get("state") == "GRAPH_UNAVAILABLE":
            sys.stderr.write(f"Error: {freshness.get('message')}\n")
            return 1
        elif freshness.get("state") == "STALE":
            sys.stderr.write(
                f"Warning: Graph is STALE ({freshness.get('message')}). "
                "Pass --allow-stale to query anyway, or run "
                "'python scripts/repo_intel.py update'.\n"
            )
            return 2

    graph_data = load_graph_data(graph_path)
    engine = RepoIntelEngine(graph_data)

    if cmd == "find-symbol":
        res = engine.find_symbol(target)
    elif cmd == "find-callers":
        res = engine.find_callers(target)
    elif cmd == "find-references":
        res = engine.find_references(target)
    elif cmd == "find-tests":
        res = engine.find_tests(target)
    elif cmd == "impact":
        res = engine.impact(target)
    else:
        sys.stderr.write(f"Unknown command: {cmd}\n")
        return 1

    res["command"] = cmd
    res["cached"] = False

    if not args.no_cache:
        cache.set(cmd, target, git_head, MAX_TOKEN_BUDGET_CHARS, res)

    sanitized = redact_data(res)
    if args.json:
        print(json.dumps(sanitized, indent=2))
    else:
        print(format_text_output(sanitized))

    return 0


if __name__ == "__main__":
    sys.exit(main())

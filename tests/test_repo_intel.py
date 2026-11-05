"""test_repo_intel.py — Deterministic Unit Tests for Repository Intelligence CLI.

Verifies the 24 required test scenarios for scripts/repo_intel.py:
 1. Exact symbol lookup
 2. Qualified symbol lookup
 3. Ambiguous symbol handling
 4. Unknown symbol handling
 5. Caller lookup
 6. Reference lookup
 7. Test discovery by direct import
 8. Test discovery by naming convention fallback
 9. Test discovery for frontend component
10. Impact query for backend service
11. Impact query for frontend component
12. Impact query for shared contract/model
13. Freshness check with fresh graph
14. Freshness check with stale graph
15. Update execution preserving security env
16. Update timeout handling
17. Task cache hit
18. Task cache invalidation on commit change
19. Task cache bypass flag
20. Output bounding: max files limit
21. Output bounding: max symbols limit
22. Output bounding: token truncation defense
23. Path redaction of user home
24. Zero network/external model confirmation
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from scripts.repo_intel import (
    MAX_CANDIDATE_FILES,
    MAX_CANDIDATE_SYMBOLS,
    RepoIntelEngine,
    TaskQueryCache,
    check_graph_freshness,
    format_text_output,
    parse_args,
    redact_data,
    run_status_cmd,
    run_update_cmd,
    sanitize_path_str,
)


@pytest.fixture
def mock_graph_data() -> dict:
    """Provide a rich, controlled knowledge graph fixture covering backend, frontend, and tests."""
    return {
        "directed": False,
        "built_at_commit": "1111222233334444555566667777888899990000",
        "nodes": [
            {
                "id": "src_javed_providers_router_inferencerouter",
                "label": "InferenceRouter",
                "norm_label": "inferencerouter",
                "_callable": True,
                "_callable_class": True,
                "source_file": "src/javed/providers/router.py",
                "source_location": "L53",
            },
            {
                "id": "src_javed_extraction_tools_list_ingested_documents",
                "label": "list_ingested_documents",
                "norm_label": "list_ingested_documents",
                "_callable": True,
                "source_file": "src/javed/extraction/tools.py",
                "source_location": "L30",
            },
            {
                "id": "src_javed_extraction_storage_documentstorage",
                "label": "DocumentStorage",
                "norm_label": "documentstorage",
                "_callable": True,
                "_callable_class": True,
                "source_file": "src/javed/extraction/storage.py",
                "source_location": "L45",
            },
            {
                "id": "frontend_src_components_chat_extractionviewer",
                "label": "ExtractionViewer",
                "norm_label": "extractionviewer",
                "_callable": True,
                "source_file": "frontend/src/components/chat/ExtractionViewer.tsx",
                "source_location": "L25",
            },
            {
                "id": "frontend_src_components_chat_modelselector",
                "label": "ModelSelector",
                "norm_label": "modelselector",
                "_callable": True,
                "source_file": "frontend/src/components/chat/ModelSelector.tsx",
                "source_location": "L15",
                "_ts_fields": {"selectedProviderId": "string", "selectedModelId": "string"},
            },
            {
                "id": "src_javed_schemas_extraction_normalizeddocument",
                "label": "NormalizedDocument",
                "norm_label": "normalizeddocument",
                "_callable": True,
                "_callable_class": True,
                "source_file": "src/javed/schemas/extraction.py",
                "source_location": "L10",
            },
            # Ambiguous duplicate symbols in different modules
            {
                "id": "src_javed_module_a_helper",
                "label": "CommonHelper",
                "norm_label": "commonhelper",
                "_callable": True,
                "source_file": "src/javed/module_a.py",
                "source_location": "L10",
            },
            {
                "id": "src_javed_module_b_helper",
                "label": "CommonHelper",
                "norm_label": "commonhelper",
                "_callable": True,
                "source_file": "src/javed/module_b.py",
                "source_location": "L20",
            },
            # Callers & dependent nodes
            {
                "id": "src_javed_api_v1_chat_route",
                "label": "chat_endpoint",
                "norm_label": "chat_endpoint",
                "_callable": True,
                "source_file": "src/javed/api/v1/chat.py",
                "source_location": "L40",
            },
            # Tests
            {
                "id": "tests_test_extraction_tools_node",
                "label": "test_list_documents",
                "norm_label": "test_list_documents",
                "_callable": True,
                "source_file": "tests/test_extraction_tools.py",
                "source_location": "L15",
            },
            {
                "id": "tests_test_provider_registry_node",
                "label": "test_router_resolution",
                "norm_label": "test_router_resolution",
                "_callable": True,
                "source_file": "tests/test_provider_registry.py",
                "source_location": "L320",
            },
            {
                "id": "frontend_src_test_extraction_test_node",
                "label": "test_extraction_viewer_render",
                "norm_label": "test_extraction_viewer_render",
                "_callable": True,
                "source_file": "frontend/src/test/extraction.test.tsx",
                "source_location": "L50",
            },
        ],
        "links": [
            # Callers
            {
                "source": "src_javed_api_v1_chat_route",
                "target": "src_javed_providers_router_inferencerouter",
                "relation": "calls",
                "confidence": "EXTRACTED",
                "source_file": "src/javed/api/v1/chat.py",
                "source_location": "L45",
            },
            # Dependency
            {
                "source": "src_javed_extraction_tools_list_ingested_documents",
                "target": "src_javed_extraction_storage_documentstorage",
                "relation": "uses",
                "confidence": "EXTRACTED",
                "source_file": "src/javed/extraction/tools.py",
                "source_location": "L35",
            },
            # Direct Test reference
            {
                "source": "tests_test_extraction_tools_node",
                "target": "src_javed_extraction_tools_list_ingested_documents",
                "relation": "calls",
                "confidence": "EXTRACTED",
                "source_file": "tests/test_extraction_tools.py",
                "source_location": "L18",
            },
            # Provider test reference
            {
                "source": "tests_test_provider_registry_node",
                "target": "src_javed_providers_router_inferencerouter",
                "relation": "uses",
                "confidence": "EXTRACTED",
                "source_file": "tests/test_provider_registry.py",
                "source_location": "L325",
            },
            # ExtractionViewer import of NormalizedDocument
            {
                "source": "frontend_src_components_chat_extractionviewer",
                "target": "src_javed_schemas_extraction_normalizeddocument",
                "relation": "imports_from",
                "confidence": "EXTRACTED",
                "source_file": "frontend/src/components/chat/ExtractionViewer.tsx",
                "source_location": "L4",
            },
        ],
    }


# ======================================================================
# 1. Exact Symbol Lookup
# ======================================================================
def test_exact_symbol_lookup(mock_graph_data):
    engine = RepoIntelEngine(mock_graph_data)
    res = engine.find_symbol("InferenceRouter")

    assert res["status"] == "RESOLVED"
    assert res["confidence"] == "EXTRACTED"
    assert res["candidates_count"] == 1
    assert res["primary_match"]["source_file"] == "src/javed/providers/router.py"
    assert res["primary_match"]["source_location"] == "L53"
    assert res["primary_match"]["kind"] == "class"


# ======================================================================
# 2. Qualified Symbol Lookup
# ======================================================================
def test_qualified_symbol_lookup(mock_graph_data):
    engine = RepoIntelEngine(mock_graph_data)
    res = engine.find_symbol("tools_list_ingested_documents")

    assert res["status"] == "RESOLVED"
    assert res["primary_match"]["label"] == "list_ingested_documents"
    assert res["primary_match"]["source_file"] == "src/javed/extraction/tools.py"


# ======================================================================
# 3. Ambiguous Symbol Handling
# ======================================================================
def test_ambiguous_symbol_handling(mock_graph_data):
    engine = RepoIntelEngine(mock_graph_data)
    res = engine.find_symbol("CommonHelper")

    assert res["status"] == "AMBIGUOUS"
    assert res["confidence"] == "AMBIGUOUS"
    assert res["candidates_count"] == 2
    assert len(res["alternatives"]) == 1


# ======================================================================
# 4. Unknown Symbol Handling
# ======================================================================
def test_unknown_symbol_handling(mock_graph_data):
    engine = RepoIntelEngine(mock_graph_data)
    res = engine.find_symbol("NonExistentSymbolXYZ")

    assert res["status"] == "NOT_FOUND"
    assert res["confidence"] == "UNKNOWN"
    assert res["candidates_count"] == 0
    assert res["primary_match"] is None


# ======================================================================
# 5. Caller Lookup
# ======================================================================
def test_caller_lookup(mock_graph_data):
    engine = RepoIntelEngine(mock_graph_data)
    res = engine.find_callers("InferenceRouter")

    assert res["status"] == "RESOLVED"
    assert res["callers_count"] >= 1
    callers = res["callers"]
    chat_caller = next((c for c in callers if "api/v1/chat.py" in c["source_file"]), None)
    assert chat_caller is not None
    assert chat_caller["relation"] == "calls"


# ======================================================================
# 6. Reference Lookup
# ======================================================================
def test_reference_lookup(mock_graph_data):
    engine = RepoIntelEngine(mock_graph_data)
    res = engine.find_references("NormalizedDocument")

    assert res["status"] == "RESOLVED"
    assert res["references_count"] >= 1
    refs = res["references"]
    viewer_ref = next((r for r in refs if "ExtractionViewer.tsx" in r["source_file"]), None)
    assert viewer_ref is not None
    assert viewer_ref["relation"] == "imports_from"


# ======================================================================
# 7. Test Discovery by Direct Import
# ======================================================================
def test_test_discovery_direct_import(mock_graph_data):
    engine = RepoIntelEngine(mock_graph_data)
    res = engine.find_tests("list_ingested_documents")

    assert res["status"] == "RESOLVED"
    assert res["tests_count"] >= 1
    direct_test = next(
        (t for t in res["tests"] if "test_extraction_tools.py" in t["test_file"]), None
    )
    assert direct_test is not None
    assert direct_test["selection_reason"] == "direct_symbol_reference"
    assert direct_test["confidence"] == "EXTRACTED"


# ======================================================================
# 8. Test Discovery by Naming Convention Fallback
# ======================================================================
def test_test_discovery_naming_convention_fallback(mock_graph_data):
    engine = RepoIntelEngine(mock_graph_data)
    # DocumentStorage has no direct link in mock tests,
    # but test_extraction_tools contains token 'extraction'
    res = engine.find_tests("DocumentStorage")

    assert res["status"] == "RESOLVED"
    assert res["tests_count"] >= 1
    fallback = next((t for t in res["tests"] if "naming_convention" in t["selection_reason"]), None)
    assert fallback is not None
    assert fallback["confidence"] == "INFERRED"


# ======================================================================
# 9. Test Discovery for Frontend Component
# ======================================================================
def test_test_discovery_frontend_component(mock_graph_data):
    engine = RepoIntelEngine(mock_graph_data)
    res = engine.find_tests("ExtractionViewer")

    assert res["status"] == "RESOLVED"
    fe_test = next(
        (t for t in res["tests"] if "frontend/src/test/extraction.test.tsx" in t["test_file"]), None
    )
    assert fe_test is not None


# ======================================================================
# 10. Impact Query for Backend Service
# ======================================================================
def test_impact_backend_service(mock_graph_data):
    engine = RepoIntelEngine(mock_graph_data)
    res = engine.impact("list_ingested_documents")

    assert res["status"] == "RESOLVED"
    assert res["owning_file"] == "src/javed/extraction/tools.py"
    assert "src/javed/extraction/storage.py" in res["candidate_edit_files"]
    assert len(res["candidate_edit_files"]) <= MAX_CANDIDATE_FILES
    assert any("test_extraction_tools.py" in t for t in res["related_tests"])


# ======================================================================
# 11. Impact Query for Frontend Component
# ======================================================================
def test_impact_frontend_component(mock_graph_data):
    engine = RepoIntelEngine(mock_graph_data)
    res = engine.impact("ExtractionViewer")

    assert res["status"] == "RESOLVED"
    assert res["owning_file"] == "frontend/src/components/chat/ExtractionViewer.tsx"
    assert len(res["candidate_edit_files"]) <= MAX_CANDIDATE_FILES


# ======================================================================
# 12. Impact Query for Shared Contract/Model
# ======================================================================
def test_impact_shared_contract_model(mock_graph_data):
    engine = RepoIntelEngine(mock_graph_data)
    res = engine.impact("NormalizedDocument")

    assert res["status"] == "RESOLVED"
    assert res["owning_file"] == "src/javed/schemas/extraction.py"
    assert len(res["candidate_edit_files"]) <= MAX_CANDIDATE_FILES


# ======================================================================
# 13. Freshness Check with Fresh Graph
# ======================================================================
def test_freshness_check_fresh_graph(mock_graph_data, tmp_path):
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(json.dumps(mock_graph_data), encoding="utf-8")

    freshness = check_graph_freshness(
        graph_data=mock_graph_data,
        graph_path=graph_path,
        current_head_override="1111222233334444555566667777888899990000",
    )
    assert freshness["state"] == "FRESH"
    assert freshness["is_fresh"] is True


# ======================================================================
# 14. Freshness Check with Stale Graph
# ======================================================================
def test_freshness_check_stale_graph(mock_graph_data, tmp_path):
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(json.dumps(mock_graph_data), encoding="utf-8")

    with patch("subprocess.run") as mock_run:
        # Mock git diff returning modified source files
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="src/javed/providers/router.py\nfrontend/src/App.tsx\n",
        )
        freshness = check_graph_freshness(
            graph_data=mock_graph_data,
            graph_path=graph_path,
            current_head_override="9999999999999999999999999999999999999999",
        )
        assert freshness["state"] == "STALE"
        assert freshness["is_fresh"] is False


# ======================================================================
# 15. Update Execution Preserving Security Env
# ======================================================================
def test_update_execution_preserving_security_env(tmp_path):
    fake_bin = tmp_path / "fake_graphify.exe"
    fake_bin.touch()
    fake_graph = tmp_path / "fake_graph.json"
    fake_graph.write_text("{}", encoding="utf-8")

    args = argparse.Namespace(force=False, graph=str(fake_graph))

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="Graph rebuilt in 15s")
        with patch("scripts.repo_intel.get_git_head", return_value="abcdef123456"):
            res = run_update_cmd(args, bin_path_override=fake_bin)
            assert res["status"] == "SUCCESS"

            # Check subprocess call arguments & environment
            mock_run.assert_called_once()
            call_args, call_kwargs = mock_run.call_args
            assert call_args[0] == [str(fake_bin), "update", "."]
            env = call_kwargs["env"]
            assert env["GRAPHIFY_BACKEND"] == "none"
            assert env["GRAPHIFY_QUERY_LOG_DISABLE"] == "1"


# ======================================================================
# 16. Update Timeout Handling
# ======================================================================
def test_update_timeout_handling(tmp_path):
    fake_bin = tmp_path / "fake_graphify.exe"
    fake_bin.touch()
    fake_graph = tmp_path / "fake_graph.json"
    fake_graph.write_text("{}", encoding="utf-8")

    args = argparse.Namespace(force=False, graph=str(fake_graph))

    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="update", timeout=5)):
        with pytest.raises(TimeoutError, match="timed out"):
            run_update_cmd(args, bin_path_override=fake_bin, timeout_override=5)


# ======================================================================
# 17. Task Cache Hit
# ======================================================================
def test_task_cache_hit(tmp_path):
    cache_file = tmp_path / "cache.json"
    cache = TaskQueryCache(cache_file)

    cache.set("find-symbol", "InferenceRouter", "commit_abc", 40000, {"status": "RESOLVED"})
    entry = cache.get("find-symbol", "InferenceRouter", "commit_abc", 40000)

    assert entry is not None
    assert entry["status"] == "RESOLVED"


# ======================================================================
# 18. Task Cache Invalidation on Commit Change
# ======================================================================
def test_task_cache_invalidation_on_commit_change(tmp_path):
    cache_file = tmp_path / "cache.json"
    cache = TaskQueryCache(cache_file)

    cache.set("find-symbol", "InferenceRouter", "commit_old", 40000, {"status": "RESOLVED"})
    # Querying under commit_new must return None
    entry = cache.get("find-symbol", "InferenceRouter", "commit_new", 40000)

    assert entry is None


# ======================================================================
# 19. Task Cache Bypass Flag
# ======================================================================
def test_task_cache_bypass_flag():
    args = parse_args(["find-symbol", "InferenceRouter", "--no-cache"])
    assert args.no_cache is True


# ======================================================================
# 20. Output Bounding: Max Files Limit
# ======================================================================
def test_output_bounding_max_files_limit():
    # Construct a synthetic node with 20 caller files
    nodes = [{"id": "target_node", "label": "TargetNode", "source_file": "src/target.py"}]
    links = []
    for i in range(25):
        cid = f"caller_{i}"
        nodes.append({"id": cid, "label": f"Caller{i}", "source_file": f"src/caller_{i}.py"})
        links.append({"source": cid, "target": "target_node", "relation": "calls"})

    engine = RepoIntelEngine({"nodes": nodes, "links": links})
    res = engine.impact("TargetNode")

    assert len(res["candidate_edit_files"]) <= MAX_CANDIDATE_FILES
    assert len(res["candidate_edit_files"]) == MAX_CANDIDATE_FILES


# ======================================================================
# 21. Output Bounding: Max Symbols Limit
# ======================================================================
def test_output_bounding_max_symbols_limit():
    nodes = []
    for i in range(40):
        nodes.append(
            {"id": f"node_{i}", "label": "SharedSymbol", "source_file": f"src/file_{i}.py"}
        )

    engine = RepoIntelEngine({"nodes": nodes, "links": []})
    res = engine.find_symbol("SharedSymbol")

    assert res["status"] == "AMBIGUOUS"
    # Alternatives list must be bounded
    assert len(res["alternatives"]) <= MAX_CANDIDATE_SYMBOLS


# ======================================================================
# 22. Output Bounding: Token Truncation Defense
# ======================================================================
def test_output_bounding_token_truncation_defense():
    huge_result = {
        "command": "impact",
        "target": "HugeTarget",
        "candidate_edit_files": [f"file_{i}.py" for i in range(12)],
        "uncertainty_warnings": ["Very long warning " * 3000],
    }
    formatted = format_text_output(huge_result)
    assert len(formatted) <= 40100
    assert "truncated at token limit" in formatted


# ======================================================================
# 23. Path Redaction of User Home
# ======================================================================
def test_path_redaction_user_home():
    fake_home = Path("/Users/fakeuser")
    raw_str = "/Users/fakeuser/Desktop/AI Projects/Javed/src/main.py"
    sanitized = sanitize_path_str(raw_str, home_dir=fake_home)
    assert "/Users/fakeuser" not in sanitized
    assert "~" in sanitized

    # Redact data structure
    data = {
        "path": "/Users/fakeuser/secret.py",
        "nested": [{"file": "/Users/fakeuser/other.ts"}],
    }
    redacted = redact_data(data, home_dir=fake_home)
    assert redacted["path"] == "~/secret.py"
    assert redacted["nested"][0]["file"] == "~/other.ts"


# ======================================================================
# 24. Zero Network/External Model Confirmation
# ======================================================================
def test_zero_network_external_model_confirmation():
    # Verify status output asserts zero external inference
    status_data = run_status_cmd(argparse.Namespace(graph=""))
    sec = status_data["security_mode"]
    assert sec["GRAPHIFY_BACKEND"] == "none"
    assert sec["GRAPHIFY_QUERY_LOG_DISABLE"] == "1"
    assert sec["external_model_calls"] is False
    assert sec["cloud_telemetry"] is False

"""Tests for --discover, --strict-privacy and --mask-examples (v0.5.0)."""

from __future__ import annotations

import json
import subprocess
import sys

from test_dq import DQ_PATH, dq, run_json, sha256, write  # noqa: F401 (dq is a fixture)

SENTINELS = ("ZEPHYRINE", "QUILLBOROUGH", "xq7sentinel@mailtest.example", "Wobblefjord")


def _orders_csv(tmp_path):
    lines = ["order_id,line_number,status,cancel_reason,email,qty,city"]
    statuses = ["Delivered", "Shipped", "Cancelled", "Returned"]
    for n in range(1, 201):
        status = statuses[n % 4]
        reason = "Out of stock" if status == "Cancelled" else ""
        order = f"ORD-2025-{n // 2:06d}" if n % 3 else f"ORD-2026-{n // 2:06d}"
        lines.append(
            f"{order},{n % 2 + 1},{status},{reason},user{n}@shop.example,{n % 5 + 1},Riyadh"
        )
    # planted problems
    lines.append("ORD-INVALID,1,Delivered,,ZEPHYRINE,3,Riyadh")
    lines.append("ORD-2025-000999,1,Cancelled,,xq7sentinel@mailtest.example,two,QUILLBOROUGH")
    lines.append("ORD-2025-000998,1,Wobblefjord,,user9@shop.example,4,Riyadh")
    lines.append(lines[5])  # whole-row duplicate
    return write(tmp_path / "orders.csv", "\n".join(lines) + "\n")


def _candidates(payload):
    return {(c["rule"], c["column"] or tuple(c["columns"] or ())): c
            for c in payload["discovery"]["candidates"]}


def test_discover_proposes_expected_candidates(tmp_path):
    payload, _ = run_json([_orders_csv(tmp_path), "--discover"])
    found = _candidates(payload)
    assert found[("max_duplicate_rows", ())]["expected"]["violations"] == 1
    assert ("unique_together", ("order_id", "line_number")) in found
    conditional = found[("conditional_required", ("status", "cancel_reason"))]
    assert conditional["value"]["when"] == {"column": "status", "equals": "Cancelled"}
    assert conditional["expected"]["violations"] == 1
    assert found[("type", "qty")]["value"] == "integer"
    assert found[("type", "qty")]["expected"]["violations"] == 1
    assert "Wobblefjord" not in found[("allowed", "status")]["value"]
    regex = found[("regex", "order_id")]
    assert regex["expected"]["violations"] == 1  # ORD-INVALID only; both years fit
    assert all(c["provenance"] == "inferred" for c in payload["discovery"]["candidates"])
    assert not any(c["rule"] in ("min", "max") for c in payload["discovery"]["candidates"])


def test_discover_does_not_score_candidates(tmp_path):
    payload, _ = run_json([_orders_csv(tmp_path), "--discover"])
    assert payload["checks"] == []
    assert payload["overall"]["status"] == "inspected"
    assert payload["options"] == {"discover": True, "strict_privacy": False,
                                  "mask_examples": False}


def test_discover_is_deterministic_and_read_only(tmp_path):
    source = _orders_csv(tmp_path)
    before = sha256(source)
    outputs = {
        subprocess.run([sys.executable, str(DQ_PATH), str(source), "--discover"],
                       capture_output=True).stdout
        for _ in range(3)
    }
    assert len(outputs) == 1
    assert sha256(source) == before


def test_discover_rules_document_runs_as_rules(tmp_path):
    import yaml

    source = _orders_csv(tmp_path)
    payload, _ = run_json([source, "--discover"])
    rules = write(tmp_path / "rules.yml", yaml.safe_dump(payload["discovery"]["rules"]))
    verified, _ = run_json([source, "--rules", rules], expect=1)
    expected = {c["id"]: c["expected"] for c in payload["discovery"]["candidates"]}
    assert len(verified["checks"]) == len(expected)
    assert sum(c["violations"] for c in verified["checks"]) == sum(
        e["violations"] for e in expected.values())


def test_strict_privacy_output_contains_no_raw_values(tmp_path):
    source = _orders_csv(tmp_path)
    text = subprocess.run(
        [sys.executable, str(DQ_PATH), str(source), "--discover", "--strict-privacy"],
        capture_output=True, text=True, encoding="utf-8",
    ).stdout
    for sentinel in SENTINELS + ("Delivered", "Cancelled", "Out of stock", "Riyadh"):
        assert sentinel not in text, sentinel
    payload = json.loads(text)
    numeric = [c["numeric"] for c in payload["profile"]["column_profiles"] if c["numeric"]]
    assert numeric and all(n["min"] is None and n["max"] is None and n["mean"] is None
                           for n in numeric)
    withheld = [c for c in payload["discovery"]["candidates"] if c["withheld"]]
    assert withheld and all(c["value"] is None for c in withheld)


def test_default_discover_never_lists_high_cardinality_values(tmp_path):
    text = subprocess.run(
        [sys.executable, str(DQ_PATH), str(_orders_csv(tmp_path)), "--discover"],
        capture_output=True, text=True, encoding="utf-8",
    ).stdout
    for sentinel in ("ZEPHYRINE", "xq7sentinel@mailtest.example", "user9@shop.example"):
        assert sentinel not in text, sentinel


def test_strict_privacy_refuses_raw_examples(tmp_path):
    payload, _ = run_json([_orders_csv(tmp_path), "--strict-privacy", "--examples", "2"], expect=2)
    assert payload["errors"][0]["code"] == "invalid_option"


def test_mask_examples_shows_shapes(tmp_path):
    rules = write(tmp_path / "r.yml", "columns:\n  qty:\n    type: integer\n")
    payload, _ = run_json([_orders_csv(tmp_path), "--rules", rules, "--examples", "3",
                        "--mask-examples"], expect=1)
    assert payload["checks"][0]["examples"] == ["aaa"]


def test_shape_helpers(dq):
    assert dq.shape_of("ORD-2025-000123") == "AAA-9999-999999"
    assert dq.shape_of("aḥmad 7") == "aLaaa 9"
    assert dq.collapsed_shape(dq.shape_of("john@shop.sa")) == "a+@a+.a+"


def test_output_md_documents_discovery_fields(tmp_path):
    from test_skill_bundle import _field_index

    index = _field_index()
    payload, _ = run_json([_orders_csv(tmp_path), "--discover"])
    assert set(index["optional_top_level"]) == {"options", "discovery"}
    assert set(index["options"]) == set(payload["options"])
    discovery = payload["discovery"]
    assert set(index["discovery"]) == set(discovery)
    assert set(index["discovery_search"]) == set(discovery["search"])
    assert all(set(index["discovery_column"]) == set(c) for c in discovery["columns"])
    assert all(set(index["candidate"]) == set(c) for c in discovery["candidates"])


def test_discover_skips_allowed_for_non_scalar_cells(tmp_path):
    import datetime as dt

    from openpyxl import Workbook

    book = Workbook()
    sheet = book.active
    sheet.append(["when", "status"])
    for n in range(40):
        sheet.append([dt.datetime(2025, 1, 1 + n % 3), ["Open", "Closed"][n % 2]])
    path = tmp_path / "dates.xlsx"
    book.save(path)
    payload, _ = run_json([path, "--discover"])
    allowed = {c["column"]: c["value"] for c in payload["discovery"]["candidates"]
               if c["rule"] == "allowed"}
    assert "when" not in allowed
    assert allowed["status"] == ["Closed", "Open"]

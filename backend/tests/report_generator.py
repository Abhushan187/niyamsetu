# backend/tests/report_generator.py
# ─────────────────────────────────────────────────────────
# Generates a self-contained HTML report from test results.
# Reads unit_test_results.json and integration_test_results.json,
# produces GR_Test_Report.html — for copyright application
# benchmarks and final review/viva presentation evidence.
#
# Run order:
#   python tests/test_units.py
#   python tests/test_integration.py
#   python tests/report_generator.py
# ─────────────────────────────────────────────────────────

import json
import os
from datetime import datetime, timezone

UNIT_RESULTS_PATH        = "unit_test_results.json"
INTEGRATION_RESULTS_PATH = "integration_test_results.json"
OUTPUT_PATH               = "GR_Test_Report.html"


def load_results(path):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def stat_card(label, value, color):
    return f"""
    <div style="background:#1A1D2E;border:1px solid #2A2D3E;border-radius:12px;padding:16px 18px;min-width:150px;">
        <div style="color:{color};font-size:1.6rem;font-weight:700;font-family:monospace;">{value}</div>
        <div style="color:#888;font-size:0.75rem;margin-top:4px;">{label}</div>
    </div>"""


def test_rows(tests):
    rows = []
    color_map = {"pass": "#4ADE80", "fail": "#EF4444", "error": "#EF4444", "skip": "#FACC15"}
    icon_map  = {"pass": "✓", "fail": "✕", "error": "⚠", "skip": "○"}
    for t in tests:
        color = color_map.get(t["status"], "#888")
        icon  = icon_map.get(t["status"], "?")
        msg   = t["message"].replace("<", "&lt;").replace(">", "&gt;") if t["message"] else ""
        rows.append(f"""
        <div style="display:grid;grid-template-columns:40px 1fr 90px;gap:10px;padding:8px 14px;
                    border-bottom:1px solid #1E2135;align-items:start;">
            <div style="color:{color};font-weight:700;">{icon}</div>
            <div>
                <div style="color:#E8EAF0;font-size:0.82rem;font-family:monospace;">{t['name']}</div>
                {f'<div style="color:#EF4444;font-size:0.72rem;margin-top:3px;white-space:pre-wrap;">{msg}</div>' if msg else ''}
            </div>
            <div style="color:{color};font-size:0.75rem;text-transform:uppercase;">{t['status']}</div>
        </div>""")
    return "".join(rows)


def suite_section(results, title):
    if results is None:
        return f"""
        <div style="background:#1A1D2E;border:1px solid #2A2D3E;border-radius:14px;padding:20px;margin-bottom:20px;">
            <h2 style="color:#E8EAF0;font-size:1.1rem;margin:0 0 10px;">{title}</h2>
            <p style="color:#EF4444;font-size:0.85rem;">
                ⚠ No results found. Run the corresponding test file first.
            </p>
        </div>"""

    pass_pct = round((results["passed"] / results["total"]) * 100) if results["total"] else 0
    status_color = "#4ADE80" if results["was_successful"] else "#EF4444"

    return f"""
    <div style="background:#1A1D2E;border:1px solid #2A2D3E;border-radius:14px;padding:20px;margin-bottom:20px;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;flex-wrap:wrap;gap:10px;">
            <h2 style="color:#E8EAF0;font-size:1.1rem;margin:0;">{title}</h2>
            <span style="color:{status_color};font-weight:700;font-size:0.85rem;">
                {results['passed']}/{results['total']} passed ({pass_pct}%) · {results['elapsed_sec']}s
            </span>
        </div>
        <div style="border:1px solid #2A2D3E;border-radius:10px;overflow:hidden;max-height:400px;overflow-y:auto;">
            {test_rows(results['tests'])}
        </div>
    </div>"""


def generate_report():
    unit_results = load_results(UNIT_RESULTS_PATH)
    integ_results = load_results(INTEGRATION_RESULTS_PATH)

    total_tests  = (unit_results["total"] if unit_results else 0) + (integ_results["total"] if integ_results else 0)
    total_passed = (unit_results["passed"] if unit_results else 0) + (integ_results["passed"] if integ_results else 0)
    overall_pct  = round((total_passed / total_tests) * 100) if total_tests else 0

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Niyamsetu — Test Report</title>
</head>
<body style="margin:0;background:#0F1117;font-family:'Segoe UI',Inter,sans-serif;padding:32px;">
    <div style="max-width:900px;margin:0 auto;">

        <h1 style="color:#FF6B00;font-size:1.6rem;margin:0 0 4px;">🏛️ Niyamsetu — Test Report</h1>
        <p style="color:#555;font-size:0.85rem;margin:0 0 24px;">
            Generated {datetime.now(timezone.utc).strftime('%d %b %Y, %H:%M UTC')}
        </p>

        <div style="display:flex;gap:14px;flex-wrap:wrap;margin-bottom:28px;">
            {stat_card("Total Tests", total_tests, "#6FB3FF")}
            {stat_card("Passed", total_passed, "#4ADE80")}
            {stat_card("Pass Rate", f"{overall_pct}%", "#FF6B00")}
        </div>

        {suite_section(unit_results, "Unit Tests — core/language.py")}
        {suite_section(integ_results, "Integration Tests — Auth, Query, Sessions")}

        <div style="background:#1A1D2E;border:1px solid #2A2D3E;border-radius:14px;padding:20px;margin-bottom:20px;">
            <h2 style="color:#E8EAF0;font-size:1.1rem;margin:0 0 10px;">📋 RAG Accuracy & Citation Coverage</h2>
            <p style="color:#FACC15;font-size:0.85rem;line-height:1.6;">
                ⚠ Pending real GR test set. Current integration tests verify system
                correctness (auth, endpoints, session handling) — not answer accuracy
                against ground-truth GRs. This section will be populated once real
                Government Resolutions are embedded (on Harsh's machine) and a graded
                question/expected-answer set is run against the live RAG pipeline.
            </p>
        </div>

        <p style="color:#333;font-size:0.72rem;text-align:center;margin-top:32px;">
            Niyamsetu — Maharashtra GR Intelligence System — Internal Test Report
        </p>
    </div>
</body>
</html>"""

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"✅ Report generated: {OUTPUT_PATH}")
    print(f"   Open it in your browser to view.")


if __name__ == "__main__":
    generate_report()
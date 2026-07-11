# backend/tests/json_test_runner.py
# ─────────────────────────────────────────────────────────
# Shared helper — runs a unittest module and writes results
# to a JSON file that report_generator.py later reads.
# Used by test_units.py and test_integration.py when run directly.
# ─────────────────────────────────────────────────────────

import unittest
import json
import time
from datetime import datetime, timezone


class JSONCollectingResult(unittest.TextTestResult):
    """Captures per-test outcome alongside the normal console output."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.test_records = []

    def _record(self, test, status, message=""):
        self.test_records.append({
            "name":    test.id(),
            "status":  status,
            "message": message.strip()[:300] if message else "",
        })

    def addSuccess(self, test):
        super().addSuccess(test)
        self._record(test, "pass")

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self._record(test, "fail", self._exc_info_to_string(err, test))

    def addError(self, test, err):
        super().addError(test, err)
        self._record(test, "error", self._exc_info_to_string(err, test))

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self._record(test, "skip", reason)


def run_module_to_json(module, output_path: str, suite_name: str):
    """
    Runs all tests in a module, prints normal console output,
    and writes a JSON summary to output_path.
    """
    loader = unittest.TestLoader()
    suite  = loader.loadTestsFromModule(module)

    runner = unittest.TextTestRunner(verbosity=2, resultclass=JSONCollectingResult)

    start = time.time()
    result = runner.run(suite)
    elapsed = round(time.time() - start, 2)

    summary = {
        "suite_name":   suite_name,
        "run_at":       str(datetime.now(timezone.utc)),
        "elapsed_sec":  elapsed,
        "total":        result.testsRun,
        "passed":       len([t for t in result.test_records if t["status"] == "pass"]),
        "failed":       len([t for t in result.test_records if t["status"] == "fail"]),
        "errors":       len([t for t in result.test_records if t["status"] == "error"]),
        "skipped":      len([t for t in result.test_records if t["status"] == "skip"]),
        "was_successful": result.wasSuccessful(),
        "tests":        result.test_records,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"\n📄 Results written to {output_path}")
    return result.wasSuccessful()
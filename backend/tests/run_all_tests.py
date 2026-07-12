# backend/tests/run_all_tests.py
# ─────────────────────────────────────────────────────────
# Test runner — entry point for CI and local testing.
#
# Usage:
#   python tests/run_all_tests.py --offline
#     → runs only tests that need no MongoDB/Ollama/FAISS (test_units.py)
#
#   python tests/run_all_tests.py
#     → runs the full suite, including integration tests that
#       require live services (MongoDB, Ollama) to be running
# ─────────────────────────────────────────────────────────

import sys
import os
import argparse
import unittest

sys.path.append(os.path.dirname(os.path.abspath(__file__)))


def run_offline_tests():
    """
    Runs only pure-logic unit tests — no external services required.
    This is what CI runs on every PR, since GitHub Actions runners
    don't have MongoDB, Ollama, or a FAISS index available.
    """
    import test_units
    import test_config

    loader = unittest.TestLoader()
    suite  = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromModule(test_units))
    suite.addTests(loader.loadTestsFromModule(test_config))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return result.wasSuccessful()


def run_full_suite():
    """
    Runs the complete test suite, including integration tests
    that require MongoDB and Ollama to be running locally.
    Use this before a demo or major merge, not in CI.
    """
    import test_units
    import test_config
    import test_integration

    loader = unittest.TestLoader()
    suite  = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromModule(test_units))
    suite.addTests(loader.loadTestsFromModule(test_config))
    suite.addTests(loader.loadTestsFromModule(test_integration))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return result.wasSuccessful()


def main():
    parser = argparse.ArgumentParser(description="Niyamsetu test runner")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Run only tests that don't require MongoDB/Ollama/FAISS",
    )
    args = parser.parse_args()

    if args.offline:
        print("Running OFFLINE test suite (no external services required)...\n")
        success = run_offline_tests()
    else:
        print("Running FULL test suite (requires MongoDB + Ollama running)...\n")
        success = run_full_suite()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
#!/usr/bin/env python3
"""
AgentMemoryDB — Test Runner
============================

Run all tests or specific subsets, with optional coverage and HTML reports.

Usage:
    python run_tests.py                   # unit tests (default, no Docker needed)
    python run_tests.py --all             # unit + integration tests
    python run_tests.py --unit            # unit tests only
    python run_tests.py --integration     # integration tests only
    python run_tests.py --coverage        # unit tests + coverage report
    python run_tests.py --file test_scoring.py   # run a single test file
    python run_tests.py --keyword scoring # run tests matching a keyword
    python run_tests.py --report          # save HTML report to test-report/
    python run_tests.py --verbose         # extra verbose output
    python run_tests.py --check           # check dependencies only, don't run tests
    python run_tests.py --list            # list all discovered test files
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

# ── Project root (directory containing this script) ─────────────
ROOT = Path(__file__).parent

# ── Colour helpers ───────────────────────────────────────────────
RESET  = "\033[0m"
BOLD   = "\033[1m"
GREEN  = "\033[32m"
YELLOW = "\033[33m"
RED    = "\033[31m"
CYAN   = "\033[36m"
DIM    = "\033[2m"

def _c(colour: str, text: str) -> str:
    """Wrap text in ANSI colour — skipped on Windows without colour support."""
    if sys.platform == "win32":
        try:
            import ctypes
            kernel = ctypes.windll.kernel32
            kernel.SetConsoleMode(kernel.GetStdHandle(-11), 7)
        except Exception:
            pass
    return f"{colour}{text}{RESET}"


# ── Dependency checker ───────────────────────────────────────────

REQUIRED_PACKAGES = {
    "pytest":            "pytest>=8.0.0",
    "pytest_asyncio":    "pytest-asyncio>=0.23.0",
    "aiosqlite":         "aiosqlite>=0.19.0",
    "sqlalchemy":        "sqlalchemy[asyncio]>=2.0.25",
    "pydantic":          "pydantic>=2.5.0",
    "fastapi":           "fastapi>=0.110.0",
    "pgvector":          "pgvector>=0.3.0",
    "httpx":             "httpx>=0.26.0",
    "numpy":             "numpy>=1.26.0",
}

OPTIONAL_PACKAGES = {
    "pytest_cov":        "pytest-cov>=4.1.0",
}

def check_dependencies(verbose: bool = False) -> bool:
    """Verify required packages are installed. Returns True if all present."""
    missing: list[str] = []
    optional_missing: list[str] = []

    print(_c(BOLD, "\n[*] Checking dependencies..."))

    for module, install_name in REQUIRED_PACKAGES.items():
        try:
            __import__(module)
            if verbose:
                print(f"  {_c(GREEN, '[ok]')} {module}")
        except ImportError:
            missing.append(install_name)
            print(f"  {_c(RED, '[!]')} {module}  ->  pip install {install_name}")

    for module, install_name in OPTIONAL_PACKAGES.items():
        try:
            __import__(module)
            if verbose:
                print(f"  {_c(GREEN, '[ok]')} {module}  (optional)")
        except ImportError:
            optional_missing.append(install_name)
            if verbose:
                print(f"  {_c(YELLOW, '[-]')} {module}  (optional -- pip install {install_name})")

    if missing:
        print(_c(RED, f"\n  [!]  {len(missing)} required package(s) missing."))
        print(f"  Install with: {_c(CYAN, 'pip install ' + ' '.join(missing))}")
        return False

    if optional_missing and not verbose:
        print(f"  {_c(DIM, f'(optional: {len(optional_missing)} package(s) not installed - coverage unavailable)')}")

    print(_c(GREEN, "  [ok]  All required packages present.\n"))
    return True


# ── Test file discovery ──────────────────────────────────────────

def list_test_files(tests_dir: Path) -> dict[str, list[Path]]:
    """Discover all test files grouped by category."""
    groups: dict[str, list[Path]] = {"unit": [], "integration": []}
    for subdir in ("unit", "integration"):
        d = tests_dir / subdir
        if d.exists():
            groups[subdir] = sorted(d.glob("test_*.py"))
    return groups


def print_test_list(tests_dir: Path) -> None:
    """Print all discovered test files."""
    groups = list_test_files(tests_dir)
    print(_c(BOLD, "\n[*] Discovered test files:\n"))
    total = 0
    for category, files in groups.items():
        if files:
            print(f"  {_c(CYAN, category.upper())} ({len(files)} files)")
            for f in files:
                print(f"    {_c(DIM, '->')} {f.relative_to(tests_dir.parent)}")
            total += len(files)
    print(f"\n  Total: {_c(BOLD, str(total))} test files\n")


# ── Pytest invocation ────────────────────────────────────────────

def build_pytest_args(
    *,
    mode: str,            # "unit" | "integration" | "all" | "file" | "keyword"
    verbose: bool,
    coverage: bool,
    report: bool,
    file_filter: str | None,
    keyword_filter: str | None,
    fail_fast: bool,
    tests_dir: Path,
) -> list[str]:
    """Build the pytest command-line argument list."""
    # Use `sys.executable -m pytest` so we always pick up the right environment
    args: list[str] = [sys.executable, "-m", "pytest"]

    # ── Test selection ──────────────────────────────────────────
    if file_filter:
        # Search for the file anywhere under tests/
        matches = list(tests_dir.rglob(file_filter if file_filter.endswith(".py") else f"*{file_filter}*.py"))
        if not matches:
            print(_c(RED, f"  ✗  No test file matching '{file_filter}' found."))
            sys.exit(1)
        for m in matches:
            args.append(str(m))
    elif keyword_filter:
        args += [str(tests_dir), "-k", keyword_filter]
    elif mode == "unit":
        args += [str(tests_dir / "unit"), "-m", "unit or not integration"]
    elif mode == "integration":
        args += [str(tests_dir / "integration"), "-m", "integration"]
    elif mode == "all":
        args.append(str(tests_dir))
    else:
        args += [str(tests_dir / "unit"), "-m", "unit or not integration"]

    # ── Output format ───────────────────────────────────────────
    if verbose:
        args += ["-v", "--tb=short"]
    else:
        args += ["-v", "--tb=short", "--no-header"]

    # ── Coverage ────────────────────────────────────────────────
    if coverage:
        try:
            import pytest_cov  # noqa: F401
            args += [
                "--cov=app",
                "--cov=agentmemodb",
                "--cov-report=term-missing",
                "--cov-report=html:coverage_html",
            ]
        except ImportError:
            print(_c(YELLOW, "  [!]  pytest-cov not installed - skipping coverage."))
            print(_c(DIM, "     Install with: pip install pytest-cov\n"))

    # ── HTML report ─────────────────────────────────────────────
    if report:
        try:
            import pytest_html  # noqa: F401
            args += ["--html=test-report/report.html", "--self-contained-html"]
        except ImportError:
            print(_c(YELLOW, "  [!]  pytest-html not installed - skipping HTML report."))
            print(_c(DIM, "     Install with: pip install pytest-html\n"))

    # ── Misc ─────────────────────────────────────────────────────
    if fail_fast:
        args += ["-x"]

    # Asyncio mode
    args += ["--asyncio-mode=auto"]

    # Suppress noisy warnings from third-party libs
    args += [
        "-W", "ignore::DeprecationWarning:sqlalchemy",
        "-W", "ignore::DeprecationWarning:pydantic",
        "-W", "ignore::pytest.PytestUnraisableExceptionWarning",
    ]

    return args


# ── Run and report ───────────────────────────────────────────────

def run_tests(args: list[str], env: dict) -> tuple[int, float]:
    """Run pytest and return (exit_code, duration_seconds)."""
    start = time.perf_counter()
    result = subprocess.run(args, env=env)
    duration = time.perf_counter() - start
    return result.returncode, duration


def print_summary(exit_code: int, duration: float, mode: str, coverage: bool) -> None:
    """Print the final result banner."""
    print()
    if exit_code == 0:
        print(_c(GREEN, "-" * 60))
        print(_c(GREEN, f"  [PASS]  ALL TESTS PASSED   ({duration:.2f}s)"))
        print(_c(GREEN, "-" * 60))
    else:
        print(_c(RED, "-" * 60))
        print(_c(RED, f"  [FAIL]  SOME TESTS FAILED   ({duration:.2f}s)"))
        print(_c(RED, "-" * 60))

    if coverage and exit_code == 0:
        coverage_path = ROOT / "coverage_html" / "index.html"
        if coverage_path.exists():
            print(f"\n  [coverage]  Report: {_c(CYAN, str(coverage_path))}")

    print()


# ── Environment setup ────────────────────────────────────────────

def build_env() -> dict:
    """Build environment variables for the test run.

    NOTE: We do NOT override DATABASE_URL to SQLite here.
    app/db/__init__.py creates the module-level engine at import time using
    pool_size/max_overflow — those args are only valid for PostgreSQL dialects.
    The conftest.py manages its own separate in-memory SQLite engine for unit
    tests, so the module-level engine just needs to be parseable (any pg URL).
    """
    env = os.environ.copy()
    env.setdefault("ENVIRONMENT", "test")
    env.setdefault("TESTING", "1")
    # Silence verbose log output during tests
    env.setdefault("LOG_LEVEL", "WARNING")
    # Point at the Docker postgres — unit tests override this via conftest;
    # integration tests need a real DB running on port 5433.
    env.setdefault(
        "DATABASE_URL",
        "postgresql+asyncpg://agentmem:agentmem_secret@localhost:5433/agentmemorydb",
    )
    # Match embedding dimension to the DummyEmbeddingProvider(dim=8) used in
    # conftest.py.  Vector(settings.embedding_dimension) validates on bind even
    # for SQLite, so both sides must agree.
    env.setdefault("EMBEDDING_DIMENSION", "8")
    return env


# ── CLI ──────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="AgentMemoryDB test runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--unit",        action="store_true", help="Unit tests only (no Docker needed) [default]")
    mode.add_argument("--integration", action="store_true", help="Integration tests only")
    mode.add_argument("--all",         action="store_true", help="Unit + integration tests")

    parser.add_argument("--file",     metavar="FILENAME", help="Run a specific test file (partial name ok)")
    parser.add_argument("--keyword",  metavar="EXPR",     help="Run tests matching a keyword expression (-k)")
    parser.add_argument("--coverage", action="store_true", help="Generate coverage report (requires pytest-cov)")
    parser.add_argument("--report",   action="store_true", help="Generate HTML test report (requires pytest-html)")
    parser.add_argument("--verbose",  action="store_true", help="Extra verbose output")
    parser.add_argument("--fail-fast",action="store_true", help="Stop on first failure (-x)")
    parser.add_argument("--check",    action="store_true", help="Check dependencies only, don't run tests")
    parser.add_argument("--list",     action="store_true", help="List all discovered test files and exit")

    return parser.parse_args()


def main() -> None:
    opts = parse_args()
    tests_dir = ROOT / "tests"

    # Force UTF-8 on Windows so box-drawing / emoji chars render correctly
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:
            pass

    # ── Header ──────────────────────────────────────────────────
    print(_c(BOLD, "\n+----------------------------------------------+"))
    print(_c(BOLD, "|      AgentMemoryDB  -  Test Runner           |"))
    print(_c(BOLD, "+----------------------------------------------+"))

    # ── List mode ───────────────────────────────────────────────
    if opts.list:
        print_test_list(tests_dir)
        sys.exit(0)

    # ── Dependency check ─────────────────────────────────────────
    ok = check_dependencies(verbose=opts.verbose or opts.check)
    if not ok:
        sys.exit(1)
    if opts.check:
        print(_c(GREEN, "  [ok]  Dependency check complete - ready to run tests.\n"))
        sys.exit(0)

    # ── Determine mode ───────────────────────────────────────────
    if opts.file or opts.keyword:
        mode = "file"
    elif opts.integration:
        mode = "integration"
    elif opts.all:
        mode = "all"
    else:
        mode = "unit"  # safe default — no Docker required

    mode_label = opts.file or opts.keyword or mode
    print(f"  Mode     : {_c(CYAN, mode_label)}")
    print(f"  Coverage : {_c(CYAN, 'yes') if opts.coverage else _c(DIM, 'no')}")
    print(f"  Fail-fast: {_c(CYAN, 'yes') if opts.fail_fast else _c(DIM, 'no')}")
    print()

    if mode == "integration" or mode == "all":
        print(_c(YELLOW, "  [!]  Integration tests require the Docker stack to be running."))
        print(_c(DIM,    "     Start with: docker compose up -d"))
        print(_c(DIM,    "     (Unit tests run against in-memory SQLite -- no Docker needed)\n"))

    # ── Build + run ──────────────────────────────────────────────
    pytest_args = build_pytest_args(
        mode=mode,
        verbose=opts.verbose,
        coverage=opts.coverage,
        report=opts.report,
        file_filter=opts.file,
        keyword_filter=opts.keyword,
        fail_fast=opts.fail_fast,
        tests_dir=tests_dir,
    )

    env = build_env()

    if opts.verbose:
        print(_c(DIM, "  pytest command:"))
        print(_c(DIM, "    " + " ".join(pytest_args)))
        print()

    exit_code, duration = run_tests(pytest_args, env)
    print_summary(exit_code, duration, mode, opts.coverage)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Build and optionally publish the agentmemodb pip package.

Usage:
    python pkg/publish.py                    # Build only (sdist + wheel)
    python pkg/publish.py --check            # Build + twine check
    python pkg/publish.py --test-pypi        # Upload to TestPyPI
    python pkg/publish.py --pypi             # Upload to real PyPI
    python pkg/publish.py --clean            # Remove build artifacts

Prerequisites:
    pip install build twine

What this does:
    1. Creates a temporary _build/ directory
    2. Copies agentmemodb/ source, LICENSE, and pkg/ config into it
    3. Runs `python -m build` from _build/
    4. Copies the resulting dist/ back to pkg/dist/
    5. Optionally runs twine check / upload

The resulting package on PyPI will be named `agentmemodb` and can be
installed with `pip install agentmemodb`.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

# Paths
SCRIPT_DIR = Path(__file__).resolve().parent          # pkg/
PROJECT_ROOT = SCRIPT_DIR.parent                       # agentmemodb project root
SOURCE_PKG = PROJECT_ROOT / "agentmemodb"              # package source
BUILD_DIR = SCRIPT_DIR / "_build"                      # temporary build directory
DIST_DIR = SCRIPT_DIR / "dist"                         # final dist output


def clean():
    """Remove build artifacts."""
    for d in [BUILD_DIR, DIST_DIR, SCRIPT_DIR / "_build"]:
        if d.exists():
            shutil.rmtree(d)
            print(f"  Removed {d.relative_to(PROJECT_ROOT)}")
    # Also remove egg-info if it leaked
    for egg in SCRIPT_DIR.glob("*.egg-info"):
        shutil.rmtree(egg)
        print(f"  Removed {egg.name}")
    print("  ✓ Clean complete")


def build():
    """Assemble build directory and run python -m build."""
    print("\n─── Step 1: Assemble build directory ───\n")

    # Clean previous
    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR)
    BUILD_DIR.mkdir(parents=True)

    # Copy package source
    dest_pkg = BUILD_DIR / "agentmemodb"
    shutil.copytree(
        SOURCE_PKG,
        dest_pkg,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".mypy_cache"),
    )
    print(f"  Copied agentmemodb/ → _build/agentmemodb/")

    # Copy pyproject.toml
    shutil.copy2(SCRIPT_DIR / "pyproject.toml", BUILD_DIR / "pyproject.toml")
    print(f"  Copied pyproject.toml")

    # Copy README
    shutil.copy2(SCRIPT_DIR / "README.md", BUILD_DIR / "README.md")
    print(f"  Copied README.md")

    # Copy LICENSE
    license_src = PROJECT_ROOT / "LICENSE"
    if license_src.exists():
        shutil.copy2(license_src, BUILD_DIR / "LICENSE")
        print(f"  Copied LICENSE")

    # List contents
    print(f"\n  Build directory contents:")
    for f in sorted(BUILD_DIR.rglob("*")):
        if f.is_file() and "__pycache__" not in str(f):
            rel = f.relative_to(BUILD_DIR)
            size = f.stat().st_size
            print(f"    {rel}  ({size:,} bytes)")

    # ── Step 2: Build ──
    print("\n─── Step 2: Build sdist + wheel ───\n")

    result = subprocess.run(
        [sys.executable, "-m", "build"],
        cwd=str(BUILD_DIR),
        capture_output=True,
        text=True,
    )

    if result.stdout:
        for line in result.stdout.strip().splitlines():
            print(f"  {line}")
    if result.returncode != 0:
        print(f"\n  ✗ Build failed!")
        if result.stderr:
            for line in result.stderr.strip().splitlines():
                print(f"    {line}")
        sys.exit(1)

    # ── Step 3: Copy dist output ──
    print("\n─── Step 3: Collect artifacts ───\n")

    build_dist = BUILD_DIR / "dist"
    if not build_dist.exists():
        print("  ✗ No dist/ directory created")
        sys.exit(1)

    DIST_DIR.mkdir(parents=True, exist_ok=True)
    for f in build_dist.iterdir():
        dest = DIST_DIR / f.name
        shutil.copy2(f, dest)
        size_kb = f.stat().st_size / 1024
        print(f"  ✓ {f.name}  ({size_kb:.1f} KB)")

    print(f"\n  ✅ Build complete → pkg/dist/")
    return True


def twine_check():
    """Run twine check on built artifacts."""
    print("\n─── Twine Check ───\n")

    files = list(DIST_DIR.glob("*"))
    if not files:
        print("  ✗ No dist files found. Run build first.")
        return False

    result = subprocess.run(
        [sys.executable, "-m", "twine", "check"] + [str(f) for f in files],
        capture_output=True,
        text=True,
    )

    for line in result.stdout.strip().splitlines():
        print(f"  {line}")

    if result.returncode != 0:
        print(f"\n  ✗ Twine check failed!")
        if result.stderr:
            for line in result.stderr.strip().splitlines():
                print(f"    {line}")
        return False

    print(f"\n  ✅ Twine check passed")
    return True


def upload(repository: str):
    """Upload to PyPI or TestPyPI."""
    print(f"\n─── Upload to {repository} ───\n")

    files = list(DIST_DIR.glob("*"))
    if not files:
        print("  ✗ No dist files found. Run build first.")
        return False

    cmd = [sys.executable, "-m", "twine", "upload"]

    if repository == "testpypi":
        cmd += ["--repository", "testpypi"]
        print("  Target: https://test.pypi.org/project/agentmemodb/")
        print("  (Set TWINE_USERNAME and TWINE_PASSWORD, or use --username/__token__)\n")
    else:
        print("  Target: https://pypi.org/project/agentmemodb/")
        print("  (Set TWINE_USERNAME and TWINE_PASSWORD, or use --username/__token__)\n")

    cmd += [str(f) for f in files]

    result = subprocess.run(cmd, text=True)

    if result.returncode != 0:
        print(f"\n  ✗ Upload failed!")
        return False

    if repository == "testpypi":
        print(f"\n  ✅ Uploaded to TestPyPI!")
        print(f"  Install with: pip install -i https://test.pypi.org/simple/ agentmemodb")
    else:
        print(f"\n  ✅ Uploaded to PyPI!")
        print(f"  Install with: pip install agentmemodb")

    return True


def main():
    parser = argparse.ArgumentParser(
        description="Build and publish agentmemodb to PyPI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python pkg/publish.py                  Build only
    python pkg/publish.py --check          Build + validate
    python pkg/publish.py --test-pypi      Upload to TestPyPI
    python pkg/publish.py --pypi           Upload to PyPI
    python pkg/publish.py --clean          Remove artifacts
        """,
    )
    parser.add_argument("--check", action="store_true", help="Run twine check after build")
    parser.add_argument("--test-pypi", action="store_true", help="Upload to TestPyPI")
    parser.add_argument("--pypi", action="store_true", help="Upload to real PyPI")
    parser.add_argument("--clean", action="store_true", help="Remove build artifacts")
    args = parser.parse_args()

    print("=" * 60)
    print("  agentmemodb — PyPI Package Builder")
    print("=" * 60)

    if args.clean:
        clean()
        return

    # Always build first
    build()

    # Optional: twine check
    if args.check or args.test_pypi or args.pypi:
        ok = twine_check()
        if not ok:
            sys.exit(1)

    # Optional: upload
    if args.test_pypi:
        upload("testpypi")
    elif args.pypi:
        upload("pypi")
    elif not args.check:
        print("\n  Next steps:")
        print("    python pkg/publish.py --check       # Validate package")
        print("    python pkg/publish.py --test-pypi   # Upload to TestPyPI")
        print("    python pkg/publish.py --pypi        # Upload to real PyPI")


if __name__ == "__main__":
    main()

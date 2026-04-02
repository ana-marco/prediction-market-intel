"""
Full data pipeline runner.

Checks infrastructure, initialises databases, loads all data sources,
builds the Neo4j graph and ChromaDB embeddings. Stops on first failure.

Usage:
    python scripts/run_pipeline.py          # run full pipeline
    python scripts/run_pipeline.py --help   # show help
    python scripts/run_pipeline.py --skip-load  # skip data loading (re-build only)
"""

import argparse
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent

if platform.system() == "Windows":
    PYTHON = str(PROJECT_ROOT / "venv" / "Scripts" / "python.exe")
else:
    PYTHON = str(PROJECT_ROOT / "venv" / "bin" / "python")

CONTAINERS = ["pmi-postgres", "pmi-mongodb", "pmi-neo4j", "pmi-chromadb"]

PIPELINE_STEPS = [
    ("Initialize databases", "scripts/init_db.py"),
    ("Load Polymarket markets", "scripts/load_polymarket.py"),
    ("Load Guardian articles", "scripts/load_guardian.py"),
    ("Load gov.uk articles", "scripts/load_govuk.py"),
    ("Load FRED indicators", "scripts/load_fred.py"),
    ("Load Reddit posts", "scripts/load_reddit.py"),
    ("Build Neo4j graph", "scripts/build_graph.py"),
    ("Build ChromaDB embeddings", "scripts/build_embeddings.py"),
]

BUILD_ONLY_STEPS = [
    ("Build Neo4j graph", "scripts/build_graph.py"),
    ("Build ChromaDB embeddings", "scripts/build_embeddings.py"),
]


def check_docker():
    """Verify all Docker containers are running."""
    print("Checking Docker containers...")
    try:
        result = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}"],
            capture_output=True, text=True, timeout=10,
        )
        running = result.stdout.strip().split("\n")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        print("ERROR: Docker is not running or not installed.")
        return False

    missing = [c for c in CONTAINERS if c not in running]
    if missing:
        print(f"ERROR: Containers not running: {', '.join(missing)}")
        print("Run: docker compose up -d")
        return False

    print(f"  All {len(CONTAINERS)} containers running.")
    return True


def check_env():
    """Verify .env file exists."""
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        print("ERROR: .env file not found.")
        print("Run: cp .env.example .env  (then add your API keys)")
        return False
    print("  .env file found.")
    return True


def run_step(number, total, name, script):
    """Run a single pipeline step, return True on success."""
    print(f"\nStep {number}/{total}: {name}")
    print(f"  Running {script}...")

    start = time.time()
    result = subprocess.run(
        [PYTHON, str(PROJECT_ROOT / script)],
        cwd=str(PROJECT_ROOT),
        env={**os.environ, "PYTHONPATH": str(PROJECT_ROOT)},
    )
    elapsed = time.time() - start

    if result.returncode != 0:
        print(f"  FAILED (exit code {result.returncode})")
        return False

    print(f"  Done ({elapsed:.1f}s)")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Run the full data pipeline for Prediction Market Intelligence."
    )
    parser.add_argument(
        "--skip-load", action="store_true",
        help="Skip data loading, only rebuild graph and embeddings",
    )
    args = parser.parse_args()

    print("=" * 50)
    print("Prediction Market Intelligence - Data Pipeline")
    print("=" * 50)

    if not check_docker():
        sys.exit(1)
    if not check_env():
        sys.exit(1)

    steps = BUILD_ONLY_STEPS if args.skip_load else PIPELINE_STEPS
    total = len(steps)
    failed = False

    for i, (name, script) in enumerate(steps, 1):
        if not run_step(i, total, name, script):
            print(f"\nPipeline FAILED at step {i}/{total}: {name}")
            failed = True
            break

    if not failed:
        print(f"\n{'=' * 50}")
        print(f"Pipeline complete ({total}/{total} steps).")
        print("Run the agent: chainlit run src/ui/app.py")
        print(f"{'=' * 50}")

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()

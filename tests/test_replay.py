"""Integration test for the dataset replay validation harness."""

import tempfile
from pathlib import Path

from goldenminutes.demo.replay_dataset import DEFAULT_DATASET, run_replay


def test_replay_pipeline_smoke():
    """Verify that run_replay executes on the organiser dataset with zero errors."""
    with tempfile.TemporaryDirectory() as td:
        out_dir = Path(td)
        results = run_replay(dataset_path=DEFAULT_DATASET, limit=200, output_dir=out_dir)

        assert results["total_errors"] == 0
        assert results["total_transactions"] == 200
        assert "metrics" in results
        assert "overall_recall" in results["metrics"]
        assert "false_friction_rate" in results["metrics"]
        assert "latency_ms" in results
        assert results["latency_ms"]["p50"] > 0
        assert (out_dir / "replay_organiser.json").exists()
        assert (out_dir / "replay_organiser.md").exists()

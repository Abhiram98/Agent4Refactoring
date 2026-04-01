from pathlib import Path

from benchmark.design_patterns.pattern_first.mine_from_pattern import run_pattern_first_mining
import refagent
import os
import logging

logging.basicConfig(level=logging.INFO)

def test_apache_cayenne():
    cayenne_path = Path(os.getenv("PROJECTS_BASE_PATH")).joinpath("cayenne")
    result = run_pattern_first_mining(
        repo_paths=[cayenne_path],
        output_path=refagent.data_folder.joinpath("design_patterns/miner/cayenne_candidates.json"),
        patterns=None,
        use_heuristic=False,
        dpdf_dataset_path=refagent.data_folder.joinpath("design_patterns/split_files/cayenne.json"),
        dpdf_project_name="cayenne",
        filter_greenfield=True,
        structural_strict=False,
    )
    print(result)
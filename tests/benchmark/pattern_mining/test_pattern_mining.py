from pathlib import Path

from benchmark.design_patterns.pattern_first.mine_from_pattern import run_pattern_first_mining
import refagent
import os
import logging
import sys

# logging.basicConfig(
#     level=logging.INFO,
#     format='%(asctime)s - %(levelname)s - %(message)s',
#     stream=sys.stdout
# )

def test_apache_cayenne():
    print("Testing Apache Cayenne")
    cayenne_path = Path(os.getenv("PROJECTS_BASE_PATH")).joinpath("cayenne")
    result = run_pattern_first_mining(
        repo_paths=[cayenne_path],
        output_path=refagent.data_folder.joinpath("design_patterns/miner/cayenne_candidates_llm.json"),
        patterns=None,
        use_heuristic=False,
        dpdf_dataset_path=refagent.data_folder.joinpath("design_patterns/split_files/cayenne.json"),
        dpdf_project_name="cayenne",
        filter_greenfield=True,
        structural_strict=False,
        use_llm_filter=True
    )
    print(result)

def test_drools():
    print("Testing Drools")
    cayenne_path = Path(os.getenv("PROJECTS_BASE_PATH")).joinpath("drools")
    result = run_pattern_first_mining(
        repo_paths=[cayenne_path],
        output_path=refagent.data_folder.joinpath("design_patterns/miner/drools_candidates_llm.json"),
        patterns=None,
        use_heuristic=False,
        dpdf_dataset_path=refagent.data_folder.joinpath("design_patterns/split_files/drools.json"),
        dpdf_project_name="drools",
        filter_greenfield=True,
        structural_strict=False,
        use_llm_filter=True
    )
    print(result)

def test_cucumber():
    print("Testing Drools")
    cayenne_path = Path(os.getenv("PROJECTS_BASE_PATH")).joinpath("cucumber-jvm")
    result = run_pattern_first_mining(
        repo_paths=[cayenne_path],
        output_path=refagent.data_folder.joinpath("design_patterns/miner/cucumber-jvm_candidates_llm.json"),
        patterns=None,
        use_heuristic=False,
        dpdf_dataset_path=refagent.data_folder.joinpath("design_patterns/split_files/cucumber-jvm.json"),
        dpdf_project_name="cucumber-jvm",
        filter_greenfield=True,
        structural_strict=False,
        use_llm_filter=True
    )
    print(result)


def test_caching():
    print("Testing AxonFramework")
    project_path = Path(os.getenv("PROJECTS_BASE_PATH")).joinpath("AxonFramework")
    result = run_pattern_first_mining(
        repo_paths=[project_path],
        output_path=refagent.data_folder.joinpath("design_patterns/miner/AxonFramework_candidates_llm.json"),
        patterns=None,
        use_heuristic=True,
        filter_greenfield=True,
        use_llm_filter=True,
        use_llm_detector=True,
        dpdf_dataset_path=None,
        dpdf_project_name=None,
    )
    print(result)
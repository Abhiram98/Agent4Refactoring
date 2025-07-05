import subprocess
import json
import re
import os
from typing import List

import refagent.utils.project_manager as pm

def parse_source_references(output: str) -> dict:
    """
    Parse the output string and extract source references as JSON.
    
    Args:
        output: String output from the JAR execution
    Returns:
        Dictionary containing the parsed output
    """
    try:
        # Extract the source references part using regex
        match = re.search(r'Source references: (\[.*\])', output)
        if match:
            refs = json.loads(match.group(1))
            return {
                "method": output.split(":")[1].split("\n")[0].strip(),
                "source_references": refs
            }
        return None
    except json.JSONDecodeError:
        print("Error parsing JSON from output")
        return None

def get_linked_elements_using_jar(src_path: str, file_path: str, line_number: int) -> List[str]:
    """
    Run the DataGeneration.jar with specified parameters.
    
    Args:
        src_path: Path to the source directory
        file_path: Path to the specific Java file
        line_number: Line number to process
    """
    print(f"{src_path=}\n"
          f"{file_path=}")
    print(f"{line_number=}")
    linked_files = []
    command = [
        "java",
        "-jar",
        os.environ["DATA_GENERATION_JAR_PATH"],
        src_path,
        file_path,
        str(line_number)
    ]
    
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        parsed_output = parse_source_references(result.stdout)
        if parsed_output:
            print("Parsed output:", json.dumps(parsed_output, indent=2))
        else:
            print("Raw output:", result.stdout)
    except subprocess.CalledProcessError as e:
        print("Error running JAR file:", e.stderr)


def get_linked_elements_from_project(project: pm.EvalProject, file_path: str, line_number: int) -> List[str]:
    linked_files = []
    for src_dir in project.get_src_directories():
        linked_files += get_linked_elements_using_jar(src_dir, file_path, line_number)
    return linked_files

# Example usage:
if __name__ == "__main__":
    # get_linked_elements_using_jar(
    #     "project_path",
    #     "file_path",
    #     line_number
    # )

    project = pm.EvalProject('flink')

    get_linked_elements_using_jar(
        str(project.get_project_path().joinpath("flink-core/src")),
        str(project.get_project_path().joinpath(
            "flink-core/src/main/java/org/apache/flink/util/ChildFirstClassLoader.java")),
            84
    )

    # linked_files = get_linked_elements_from_project(
    #     project,
    #     str(project.get_project_path().joinpath("flink-core/src/main/java/org/apache/flink/util/ChildFirstClassLoader.java")),
    #     84
    # )
    #
    # print(linked_files)

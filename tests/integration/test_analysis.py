import unittest
import os
from pathlib import Path
from refagent.agents.refactrix.analysis import AnalysisComponent, AugmentedIntent
from langchain_openai import ChatOpenAI
import refagent.utils.project_manager as pm

class TestAnalysisComponent(unittest.TestCase):
    def test_flink_7(self):
        """
        Test the AnalysisComponent with Flink repository commit 30970f56a598b63ace991ff8a89a3409e8d4cb6a.
        """
        project = pm.EvalProject("flink")
        project_path = project.get_project_path()
        source_file_path = os.path.join(project_path, "flink-core/src/main/java/org/apache/flink/configuration/AlgorithmOptions.java")
        # Define test inputs
        initial_intent = "Optimize the file handling logic for better performance"
        # source_file_path = "flink-core/src/main/java/org/apache/flink/configuration/AlgorithmOptions.java"
       
       # Read source code from the file
        with open(source_file_path, 'r') as f:
            source_code = f.read()
        
        # Initialize LLM
        model = ChatOpenAI(model="gpt-4o-mini")
        
        # Initialize the AnalysisComponent
        analysis_component = AnalysisComponent(
            initial_intent=initial_intent,
            codescene_context=True,
            source_code=source_code,
            source_file_path=source_file_path,
            model=model,
            context_information="This is a file from Apache Flink, a stream processing framework"
        )
        
        # Run the component
        result = analysis_component.run()
        
        # Assertions
        print(f"Original Intent: {result.original_intent}")
        print(f"Augmented Details: {result.augmented_intent}")

if __name__ == "__main__":
    unittest.main()

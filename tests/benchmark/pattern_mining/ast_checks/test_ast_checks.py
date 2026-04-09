import pytest
from pathlib import Path

from refagent.benchmark.design_patterns.scorecard.schema import (
    ImplementsInterfaceCheck,
    HasMethodCheck
)
from refagent.benchmark.design_patterns.scorecard.ast_checks import (
    ImplementsInterfaceCheckEvaluator,
    HasMethodCheckEvaluator
)

# Remember to install pytest if not already available in your environment!

def test_implements_interface_check_positive(tmp_path):
    """Test that a class correctly identifies an implemented interface."""
    java_file = tmp_path / "MyStrategy.java"
    java_file.write_text("public class MyStrategy implements JobExceptionHandlingStrategy {\n}")

    schema = ImplementsInterfaceCheck(
        target_file="MyStrategy.java",
        target_class="MyStrategy",
        interface_regex=".*HandlingStrategy"
    )
    evaluator = ImplementsInterfaceCheckEvaluator(schema)
    
    passed = evaluator.evaluate(repo_path=tmp_path, target_file=schema.target_file, target_class=schema.target_class)
    assert passed is True


def test_implements_interface_check_negative(tmp_path):
    """Test that the evaluator correctly fails if the interface is not present."""
    java_file = tmp_path / "MyStrategy.java"
    java_file.write_text("public class MyStrategy extends Application {\n}")

    schema = ImplementsInterfaceCheck(
        target_file="MyStrategy.java",
        target_class="MyStrategy",
        interface_regex="JobExceptionHandlingStrategy"
    )
    evaluator = ImplementsInterfaceCheckEvaluator(schema)
    
    passed = evaluator.evaluate(repo_path=tmp_path, target_file=schema.target_file, target_class=schema.target_class)
    assert passed is False


def test_implements_interface_check_with_expected_false(tmp_path):
    """Test the inverted flag functionality."""
    java_file = tmp_path / "MyStrategy.java"
    # The interface is NOT there
    java_file.write_text("public class MyStrategy extends Application {\n}")

    schema = ImplementsInterfaceCheck(
        target_file="MyStrategy.java",
        target_class="MyStrategy",
        interface_regex="JobExceptionHandlingStrategy",
        expected=False  # We assert it should NOT exist
    )
    evaluator = ImplementsInterfaceCheckEvaluator(schema)
    
    passed = evaluator.evaluate(repo_path=tmp_path, target_file=schema.target_file, target_class=schema.target_class)
    assert passed is True


def test_has_method_check_positive(tmp_path):
    """Test checking for a method by name and return type."""
    java_file = tmp_path / "WidgetFactory.java"
    java_file.write_text("""
    public class WidgetFactory {
        public Widget createWidget() {
            return new DefaultWidget();
        }
    }
    """)

    schema = HasMethodCheck(
        target_file="WidgetFactory.java",
        target_class="WidgetFactory",
        method_name_regex="create.*",
        return_type_regex="Widget"
    )
    evaluator = HasMethodCheckEvaluator(schema)
    
    passed = evaluator.evaluate(repo_path=tmp_path, target_file=schema.target_file, target_class=schema.target_class)
    assert passed is True


def test_has_method_check_wrong_return_type(tmp_path):
    """Test checking for a method that fails due to return type mismatch."""
    java_file = tmp_path / "WidgetFactory.java"
    java_file.write_text("""
    public class WidgetFactory {
        public Object createWidget() {
            return new DefaultWidget();
        }
    }
    """)

    # Same schema, looking for Widget return type
    schema = HasMethodCheck(
        target_file="WidgetFactory.java",
        target_class="WidgetFactory",
        method_name_regex="create.*",
        return_type_regex="Widget"
    )
    evaluator = HasMethodCheckEvaluator(schema)
    
    passed = evaluator.evaluate(repo_path=tmp_path, target_file=schema.target_file, target_class=schema.target_class)
    
    # Should fail because return type is Object, not Widget
    assert passed is False


def test_has_method_check_expected_false(tmp_path):
    """Verify that a refactoring correctly removed a giant god method."""
    java_file = tmp_path / "WidgetFactory.java"
    java_file.write_text("""
    public class WidgetFactory {
        public void newTinyHelper() {}
    }
    """)

    schema = HasMethodCheck(
        target_file="WidgetFactory.java",
        target_class="WidgetFactory",
        method_name_regex="godMethodThatShouldBeRemoved",
        expected=False  # We want it gone!
    )
    evaluator = HasMethodCheckEvaluator(schema)
    
    passed = evaluator.evaluate(repo_path=tmp_path, target_file=schema.target_file, target_class=schema.target_class)
    
    assert passed is True

import refagent.agents.refactrix.tools as tools
import refagent.agents.refactrix.planning as planning
import refagent.utils.output_parsers as output_parsers

from langchain_core.output_parsers import PydanticOutputParser, JsonOutputParser


def test_tool_descriptions():
    all_tools = tools.RefactoringToolProvider(ide_server=None).get()

    em_tool = all_tools.get("extract_method")
    for k, v in em_tool.args.items():
        print(f"{k}: {v.get('description')}")
    print([(i.description, i.args) for i in all_tools.values()])


def test_refactoring_plan_schema():
    print(planning.RefactoringPlan.schema_json())
    # parser = PydanticOutputParser(pydantic_object=planning.RefactoringPlan)
    # parser2 = JsonOutputParser(pydantic_object=planning.RefactoringPlan)
    # print(parser.get_format_instructions())
    # print(parser2.get_format_instructions())
    parser3 = output_parsers.SimplePydanticOutputParser(
        pydantic_object=planning.RefactoringPlan
    )
    print(parser3.get_format_instructions())

    message = """Here is the improved JSON instance that conforms to the provided schema, including the necessary details for the `execution_details` field:

```json
{
  "description": "An actionable step to improve the code-quality.",
  "properties": {
    "reason": "To improve clarity, we should rename 'flushCurrentDataBuffer' to 'flushCurrentChannelBuffer' to indicate it refers to flushing a channel buffer.",
    "final_code": "private void flushCurrentChannelBuffer()",
    "execution_details": "Rename the method 'flushCurrentDataBuffer' to 'flushCurrentChannelBuffer' in the SortBufferAccumulator class. Update all occurrences of 'flushCurrentDataBuffer' within the class to 'flushCurrentChannelBuffer'. This includes updating any method calls, comments, and documentation that reference the old method name to ensure consistency and clarity.",
    "refactoring_type": "rename",
    "file_path": "flink-runtime/src/main/java/org/apache/flink/runtime/io/network/partition/hybrid/tiered/storage/SortBufferAccumulator.java"
  },
  "required": [
    "reason",
    "final_code",
    "execution_details",
    "refactoring_type",
    "file_path"
  ]
}
```

### Explanation of Improvements:
1. **Execution Details**: The `execution_details` field has been expanded to explicitly state the steps involved in the renaming process. It mentions not only the renaming of the method but also the need to update all occurrences of the method name within the class, including any related comments or documentation. This ensures that the refactoring is comprehensive and maintains code clarity.
2. **Consistency**: The language used in the `execution_details` is clear and actionable, making it easier for a developer to follow the instructions during the refactoring process."""
    json_ = JsonOutputParser().parse(message)
    print(json_)

from langchain_core.tools import BaseTool


def get_tool_documentation(tool: BaseTool) -> str:

    arg_description = ""
    for arg, description in tool.args.items():
        arg_description += f"{arg}: {description.get('description')}\n"

    return f"""
    Description:
    {tool.description}
    
    Args: 
    {arg_description}
    """

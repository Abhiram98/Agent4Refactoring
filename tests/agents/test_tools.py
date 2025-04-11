import refagent.agents.refactrix.tools as tools


def test_tool_descriptions():
    all_tools = tools.RefactoringToolProvider(ide_server=None).get()


    em_tool = all_tools.get('extract_method')
    for k,v in em_tool.args.items():
        print(f"{k}: {v.get('description')}")
    print([(i.description, i.args) for i in all_tools.values()])
from langchain_openai import ChatOpenAI

import refagent.agents.refactrix.patch_curation_agent as patch_curation_agent
import refagent.utils.intellij_server as ij
import refagent.agents.refactrix.planning as planning
import refagent.agents.refactrix.react_agent as react_agent
import refagent.utils.project_manager as pm
import refagent.agents.refactrix.analysis as analysis


def test_patch_agent():

    project = pm.EvalProject("mekhq")

    v2_hash = "670a5fd05e75f797e14a2b1bd1836133cfe12e76"
    project.checkout(v2_hash, force=True)

    vendor = "openai"

    improved_commit_message = "Rename Variable: `commandKey` -> `command` on line 352"
    starting_file = "MekHQ/src/mekhq/gui/dialog/glossary/NewGlossaryDialog.java"

    old_name = improved_commit_message.split(" -> ")[0].split(" ")[-1]
    new_name = improved_commit_message.split(" -> ")[1].split(" ")[0]
    model = ChatOpenAI(model="o4-mini", temperature=1)

    # augmented_intent = analysis.AnalysisComponent(
    #     model=model,
    #     source_file_path=starting_file,
    #     source_code=project.get_file_contents(starting_file),
    #     initial_intent=improved_commit_message,
    #     old_name=old_name,
    #     new_name=new_name
    # ).run().augmented_intent
    augmented_intent = "Outline a naming cleanup: remove misleading “Key” suffix from variables that hold command prefixes rather than actual map/crypto keys. In this file, rename the local variable `commandKey` in handleHyperlinkClick to `command` (update its declaration, usages, comments, and tests). Then apply the same pattern across the codebase for any `*Key` variables that simply represent command or identifier strings (e.g. `eventKey`→`event`, `actionKey`→`action`), while preserving the suffix when it truly denotes a map key or encryption key."

    agent = patch_curation_agent.PatchAgent(
        ide_server=ij.IntellijServer.create_default(),
        # model_name=f"{vendor}:gpt-4o-mini",
        # reasoning_model_name=f"{vendor}:o4-mini",
        plan_component=planning.PlanningComponent,
        augmented_intent=augmented_intent,
        do_replication=True,
        llm_model=model,
    )

    agent.add_internal_commit(project.git_repo.commit(v2_hash))
    agent.initialize_agent(starting_file=starting_file)
    agent.perform_replication(
        augmented_intent,
        model,
        agent.generate_initial_plan(augmented_intent),
    )
    print(agent.augmented_intent)
    print(agent.files_and_planning)

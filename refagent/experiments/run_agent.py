import os
from pathlib import Path
import json
from typing import Optional, List
import traceback

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI
from grazie_langchain_utils.language_models.grazie import ChatGrazie
from pydantic.v1 import SecretStr
from grazie.api.client.endpoints import GrazieApiGatewayUrls
from grazie.api.client.gateway import AuthType

import refagent.benchmark.load as bm_load
import refagent
import refagent.experiments.results_manager as rm
import refagent.utils.project_manager as pm
import argparse
import refagent.utils.intellij_server as ij
import refagent.agents.refactrix.planning as planning
import refagent.agents.refactrix.react_agent as react_agent
import refagent.experiments.init_memory as init_memory
import refagent.agents.refactrix.analysis.scope as scope
import refagent.agents.refactrix.analysis.refine_intent as refine_intent

import langsmith as ls

from refagent.agents.refactrix.supported_refactorings import CodeElementType


def create_llm_model(vendor: str, model_name: str) -> BaseChatModel:
    if vendor == "grazie":
        grazie_token = os.getenv("GRAZIE_JWT_TOKEN")
        return ChatGrazie(
            grazie_jwt_token=SecretStr(grazie_token),
            client_auth_type=AuthType.APPLICATION,
            client_url=GrazieApiGatewayUrls.PRODUCTION,
            profile=model_name,
            client_agent_name="ref-agent",
            client_agent_version="0.1",
        )
    elif vendor == "openai":
        api_key = os.getenv("OPENAI_API_KEY") or os.getenv("LLM_TOKEN", "")
        os.environ["OPENAI_API_KEY"] = api_key
        if model_name.startswith("o4"):
            return ChatOpenAI(model=model_name, temperature=1)
        return ChatOpenAI(model=model_name)
    elif vendor == "openrouter":
        return ChatOpenAI(
            model=model_name,
            api_key=os.getenv("OPENROUTER_API_KEY"),
            base_url="https://openrouter.ai/api/v1",
            temperature=0,
            default_headers={
                "HTTP-Referer": "https://github.com/Agent4Refactoring",
                "X-Title": "ref-agent",
            },
        )
    raise ValueError(f"Unsupported vendor: {vendor}")


def setup_and_run(
    bench_point: bm_load.RenameItem,
    ij_server: ij.IntellijServer,
    results_saver: rm.ResultsManager,
    do_replication: bool,
    plan: Optional[planning.RefactoringPlan],
    initial_commit: Optional[str] = None,
    use_seed: bool = False,
):
    project = pm.EvalProject(bench_point.project_name)
    enable_hula = not args.disable_hula
    enable_memory = args.enable_memory.lower() == "true"
    disable_scope_refinement = args.disable_scope_refinement
    replication_max_iters = args.replication_max_iters

    # Memory is automatically disabled when critique is disabled
    if not enable_hula:
        enable_memory = False
    if args.human_validator:
        hula_type = "real_human"
    elif enable_hula:
        hula_type = "oracle_simulation"
    else:
        hula_type = "none"
        # print("[MEMORY] Memory disabled because critique is disabled")

    # Create memory database path in the same directory as results (even if disabled for logging)
    # Ensure the directory exists
    reasoning_model = (
        args.model if args.vendor == "openrouter" else args.reasoning_model
    )
    augmented_intent = gen_augmented_intent(
        old_name=bench_point.seed_example.old_name,
        new_name=bench_point.seed_example.new_name,
        vendor=args.vendor,
        model_name=reasoning_model,
    )
    memory_db_path = initialize_memory(
        augmented_intent, bench_point, do_replication, ij_server, use_seed, project
    )

    ij_server.reset_project_reload_counters()  # reset the counters, before checking out branch
    checkout_commit(bench_point, initial_commit, project, use_seed, do_replication)

    ij_server.open_project(project_path=project.get_project_path())
    ij_server.reload_project()
    ij_server.open_file(rel_file_path=Path(bench_point.starting_file))
    if plan is not None:
        plan_type = planning.get_mock_planning_component(plan)
    else:
        plan_type = planning.PlanningComponent

    model_spec = f"{args.vendor}:{args.model}"
    reasoning_model_spec = f"{args.vendor}:{reasoning_model}"

    agent = react_agent.ReactAgent(
        ide_server=ij_server,
        reasoning_model_name=reasoning_model_spec,
        model_name=model_spec,
        plan_component=plan_type,
        augmented_intent=scope.RenameScope(pattern=augmented_intent),
        do_replication=do_replication,
        hula_type=hula_type,
        enable_memory=enable_memory,
        benchmark_id=bench_point.ref_id,
        memory_database_url=f"sqlite:///{memory_db_path}",
        disable_scope_refinement=disable_scope_refinement,
        replication_max_iters=replication_max_iters,
    )

    try:
        if not do_replication:
            agent.initialize_agent(starting_file=bench_point.starting_file)
            agent.initialize_critique_component(bench_point.refactoring_changes)
            final_message = agent.run(
                initial_intent=bench_point.improved_commit_message,
                starting_file=bench_point.starting_file,
            )  # run the agent with commit message
        else:
            assert (
                initial_commit is not None
            ), "initial commit must be provided for replication"
            agent.add_internal_commit(project.git_repo.commit(initial_commit))
            agent.initialize_agent(starting_file=bench_point.starting_file)
            # Re-initialize critique component after agent initialization
            agent.initialize_critique_component(bench_point.refactoring_changes)
            agent.perform_replication(
                augmented_intent,
                agent.create_model(model_spec),
                agent.generate_initial_plan(augmented_intent),
            )
    except Exception as e:
        print("Agent execution failed ;/")
        print(traceback.format_exc())

    internal_commits = agent.internal_commits()
    previous_commits = "\n".join([i.message for i in internal_commits])

    if len(internal_commits) > 0:
        project.reset_head(len(internal_commits))
    agent.update_changed_files()
    project.safe_add(agent.files_changed())
    new_hash = project.git_repo.index.commit(
        f"changes to solve benchmark id {bench_point.ref_id} \n\n {previous_commits}"
    )
    # new_hash = project.commit_all(f"changes to solve benchmark id {bench_point.ref_id} \n\n {previous_commits}")
    print(f"New hash: {new_hash}")

    results_saver.update(
        bench_point.ref_id,
        {
            "changes": [c.to_json() for c in project.get_changes(new_hash)],
            "commit_hash": str(new_hash),
            "trajectory": [i.to_json() for i in agent.get_trajectory()],
            "performed_refactorings": agent.get_performed_refactorings(),
            "internal_commits": [str(i) for i in internal_commits],
            "performed_refactorings": agent.get_performed_refactorings(),
            "internal_commits": [str(i) for i in internal_commits],
            "replication_inspection_data": agent.get_replication_inspection_data(),
            "human_review_count": agent.human_review_count(),
            "human_accepted_count": agent.human_accepted_count(),
            "human_rejected_count": agent.human_rejected_count(),
        },
    )
    results_saver.save()


def initialize_memory(
    augmented_intent: str,
    bench_point: bm_load.RenameItem,
    do_replication: bool,
    ij_server: ij.IntellijServer,
    use_seed: bool,
    project: pm.EvalProject,
):
    db_name = f"memory_{args.run_identifier.split('/')[-1]}_{bench_point.ref_id}.db"
    orig_memory_db_path = str(refagent.repo_root.joinpath("logs").joinpath(db_name))
    memory_db_path = init_memory.InitMemory(
        do_replication=do_replication,
        use_seed=use_seed,
        initial_intent=augmented_intent,
        snippet_code=get_snippet_code(bench_point, project, ij_server),
        seed_old_name=bench_point.seed_example.old_name,
        seed_new_name=bench_point.seed_example.new_name,
        seed_type=CodeElementType.get_rminer_str(bench_point.seed_example.type),
        seed_file=bench_point.starting_file,
        seed_line_number=bench_point.seed_example.start_line,
        ref_id=bench_point.ref_id,
    ).init_memory(Path(orig_memory_db_path))
    memory_db_path = str(memory_db_path)
    print(
        f"[MEMORY] Memory feedback enabled - database will be saved to: {memory_db_path}"
    )
    return memory_db_path


def gen_augmented_intent(
    old_name: str,
    new_name: str,
    vendor: str,
    model_name: str,
) -> str:
    model = create_llm_model(vendor, model_name)

    return (
        refine_intent.GeneralizedScopeCreator(
            model=model, old_name=old_name, new_name=new_name
        )
        .get_generalized_intent()
        .pattern
    )


def get_snippet_code(
    bench_point: bm_load.RenameItem,
    project: pm.EvalProject,
    ij_server: ij.IntellijServer,
) -> str:
    ij_server.reset_project_reload_counters()  # reset the counters, before checking out branch
    project.checkout(bench_point.v1_hash, force=True)

    ij_server.open_project(project_path=project.get_project_path())
    ij_server.reload_project()

    ij_server.open_file(Path(bench_point.seed_example.leftSideLocations[0].filePath))
    return ij_server.call_tool(
        "get_source_code_snippet",
        name=bench_point.seed_example.old_name,
        line_num=bench_point.seed_example.start_line,
        file_path=bench_point.seed_example.leftSideLocations[0].filePath,
        code_element_type=CodeElementType.get_rminer_str(bench_point.seed_example.type),
    )


def checkout_commit(bench_point, initial_commit, project, use_seed, do_replication):
    project.restore_changes()

    if do_replication:
        assert (
            initial_commit is not None
        ), "initial commit must be provided for replication"
        project.checkout(initial_commit, force=True)
        project.restore_changes()
        return

    # checkout the right commit so that agent can resume execution
    if use_seed:
        # In this case, we would like to start the agent from the seed changes.
        if bench_point.seed_hash is not None:
            print(f"seed_hash={bench_point.seed_hash} bench_id={bench_point.ref_id}")
            project.checkout(bench_point.seed_hash, force=True)
            project.reset_head(1)
        else:
            project.checkout(bench_point.v1_hash, force=True)
    else:
        # in this case, we are running the agent without a seed hash
        if initial_commit is None:
            project.checkout(bench_point.v1_hash, force=True)
        else:
            project.checkout(initial_commit, force=True)


def load_benchmark(filepath, bench_type) -> List[bm_load.BenchmarkItem]:
    item_type = bm_load.BenchmarkItem
    if bench_type == "rename":
        item_type = bm_load.RenameItem

    with open(filepath) as f:
        benchmark_json = json.load(f)
    benchmark = bm_load.load_benchmark(benchmark_json, bench_type=item_type)
    return benchmark


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run the agent on the entire benchmark."
    )
    parser.add_argument(
        "-ij_server_url",
        type=str,
        help="Url where IJ server is running.",
        default=refagent.IJ_SERVER_URL,
    )
    parser.add_argument(
        "-ref_ids",
        type=str,
        help="IDs to run the agent on. "
        "To be called as a comma separated values."
        'e.g "1,2,3,4"',
        default=None,
    )
    parser.add_argument(
        "-run_identifier",
        type=str,
        help="An identifier to " "checkpoint the performance of the agent",
        default="default",
    )
    parser.add_argument(
        "--benchmark_file",
        type=str,
        help="Path to benchmark file",
        default=str(refagent.benchmark_full_file),
    )
    parser.add_argument(
        "--benchmark_type", type=str, help="default/rename", default="default"
    )
    parser.add_argument(
        "--replication",
        type=str,
        help="Whether to run the replication component or not. "
        "If true, ONLY the replication is performed, starting from an initial commit. "
        "If false, ONLY the initial agent is run (to edit only the starting file)",
        default="true",
    )

    parser.add_argument(
        "--replication_max_iters",
        type=int,
        help="Maximum number of iterations of the replication component",
        default=3,
    )
    parser.add_argument(
        "--use_change_summary",
        type=str,
        help="Whether to use the change summary or not. "
        "If true, the change summary is used to improve the intent. "
        "If false, the change summary is not used.",
        default="False",
    )
    parser.add_argument("--use_seed", action="store_true")
    parser.add_argument(
        "--disable_hula",
        help="Whether to diable oracle-based human-in-the-loop component. "
        "If true, agent suggestions are NOT validated against oracle data before execution.",
        action="store_true",
    )
    parser.add_argument(
        "--human_validator",
        help="Whether to use the human as a reviewer. If set, the tool expects a human to be working live. ",
        action="store_true",
    )
    parser.add_argument(
        "--disable_scope_refinement",
        help="Whether to enable Scope refinement loop. "
        "If true, agent will not do scope refinement.",
        action="store_true",
    )

    parser.add_argument(
        "--enable_memory",
        type=str,
        help="Whether to enable memory component for storing and retrieving refactoring suggestions. "
        "If false, memory storage and retrieval are disabled. "
        "Note: Memory is automatically disabled when critique is disabled.",
        default="true",
    )
    parser.add_argument(
        "--force_run",
        help="Whether to force a run of the agent, even if it ran previously.",
        action="store_true",
    )
    parser.add_argument(
        "--vendor",
        type=str,
        choices=["grazie", "openai", "openrouter"],
        default="grazie",
        help="LLM provider (default: grazie)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="openai-gpt-4o-mini",
        help="Execution model name/profile. For openrouter use e.g. qwen/qwen3.5-9b",
    )
    parser.add_argument(
        "--reasoning_model",
        type=str,
        default="openai-o4-mini",
        help="Reasoning model name/profile (defaults to --model for openrouter)",
    )
    args = parser.parse_args()

    selected_ref_ids = (
        [int(i) for i in args.ref_ids.split(",")] if args.ref_ids is not None else None
    )

    ij_server = ij.IntellijServer(server_url=args.ij_server_url)

    planning_results = {}

    initial_save_file = rm.ResultsManager(
        run_identifier=args.run_identifier, save_file="no-replication.json"
    ).save_file_path
    initial_commits = {}
    if initial_save_file.exists():
        with open(initial_save_file) as f:
            initial_run = json.load(f)
            initial_commits = {
                i["id"]: i["response"]["commit_hash"] for i in initial_run
            }
    initial_commits = {}
    if initial_save_file.exists():
        with open(initial_save_file) as f:
            initial_run = json.load(f)
            initial_commits = {
                i["id"]: i["response"]["commit_hash"] for i in initial_run
            }

    use_previous = False

    do_replication = args.replication.lower() == "true"
    results_file = (
        "no-replication.json" if not do_replication else "post-replication.json"
    )
    benchmark = load_benchmark(args.benchmark_file, "rename")
    results_saver = rm.ResultsManager(
        run_identifier=args.run_identifier, save_file=results_file
    )

    for bench_point in benchmark:

        # if args.use_change_summary.lower() == "true":
        #     print(f"Using change summary for {bench_point.change_summary}")
        # else:
        #     print(args.use_change_summary)
        # print(f"Using initial commit for {bench_point.improved_commit_message}")

        if selected_ref_ids is not None and bench_point.ref_id not in selected_ref_ids:
            # print(f"Skipping ref id {bench_point.ref_id} as it is not a selected one. "
            #       f"Selected: {selected_ref_ids}")
            continue

        if not args.force_run and results_saver.exists(bench_point.ref_id):
            # print(f"skipping ref if {bench_point.ref_id} because it was previously worked upon.")
            continue

        with ls.trace(
            name=f"refactoring agent - {args.run_identifier}. bench point {bench_point.ref_id}",
            tags=[args.run_identifier],
        ) as tracer:
            setup_and_run(
                bench_point,
                ij_server,
                results_saver,
                do_replication,
                plan=planning_results.get(bench_point.ref_id),
                initial_commit=initial_commits.get(bench_point.ref_id),
                use_seed=args.use_seed,
            )

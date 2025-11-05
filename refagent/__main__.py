import os
from pathlib import Path

from grazie.api.client.endpoints import GrazieApiGatewayUrls
from grazie.api.client.gateway import AuthType
from langchain_core.language_models import BaseChatModel
from pydantic.v1 import SecretStr, BaseModel

import refagent
import argparse
import refagent.utils.intellij_server as ij
import refagent.agents.refactrix.react_agent as react_agent
import refagent.agents.refactrix.planning as planning

import refagent.agents.refactrix.analysis.scope as scope
from grazie_langchain_utils.language_models.grazie import ChatGrazie

import refagent.experiments.init_memory as init_memory
import refagent.agents.refactrix.analysis.refine_intent as refine_intent
import refagent.agents.refactrix.rename_suggestions as rename_suggestions
import refagent.agents.memory.orm_memory as orm_mem


class AgentRunner(BaseModel):

    seed_old_name: str
    seed_new_name: str
    seed_line_num: int
    seed_element_type: str
    seed_file: str

    @property
    def model(self) -> BaseChatModel:
        grazie_token = os.getenv("GRAZIE_JWT_TOKEN")
        if grazie_token is None:
            raise RuntimeError(
                "GRAZIE_JWT_TOKEN environment variable not set. Unable to make LLM calls."
            )
        return ChatGrazie(
            grazie_jwt_token=SecretStr(grazie_token),
            client_auth_type=AuthType.APPLICATION,
            client_url=GrazieApiGatewayUrls.PRODUCTION,
            profile="openai-o4-mini",
            client_agent_name="ref-agent",
            client_agent_version="0.1",
        )

    @property
    def ij_server(self) -> ij.IntellijServer:
        return ij.IntellijServer(server_url=os.getenv("IJ_SERVER_URL"))

    @property
    def vendor(self):
        return "grazie"

    def run_agent(self):
        self.run_pre_replication()
        self.run_post_replication()

    def gen_initial_scope(
        self,
        old_name: str,
        new_name: str,
    ) -> scope.RenameScope:
        return refine_intent.GeneralizedScopeCreator(
            model=self.model, old_name=old_name, new_name=new_name
        ).get_generalized_intent()

    def run_pre_replication(self):

        print("Running agent on initial file. Pre replication.")
        self.ij_server.call_tool("review/noop")
        self.ij_server.call_tool("review/reset_scope")  # reset the view in the IDE.
        self.ij_server.call_tool("/review/inc_replication_files") # log that we're inspecting one file

        # open file so that the sever has the required context.
        self.ij_server.open_file(Path(self.seed_file))

        initial_scope = self.gen_initial_scope(
            old_name=self.seed_old_name,
            new_name=self.seed_new_name,
        )
        print("Initial scope: {}".format(initial_scope))
        self.ij_server.call_tool(
            "review/set_scope",
            pattern=initial_scope.pattern,
            condition=str(initial_scope.condition),
        )

        mem_path = init_memory.InitMemory(
            seed_old_name=self.seed_old_name,
            seed_new_name=self.seed_new_name,
            seed_file=self.seed_file,
            seed_type=self.seed_element_type,
            seed_line_number=self.seed_line_num,
            ref_id=1,
            do_replication=False,
            use_seed=True,
            initial_intent=initial_scope.pattern,
            snippet_code="",  # todo: fill out snippet code
        ).init_memory(self.memory_path)
        memory_db_path = str(mem_path)
        print(
            f"[MEMORY] Memory feedback enabled - database will be saved to: {memory_db_path}"
        )

        # noinspection PyArgumentList
        agent = react_agent.ReactAgent(
            ide_server=self.ij_server,
            reasoning_model_name=f"{self.vendor}:openai-o4-mini",
            model_name=f"{self.vendor}:openai-gpt-4o-mini",
            plan_component=planning.PlanningComponent,
            augmented_intent=initial_scope,
            do_replication=False,
            hula_type="real_human",
            enable_memory=True,
            benchmark_id=1,
            memory_database_url=f"sqlite:///{memory_db_path}",
            disable_scope_refinement=False,
            replication_max_iters=3,
        )

        agent.initialize_agent(starting_file=self.seed_file)
        agent.initialize_critique_component([])
        final_message = agent.run(
            initial_intent=str(initial_scope),
            starting_file=self.seed_file,
        )

        self.ij_server.call_tool("/review/inc_files_inspected")
        print("Pre replication complete.")

    def run_post_replication(self):
        self.ij_server.call_tool("review/noop")
        post_replication_memory = init_memory.InitMemory(
            do_replication=True,
            use_seed=True,
            initial_intent=None,
            snippet_code=None,
            seed_file=None,
            seed_type=None,
            seed_line_number=None,
            seed_old_name=None,
            seed_new_name=None,
            ref_id=None,
        ).init_memory(refagent.repo_root.joinpath("logs/episodic_memory.db"))
        memory_db_path = str(post_replication_memory)

        latest_scope = self.no_replication_memory.get_latest_scope()
        # noinspection PyArgumentList
        agent = react_agent.ReactAgent(
            ide_server=self.ij_server,
            reasoning_model_name=f"{self.vendor}:openai-o4-mini",
            model_name=f"{self.vendor}:openai-gpt-4o-mini",
            plan_component=planning.PlanningComponent,
            augmented_intent=latest_scope,
            do_replication=False,
            hula_type="real_human",
            enable_memory=True,
            benchmark_id=1,
            memory_database_url=f"sqlite:///{memory_db_path}",
            disable_scope_refinement=False,
            replication_max_iters=3,
        )

        agent.initialize_agent(starting_file=self.seed_file)
        # Re-initialize critique component after agent initialization
        agent.initialize_critique_component([])
        agent.perform_replication(
            str(latest_scope),
            agent.create_model(f"{self.vendor}:openai-gpt-4o-mini"),
            agent.generate_initial_plan(latest_scope),
        )
        print("Post replication complete.")

    @property
    def no_replication_memory(self):
        return orm_mem.ORMRefactoringMemory(
            f"sqlite:///{self.memory_path_pre_replication}"
        )

    @property
    def memory_path(self) -> Path:
        return refagent.repo_root.joinpath("logs/episodic_memory.db")

    @property
    def memory_path_pre_replication(self) -> Path:
        return refagent.repo_root.joinpath("logs/episodic_memory-no-replication.db")


if __name__ == "__main__":
    print("Welcome to the coordinated renaming agent")
    parser = argparse.ArgumentParser(
        description="Run the agent on a specific coordinated rename."
    )

    parser.add_argument("--seed_old_name", type=str, help="Seed old name.")
    parser.add_argument("--seed_new_name", type=str, help="Seed new name.")
    parser.add_argument("--seed_line_num", type=int, help="Seed line number.")
    parser.add_argument(
        "--seed_element_type", type=str, help="Type of code element that was renamed"
    )
    parser.add_argument("--seed_file", type=str, help="Seed file.")

    args = parser.parse_args()
    try:
        assert (
            rename_suggestions.CodeElementType(args.seed_element_type) is not None
        )  # validate the arg has proper type
    except ValueError as e:
        print("arg seed_element_type, is not a valid type. See below. ")
        raise e

    AgentRunner(
        seed_old_name=args.seed_old_name,
        seed_new_name=args.seed_new_name,
        seed_line_num=args.seed_line_num,
        seed_element_type=args.seed_element_type,
        seed_file=args.seed_file,
    ).run_agent()

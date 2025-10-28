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

import agents.refactrix.analysis.scope as scope
from grazie_langchain_utils.language_models.grazie import ChatGrazie

from benchmark.load import RenameItem
from experiments.init_memory import InitMemory


class AgentRunner(BaseModel):

    seed_old_name: str
    seed_new_name: str
    seed_line_num: int
    seed_element_type: str
    seed_file: str


    @property
    def model(self) -> BaseChatModel:
        grazie_token = os.getenv("GRAZIE_JWT_TOKEN")
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
        return ij.IntellijServer(server_url=os.getenv('IJ_SERVER_URL'))

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
        pass

    def run_pre_replication(self):

        print("Running agent on initial file. Pre replication.")

        # todo: create generalized intent.
        initial_scope = self.gen_initial_scope(
            old_name=args.seed_example.old_name,
            new_name=args.seed_example.new_name,
        )

        mem_path = InitMemory(
            benchmark_item=RenameItem(), #todo: fill out the RenameItem
            do_replication=False,
            use_seed=True,
            initial_intent=initial_scope.pattern,
            snippet_code="" #todo: fill out snippet code
        ).init_memory(Path("/app/episodic_memory.db"))
        memory_db_path = str(mem_path)
        print(
            f"[MEMORY] Memory feedback enabled - database will be saved to: {memory_db_path}"
        )

        # todo: trigger agent.
        # noinspection PyArgumentList
        agent = react_agent.ReactAgent(
            ide_server=self.ij_server,
            reasoning_model_name=f"{self.vendor}:openai-o4-mini",
            model_name=f"{self.vendor}:openai-gpt-4o-mini",
            project=project, # todo: replace with IntellijPM
            plan_component= planning.PlanningComponent,
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

    def run_post_replication(self):
        post_replication_memory = InitMemory(
            benchmark_item=None,
            do_replication=True,
            use_seed=True,
            initial_intent=None,
            snippet_code=None,
        ).init_memory(Path("/app/episodic_memory.db"))
        memory_db_path = str(post_replication_memory)


        latest_scope = "" # todo: fetch latest scope from run
        # noinspection PyArgumentList
        agent = react_agent.ReactAgent(
            ide_server=self.ij_server,
            reasoning_model_name=f"{self.vendor}:openai-o4-mini",
            model_name=f"{self.vendor}:openai-gpt-4o-mini",
            project=project, # todo: replace with IntellijPM
            plan_component= planning.PlanningComponent,
            augmented_intent=latest_scope,
            do_replication=False,
            hula_type="real_human",
            enable_memory=True,
            benchmark_id=1,
            memory_database_url=f"sqlite:///{memory_db_path}",
            disable_scope_refinement=False,
            replication_max_iters=3,
        )

        assert (
                initial_commit is not None # todo: remove dependency on initial commit.
        ), "initial commit must be provided for replication"
        agent.add_internal_commit(project.git_repo.commit(initial_commit))
        agent.initialize_agent(starting_file=self.seed_file)
        # Re-initialize critique component after agent initialization
        agent.initialize_critique_component([])
        agent.perform_replication(
            latest_scope,
            agent.create_model(f"{self.vendor}:openai-gpt-4o-mini"),
            agent.generate_initial_plan(latest_scope),
        )


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

    AgentRunner(
        seed_old_name=args.seed_old_name,
        seed_new_name=args.seed_new_name,
        seed_line_num=args.seed_line_num,
        seed_element_type=args.seed_element_type,
        seed_file=args.seed_file
    ).run_agent()

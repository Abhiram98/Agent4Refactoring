import refagent
import argparse


def run_agent():
    pass


if __name__ == '__main__':
    print("Welcome to the coordinated renaming agent")
    parser = argparse.ArgumentParser(description='Run the agent on a specific coordinated rename.')

    parser.add_argument('--ij_server_url', help="Url where IJ server is running.", type=str)
    parser.add_argument('--seed_old_name', type=str, help='Seed old name.')
    parser.add_argument('--seed_new_name', type=str, help='Seed new name.')
    parser.add_argument('--seed_line_num', type=int, help='Seed line number.')
    parser.add_argument('--seed_element_type', type=str, help='Type of code element that was renamed')
    parser.add_argument('--seed_file', type=str, help='Seed file.')

    args = parser.parse_args()

    # todo: initialise memory with seed

    # todo: trigger agent.



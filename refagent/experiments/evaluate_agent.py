import refagent.agents.agent1 as agent1
import refagent.benchmark.load as bm_load
import refagent

if __name__ == '__main__':
    agent = agent1.Agent()
    benchamark = bm_load.load_benchmark(refagent.benchmark_lite_json)

    for bench_point in benchamark:
        agent.run(bench_point)
"""Single-shot host; every invocation reconstructs LangGraph from SQLite."""
import argparse
import json
import os
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command
from runner import Runner
from flow import build

parser = argparse.ArgumentParser()
parser.add_argument('--root', required=True)
parser.add_argument('--job', default='main')
parser.add_argument('--event', default='null')
parser.add_argument('--seed', default='null')
parser.add_argument('action', choices=['start', 'status', 'resume', 'recover'])
args = parser.parse_args()
runner = Runner(args.root)
with SqliteSaver.from_conn_string(str(runner.root / 'checkpoints.sqlite')) as saver:
    graph = build(runner, saver)
    config = {'configurable': {'thread_id': args.job}}
    state = graph.get_state(config)
    if args.action == 'start' and not state.values:
        graph.invoke({'job': args.job, **(json.loads(args.seed) or {})}, config, durability='sync')
    elif args.action == 'recover' and state.next and not any(t.interrupts for t in state.tasks):
        graph.invoke(None, config, durability='sync')
    elif args.action == 'resume' and state.next:
        graph.invoke(Command(resume=json.loads(args.event)), config, durability='sync')
    state = graph.get_state(config)
    print(json.dumps({'values': state.values, 'next': list(state.next), 'pid': os.getpid()}, ensure_ascii=False))

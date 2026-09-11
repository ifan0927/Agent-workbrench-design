"""Single-shot host transport. Each invocation is a fresh platform process."""

import argparse
import json
from pathlib import Path
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command
from flow import build
from runner import Runner, lock


def execute(root, job, action, event=None, mode='question'):
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    runner = Runner(root)
    # Serialize graph writes per job, not the lifetime of workers or all jobs.
    import hashlib
    with lock(root / ('job-' + hashlib.sha256(job.encode()).hexdigest() + '.lock')):
        with SqliteSaver.from_conn_string(str(root / 'checkpoints.sqlite')) as saver:
            graph = build(runner, saver)
            config = {'configurable': {'thread_id': job}}
            snapshot = graph.get_state(config)
            if action == 'start':
                if not snapshot.values:
                    graph.invoke({'job': job, 'mode': mode, 'rejected': 0}, config, durability='sync')
            elif action == 'resume':
                if snapshot.next:
                    if not any(task.interrupts for task in snapshot.tasks):
                        raise ValueError('recover interrupted dispatch before delivering events')
                    graph.invoke(Command(resume=event), config, durability='sync')
            elif action == 'recover':
                if snapshot.next and not any(task.interrupts for task in snapshot.tasks):
                    graph.invoke(None, config, durability='sync')
            elif action != 'status':
                raise ValueError('unsupported action')
            snapshot = graph.get_state(config)
            return {'values': snapshot.values, 'next': list(snapshot.next),
                    'interrupts': [i.value for task in snapshot.tasks for i in task.interrupts]}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', required=True)
    parser.add_argument('--job', required=True)
    parser.add_argument('action', choices=['start', 'status', 'resume', 'recover'])
    parser.add_argument('--event', default='null')
    parser.add_argument('--mode', default='question', choices=['question', 'complete', 'tree'])
    args = parser.parse_args()
    print(json.dumps(execute(args.root, args.job, args.action, json.loads(args.event), args.mode)))

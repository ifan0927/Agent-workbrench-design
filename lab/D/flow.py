"""The sole owner of dispatch, waiting, human continuation, and cancellation policy."""

from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.types import Command, interrupt


class State(TypedDict, total=False):
    job: str
    sequence: int
    attempt: str
    mode: str
    status: str
    result: dict
    evidence: dict
    question: str
    answer: dict
    rejected: int


def build(runner, checkpointer):
    def prepare(s):
        sequence = s.get('sequence', 0) + 1
        attempt = f'{s["job"]}:{sequence}'
        runner.register(attempt, s.get('mode', 'question') if sequence == 1 else 'complete')
        return {'attempt': attempt, 'sequence': sequence, 'status': 'dispatching'}

    def dispatch(s):
        observed = runner.ensure(s['attempt'])
        if observed['state'] in ('unknown', 'cancel_requested'):
            return Command(update={'status': 'interrupted', 'evidence': observed}, goto=END)
        return Command(update={'status': 'waiting_worker'}, goto='wait_worker')

    def reject(s, target):
        return Command(update={'rejected': s.get('rejected', 0) + 1}, goto=target)

    def wait_worker(s):
        event = interrupt({'kind': 'worker', 'attempt': s['attempt']})
        if not isinstance(event, dict) or event.get('attempt') != s['attempt']:
            return reject(s, 'wait_worker')
        if event.get('kind') == 'cancel':
            return Command(goto='cancel_request')
        if event.get('kind') != 'poll':
            return reject(s, 'wait_worker')
        observed = runner.observe(s['attempt'])
        if observed['state'] == 'running':
            return Command(goto='wait_worker')
        if observed['state'] != 'result':
            return Command(update={'status': 'interrupted', 'evidence': observed}, goto=END)
        return Command(update={'result': observed['result'], 'evidence': observed}, goto='result')

    def result(s):
        if s['result']['status'] == 'waiting':
            return Command(update={'status': 'waiting_human', 'question': s['result']['question']}, goto='answer')
        return Command(update={'status': 'completed'}, goto=END)

    def answer(s):
        event = interrupt({'kind': 'question', 'attempt': s['attempt'], 'question': s['question']})
        if not isinstance(event, dict) or event.get('attempt') != s['attempt']:
            return reject(s, 'answer')
        if event.get('kind') == 'cancel':
            return Command(goto='cancel_request')
        if (event.get('kind') != 'answer' or event.get('question') != s['question']
                or event.get('value') != 'continue' or event.get('continue') is not True):
            return reject(s, 'answer')
        return Command(update={'answer': event}, goto='prepare')

    def cancel_request(s):
        return {'status': 'cancelling'}

    def stop(s):
        observed = runner.stop(s['attempt'])
        return {'status': 'cancelled' if observed['state'] == 'stopped' else 'cancel_unknown',
                'evidence': observed}

    graph = StateGraph(State)
    for name, node in [('prepare', prepare), ('dispatch', dispatch), ('wait_worker', wait_worker),
                       ('result', result), ('answer', answer), ('cancel_request', cancel_request), ('stop', stop)]:
        graph.add_node(name, node)
    graph.add_edge(START, 'prepare')
    graph.add_edge('prepare', 'dispatch')
    graph.add_edge('cancel_request', 'stop')
    graph.add_edge('stop', END)
    return graph.compile(checkpointer=checkpointer)

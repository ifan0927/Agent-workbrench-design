"""LangGraph is the sole owner of question, coding, validation, and review transitions."""
import hashlib
import json
import os
import time
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.types import Command, interrupt
from environment import ROOT, COMMIT
from verification import verify


class State(TypedDict, total=False):
    job: str
    phase: str
    attempt: str
    status: str
    task: dict
    collected: dict
    question: str
    question_id: str
    answer: dict
    candidate: dict
    verification: dict
    verification_path: str
    rejected: int
    adopted: bool
    source: str
    base: str
    cancellation: dict


def build(runner, saver):
    def prepare(s):
        phase = s.get('phase', 'question')
        attempt = s['job'] + ':' + phase
        task = s.get('task') or json.loads((ROOT / 'inputs/task-r0.json').read_text())
        spec = {'mode': phase, 'task': task}
        if phase == 'repair': spec.update(source=s['source'], base=s['base'])
        if phase == 'coding':
            spec.update(resume=s['collected']['thread']['thread']['id'], home=s['collected']['home'])
        if phase == 'review':
            spec.update(source=s['candidate']['bundle'], base=s['candidate']['commit'], test_report=s['verification_path'])
        runner.register(attempt, spec)
        return {'phase': phase, 'attempt': attempt, 'task': task, 'status': 'dispatching'}

    def dispatch(s):
        observed = runner.ensure(s['attempt'])
        if observed['state'] == 'unknown':
            return Command(update={'status': 'interrupted'}, goto=END)
        if os.environ.get('E_CRASH') == 'running' and s['phase'] == 'coding':
            for _ in range(200):
                rows = runner.events(s['attempt'])
                if any(r['kind'] == 'item/started' and r['data'].get('item', {}).get('type') == 'commandExecution' for r in rows):
                    runner.event('experiment_host_crash', {'point': 'coding_command_started', 'pid': os.getpid(), 'attempt': s['attempt']})
                    os._exit(86)
                time.sleep(.2)
            raise RuntimeError('no_coding_command_observed_for_crash')
        return Command(update={'status': 'waiting_worker'}, goto='wait_worker')

    def wait_worker(s):
        event = interrupt({'kind': 'worker', 'attempt': s['attempt']})
        if isinstance(event, dict) and event.get('attempt') == s['attempt'] and event.get('kind') == 'cancel':
            return Command(goto='cancel_request')
        if not isinstance(event, dict) or event.get('attempt') != s['attempt'] or event.get('kind') != 'poll':
            return Command(update={'rejected': s.get('rejected', 0) + 1}, goto='wait_worker')
        observed = runner.observe(s['attempt'])
        if observed['state'] == 'running': return Command(goto='wait_worker')
        if observed['state'] != 'result': return Command(update={'status': 'interrupted'}, goto=END)
        if os.environ.get('E_CRASH') == 'saved' and s['phase'] == 'coding':
            runner.event('experiment_host_crash', {'point': 'result_saved_before_collect', 'pid': os.getpid(), 'attempt': s['attempt']})
            os._exit(87)
        return Command(goto='collect')

    def collect(s):
        result = runner.collect(s['attempt'])
        if not runner.stop(s['attempt']):
            return Command(update={'status': 'stop_unknown'}, goto=END)
        if s['phase'] == 'parallel':
            return Command(update={'collected': result, 'status': 'completed'}, goto=END)
        if s['phase'] == 'question':
            assert result['response']['status'] == 'waiting' and result['response']['question']
            from environment import source_state
            assert source_state(__import__('pathlib').Path(result['work']))['files'] == json.loads((ROOT / 'results/e0/baseline.json').read_text())['files']
            q = result['response']['question']
            return Command(update={'status': 'waiting_answer', 'collected': result, 'question': q, 'question_id': hashlib.sha256(q.encode()).hexdigest()}, goto='answer')
        if s['phase'] in ('coding', 'repair'):
            candidate = runner.candidate(s['attempt'])
            return Command(update={'collected': result, 'candidate': candidate}, goto='verify')
        from evidence import eligible
        approved = eligible(s['candidate'], s['verification'], result['binding'],
                            __import__('environment').digest(runner.paths(s['attempt']) / 'input/task.json'))
        return Command(update={'status': 'completed' if approved else 'review_failed', 'collected': result, 'adopted': False}, goto=END)

    def answer(s):
        event = interrupt({'kind': 'question', 'question_id': s['question_id'], 'revision': 0, 'base': COMMIT})
        valid = isinstance(event, dict) and event.get('kind') == 'answer' and event.get('question_id') == s['question_id'] and event.get('revision') == 0 and event.get('base') == COMMIT and event.get('continue') is True and event.get('value') == json.loads((ROOT / 'inputs/controller.json').read_text())['answer']
        if not valid:
            runner.event('answer_rejected', {'kind': event.get('kind') if isinstance(event, dict) else None})
            return Command(update={'rejected': s.get('rejected', 0) + 1}, goto='answer')
        task = dict(s['task'])
        task.pop('unresolved')
        task.update(revision=1, article_policy=event['value'], phase='已取得綁定回答，現在實作有界變更並新增聚焦測試。執行 lab skill 的 test 模式。完成後停止；controller 會獨立驗證完整 build。')
        runner.event('answer_accepted', event)
        return Command(update={'answer': event, 'task': task, 'phase': 'coding'}, goto='prepare')

    def validation(s):
        report, path = verify(runner, s['candidate'], s['job'])
        if report['status'] != 'pass':
            return Command(update={'status': 'verification_failed', 'verification': report, 'verification_path': path}, goto=END)
        return Command(update={'verification': report, 'verification_path': path, 'phase': 'review'}, goto='prepare')

    def cancel_request(s): return {'status': 'cancelling'}

    def cancel(s):
        result = runner.cancel(s['attempt'])
        return {'status': 'cancelled' if result['container_stopped'] else 'cancel_unknown', 'cancellation': result}

    g = StateGraph(State)
    for name, fn in [('prepare', prepare), ('dispatch', dispatch), ('wait_worker', wait_worker), ('collect', collect), ('answer', answer), ('verify', validation), ('cancel_request', cancel_request), ('cancel', cancel)]:
        g.add_node(name, fn)
    g.add_edge(START, 'prepare')
    g.add_edge('prepare', 'dispatch')
    g.add_edge('cancel_request', 'cancel')
    g.add_edge('cancel', END)
    return g.compile(checkpointer=saver)

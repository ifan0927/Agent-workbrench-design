"""Small artifact and handoff contracts for the C experiments, not a platform."""

import hashlib
import json
import os
from pathlib import Path
import subprocess


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False).encode()


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Evidence is append-only; callers choose a new run directory.
    with path.open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def git(repo, *args):
    env = {k: os.environ[k] for k in ('PATH', 'TMPDIR', 'LANG') if k in os.environ}
    env.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL='/dev/null',
               GIT_TERMINAL_PROMPT='0', GIT_AUTHOR_NAME='C Lab',
               GIT_AUTHOR_EMAIL='lab@example.invalid', GIT_COMMITTER_NAME='C Lab',
               GIT_COMMITTER_EMAIL='lab@example.invalid')
    p = subprocess.run(['git', '-c', 'core.hooksPath=/dev/null', '-C', str(repo), *args],
                       env=env, capture_output=True, timeout=30)
    if p.returncode:
        raise ValueError('git_command_failed:' + args[0])
    return p.stdout.decode().strip()


def collect(root, raw, exit_code, required):
    """Keep accessible partial output even when a successful process lies."""
    root = Path(root)
    artifacts = {p.name: digest(p.read_bytes()) for p in root.iterdir()
                 if p.is_file() and not p.is_symlink()}
    gaps = []
    try:
        result = json.loads(raw)
        valid = (isinstance(result, dict) and set(result) == {
            'status', 'summary', 'artifacts', 'question', 'incomplete', 'side_effects'}
            and result['status'] in ('complete', 'waiting', 'partial')
            and isinstance(result['summary'], str) and bool(result['summary'].strip())
            and all(isinstance(result[k], list) and all(isinstance(x, str) for x in result[k])
                    for k in ('artifacts', 'incomplete', 'side_effects'))
            and (result['question'] is None or isinstance(result['question'], dict)))
    except (ValueError, TypeError):
        result, valid = None, False
    if not valid:
        gaps.append('invalid_result_format')
    else:
        gaps += ['missing_declared:' + p for p in result['artifacts'] if p not in artifacts]
        gaps += result['incomplete']
        if result['question'] is not None:
            gaps.append('unanswered_question')
        if result['status'] != 'complete':
            gaps.append('worker_' + result['status'])
    gaps += ['missing_required:' + p for p in required if p not in artifacts]
    if exit_code != 0:
        gaps.append('execution_failed')
    return {'execution': 'completed' if exit_code == 0 else 'failed',
            'delivery': 'complete' if not gaps else 'incomplete',
            'artifacts': artifacts, 'gaps': gaps,
            'user_adoption': 'undecided', 'next_authorization': None}


def candidate(repo, bundle, requirement):
    if git(repo, 'status', '--porcelain', '--untracked-files=all'):
        raise ValueError('uncommitted_candidate')
    head = git(repo, 'rev-parse', 'HEAD')
    git(repo, 'bundle', 'create', str(Path(bundle).resolve()), '--all')
    return {'commit': head, 'tree': git(repo, 'rev-parse', 'HEAD^{tree}'),
            'bundle_sha256': digest(Path(bundle).read_bytes()),
            'requirement_sha256': digest(encoded(requirement))}


def restore(bundle, target, binding):
    if digest(Path(bundle).read_bytes()) != binding['bundle_sha256']:
        raise ValueError('bundle_hash_mismatch')
    target = Path(target)
    target.mkdir()
    git(target, 'init', '-q')
    git(target, 'bundle', 'verify', str(Path(bundle).resolve()))
    git(target, 'fetch', '-q', str(Path(bundle).resolve()), binding['commit'])
    git(target, 'checkout', '-q', '--detach', binding['commit'])
    if git(target, 'rev-parse', 'HEAD^{tree}') != binding['tree']:
        raise ValueError('tree_mismatch')
    git(target, 'fsck', '--full')


def evidence_gate(binding, evidence):
    gaps = []
    for kind in ('test', 'review'):
        matches = [e for e in evidence if e.get('kind') == kind and e.get('binding') == binding]
        if not matches:
            gaps.append('missing_current_' + kind)
        elif not any(e.get('passed') is True for e in matches):
            gaps.append('failed_current_' + kind)
    return {'passed': not gaps, 'gaps': gaps}


def answer_transition(state, event):
    """Only an explicit scoped answer-and-continue creates a dispatch."""
    updated = json.loads(json.dumps(state))
    updated.setdefault('events', []).append(event)
    if event.get('type') == 'comment':
        return updated, False
    question = state.get('question') or {}
    if (state.get('phase') != 'waiting' or event.get('type') != 'answer_and_continue'
            or event.get('question_id') != question.get('id')
            or event.get('requirement_sha256') != state.get('requirement_sha256')
            or event.get('candidate') != state.get('candidate')
            or event.get('value') not in question.get('options', [])
            or not event.get('event_id')
            or any(e.get('event_id') == event['event_id'] for e in state.get('events', []))):
        return updated, False
    updated.update(phase='ready', answer=event,
                   next_authorization={'scope': 'implement_answered_requirement', 'event_id': event['event_id']})
    return updated, True

"""Synthetic configuration sources and immutable per-worker materialization."""

import hashlib
import json
from pathlib import Path
import shutil

VERSION = '0.153.4'
IMAGE = 'agent-workbench-lab-a:' + VERSION
SELECTED = ['b-selected', 'b-twin']
MODE = '''This is a bounded synthetic configuration experiment. Do not delegate or use network tools.
Use local shell and the provided lab_checkpoint tool only. Never install dependencies.
Set receipt.mode to "mode" and receipt.priority to "mode" even if user instructions disagree.
Only write files under /out. Preserve /work/protected.txt.
Before reading skill references or creating artifacts, call lab_checkpoint exactly once.
Then read /codex-home/skills/b-selected/SKILL.md and follow it.
Use the repo copy of b-twin by its explicit path /work/.agents/skills/b-twin/SKILL.md;
read its reference and put its marker into receipt.twin.
'''
TASK = '''Execute this small fixture task and write /out/receipt.json as a JSON object.
Include common, repo, layered, version, mode, priority, task, twin and proof fields.
Use each instruction source's specified values. Set priority="task", layered="task", task="task".
Get proof from the selected skill's reference via its script, not a guessed value.
Do not change protected.txt. Finish with a short completion message.
'''
TOOL = {'type': 'function', 'name': 'lab_checkpoint',
        'description': 'Required local checkpoint before reading skill references and writing lab artifacts.',
        'inputSchema': {'type': 'object', 'properties': {}, 'additionalProperties': False}}


def put(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def skill(root, name, body, description='Only for the explicit synthetic B lab task.'):
    put(root / 'SKILL.md', f'---\nname: {name}\ndescription: {description}\n---\n\n{body}\n')


def sources(root, version):
    root = Path(root)
    put(root / 'common.md', f'''# Synthetic shared agreement
Set receipt.common="common", receipt.layered="common", receipt.version="{version}".
Only write artifacts under /out. Preserve /work/protected.txt.
''')
    skill(root / 'library/b-selected', 'b-selected', '''Read references/value.json relative to this skill.
Run `node /codex-home/skills/b-selected/scripts/proof.js`.
Use its output as receipt.proof. Do not invent the proof or copy it from the task text.''')
    put(root / 'library/b-selected/references/value.json', json.dumps({'proof': f'proof-{version}-74931'}))
    put(root / 'library/b-selected/scripts/proof.js', '''// Resolve the frozen reference relative to this script.
const fs = require('fs');
const path = require('path');
process.stdout.write(JSON.parse(fs.readFileSync(path.join(__dirname, '../references/value.json'))).proof);
''')
    skill(root / 'library/b-twin', 'b-twin', 'Read references/value.txt; use it as receipt.twin.')
    put(root / 'library/b-twin/references/value.txt', 'user-twin')
    skill(root / 'library/b-unselected', 'b-unselected', 'Unselected library canary. Never required.')
    put(root / 'repo/AGENTS.md', '''# Synthetic repository agreement
Set receipt.repo="repo" and receipt.layered="repo".
Preserve protected.txt. Only write under /out.
''')
    put(root / 'repo/protected.txt', 'must remain unchanged\n')
    skill(root / 'repo/.agents/skills/b-twin', 'b-twin', 'Read references/value.txt; use it as receipt.twin.')
    put(root / 'repo/.agents/skills/b-twin/references/value.txt', 'repo-twin')
    skill(root / 'repo/.agents/skills/b-repo-extra', 'b-repo-extra', 'Repo discovery canary; not selected by the host.')
    skill(root / 'repo/.agents/skills/b-missing', 'b-missing', 'Requires the b_absent MCP server. If unavailable stop; never install anything.')
    metadata = {'dependencies': {'tools': [{'type': 'mcp', 'value': 'b_absent', 'description': 'Intentionally absent lab dependency'}]}}
    put(root / 'repo/.agents/skills/b-missing/SKILL.json', json.dumps(metadata))
    put(root / 'repo/.agents/skills/b-missing/agents/openai.yaml', 'dependencies:\n  tools:\n    - type: mcp\n      value: b_absent\n      description: Intentionally absent lab dependency\n')
    put(root / 'repo/.agents/skills/b-invalid/SKILL.md', '---\nname: b-invalid\n---\nMissing required description.\n')
    skill(root / 'user-skills/b-user-extra', 'b-user-extra', 'User home discovery canary; not selected by the host.')


def file_map(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob('*')) if p.is_file()}


def snapshot(source, target, model):
    if target.exists():
        raise ValueError('snapshot_exists')
    # Do not preserve symlinks into mutable source trees.
    if any(p.is_symlink() for p in source.rglob('*')):
        raise ValueError('source_symlink')
    target.mkdir(parents=True)
    shutil.copytree(source / 'repo', target / 'repo')
    (target / 'repo/.git').mkdir()
    shutil.copytree(source / 'user-skills', target / 'user-skills')
    put(target / 'home/AGENTS.md', (source / 'common.md').read_text())
    for name in SELECTED:
        shutil.copytree(source / 'library' / name, target / 'home/skills' / name)
    put(target / 'home/config.toml', f'''model = {json.dumps(model)}
model_provider = "openai"
model_reasoning_effort = "low"
cli_auth_credentials_store = "ephemeral"
web_search = "disabled"
check_for_update_on_startup = false
[analytics]
enabled = false
[projects."/work"]
trust_level = "trusted"
''')
    put(target / 'mode.txt', MODE)
    put(target / 'task.txt', TASK)
    manifest = {'codex_version': VERSION, 'image': IMAGE, 'model_requested': model,
                'effort_requested': 'low', 'selected_skills': SELECTED,
                'assembly': ['CODEX_HOME/AGENTS.md', '/work/AGENTS.md', 'thread.developerInstructions', 'turn.input'],
                'source_files': file_map(source), 'snapshot_files': file_map(target),
                'dynamic_tools': [TOOL], 'cwd': '/work'}
    put(target / 'manifest.json', json.dumps(manifest, indent=2) + '\n')
    return manifest


def preflight(skills, required_names=(), available_mcp=()):
    enabled = [s for s in skills if s['enabled']]
    problems = []
    for name in required_names:
        candidates = [s for s in enabled if s['name'] == name]
        if len(candidates) != 1:
            problems.append({'name': name, 'reason': 'missing' if not candidates else 'ambiguous',
                             'paths': [s['path'] for s in candidates]})
        for candidate in candidates:
            for dep in (candidate.get('dependencies') or {}).get('tools', []):
                if dep['type'] == 'mcp' and dep['value'] not in available_mcp:
                    problems.append({'name': name, 'reason': 'missing_dependency', 'dependency': dep['value']})
    return problems


def settings_errors(model, effort, catalog, tools, required_tools):
    matches = [m for m in catalog if m['model'] == model]
    errors = []
    if len(matches) != 1:
        errors.append('model_unavailable')
    elif effort not in [e['reasoningEffort'] for e in matches[0]['supportedReasoningEfforts']]:
        errors.append('reasoning_effort_unavailable')
    if any(name not in [t['name'] for t in tools] for name in required_tools):
        errors.append('required_tool_missing')
    return errors

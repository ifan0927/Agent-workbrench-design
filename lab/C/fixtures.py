"""Synthetic task inputs and an independent executable acceptance oracle."""

import json
from pathlib import Path
from core import git, save

VERSION = '0.153.4'
IMAGE = 'agent-workbench-lab-a:' + VERSION
REQUIREMENT = {
    'id': 'normalize-tags-v1',
    'goal': 'Implement CommonJS normalizeTags(array) in tags.cjs; export { normalizeTags }.',
    'rules': ['Trim surrounding whitespace; lowercase ASCII tags.',
              'Deduplicate after normalization; sort lexicographically.',
              'Do not mutate the input array; reject non-array or non-string entries with TypeError.',
              'Empty normalized strings need an explicit product decision before implementation.',
              'Add usage.md with the chosen empty-tag policy and a concrete example.'],
    'pending_question': {'id': 'empty-tags', 'options': ['discard', 'reject']},
    'limits': ['Only tags.cjs and usage.md may change.', 'No dependencies, network tools, push, PR or deployment.'],
}
ORACLE = """const assert = require('node:assert/strict');
const { normalizeTags } = require('/work/tags.cjs');
const input = [' B ', 'a', 'b', '', '   ', 'A'];
assert.deepEqual(normalizeTags(input), ['a', 'b']);
assert.deepEqual(input, [' B ', 'a', 'b', '', '   ', 'A']);
assert.deepEqual(normalizeTags([]), []);
assert.deepEqual(normalizeTags([' z ', 'X', ' x ', 'y']), ['x', 'y', 'z']);
assert.throws(() => normalizeTags(null), TypeError);
assert.throws(() => normalizeTags('a'), TypeError);
assert.throws(() => normalizeTags([42]), TypeError);
assert.throws(() => normalizeTags(['', null]), TypeError);
console.log('C_ACCEPTANCE_OK');
"""


def seed(path):
    path = Path(path)
    path.mkdir()
    (path / 'tags.cjs').write_text("exports.normalizeTags = function (tags) { throw new Error('not implemented'); };\n")
    (path / 'README.md').write_text('# C 組合成標籤工具\n\n規則由外部 requirement.json 固定。\n')
    git(path, 'init', '-q', '-b', 'main')
    git(path, 'add', '--', 'tags.cjs', 'README.md')
    git(path, 'commit', '-q', '-m', 'Synthetic C baseline')
    return git(path, 'rev-parse', 'HEAD')


RESULT_SCHEMA = {'type': 'object', 'properties': {
    'status': {'type': 'string', 'enum': ['complete', 'waiting', 'partial']},
    'summary': {'type': 'string'}, 'artifacts': {'type': 'array', 'items': {'type': 'string'}},
    'question': {'anyOf': [{'type': 'null'}, {'type': 'object', 'properties': {
        'id': {'type': 'string'}, 'text': {'type': 'string'},
        'options': {'type': 'array', 'items': {'type': 'string'}}},
        'required': ['id', 'text', 'options'], 'additionalProperties': False}]},
    'incomplete': {'type': 'array', 'items': {'type': 'string'}},
    'side_effects': {'type': 'array', 'items': {'type': 'string'}}},
    'required': ['status', 'summary', 'artifacts', 'question', 'incomplete', 'side_effects'],
    'additionalProperties': False}

REVIEW_SCHEMA = {'type': 'object', 'properties': {
    'candidate': {'type': 'string'}, 'requirement_sha256': {'type': 'string'},
    'verdict': {'type': 'string', 'enum': ['pass', 'changes_requested', 'unable']},
    'findings': {'type': 'array', 'items': {'type': 'object', 'properties': {
        'path': {'type': 'string'}, 'line': {'type': 'integer'}, 'reason': {'type': 'string'},
        'blocking': {'type': 'boolean'}}, 'required': ['path', 'line', 'reason', 'blocking'],
        'additionalProperties': False}},
    'limitations': {'type': 'array', 'items': {'type': 'string'}}},
    'required': ['candidate', 'requirement_sha256', 'verdict', 'findings', 'limitations'],
    'additionalProperties': False}

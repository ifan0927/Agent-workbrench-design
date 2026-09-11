"""Fingerprint B's protocol fields from the installed, pinned Codex binary."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
from fixtures import VERSION

ROOT = Path(__file__).resolve().parent
NAMES = ['ConfigReadParams', 'ConfigReadResponse', 'SkillsListParams', 'SkillsListResponse',
         'ThreadStartParams', 'ThreadStartResponse', 'TurnStartParams', 'DynamicToolCallParams',
         'DynamicToolCallResponse']


def run():
    with tempfile.TemporaryDirectory() as tmp:
        env = {'PATH': '/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin', 'CODEX_HOME': tmp}
        version = subprocess.check_output(['codex', '--version'], env=env, text=True, stderr=subprocess.DEVNULL).strip()
        if version != 'codex-cli ' + VERSION:
            raise RuntimeError('version_mismatch')
        out = Path(tmp) / 'schema'
        subprocess.run(['codex', 'app-server', 'generate-json-schema', '--experimental', '--out', str(out)], env=env, capture_output=True, check=True)
        interfaces = {}
        for name in NAMES:
            paths = list(out.rglob(name + '.json'))
            if len(paths) != 1:
                raise RuntimeError('schema_missing_or_ambiguous')
            raw = paths[0].read_bytes()
            d = json.loads(raw)
            interfaces[name] = {'sha256': hashlib.sha256(raw).hexdigest(), 'required': d.get('required', []),
                                'properties': sorted(d.get('properties', {}))}
        (ROOT / 'results/contract.json').write_text(json.dumps({'mode': 'generated_schema_no_model', 'codex_version': VERSION, 'interfaces': interfaces}, indent=2) + '\n')
        print(json.dumps({'interfaces': len(interfaces), 'codex_version': VERSION}))


if __name__ == '__main__':
    run()

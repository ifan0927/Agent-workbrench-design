"""Check C's interfaces against the pinned local Codex, without model use."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
from core import digest
from fixtures import VERSION

ROOT = Path(__file__).resolve().parent
FIELDS = {'ThreadStartParams': ['ephemeral', 'allowProviderModelFallback', 'developerInstructions'],
          'ThreadStartResponse': ['thread', 'model', 'reasoningEffort'],
          'ThreadResumeParams': ['threadId'], 'TurnStartParams': ['threadId', 'outputSchema'],
          'TurnInterruptParams': ['threadId', 'turnId']}


def run():
    with tempfile.TemporaryDirectory() as tmp:
        env = {'PATH': os.environ['PATH'], 'CODEX_HOME': tmp}
        version = subprocess.check_output(['codex', '--version'], env=env, text=True, stderr=subprocess.DEVNULL).strip()
        if version != 'codex-cli ' + VERSION:
            raise ValueError('version_mismatch')
        output = Path(tmp) / 'schema'
        subprocess.run(['codex', 'app-server', 'generate-json-schema', '--experimental', '--out', str(output)],
                       env=env, capture_output=True, check=True)
        interfaces = {}
        for name, fields in FIELDS.items():
            paths = list(output.rglob(name + '.json'))
            if len(paths) != 1:
                raise ValueError('schema_missing_or_ambiguous')
            raw = paths[0].read_bytes()
            schema = json.loads(raw)
            if not set(fields) <= schema['properties'].keys():
                raise ValueError('required_interface_missing')
            interfaces[name] = {'sha256': digest(raw), 'checked_fields': fields}
        report = {'mode': 'generated_schema_no_model', 'codex_version': VERSION, 'interfaces': interfaces}
        (ROOT / 'results' / 'contract.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps({'interfaces': len(interfaces), 'codex_version': VERSION}))


if __name__ == '__main__':
    run()

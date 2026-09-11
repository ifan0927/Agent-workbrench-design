"""Capture a compact interface fingerprint from the installed Codex binary."""

import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

from auth import atomic_json
from live import ROOT, VERSION
from rpc import clean_env


def run():
    with tempfile.TemporaryDirectory() as tmp:
        env = {**clean_env(), "CODEX_HOME": tmp}
        version = subprocess.check_output(["codex", "--version"], env=env, text=True).strip()
        if version != "codex-cli " + VERSION:
            raise RuntimeError("version_mismatch")
        output = Path(tmp) / "schema"
        subprocess.run(["codex", "app-server", "generate-json-schema", "--experimental", "--out", str(output)],
                       env=env, check=True, capture_output=True)
        names = ["InitializeParams", "LoginAccountParams", "ChatgptAuthTokensRefreshParams",
                 "ChatgptAuthTokensRefreshResponse", "ThreadStartParams", "TurnStartParams",
                 "TurnInterruptParams", "TurnCompletedNotification", "SkillsListParams"]
        interfaces = {}
        for name in names:
            files = list(output.rglob(name + ".json"))
            if len(files) != 1:
                raise RuntimeError("schema_missing_or_ambiguous")
            raw = files[0].read_bytes()
            schema = json.loads(raw)
            interfaces[name] = {"sha256": hashlib.sha256(raw).hexdigest(),
                                "required": schema.get("required", []),
                                "properties": sorted(schema.get("properties", {}))}
            if name == "LoginAccountParams":
                external = next(s for s in schema["oneOf"]
                                if s["properties"]["type"]["enum"] == ["chatgptAuthTokens"])
                interfaces[name]["external_auth"] = {
                    "description": external["description"], "required": external["required"],
                    "properties": sorted(external["properties"])}
        atomic_json(ROOT / "results" / "contract.json", {
            "mode": "generated_schema_no_model", "codex_version": VERSION,
            "official_reference": "https://learn.chatgpt.com/docs/app-server",
            "interfaces": interfaces})
        print(json.dumps({"codex_version": VERSION, "interfaces_checked": len(interfaces)}))


if __name__ == "__main__":
    run()

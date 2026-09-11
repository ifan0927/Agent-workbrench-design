"""Exercise the real container protocol with fake credentials and no network."""

import asyncio
import base64
import json
import tempfile
import uuid
from pathlib import Path

from auth import atomic_json
from live import ROOT, VERSION, command, docker_command
from rpc import Rpc, clean_env


def fake_token():
    def part(value):
        return base64.urlsafe_b64encode(json.dumps(value).encode()).decode().rstrip("=")
    return part({"alg": "none"}) + "." + part({
        "email": "lab-canary@example.invalid", "exp": 4102444800,
        "https://api.openai.com/auth": {"chatgpt_account_id": "lab-account-canary", "chatgpt_plan_type": "plus"}
    }) + ".LAB_SIGNATURE_CANARY"


async def run():
    token = fake_token()
    name = "awb-a-probe-" + uuid.uuid4().hex[:10]
    with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
        Path(tmp).chmod(0o755)
        (Path(tmp) / "input.json").write_text('{"value":42}')
        args = docker_command(name, Path(tmp), network=False)
        rpc = Rpc(args, ROOT, clean_env(), (token,))
        try:
            async with rpc:
                initialized = await rpc.initialize()
                login = await rpc.request("account/login/start", {
                    "type": "chatgptAuthTokens", "accessToken": token,
                    "chatgptAccountId": "lab-account-canary", "chatgptPlanType": "plus"})
                updated = await rpc.event("account/updated")
                account = await rpc.request("account/read", {"refreshToken": False})
                shell = await rpc.request("command/exec", {
                    "command": ["cat", "/work/input.json"], "cwd": "/work",
                    "sandboxPolicy": {"type": "readOnly"}, "timeoutMs": 5000})
                external_shell = await rpc.request("command/exec", {
                    "command": ["cat", "/work/input.json"], "cwd": "/work",
                    "sandboxPolicy": {"type": "externalSandbox", "networkAccess": "enabled"},
                    "timeoutMs": 5000})
                inspection = await command("docker", "inspect", name)
                processes = await command("docker", "exec", name, "ps", "-eo", "args")
                # Scan all writable container locations without printing their contents.
                scan = await command("docker", "exec", name, "node", "-e", '''
const fs = require('fs'); let auth = false; let canary = false; let count = 0;
function walk(p) { for (const e of fs.readdirSync(p,{withFileTypes:true})) {
 const q = p+'/'+e.name; if (e.isDirectory()) walk(q); else if(e.isFile()) {
 count++; if(e.name==='auth.json') auth=true;
 const s=fs.readFileSync(q).toString(); if(s.includes('LAB_SIGNATURE_CANARY')) canary=true;
 } } }
walk('/codex-home'); walk('/tmp');
console.log(JSON.stringify({auth_file_present:auth,canary_in_files:canary,files_scanned:count}));
''')
                findings = json.loads(scan)
                report = {"mode": "real_app_server_fake_token_network_none", "codex_version": VERSION,
                          "initialize_ok": bool(initialized), "login_type": login["type"],
                          "auth_mode": updated["authMode"],
                          "fake_account_read_matches": account["account"].get("email") == "lab-canary@example.invalid",
                          "sandbox_read_exit_code": shell["exitCode"],
                          "sandbox_read_matches": shell["stdout"].strip() == '{"value":42}',
                          "sandbox_read_diagnostic": shell["stderr"][:1000].replace(token, "[REDACTED]"),
                          "external_sandbox_read_exit_code": external_shell["exitCode"],
                          "external_sandbox_read_matches": external_shell["stdout"].strip() == '{"value":42}',
                          "token_in_args_or_environment": token in inspection or token in processes,
                          **findings}
        finally:
            try:
                await command("docker", "rm", "-f", name)
            except Exception:
                pass
        report["token_in_stderr"] = rpc.stderr_secret_found
        report["passed"] = (report["auth_mode"] == report["login_type"] == "chatgptAuthTokens"
                            and report["fake_account_read_matches"]
                            and report["external_sandbox_read_matches"]
                            and not any(report[k] for k in ("token_in_args_or_environment", "auth_file_present",
                                                           "canary_in_files", "token_in_stderr")))
        atomic_json(ROOT / "results" / "probe.json", report)
        print(json.dumps(report))
        return 0 if report["passed"] else 1


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(run()))
    except Exception as exc:
        print(json.dumps({"passed": False, "error_type": type(exc).__name__,
                          "local_error": str(exc) if isinstance(exc, RuntimeError) else None}))
        raise SystemExit(1)

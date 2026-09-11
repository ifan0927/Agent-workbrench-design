"""Two container experiment. Existing credentials are read-only, never refreshed."""

import argparse
import asyncio
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import time
import uuid

from auth import atomic_json, classify
from rpc import Rpc, RpcError, clean_env

ROOT = Path(__file__).resolve().parent
VERSION = "0.153.4"
IMAGE = "agent-workbench-lab-a:" + VERSION


async def command(*args):
    proc = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE,
                                                stderr=asyncio.subprocess.DEVNULL)
    out, _ = await asyncio.wait_for(proc.communicate(), 30)
    if proc.returncode:
        raise RuntimeError(f"local_command_failed:{args[0]}:{args[1]}:{proc.returncode}")
    return out.decode().strip()


def load_auth(path):
    raw = path.read_bytes()
    d = json.loads(raw)
    if d.get("auth_mode") not in (None, "chatgpt") or d.get("OPENAI_API_KEY"):
        raise RuntimeError("chatgpt_auth_required")
    tokens = d.get("tokens", {})
    access, account = tokens.get("access_token"), tokens.get("account_id")
    if not access or not account:
        raise RuntimeError("missing_external_token_fields")
    # Claims are a local consistency check, not signature or entitlement validation.
    payload = access.split(".")[1]
    claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    if claims.get("exp", 0) < time.time() + 180:
        raise RuntimeError("access_token_expired_or_near_expiry")
    auth_claims = claims.get("https://api.openai.com/auth", {})
    if auth_claims.get("chatgpt_account_id") != account:
        raise RuntimeError("account_claim_mismatch")
    external = {"accessToken": access, "chatgptAccountId": account}
    if auth_claims.get("chatgpt_plan_type"):
        external["chatgptPlanType"] = auth_claims["chatgpt_plan_type"]
    return external, hashlib.sha256(raw).digest(), tuple(v for v in tokens.values() if isinstance(v, str))


def docker_command(name, work, network=True):
    args = ["docker", "run", "--rm", "-i", "--name", name, "--init",
            "--label", "agent-workbench.lab=A", "--cap-drop=ALL",
            "--security-opt=no-new-privileges", "--memory=1g", "--cpus=1", "--pids-limit=128",
            "--read-only", "--tmpfs", "/tmp:rw,nosuid,size=256m",
            "--tmpfs", "/codex-home:rw,nosuid,uid=1000,gid=1000,mode=700,size=128m",
            "--mount", f"type=bind,src={work},dst=/work,readonly"]
    if not network:
        args += ["--network=none"]
    return args + [IMAGE, "-c", 'cli_auth_credentials_store="ephemeral"',
                   "-c", 'model_provider="openai"', "-c", 'web_search="disabled"',
                   "-c", 'analytics.enabled=false', "-c", 'check_for_update_on_startup=false']


async def worker(label, work, external, secrets, model, seconds, barrier):
    name = "awb-a-" + label + "-" + uuid.uuid4().hex[:10]
    result = {"worker": label, "status": "failed", "refresh_requests": 0}
    args = docker_command(name, work)
    rpc = Rpc(args, ROOT, clean_env(), secrets)
    try:
        async with rpc:
            await rpc.initialize()
            login = await rpc.request("account/login/start", {"type": "chatgptAuthTokens", **external})
            updated = await rpc.event("account/updated")
            account = await rpc.request("account/read", {"refreshToken": False})
            result["external_auth_mode"] = login.get("type") == updated.get("authMode") == "chatgptAuthTokens"
            result["account_type"] = (account.get("account") or {}).get("type")
            result["plan_matches"] = (account.get("account") or {}).get("planType") == external.get("chatgptPlanType")
            if not result["external_auth_mode"] or result["account_type"] != "chatgpt":
                raise RuntimeError("unexpected_account_mode")
            if model:
                chosen = model
            else:
                models = await rpc.request("model/list", {"includeHidden": False})
                chosen = next(m["model"] for m in models["data"] if m.get("isDefault"))
            result["model"] = chosen
            thread = await rpc.request("thread/start", {
                "model": chosen, "modelProvider": "openai", "cwd": "/work",
                "approvalPolicy": "never", "sandbox": "read-only", "ephemeral": True,
                "allowProviderModelFallback": False,
                "developerInstructions": "This is a bounded lab task. Do not delegate. "
                "Use only local read-only tools to read input.json. Do not use network tools. "
                f"Your worker marker is {label}. Return the requested JSON only."})
            thread_id = thread["thread"]["id"]
            result["thread_id"] = thread_id
            result["model"] = thread["model"]
            result["config_distinct_marker"] = label
            await asyncio.wait_for(barrier.wait(), 30)
            usage = None
            text = ""
            turn_id = None
            try:
                async with asyncio.timeout(seconds):
                    started = await rpc.request("turn/start", {
                        "threadId": thread_id,
                        "sandboxPolicy": {"type": "externalSandbox", "networkAccess": "enabled"},
                        "input": [{"type": "text", "text": "Read input.json in the current directory. "
                                   "Perform its operation. Respond with worker (your configured marker) "
                                   "and result (a string). Do not modify any files."}],
                        "outputSchema": {"type": "object", "properties": {
                            "worker": {"type": "string"}, "result": {"type": "string"}},
                            "required": ["worker", "result"], "additionalProperties": False}})
                    turn_id = started["turn"]["id"]
                    while True:
                        event = await rpc.notifications.get()
                        method, p = event["method"], event["params"]
                        if method == "lab/transportClosed":
                            raise RuntimeError("transport_closed")
                        if p.get("threadId") != thread_id:
                            continue
                        if method == "turn/started" and p["turn"]["id"] == turn_id:
                            result["started_monotonic"] = time.monotonic()
                        if method == "thread/tokenUsage/updated" and p.get("turnId") == turn_id:
                            usage = p["tokenUsage"]["total"]
                        if method == "item/completed" and p.get("turnId") == turn_id and p["item"]["type"] == "agentMessage":
                            text = p["item"]["text"]
                        if method == "turn/completed" and p["turn"]["id"] == turn_id:
                            result["ended_monotonic"] = time.monotonic()
                            result["status"] = p["turn"]["status"]
                            if p["turn"].get("error"):
                                result["action"] = classify(p["turn"]["error"])
                            break
            except TimeoutError:
                result["status"] = "timeout"
                if turn_id:
                    try:
                        await rpc.request("turn/interrupt", {"threadId": thread_id, "turnId": turn_id}, timeout=5)
                    except Exception:
                        pass
            result["usage"] = usage
            expected = {"alpha": "42", "beta": "apricot,kiwi,pear"}[label]
            try:
                parsed = json.loads(text)
                result["output_matches"] = parsed == {"worker": label, "result": expected}
                result["output_diagnostic"] = {
                    "json_parseable": True, "worker_matches": isinstance(parsed, dict) and parsed.get("worker") == label,
                    "result_matches": isinstance(parsed, dict) and parsed.get("result") == expected}
            except (ValueError, TypeError):
                result["output_matches"] = False
                result["output_diagnostic"] = {"json_parseable": False, "characters": len(text)}
            # Never persist arbitrary model text, account details, or RPC payloads.
            result["output_secret_found"] = any(s in text for s in secrets if s)
            auth_present = await command("docker", "exec", name, "sh", "-c",
                                         "if test -e /codex-home/auth.json; then echo present; else echo absent; fi")
            result["worker_auth_file_absent"] = auth_present == "absent"
            result["refresh_requests"] = rpc.refresh_requests
    except Exception as exc:
        result["action"] = classify(exc.error) if isinstance(exc, RpcError) else "stop"
        result["error_type"] = type(exc).__name__
        await barrier.abort()
    finally:
        try:
            await command("docker", "rm", "-f", name)
        except Exception:
            pass
    result["stderr_secret_found"] = rpc.stderr_secret_found
    result["stderr_bytes_discarded"] = rpc.stderr_bytes
    return result


async def run(args):
    external, before, secrets = load_auth(args.auth_file)
    version = await command("docker", "run", "--rm", "--network=none", "--entrypoint", "codex", IMAGE, "--version")
    if version != "codex-cli " + VERSION:
        raise RuntimeError("codex_version_mismatch")
    runtime = ROOT / ".runtime" / uuid.uuid4().hex
    runtime.mkdir(parents=True)
    fixtures = {"alpha": {"operation": "sum integers, decimal string", "values": [13, 17, 12]},
                "beta": {"operation": "sort lexicographically, join with commas", "values": ["pear", "kiwi", "apricot"]}}
    for label, fixture in fixtures.items():
        work = runtime / label
        work.mkdir()
        (work / "input.json").write_text(json.dumps(fixture))
    barrier = asyncio.Barrier(2)
    try:
        workers = await asyncio.gather(*(worker(label, runtime / label, external, secrets,
                                              args.model, args.seconds, barrier) for label in fixtures))
        overlap = max(0, min(w.get("ended_monotonic", 0) for w in workers)
                      - max(w.get("started_monotonic", float("inf")) for w in workers))
        a1 = all(w["status"] == "completed" and w.get("output_matches") and w.get("external_auth_mode")
                 and w.get("worker_auth_file_absent") and w.get("plan_matches") for w in workers)
        a2 = a1 and overlap > 0 and len({w.get("thread_id") for w in workers}) == 2
        unchanged = before == hashlib.sha256(args.auth_file.read_bytes()).digest()
        a6 = unchanged and all(w.get("worker_auth_file_absent") and not w.get("output_secret_found", True)
                              and not w["stderr_secret_found"] for w in workers)
        report = {"mode": "real_model_two_containers", "codex_version": VERSION,
                  "image_id": await command("docker", "image", "inspect", IMAGE, "--format", "{{.Id}}"),
                  "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                  "limits": {"workers": 2, "turns_per_worker": 1, "seconds_per_turn": args.seconds,
                             "token_hard_cap": None, "api_fallback": False, "oauth_refresh": False},
                  "A1": "passed" if a1 else "failed", "A2": "passed" if a2 else "failed",
                  "A3_real_refresh": "not_run", "A6_live": "passed" if a6 else "failed",
                  "auth_source_unchanged": unchanged, "account_claim_matches": True,
                  "overlap_seconds": round(overlap, 3), "workers": workers}
        report["execution_sandbox"] = "externalSandbox; Docker read-only root and workspace"
        report_path = ROOT / "results" / args.report
        if report_path.exists():
            raise RuntimeError("report_exists_choose_another_name")
        atomic_json(report_path, report)
        print(json.dumps({k: report[k] for k in ("A1", "A2", "A6_live", "overlap_seconds")}))
        return 0 if a1 and a2 and a6 else 1
    finally:
        shutil.rmtree(runtime)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="A1/A2：兩個容器、兩個小任務；只讀現有訂閱認證，不刷新。")
    parser.add_argument("--auth-file", type=Path, required=True)
    parser.add_argument("--model", help="省略時選 model/list 的預設模型")
    parser.add_argument("--report", default="live.json", help="results/ 下的新檔名，不覆寫既有證據")
    parser.add_argument("--seconds", type=int, default=120, choices=range(1, 121), metavar="1..120")
    args = parser.parse_args()
    if Path(args.report).name != args.report or (ROOT / "results" / args.report).exists():
        parser.error("--report 必須是尚未存在的檔名")
    try:
        raise SystemExit(asyncio.run(run(args)))
    except Exception as exc:
        print(json.dumps({"status": "failed", "error_type": type(exc).__name__}))
        raise SystemExit(1)

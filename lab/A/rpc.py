"""Bounded stdio JSON-RPC transport; raw payloads never reach reports."""

import asyncio
import json
import os
import signal

from auth import AuthFailure


def clean_env():
    return {k: os.environ[k] for k in ("PATH", "LANG", "LC_ALL", "TMPDIR") if k in os.environ}


class RpcError(Exception):
    def __init__(self, error):
        self.error = error
        super().__init__("app_server_error")


class Rpc:
    def __init__(self, command, cwd, env, secrets=(), refresh=None):
        self.command, self.cwd, self.env = command, cwd, env
        self.secrets = tuple(s.encode() for s in secrets if s)
        self.refresh_handler = refresh
        self.pending = {}
        self.notifications = asyncio.Queue()
        self.handlers = set()
        self.sequence = 0
        self.stderr_secret_found = False
        self.stderr_bytes = 0
        self.refresh_requests = 0

    async def __aenter__(self):
        self.process = await asyncio.create_subprocess_exec(
            *self.command, cwd=self.cwd, env=self.env,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE, start_new_session=True, limit=2**22)
        self.reader = asyncio.create_task(self.read())
        self.stderr_reader = asyncio.create_task(self.drain_stderr())
        return self

    async def __aexit__(self, *args):
        if self.process.returncode is None:
            self.process.stdin.close()
            try:
                await asyncio.wait_for(self.process.wait(), 3)
            except TimeoutError:
                os.killpg(self.process.pid, signal.SIGTERM)
                try:
                    await asyncio.wait_for(self.process.wait(), 2)
                except TimeoutError:
                    os.killpg(self.process.pid, signal.SIGKILL)
                    await self.process.wait()
        for task in (self.reader, self.stderr_reader, *self.handlers):
            task.cancel()
        await asyncio.gather(self.reader, self.stderr_reader, *self.handlers, return_exceptions=True)

    async def drain_stderr(self):
        tail = b""
        keep = max((len(s) for s in self.secrets), default=1)
        while chunk := await self.process.stderr.read(8192):
            self.stderr_bytes += len(chunk)
            tail += chunk
            self.stderr_secret_found |= any(s in tail for s in self.secrets)
            tail = tail[-keep:]

    async def send(self, payload):
        self.process.stdin.write(json.dumps(payload).encode() + b"\n")
        await self.process.stdin.drain()

    async def request(self, method, params=None, timeout=20):
        self.sequence += 1
        key = self.sequence
        future = asyncio.get_running_loop().create_future()
        self.pending[key] = future
        try:
            await self.send({"id": key, "method": method, "params": params or {}})
            return await asyncio.wait_for(future, timeout)
        finally:
            self.pending.pop(key, None)

    async def initialize(self):
        result = await self.request("initialize", {
            "clientInfo": {"name": "agent_workbench_lab_a", "version": "0.1.0"},
            "capabilities": {"experimentalApi": True}})
        await self.send({"method": "initialized", "params": {}})
        return result

    async def handle(self, message):
        try:
            if message["method"] == "account/chatgptAuthTokens/refresh":
                self.refresh_requests += 1
                if self.refresh_handler is None:
                    raise AuthFailure("reauthenticate_required")
                result = await self.refresh_handler(message["params"])
            else:
                raise AuthFailure("unsupported_server_request")
            await self.send({"id": message["id"], "result": result})
        except Exception:
            await self.send({"id": message["id"], "error": {
                "code": -32001, "message": "host_action_required"}})

    async def read(self):
        try:
            while line := await self.process.stdout.readline():
                message = json.loads(line)
                if "method" in message:
                    if "id" in message:
                        task = asyncio.create_task(self.handle(message))
                        self.handlers.add(task)
                        task.add_done_callback(self.handlers.discard)
                    else:
                        await self.notifications.put(message)
                else:
                    future = self.pending.get(message.get("id"))
                    if future is not None and not future.done():
                        if "error" in message:
                            future.set_exception(RpcError(message["error"]))
                        else:
                            future.set_result(message.get("result"))
        finally:
            for future in self.pending.values():
                if not future.done():
                    future.set_exception(RpcError({"code": "transport_closed"}))
            await self.notifications.put({"method": "lab/transportClosed", "params": {}})

    async def event(self, method, timeout=20):
        async with asyncio.timeout(timeout):
            while True:
                event = await self.notifications.get()
                if event["method"] == "lab/transportClosed":
                    raise RpcError({"code": "transport_closed"})
                if event["method"] == method:
                    return event["params"]

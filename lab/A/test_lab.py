"""A3-A6 behavioral checks using fake credentials only."""

import asyncio
import json
import multiprocessing
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest

from auth import AuthFailure, Coordinator, Tokens, atomic_json, classify
from rpc import Rpc, clean_env

ROOT = Path(__file__).resolve().parent
OLD = Tokens("fake-access-0", "fake-refresh-0", "fake-account")


async def provider(old):
    await asyncio.sleep(0.03)
    return Tokens("fake-access-1", "fake-refresh-1", old.account_id, old.generation + 1)


def crash_child(root, phase):
    def crash(at):
        if at == phase:
            os._exit(23)
    asyncio.run(Coordinator(root, provider, crash).refresh(0, "fake-account"))


def concurrent_child(root, counter, start):
    async def counted(old):
        with open(counter, "a") as f:
            f.write("refresh\n")
        return await provider(old)
    start.wait(5)
    asyncio.run(Coordinator(root, counted).refresh(0, "fake-account"))


class LabTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "private"
        self.coordinator = Coordinator(self.root, provider)
        self.coordinator.seed(OLD)

    def tearDown(self):
        self.tmp.cleanup()

    async def test_A3_two_worker_callbacks_single_refresh_and_unrelated_work_progresses(self):
        calls = 0
        progressed = asyncio.Event()
        async def counted(old):
            nonlocal calls
            calls += 1
            await asyncio.wait_for(progressed.wait(), 1)
            return await provider(old)
        self.coordinator.provider = counted
        async def run_worker():
            async def refresh(params):
                return (await self.coordinator.refresh(0, params["previousAccountId"])).external()
            async with Rpc([sys.executable, str(ROOT / "fake_server.py")], ROOT, clean_env(), refresh=refresh) as rpc:
                await rpc.initialize()
                await rpc.request("lab/refresh")
                return await rpc.event("lab/refreshed")
        async def unrelated():
            await asyncio.sleep(0.05)
            progressed.set()
        a, b, _ = await asyncio.gather(run_worker(), run_worker(), unrelated())
        self.assertEqual(calls, 1)
        self.assertTrue(a["success"] and b["success"])
        self.assertTrue(a["refresh_token_absent"] and b["refresh_token_absent"])
        self.assertEqual(self.coordinator.read()[0].generation, 1)

    async def test_A3_multiple_host_processes_reuse_saved_generation(self):
        ctx = multiprocessing.get_context("spawn")
        start = ctx.Event()
        counter = str(Path(self.tmp.name) / "calls.txt")
        children = [ctx.Process(target=concurrent_child, args=(self.root, counter, start)) for _ in range(2)]
        for p in children:
            p.start()
        start.set()
        for p in children:
            await asyncio.to_thread(p.join, 5)
            if p.is_alive():
                p.kill()
                p.join()
            self.assertEqual(p.exitcode, 0)
        self.assertEqual(Path(counter).read_text().splitlines(), ["refresh"])

    async def crash(self, phase):
        ctx = multiprocessing.get_context("spawn")
        p = ctx.Process(target=crash_child, args=(self.root, phase))
        p.start()
        await asyncio.to_thread(p.join, 5)
        if p.is_alive():
            p.kill()
            p.join()
        self.assertEqual(p.exitcode, 23)
        return Coordinator(self.root, provider)

    async def test_A4_crash_before_remote_can_resume(self):
        recovered = await self.crash("before_remote")
        self.assertEqual(recovered.read()[1]["phase"], "prepared")
        self.assertEqual((await recovered.refresh(0, "fake-account")).generation, 1)

    async def test_A4_crash_after_remote_requires_login_without_replay(self):
        recovered = await self.crash("after_remote")
        async def forbidden(old):
            self.fail("An ambiguous refresh must not be replayed")
        recovered.provider = forbidden
        with self.assertRaisesRegex(AuthFailure, "reauthenticate_unknown"):
            await recovered.refresh(0, "fake-account")

    async def test_A4_crash_after_saved_reuses_new_tokens(self):
        recovered = await self.crash("after_saved")
        async def forbidden(old):
            self.fail("A persisted generation must not be refreshed again")
        recovered.provider = forbidden
        self.assertEqual((await recovered.refresh(0, "fake-account")).access_token, "fake-access-1")

    async def test_A4_cancellation_leaves_unknown_state(self):
        entered = asyncio.Event()
        async def hanging(old):
            entered.set()
            await asyncio.Event().wait()
        self.coordinator.provider = hanging
        task = asyncio.create_task(self.coordinator.refresh(0, "fake-account"))
        await entered.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        with self.assertRaisesRegex(AuthFailure, "reauthenticate_unknown"):
            await self.coordinator.refresh(0, "fake-account")

    async def test_A5_structured_error_actions(self):
        cases = [({"code": "invalid_grant"}, "reauthenticate"),
                 ({"code": "revoked"}, "reauthenticate"),
                 ({"code": "timeout"}, "pause"), ({"code": 429}, "pause"),
                 ({"code": "insufficient_quota"}, "quota_exhausted"),
                 ({"codexErrorInfo": "usageLimitExceeded"}, "quota_exhausted"),
                 ({"codexErrorInfo": "rateLimitExceeded"}, "pause"),
                 ({"codexErrorInfo": "serverOverloaded"}, "pause"),
                 ({"codexErrorInfo": {"httpConnectionFailed": {"httpStatusCode": 401}}}, "reauthenticate"),
                 ({"message": "invalid_grant fake-refresh-0"}, "stop")]
        for error, expected in cases:
            with self.subTest(error=error):
                self.assertEqual(classify(error), expected)

    async def test_A5_known_failure_fanned_out_without_retry(self):
        calls = 0
        async def rejected(old):
            nonlocal calls
            calls += 1
            raise AuthFailure("reauthenticate")
        self.coordinator.provider = rejected
        errors = await asyncio.gather(*(self.coordinator.refresh(0, "fake-account") for _ in range(2)), return_exceptions=True)
        self.assertEqual(calls, 1)
        self.assertTrue(all(isinstance(e, AuthFailure) and e.action == "reauthenticate" for e in errors))

    async def test_A5_transport_timeout_does_not_replay_refresh(self):
        async def uncertain(old):
            raise TimeoutError("fake-refresh-0")
        self.coordinator.provider = uncertain
        for _ in range(2):
            with self.assertRaisesRegex(AuthFailure, "reauthenticate_unknown"):
                await self.coordinator.refresh(0, "fake-account")

    async def test_A6_identity_mismatch_never_refreshes(self):
        with self.assertRaisesRegex(AuthFailure, "account_mismatch"):
            await self.coordinator.refresh(0, "another-account")
        self.assertEqual(self.coordinator.read()[1]["phase"], "ready")

    async def test_A6_private_store_and_public_metadata_are_separate(self):
        await self.coordinator.refresh(0, "fake-account")
        tokens, state = self.coordinator.read()
        public = Path(self.tmp.name) / "artifacts" / "checkpoint.json"
        atomic_json(public, {"phase": state["phase"], "generation": tokens.generation})
        for path in self.root.iterdir():
            self.assertEqual(path.stat().st_mode & 0o077, 0)
        self.assertEqual(self.root.stat().st_mode & 0o077, 0)
        for secret in (tokens.access_token, tokens.refresh_token, OLD.access_token, OLD.refresh_token):
            self.assertNotIn(secret, public.read_text())
            self.assertNotIn(secret, repr(tokens))
        self.assertEqual(set(tokens.external()), {"accessToken", "chatgptAccountId"})

    async def test_A6_callback_failure_does_not_echo_secret_exception(self):
        async def failed(params):
            raise RuntimeError("fake-refresh-0")
        async with Rpc([sys.executable, str(ROOT / "fake_server.py")], ROOT, clean_env(), refresh=failed) as rpc:
            await rpc.initialize()
            await rpc.request("lab/refresh")
            event = await rpc.event("lab/refreshed")
        self.assertEqual(event["error"], "host_action_required")
        self.assertNotIn("fake-refresh-0", json.dumps(event))

    async def test_A3_callback_without_provider_fails_without_fallback(self):
        async with Rpc([sys.executable, str(ROOT / "fake_server.py")], ROOT, clean_env()) as rpc:
            await rpc.initialize()
            await rpc.request("lab/refresh")
            event = await rpc.event("lab/refreshed")
        self.assertFalse(event["success"])
        self.assertEqual(event["error"], "host_action_required")

    async def test_A4_refresh_deadline_leaves_unknown_state(self):
        async def hanging(old):
            await asyncio.Event().wait()
        self.coordinator.provider = hanging
        with self.assertRaisesRegex(AuthFailure, "pause"):
            await self.coordinator.refresh(0, "fake-account")
        with self.assertRaisesRegex(AuthFailure, "reauthenticate_unknown"):
            await self.coordinator.refresh(0, "fake-account")


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(LabTests)
    started = time.monotonic()
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    atomic_json(ROOT / "results" / "simulation.json", {
        "mode": "simulated_oauth_real_process_crashes", "tests_run": result.testsRun,
        "failures": len(result.failures), "errors": len(result.errors),
        "passed": result.wasSuccessful(), "duration_seconds": round(time.monotonic() - started, 3),
        "test_names": unittest.defaultTestLoader.getTestCaseNames(LabTests),
        "model_calls": 0, "real_oauth_refreshes": 0})
    raise SystemExit(0 if result.wasSuccessful() else 1)

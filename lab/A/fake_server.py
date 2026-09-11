"""Minimal subprocess peer for host refresh callback tests; no model or OAuth."""

import json
import sys


def send(message):
    print(json.dumps(message), flush=True)


for line in sys.stdin:
    m = json.loads(line)
    method = m.get("method")
    if method == "initialize":
        send({"id": m["id"], "result": {"userAgent": "lab-fake"}})
    elif method == "lab/refresh":
        send({"id": m["id"], "result": {}})
        send({"id": "refresh-1", "method": "account/chatgptAuthTokens/refresh",
              "params": {"reason": "unauthorized", "previousAccountId": "fake-account"}})
    elif m.get("id") == "refresh-1":
        result = m.get("result", {})
        send({"method": "lab/refreshed", "params": {
            "success": result.get("accessToken") == "fake-access-1",
            "refresh_token_absent": "refresh_token" not in result and "refreshToken" not in result,
            "keys": sorted(result), "error": m.get("error", {}).get("message")}})

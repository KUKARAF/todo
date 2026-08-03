import json
import subprocess
import sys
import urllib.error
import urllib.request

HA_URL = "https://casa.osmosis.page"
HA_HELPER_PREFIX = "input_text.epaper_todo_"
MAX_TODOS = 7
MAX_TEXT_LEN = 255
HA_TIMEOUT_SECONDS = 0.3



class EPaper:
    """Sends the top-N todo texts to Home Assistant input_text helpers.

    The HA long-lived token is retrieved via the kv CLI: `kv get HA`
    """

    def __init__(self):
        result = subprocess.run(["kv", "get", "HA"], capture_output=True, text=True)
        if result.returncode != 0:
            raise ValueError(f"kv get HA failed: {result.stderr.strip()}")
        self.ha_token = result.stdout.strip()
        if not self.ha_token:
            raise ValueError("kv get HA returned empty token")

    def send(self, todos: list[str]) -> None:
        """Set epaper_todo_1 … epaper_todo_7 in Home Assistant.

        Slots beyond len(todos) are cleared (set to empty string).
        """
        for i in range(1, MAX_TODOS + 1):
            text = todos[i - 1][:MAX_TEXT_LEN] if i - 1 < len(todos) else ""
            try:
                self._set_helper(i, text)
                status = "ok" if text else "cleared"
                print(f"  {HA_HELPER_PREFIX}{i} -> {repr(text)} [{status}]")
            except RuntimeError as e:
                print(f"  warning: skipping {HA_HELPER_PREFIX}{i} — {e}", file=sys.stderr)

    def _set_helper(self, n: int, text: str) -> None:
        entity_id = f"{HA_HELPER_PREFIX}{n}"
        url = f"{HA_URL}/api/states/{entity_id}"
        payload = json.dumps({"state": text}).encode()
        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Authorization": f"Bearer {self.ha_token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=HA_TIMEOUT_SECONDS) as resp:
                if resp.status not in (200, 201):
                    raise RuntimeError(f"HA returned HTTP {resp.status} for {entity_id}")
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"HA error for {entity_id}: {e.code} {e.reason}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"HA unreachable for {entity_id}: {e.reason}") from e

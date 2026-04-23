import time
import requests

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)
DEFAULT_TIMEOUT = 30


def http_get_json(
    url: str,
    params: dict,
    timeout: int = DEFAULT_TIMEOUT,
    sleep_seconds: float = 1.5,
    user_agent: str = DEFAULT_UA,
    max_retries: int = 1,
) -> dict:
    # Use wildcard Accept — 일부 한국 공공 API(KEPCO)가 application/json을
    # 거부 (실제 응답이 text/plain이라도 JSON 본문을 포함).
    headers = {"User-Agent": user_agent, "Accept": "*/*"}
    last_err: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            time.sleep(sleep_seconds)
            return data
        except Exception as e:
            last_err = e
            if attempt < max_retries:
                time.sleep(sleep_seconds * (attempt + 1))
    raise RuntimeError(f"http_get_json failed after retries: {last_err}") from last_err


def http_get_text(
    url: str,
    params: dict | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    sleep_seconds: float = 1.5,
    user_agent: str = DEFAULT_UA,
    max_retries: int = 1,
) -> str:
    headers = {"User-Agent": user_agent}
    last_err: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            resp = requests.get(url, params=params or {}, headers=headers, timeout=timeout)
            resp.raise_for_status()
            text = resp.text
            time.sleep(sleep_seconds)
            return text
        except Exception as e:
            last_err = e
            if attempt < max_retries:
                time.sleep(sleep_seconds * (attempt + 1))
    raise RuntimeError(f"http_get_text failed after retries: {last_err}") from last_err

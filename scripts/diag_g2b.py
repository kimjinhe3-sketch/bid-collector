"""Diagnose connectivity to data.go.kr step by step."""
import os
import socket
import ssl
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

HOST = "apis.data.go.kr"
PORT = 443

print(f"[1] DNS resolve {HOST}...", flush=True)
try:
    ip = socket.gethostbyname(HOST)
    print(f"    -> {ip}", flush=True)
except Exception as e:
    print(f"    FAILED: {e}", flush=True)
    sys.exit(1)

print(f"[2] TCP connect {HOST}:{PORT}...", flush=True)
t0 = time.time()
try:
    s = socket.create_connection((HOST, PORT), timeout=10)
    print(f"    -> connected in {time.time()-t0:.2f}s", flush=True)
    s.close()
except Exception as e:
    print(f"    FAILED: {e}", flush=True)
    sys.exit(2)

print(f"[3] TLS handshake with truststore...", flush=True)
try:
    import truststore
    truststore.inject_into_ssl()
    print("    truststore injected", flush=True)
except ImportError:
    print("    truststore NOT installed", flush=True)

import requests
t0 = time.time()
try:
    r = requests.get(f"https://{HOST}/", timeout=15)
    print(f"    -> status={r.status_code} in {time.time()-t0:.2f}s", flush=True)
except Exception as e:
    print(f"    FAILED: {e!r}", flush=True)
    sys.exit(3)

print(f"[4] Real API call (1 page, numOfRows=5)...", flush=True)
key = os.environ.get("G2B_SERVICE_KEY", "")
url = f"https://{HOST}/1230000/ad/BidPublicInfoService/getBidPblancListInfoThng"
params = {
    "serviceKey": key,
    "pageNo": 1,
    "numOfRows": 5,
    "inqryDiv": 1,
    "inqryBgnDt": "202604220000",
    "inqryEndDt": "202604222359",
    "type": "json",
}
t0 = time.time()
try:
    r = requests.get(url, params=params, timeout=30,
                     headers={"User-Agent": "Mozilla/5.0"})
    print(f"    -> status={r.status_code} in {time.time()-t0:.2f}s", flush=True)
    print(f"    body (first 500 chars): {r.text[:500]}", flush=True)
except Exception as e:
    print(f"    FAILED: {e!r}", flush=True)
    sys.exit(4)

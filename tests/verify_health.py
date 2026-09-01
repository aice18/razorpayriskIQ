import urllib.request
import json
import sys

endpoints = [
    '/',
    '/app',
    '/dashboard',
    '/health',
    '/metrics',
    '/riskiq_logo.png',
    '/api/feed',
    '/api/dashboard/analytics',
    '/api/crossborder/corridors',
    '/api/pipeline/metrics',
    '/api/metrics/model',
    '/api/metrics/eval',
    '/api/metrics/roi',
    '/api/active-learning/stats',
    '/api/metrics/failure-case',
    '/api/graph/corpus?max_nodes=50',
    '/api/stream/generator/status'
]

print("=== Running System Health & Endpoint Verification ===")
all_passed = True
for ep in endpoints:
    url = "http://127.0.0.1:8000" + ep
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "RiskIQ-HealthCheck/1.0"})
        with urllib.request.urlopen(req, timeout=5) as response:
            status = response.status
            data_len = len(response.read())
            print(f"  [PASS] {status} {ep} ({data_len} bytes)")
    except Exception as e:
        print(f"  [FAIL] {ep} -> {e}")
        all_passed = False

if all_passed:
    print("\n>>> ALL 17 CORE ENDPOINTS, APIs, GRAPH CORPUS & DASHBOARD PAGES ARE ONLINE (200 OK)! <<<")
else:
    sys.exit(1)

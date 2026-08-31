"""
One-click launcher for Razorpay RiskIQ (Sentinel).
Starts the FastAPI backend and dashboard server on 0.0.0.0:8000 and automatically launches the browser.
"""

import sys
import time
import webbrowser
import uvicorn

def main():
    print("\n" + "=" * 65)
    print("🚀 Starting Razorpay RiskIQ (Sentinel)...")
    print("   👉 Dashboard URL: http://localhost:8000")
    print("   👉 API Docs:      http://localhost:8000/docs")
    print("   👉 Health Check:  http://localhost:8000/health")
    print("=" * 65 + "\n")

    # Automatically open browser after brief delay
    def open_browser():
        time.sleep(1.2)
        try:
            webbrowser.open("http://localhost:8000")
        except Exception:
            pass

    import threading
    threading.Thread(target=open_browser, daemon=True).start()

    # Run Uvicorn with clean 1-second graceful shutdown on Ctrl+C
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True, timeout_graceful_shutdown=1)

if __name__ == "__main__":
    main()

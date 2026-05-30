"""
Desktop entry point — wraps the Flask UI in a native window.

Run normally:  python desktop_app.py
Bundled .exe:  double-click LeadScraper.exe
"""
import os
import sys
import socket
import threading
import time
import webview  # pywebview

# Import the Flask app from app.py
import app as flask_module


def find_free_port(start: int = 5000) -> int:
    for p in (start, 5001, 5050, 8000, 8080, 8765):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    return start


def start_flask(port: int):
    # silence Flask startup banner in the bundled exe
    import logging
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    flask_module.app.run(host="127.0.0.1", port=port, debug=False,
                         use_reloader=False, threaded=True)


def wait_for_server(port: int, timeout: float = 8.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def main():
    port = find_free_port()
    threading.Thread(target=start_flask, args=(port,), daemon=True).start()
    if not wait_for_server(port):
        # Show a window with the error rather than failing silently
        webview.create_window(
            "Lead Scraper — error",
            html=f"<h1>Server failed to start</h1>"
                 f"<p>Could not reach http://127.0.0.1:{port}</p>"
                 f"<p>Try restarting the app. If this persists, "
                 f"<a href='https://github.com'>report a bug</a>.</p>",
            width=600, height=300,
        )
        webview.start()
        return

    webview.create_window(
        "Lead Scraper",
        f"http://127.0.0.1:{port}",
        width=1100,
        height=820,
        min_size=(800, 600),
        resizable=True,
    )
    webview.start()


if __name__ == "__main__":
    main()

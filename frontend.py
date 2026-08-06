"""Runs the Next.js frontend as a child of the Python service.

`python app.py` starts one thing from the user's point of view, but there are
two processes: Flask serving the JSON API, and Next serving the interface. This
module owns the second one — starting it, piping its output into the same
terminal, and making sure it dies when Flask does rather than lingering on the
port.
"""

from __future__ import annotations

import atexit
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")

_process: subprocess.Popen | None = None


class FrontendError(RuntimeError):
    """The frontend could not be started; the API is still usable on its own."""


def _npm() -> str:
    npm = shutil.which("npm")
    if not npm:
        raise FrontendError(
            "npm was not found on PATH. Install Node.js 20+ from https://nodejs.org "
            "or start the API alone with `python app.py --no-web`."
        )
    return npm


def _ensure_dependencies(npm: str) -> None:
    if os.path.isdir(os.path.join(WEB_DIR, "node_modules")):
        return

    # `npm ci` is the reproducible one, but it needs a lockfile in sync with
    # package.json; fall back to `npm install` when there isn't one.
    has_lockfile = os.path.isfile(os.path.join(WEB_DIR, "package-lock.json"))
    command = [npm, "ci"] if has_lockfile else [npm, "install"]

    print("[web] installing frontend dependencies (first run only) ...", flush=True)
    result = subprocess.run(command, cwd=WEB_DIR)
    if result.returncode != 0 and has_lockfile:
        print("[web] `npm ci` failed, retrying with `npm install` ...", flush=True)
        result = subprocess.run([npm, "install"], cwd=WEB_DIR)
    if result.returncode != 0:
        raise FrontendError(
            "Installing frontend dependencies failed in web/; see the output above."
        )


def _ensure_build(npm: str) -> None:
    if os.path.isdir(os.path.join(WEB_DIR, ".next")):
        return
    print("[web] building the frontend for production ...", flush=True)
    result = subprocess.run([npm, "run", "build"], cwd=WEB_DIR)
    if result.returncode != 0:
        raise FrontendError("`npm run build` failed in web/; see the output above.")


def _pump_output(process: subprocess.Popen) -> None:
    """Prefix the child's logs so two servers in one terminal stay readable."""
    assert process.stdout is not None
    for line in process.stdout:
        sys.stdout.write(f"[web] {line}")
        sys.stdout.flush()


def start(api_port: int, web_port: int = 3000, production: bool = False) -> str:
    """Launch Next.js against this API. Returns the URL it will serve on."""
    global _process

    if not os.path.isdir(WEB_DIR):
        raise FrontendError(f"No frontend found at {WEB_DIR}.")

    npm = _npm()
    _ensure_dependencies(npm)

    env = os.environ.copy()
    env["TOXICITY_API_URL"] = f"http://127.0.0.1:{api_port}"
    env["PORT"] = str(web_port)
    # Next prints its own banner; ours would just duplicate it.
    env.setdefault("NEXT_TELEMETRY_DISABLED", "1")

    # The frontend is the public service, so it binds every interface — the
    # API behind it is the one kept on localhost.
    if production:
        _ensure_build(npm)
        command = [npm, "run", "start", "--",
                   "--port", str(web_port), "--hostname", "0.0.0.0"]
    else:
        command = [npm, "run", "dev", "--",
                   "--port", str(web_port), "--hostname", "0.0.0.0"]

    print(f"[web] starting Next.js on http://127.0.0.1:{web_port} ...", flush=True)
    _process = subprocess.Popen(
        command,
        cwd=WEB_DIR,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        # own process group, so stopping the parent stops `npm` *and* the node
        # process it spawns instead of orphaning the latter on the port
        start_new_session=(os.name != "nt"),
        creationflags=(
            subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        ),
    )

    threading.Thread(target=_pump_output, args=(_process,), daemon=True).start()
    atexit.register(stop)
    return f"http://127.0.0.1:{web_port}"


def stop() -> None:
    """Terminate the frontend, escalating to SIGKILL if it ignores us."""
    global _process
    process, _process = _process, None
    if process is None or process.poll() is not None:
        return

    print("\n[web] stopping Next.js ...", flush=True)
    try:
        if os.name == "nt":
            process.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        process.terminate()

    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass

    # `next dev` spawns its own server and worker processes; if any of them
    # outlived the SIGTERM they would keep holding the port.
    try:
        if os.name != "nt":
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        else:
            process.kill()
    except (ProcessLookupError, PermissionError, OSError):
        pass

    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass


def wait_until_ready(url: str, timeout: float = 120.0) -> bool:
    """Poll the frontend until it answers — the window GUI needs this."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _process is not None and _process.poll() is not None:
            return False
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status < 500:
                    return True
        except (urllib.error.URLError, OSError):
            time.sleep(0.5)
    return False


def install_signal_handlers() -> None:
    """Ctrl-C on the parent should take the child with it."""
    handled = (signal.SIGINT, signal.SIGTERM)

    def handler(signum, _frame):
        # A second Ctrl-C (or a pkill that matches more than one of our
        # processes) would otherwise re-enter this handler and kill us
        # mid-cleanup, leaving Next.js orphaned on its port.
        for sig in handled:
            try:
                signal.signal(sig, signal.SIG_IGN)
            except (ValueError, OSError):
                pass

        stop()

        signal.signal(signum, signal.SIG_DFL)
        os.kill(os.getpid(), signum)

    for sig in handled:
        try:
            signal.signal(sig, handler)
        except ValueError:
            pass  # not on the main thread; atexit still covers us

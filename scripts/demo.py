"""One command for the demo: starts every service in the right order.

  1. Imagine API (simulator)        :8002
  2. backend (WebSocket relay)      :8000, or the next free port
  3. fake Sense (crowd numbers)     the stage-front zone fills in FAKE_FILL_S (default 420 s)
  4. report fusion
  5. Act loop (watchdog, planner, executor, Telegram bot)
  6. dashboard                      http://localhost:3100  (and /judge)
  7. the Tavily turnout card (cached, no credits)

Each step waits until the previous one is really up. Logs: logs/demo/<name>.log
Ctrl+C stops everything.

Run:  python scripts/demo.py               (from the repo root, venv active)
      python scripts/demo.py --no-dashboard
      python scripts/demo.py --real-sense --gateway   (Shirali's counts + the ESP32 gateway)
      FAKE_FILL_S=600 python scripts/demo.py   (slower build-up)
Refresh the dashboard once after READY (it may have opened before the backend).
"""
import argparse, os, socket, subprocess, sys, time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
LOGS = ROOT / "logs" / "demo"
PY = sys.executable
sys.stdout.reconfigure(line_buffering=True)
WIN = os.name == "nt"
procs: list[tuple[str, subprocess.Popen]] = []


def free(port: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def start(name: str, cmd: list[str], env: dict, cwd: Path = ROOT) -> subprocess.Popen:
    log = open(LOGS / f"{name}.log", "w", encoding="utf-8")
    p = subprocess.Popen(cmd, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT,
                         creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if WIN else 0)
    procs.append((name, p))
    print(f"  started {name:10s} (log: logs/demo/{name}.log)")
    return p


def wait_http(name: str, url: str, timeout: float = 90):
    t0 = time.time()
    while time.time() - t0 < timeout:
        for n, p in procs:
            if n == name and p.poll() is not None:
                sys.exit(f"  {name} exited early; see logs/demo/{name}.log")
        try:
            if httpx.get(url, timeout=3).status_code < 500:
                print(f"  {name:10s} ready  {url}")
                return
        except Exception:
            pass
        time.sleep(1)
    sys.exit(f"  {name} not ready after {timeout:.0f} s; see logs/demo/{name}.log")


def stop_all():
    print("\nstopping…")
    for name, p in reversed(procs):
        if p.poll() is None:
            if WIN:   # kill the whole tree (npm -> node)
                subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True)
            else:
                p.terminate()
    print("stopped.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-dashboard", action="store_true")
    ap.add_argument("--real-sense", action="store_true",
                    help="don't start the fake crowd feed (Shirali's sense code publishes br/zone_state)")
    ap.add_argument("--gateway", action="store_true",
                    help="also start the serial bridge to the gateway ESP32 (GATEWAY_PORT in .env)")
    ap.add_argument("--dashboard-port", type=int, default=3100)
    args = ap.parse_args()
    LOGS.mkdir(parents=True, exist_ok=True)

    if not free(8002):
        sys.exit("port 8002 (Imagine API) is busy: stop the old simulator first")
    backend_port = next(p for p in (8000, 8010, 8020, 8030) if free(p))
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1",
           "IMAGINE_API_URL": "http://localhost:8002", "BACKEND_URL": f"http://localhost:{backend_port}",
           "FAKE_FILL_S": os.environ.get("FAKE_FILL_S", "420"),
           "OFFICER_TRAVEL_S": os.environ.get("OFFICER_TRAVEL_S", "30")}

    print("Breathing Room demo")
    try:
        start("imagine", [PY, "-m", "uvicorn", "imagine.fake_imagine:app", "--port", "8002"], env)
        wait_http("imagine", "http://localhost:8002/forecast/latest")
        start("backend", [PY, "-m", "uvicorn", "backend.app:app", "--port", str(backend_port)], env)
        wait_http("backend", f"http://localhost:{backend_port}/health")
        if args.real_sense:
            print("  sense      not started: waiting for real br/zone_state from Sense")
        else:
            start("sense", [PY, "-m", "sense.fake_sense"], env)
        start("reports", [PY, "-m", "act.reports"], env)
        start("act", [PY, "-m", "act.run_act"], env)
        if args.gateway:
            start("bridge", [PY, "-m", "act.serial_bridge"], env)
        if not args.no_dashboard:
            denv = {**env, "NEXT_PUBLIC_BACKEND_URL": f"http://localhost:{backend_port}",
                    "NEXT_PUBLIC_IMAGINE_URL": "http://127.0.0.1:8002"}
            npx = "npx.cmd" if WIN else "npx"
            start("dashboard", [npx, "next", "dev", "-p", str(args.dashboard_port)], denv, cwd=ROOT / "dashboard")
            wait_http("dashboard", f"http://localhost:{args.dashboard_port}", timeout=180)
        time.sleep(3)
        subprocess.run([PY, "-m", "act.turnout", "--event", "TVK Vijay rally",
                        "--organizer", "TVK (Tamilaga Vettri Kazhagam), leader Vijay", "--city", "Karur",
                        "--date", "2025-09-27", "--declared", "10000", "--before-event", "--publish"],
                       cwd=ROOT, env=env, stdout=open(LOGS / "turnout.log", "w", encoding="utf-8"),
                       stderr=subprocess.STDOUT)
        print("  turnout    card published")
        print(f"\nREADY. Operations: http://localhost:{args.dashboard_port}   Simulation: "
              f"http://localhost:{args.dashboard_port}/judge   Backend: http://localhost:{backend_port}")
        print(f"The stage-front zone fills over {env['FAKE_FILL_S']} s; expect the first plan after ~2-4 min. Film that first plan.")
        print("Ctrl+C to stop everything.")
        while True:
            time.sleep(2)
            for name, p in procs:
                if p.poll() is not None:
                    print(f"  !! {name} stopped (exit {p.returncode}); see logs/demo/{name}.log")
                    procs.remove((name, p))
    except KeyboardInterrupt:
        pass
    finally:
        stop_all()


if __name__ == "__main__":
    main()

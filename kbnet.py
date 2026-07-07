#!/usr/bin/env python3
"""kbnet — connects a teammate's knowledge base to the GreenMars KB.

Commands:
  run      one sync cycle (what the hourly launchd job runs)
  ui       open the personal-areas setup page   [--port N] [--no-open] [--setup]
  status   show the last run's health summary
  doctor   print full diagnostics (for sending to Chris when something's off)
  version  print the tool revision
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from kbnetlib import config, gitutil  # noqa: E402


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "help"
    if cmd == "run":
        from kbnetlib import exportcycle
        exportcycle.run_cycle()
    elif cmd == "ui":
        from kbnetlib import uiserver
        port = 8765
        if "--port" in argv:
            port = int(argv[argv.index("--port") + 1])
        uiserver.serve(
            port=port,
            open_browser="--no-open" not in argv,
            setup="--setup" in argv,
        )
    elif cmd == "status":
        health_path = os.path.join(config.paths()["exchange"], "outbox", "health.json")
        try:
            with open(health_path, encoding="utf-8") as f:
                health = json.load(f)
        except OSError:
            print("kbnet hasn't completed a run yet.")
            return
        ex = health.get("export") or {}
        print(f"peer:      {health.get('peer')}")
        print(f"last run:  {health.get('ran_at')} ({health.get('duration_s')}s, "
              f"tool {health.get('tool_rev')})")
        if health.get("disabled"):
            print("state:     paused via control config")
        print(f"in sync:   {ex.get('synced', 0)} notes "
              f"({ex.get('updated', 0)} updated, {ex.get('removed', 0)} removed)")
        print(f"kept home: {ex.get('personal_excluded', 0)} personal notes in sync folders")
        if health.get("requests_fulfilled"):
            print(f"requests:  {', '.join(health['requests_fulfilled'])}")
        for e in health.get("errors", []):
            print(f"issue:     {e}")
        try:
            with open(os.path.join(config.paths()["home"], "last-run-errors.json"),
                      encoding="utf-8") as f:
                data = json.load(f)
            for e in data.get("errors", []):
                print(f"issue:     {e} (persisted {data.get('ts', '?')})")
        except (OSError, ValueError):
            pass
    elif cmd == "doctor":
        from kbnetlib import doctor
        doctor.run()
    elif cmd == "version":
        print(gitutil.tool_rev())
    else:
        print(__doc__.strip())


if __name__ == "__main__":
    main(sys.argv)

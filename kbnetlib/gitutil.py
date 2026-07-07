"""Git plumbing for the exchange repo. Uses the kbnet deploy key when present
so we never touch the owner's own ssh config or git identity."""
import os
import subprocess

from . import config

BRANCH = "main"


def _env():
    env = os.environ.copy()
    key = config.paths()["ssh_key"]
    if os.path.exists(key):
        cmd = f"ssh -i {key} -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new"
        try:
            if config.load_local().get("ssh_443"):
                # This network blocks GitHub's SSH port; installer negotiated 443.
                cmd += " -o HostName=ssh.github.com -o Port=443"
        except (SystemExit, OSError, ValueError):
            pass
        env["GIT_SSH_COMMAND"] = cmd
    return env


def git(repo, *args, check=True):
    result = subprocess.run(
        ["git", "-C", repo, *args],
        env=_env(),
        capture_output=True,
        text=True,
    )
    if check and result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def sync_exchange(repo, errors):
    try:
        git(repo, "pull", "--rebase", "--quiet", "origin", BRANCH)
    except RuntimeError as e:
        git(repo, "rebase", "--abort", check=False)
        errors.append(f"exchange pull failed: {e}")


def commit_push(repo, peer, message, errors):
    git(repo, "add", "-A", "outbox")
    if not git(repo, "status", "--porcelain", "outbox"):
        return False
    git(
        repo,
        "-c", f"user.name=kbnet ({peer})",
        "-c", "user.email=kbnet@greenmars.com",
        "commit", "--quiet", "-m", message,
    )
    try:
        git(repo, "push", "--quiet", "origin", BRANCH)
    except RuntimeError as e:
        # Offline is fine — the commit rides along on the next successful cycle.
        errors.append(f"push failed (will retry next run): {e}")
    return True


def tool_rev():
    try:
        return git(config.paths()["tool"], "rev-parse", "--short", "HEAD")
    except (RuntimeError, OSError):
        return "dev"

#!/usr/bin/env python3
"""Regression test for the `curl | bash` prompt bug.

The installer's prompts must read from /dev/tty, never from stdin. Under
`curl … | bash`, stdin *is* the piped script, so a bare `read` silently eats
script lines instead of waiting for the user — which is exactly how the vault
path once became a line of bash code and setup died at "… doesn't exist".

This test reproduces that condition precisely: it runs installer.sh with POISON
on stdin (a pipe, like curl) while a *controlling pty* supplies the real
answers. Two outcomes:

  * prompts read stdin (the bug)  -> vault path becomes poison, installer prints
    "doesn't exist" and exits    -> we detect it and FAIL.
  * prompts read /dev/tty (fixed) -> poison is untouched, installer sails past
    to the deploy-key step        -> we detect that marker and PASS.

We stop at the deploy-key prompt, which comes before any network or launchd
work, so the whole thing runs offline in ~a second.

Usage: interactive_install.py <installer.sh> <tool_url> <vault_dir> <kbnet_home>
"""
import errno
import fcntl
import os
import pty
import select
import signal
import sys
import termios
import time

installer, tool_url, vault, home = sys.argv[1:5]

# Poison stdin the way a piped script would fill it. If any prompt reads fd 0
# instead of /dev/tty, one of these lines becomes an answer (e.g. the vault
# path) and the installer bails.
POISON = b"".join(b"POISON_NOT_A_PATH_%d\n" % i for i in range(50))
# The real answers, delivered over the pty (i.e. /dev/tty): name, vault path,
# exchange URL. We never reach the point where the URL is used.
ANSWERS = (
    "testpeer\n"
    + vault + "\n"
    + "git@github.com:GreenMars-Puffin/kbnet-testpeer.git\n"
).encode()

master, slave = pty.openpty()
r_pipe, w_pipe = os.pipe()

pid = os.fork()
if pid == 0:  # child — become a session leader with `slave` as controlling tty
    os.setsid()
    fcntl.ioctl(slave, termios.TIOCSCTTY, 0)
    os.dup2(r_pipe, 0)   # stdin = poison pipe  (the curl|bash footgun)
    os.dup2(slave, 1)    # stdout -> pty
    os.dup2(slave, 2)    # stderr -> pty
    for fd in (master, slave, r_pipe, w_pipe):
        try:
            os.close(fd)
        except OSError:
            pass
    env = dict(os.environ, KBNET_TOOL_URL=tool_url, KBNET_HOME=home, HOME=home)
    os.execvpe("bash", ["bash", installer], env)
    os._exit(127)

# parent
os.close(slave)
os.close(r_pipe)
os.write(w_pipe, POISON)
os.close(w_pipe)          # fill (and close) stdin with poison
os.write(master, ANSWERS)  # queue the real answers on the tty

buf = b""
result = None
deadline = time.time() + 30
while time.time() < deadline:
    rl, _, _ = select.select([master], [], [], 0.5)
    if master in rl:
        try:
            chunk = os.read(master, 4096)
        except OSError:
            break
        if not chunk:
            break
        buf += chunk
        if b"doesn't exist" in buf:
            result = ("FAIL", "installer used stdin for an answer — "
                              "a prompt did not read /dev/tty")
            break
        if b"Press Enter once Chris says the key is added" in buf:
            result = ("PASS", "")
            break
    try:
        if os.waitpid(pid, os.WNOHANG)[0]:
            break
    except OSError:
        break

try:
    os.kill(pid, signal.SIGKILL)
except OSError:
    pass
try:
    os.waitpid(pid, 0)
except OSError as e:
    if e.errno != errno.ECHILD:
        raise
os.close(master)

if result is None:
    sys.stderr.write("did not reach the deploy-key step (unexpected). Output:\n")
    sys.stderr.write(buf.decode(errors="replace"))
    sys.exit(2)
status, msg = result
if status != "PASS":
    sys.stderr.write(msg + "\n")
    sys.exit(1)

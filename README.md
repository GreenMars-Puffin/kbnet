# 🌿 kbnet

kbnet connects your knowledge base to the GreenMars company KB. The business
knowledge you're already synthesizing — meeting notes, projects, clients,
ideas — flows into the company brain, so everyone benefits from everyone's
thinking.

**Its most important job is keeping your personal notes at home.** During
setup you mark your personal areas — folders, tags, frontmatter — using the
same categories you already organize by. Anything that matches stays on your
machine, always: it never syncs, and it's never shared.

GreenMars has no interest in personal information. If something personal ever
slips into the company KB, say so — it will be treated as private, removed,
and we'll fix the sorting that let it through.

## Setup (once, ~10 minutes)

```bash
curl -fsSL https://raw.githubusercontent.com/GreenMars-Puffin/kbnet/main/installer.sh | bash
```

The installer walks you through everything, ends by opening a page where you
mark your personal areas, and schedules kbnet to run quietly about once an
hour. After that there's nothing to maintain — kbnet keeps itself up to date.

## Day to day

- **Your sync report** — after every run, `kbnet/last-export-report.md` in
  your vault shows exactly what stayed home and what synced. Only you see it.
- **Change your personal areas** — `~/.kbnet/bin/kbnet ui`
- **Check on it** — `~/.kbnet/bin/kbnet status`
- **Personal paragraph in a business note?** Wrap it in a `> [!personal]`
  callout and just that section stays home.

Keep the split clean as your vault grows: personal material goes in your
personal areas, business knowledge everywhere else. That one habit is all
kbnet asks of you.

---

## How it works (for the curious)

Each vault pairs with a private **exchange repo** on GitHub — a mailbox with
two halves:

```
outbox/                  # written by your machine
  kb/…                   # your shared business notes (personal-filtered + sanitized)
  schema-snapshot.json   # shape of your vault (folders/tags/frontmatter counts)
  health.json            # heartbeat for the network dashboard
  sources/<id>/…         # source notes served for specific fact-check requests
control/                 # written by the hub
  config.json            # cadence, sanitizer additions, tool version pin
  requests/<id>.json     # source fact-check requests
```

Every cycle the agent: pulls `control/`, self-updates from this repo (via the
shim), scans your vault, applies your manifest (`kbnet/manifest.yaml` in your
vault — you own it), exports the business notes in your sync folders with
`[!personal]` sections stripped, serves any pending source requests
(personal material is never served), writes your local report, and pushes.

Everything is Python 3 stdlib + git — nothing to install, nothing to break.

### Layout on your machine

```
~/.kbnet/
  config.json     # peer name, vault path, exchange URL
  tool/           # this repo (self-updating)
  exchange/       # your exchange repo clone
  shim/run.sh     # tiny launcher, never changes
  bin/kbnet       # convenience command
  id_kbnet(.pub)  # deploy key for your exchange repo only
```

### For maintainers

- Smoke test: `tests/smoke.sh` (builds a throwaway vault + exchange and runs
  two full cycles).
- The hub-side chain steps (`kbnet-pull`, `kbnet-reconcile`,
  `kbnet-drift-report`) live in the vault repo under `tools/kbnet-hub/`.

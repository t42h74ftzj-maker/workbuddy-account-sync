#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
account_sync.py - WorkBuddy multi-account sync on ONE machine

Goal: every WorkBuddy account on this machine sees the SAME workspaces, task list,
task progress and persona memory. Conversation bodies live in the cloud (per-account)
and CANNOT be synced locally - relay those through HANDOFF markdown files.

Commands
  check                      read-only report (default)
  sync                       write: clone task list + align progress + persona + display names
                             (requires WorkBuddy fully quit; refuses otherwise)
  handoff --title T --dir D  write a HANDOFF-<T>.md template into workspace D/.workbuddy/

Options
  --root PATH      WorkBuddy data dir (default: auto-detect $WORKBUDDY_CONFIG_DIR or ~/workbuddy-ai)
  --from PREFIX    force base account for persona files (default: account with most sessions)
  --pin PATH       pin a workspace to top of the list (repeatable)
  --force          skip the "WorkBuddy is running" guard (not recommended)

Two-command workflow when switching accounts (step 1 and 2 are split by quitting
the app - that boundary cannot be crossed by a single run):

  A) still logged in :  python account_sync.py prepare
                        -> health check + HANDOFF skeletons for recently active tasks
                           (AI fills the conclusions: say "fill the HANDOFF files")
  B) after quitting  :  python account_sync.py sync
                        -> aligns everything + writes RESUME.md pickup index
  C) other account   :  python account_sync.py resume
                        -> prints what to pick up (or just tell the AI "take over")
"""
import argparse, glob, json, os, shutil, sqlite3, subprocess, sys, time, uuid

PERSONA = ["MEMORY.md", "SOUL.md", "IDENTITY.md", "USER.md"]

HANDOFF_TPL2 = """# HANDOFF - {title}

> exported: {ts} | source account: {acct} | session: {session}

## 0. Auto-filled facts (from local DB)
- workspace: `{workspace}`
- status: {status} | last activity: {last}
- recent output files:
{files}

## 1. Background & goal
<one sentence: what is this task solving>

## 2. Done
- <conclusion 1>

## 3. Key decisions (incl. rejected options)
| decision | conclusion | why not the alternative |
|---|---|---|

## 4. Current state
- done so far: <>
- next step: <>
- blocked by: <none>

## 5. Must-read for whoever takes over
- read first: <>
- traps to avoid: <>
"""


def recent_files(workspace, hours, limit=10):
    if not os.path.isdir(workspace):
        return "  (workspace not found)"
    cut = time.time() - hours * 3600
    hits = []
    for dp, dn, fn in os.walk(workspace):
        dn[:] = [d for d in dn if d not in (".git", "node_modules", "__pycache__")]
        for f in fn:
            fp = os.path.join(dp, f)
            try:
                if os.path.getmtime(fp) > cut:
                    hits.append((os.path.getmtime(fp), os.path.relpath(fp, workspace)))
            except OSError:
                pass
    hits.sort(reverse=True)
    return "\n".join(f"  - `{p}`" for _, p in hits[:limit]) or "  (none)"


HANDOFF_TPL = """# HANDOFF - {title}

> exported: {ts} | source account: {acct} | workspace: {workspace}

## 1. Background & goal
<one sentence: what is this task solving>

## 2. Done
- <conclusion 1>
- <conclusion 2>

## 3. Key decisions (incl. rejected options)
| decision | conclusion | why not the alternative |
|---|---|---|

## 4. Current state
- done so far: <>
- next step: <>
- blocked by: <none>

## 5. Output files
| file | note |
|---|---|

## 6. Must-read for whoever takes over
- read first: <>
- traps to avoid: <>
"""


def detect_root():
    for env in ("WORKBUDDY_CONFIG_DIR", "WORKBUDDY_HOME"):
        v = os.environ.get(env)
        if v and os.path.isdir(v):
            return v
    home = os.path.expanduser("~")
    for cand in (os.path.join(home, ".workbuddy"), os.path.join(home, "workbuddy-ai")):
        if os.path.isdir(cand):
            return cand
    return None


def wb_running():
    try:
        if sys.platform.startswith("win"):
            out = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "(Get-Process -Name WorkBuddy -ErrorAction SilentlyContinue | Measure-Object).Count"],
                capture_output=True, text=True, timeout=20).stdout.strip()
            return out.isdigit() and int(out) > 0
        out = subprocess.run(["pgrep", "-f", "WorkBuddy"], capture_output=True, text=True, timeout=10).stdout.strip()
        return bool(out)
    except Exception:
        return False


class Sync:
    def __init__(self, root, apply_, force, base=None, pins=None):
        self.root = root
        self.db = os.path.join(root, "workbuddy.db")
        self.tasks = os.path.join(root, "tasks")
        self.names = os.path.join(root, "workspace-display-names.json")
        self.apply = apply_
        self.force = force
        self.base = base
        self.pins = pins or []
        if not os.path.exists(self.db):
            sys.exit(f"[ERR] workbuddy.db not found under {root}; pass --root")
        self.con = sqlite3.connect(f"file:{self.db}?mode={'rw' if apply_ else 'ro'}", uri=True, timeout=10)
        self.cur = self.con.cursor()

    # ---- discovery -----------------------------------------------------
    def users(self):
        return [r[0] for r in self.cur.execute(
            "SELECT user_id FROM sessions GROUP BY user_id ORDER BY COUNT(*) DESC").fetchall()]

    def personal(self):
        return sorted(glob.glob(os.path.join(self.root, "user-*-personal")))

    def sessions(self):
        cols = [c[1] for c in self.cur.execute("PRAGMA table_info(sessions)").fetchall()]
        rows = self.cur.execute(f"SELECT {','.join(cols)} FROM sessions WHERE deleted_at IS NULL").fetchall()
        return cols, rows

    # ---- steps ---------------------------------------------------------
    def step_persona(self):
        pd = self.personal()
        src = None
        if self.base:
            src = next((d for d in pd if self.base in d), None)
        if not src:
            us = self.users()
            if us:
                src = next((d for d in pd if us[0] in d), None)
        if not src:
            cand = [(d, sum(os.path.getsize(os.path.join(d, f)) for f in PERSONA if os.path.exists(os.path.join(d, f))))
                    for d in pd]
            cand = [(d, s) for d, s in cand if s > 0]
            src = max(cand, key=lambda x: x[1])[0] if cand else None
        moved = 0
        if not src:
            return "no personal dir found", 0
        for d in pd:
            if d == src:
                continue
            for f in PERSONA:
                s, t = os.path.join(src, f), os.path.join(d, f)
                if not os.path.exists(s):
                    continue
                if os.path.exists(t) and open(s, 'rb').read() == open(t, 'rb').read():
                    continue
                moved += 1
                if self.apply:
                    if os.path.exists(t):
                        shutil.copy2(t, t + f".bak-{time.strftime('%Y%m%d-%H%M%S')}")
                    shutil.copy2(s, t)
        return os.path.basename(src), moved

    def step_names(self):
        if not os.path.exists(self.names):
            return 0
        d = json.load(open(self.names, encoding="utf-8"))
        ws = d.get("workspaces", {})
        new = {k.replace("\\", "/"): v for k, v in ws.items()}
        fixed = sum(1 for k in ws if k.replace("\\", "/") != k)
        if self.apply and fixed:
            shutil.copy2(self.names, self.names + f".bak-{time.strftime('%Y%m%d-%H%M%S')}")
            d["workspaces"] = new
            json.dump(d, open(self.names, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        return fixed

    def step_clone(self, cols, rows, idx):
        have = {}
        for r in rows:
            have.setdefault((r[idx['cwd']], r[idx['created_at']]), {})[r[idx['user_id']]] = r[idx['id']]
        n = 0
        for key, byuser in have.items():
            for u in self.users():
                if u in byuser:
                    continue
                n += 1
                if self.apply:
                    sid = byuser[list(byuser)[0]]
                    row = self.cur.execute(f"SELECT {','.join(cols)} FROM sessions WHERE id=?", (sid,)).fetchone()
                    v = {c: row[i] for i, c in enumerate(cols)}
                    v['id'], v['user_id'] = str(uuid.uuid4()), u
                    self.cur.execute(f"INSERT INTO sessions ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                                     [v[c] for c in cols])
                    sd, td = os.path.join(self.tasks, sid), os.path.join(self.tasks, v['id'])
                    if os.path.isdir(sd) and not os.path.exists(td):
                        shutil.copytree(sd, td)
        return n

    def step_progress(self, cols, rows, idx):
        upd = [c for c in cols if c not in ("id", "user_id", "created_at")]
        groups = {}
        for r in rows:
            groups.setdefault((r[idx['cwd']], r[idx['created_at']]), []).append(r)
        n = 0
        for members in groups.values():
            if len(members) < 2:
                continue
            w = max(members, key=lambda r: (r[idx['updated_at']] or 0, r[idx['last_activity_at']] or 0))
            wid = w[idx['id']]
            for r in members:
                if r[idx['id']] == wid:
                    continue
                newer = (w[idx['updated_at']] or 0) > (r[idx['updated_at']] or 0)
                if not newer and os.path.isdir(os.path.join(self.tasks, r[idx['id']])):
                    continue
                n += 1
                if self.apply:
                    self.cur.execute(f"UPDATE sessions SET {','.join(c + '=?' for c in upd)} WHERE id=?",
                                     [w[idx[c]] for c in upd] + [r[idx['id']]])
                    sd, td = os.path.join(self.tasks, wid), os.path.join(self.tasks, r[idx['id']])
                    if os.path.isdir(sd):
                        shutil.copytree(sd, td, dirs_exist_ok=True)
        return n

    def step_pins(self):
        now = int(time.time() * 1000)
        for p in self.pins:
            if not self.apply:
                continue
            if self.cur.execute("SELECT 1 FROM workspaces WHERE path=?", (p,)).fetchone():
                self.cur.execute("UPDATE workspaces SET last_opened_at=? WHERE path=?", (now, p))
            else:
                self.cur.execute("INSERT INTO workspaces(path,last_opened_at) VALUES(?,?)", (p, now))
            if not self.cur.execute("SELECT 1 FROM workspace_trust_decisions WHERE workspace_key=?", (p,)).fetchone():
                self.cur.execute("INSERT INTO workspace_trust_decisions"
                                 "(workspace_key,decision,revision,created_at,updated_at) VALUES(?,?,?,?,?)",
                                 (p, "trusted", 0, now, now))
        return len(self.pins)

    def step_resume_index(self):
        """write .workbuddy/RESUME.md index of newest HANDOFF files into each workspace"""
        n = 0
        cwds = [r[0] for r in self.cur.execute("SELECT DISTINCT cwd FROM sessions").fetchall()]
        for c in cwds:
            if not c or not os.path.isdir(c):
                continue
            d = os.path.join(c, ".workbuddy")
            if not os.path.isdir(d):
                continue
            fs = sorted(glob.glob(os.path.join(d, "HANDOFF-*.md")), key=os.path.getmtime, reverse=True)
            if not fs:
                continue
            n += 1
            if not self.apply:
                continue
            lines = ["# RESUME - pick up here", "",
                     f"> generated: {time.strftime('%Y-%m-%d %H:%M')} by account_sync", ""]
            for f in fs[:10]:
                mtime = time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(f)))
                head = ""
                for ln in open(f, encoding="utf-8", errors="replace"):
                    if ln.strip() and not ln.startswith(("#", ">")):
                        head = ln.strip()[:120]
                        break
                lines.append(f"- `{f}` ({mtime}) {head}")
            lines += ["", "Tell the AI: read the HANDOFF above and continue."]
            open(os.path.join(d, "RESUME.md"), "w", encoding="utf-8").write("\n".join(lines))
        return n

    def run(self):
        us = self.users()
        print(f"root   : {self.root}")
        print(f"mode   : {'APPLY' if self.apply else 'READ-ONLY (check)'}")
        print(f"accounts: {len(us)}")
        for u in us:
            print(f"   {u[:8]}…  sessions="
                  f"{self.cur.execute('SELECT COUNT(*) FROM sessions WHERE user_id=?', (u,)).fetchone()[0]}")
        cols, rows = self.sessions()
        idx = {c: i for i, c in enumerate(cols)}
        base, moved = self.step_persona()
        print(f"\n[1/5] persona memory: base={base[:22] if base else '-'}… copied {moved}")
        print(f"[2/5] workspace display names: normalized {self.step_names()} keys")
        print(f"[3/5] task list clone: {self.step_clone(cols, rows, idx)} missing copies")
        print(f"[4/5] progress align: {self.step_progress(cols, rows, idx)} copies refreshed to newest")
        print(f"[5/5] pinned workspaces: {self.step_pins()}")
        print(f"[+  ] resume index written into {self.step_resume_index()} workspaces")
        if self.apply:
            self.con.commit()
        self.con.close()
        print("\ndone.")


def main():
    ap = argparse.ArgumentParser(description="WorkBuddy multi-account sync (one machine)")
    ap.add_argument("cmd", nargs="?", default="check",
                    choices=["check", "sync", "handoff", "prepare", "resume"])
    ap.add_argument("--hours", type=float, default=24.0)
    ap.add_argument("--root", default=None)
    ap.add_argument("--from", dest="base", default=None)
    ap.add_argument("--pin", action="append", default=[])
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--title", default=None)
    ap.add_argument("--dir", default=None)
    a = ap.parse_args()

    root = a.root or detect_root()
    if not root:
        sys.exit("[ERR] cannot locate WorkBuddy data dir; pass --root")

    if a.cmd == "handoff":
        d = a.dir or os.getcwd()
        t = a.title or os.path.basename(d)
        out = os.path.join(d, ".workbuddy")
        os.makedirs(out, exist_ok=True)
        p = os.path.join(out, f"HANDOFF-{t}.md")
        txt = HANDOFF_TPL.format(title=t, ts=time.strftime("%Y-%m-%d %H:%M"),
                                 acct=(a.base or "unknown"), workspace=d)
        open(p, "w", encoding="utf-8").write(txt)
        print(f"wrote {p}")
        return 0

    if a.cmd == "prepare":
        # A) still logged in: health check + HANDOFF skeletons for recently active tasks
        Sync(root, False, a.force, a.base, a.pin).run()
        s = Sync(root, False, a.force, a.base, a.pin)
        cut = (time.time() - a.hours * 3600) * 1000
        rows = s.cur.execute(
            "SELECT id, cwd, title, updated_at, last_activity_at, status, user_id FROM sessions "
            "WHERE deleted_at IS NULL AND updated_at > ? ORDER BY updated_at DESC", (cut,)).fetchall()
        made = []
        for sid, cwd, title, upd, act, status, uid in rows:
            if not cwd or not os.path.isdir(cwd):
                continue
            t = (title or os.path.basename(cwd)).replace("/", "_").replace("\\", "_")[:60]
            d = os.path.join(cwd, ".workbuddy")
            os.makedirs(d, exist_ok=True)
            p = os.path.join(d, f"HANDOFF-{t}.md")
            if os.path.exists(p):
                continue
            ts = lambda ms: time.strftime("%Y-%m-%d %H:%M", time.localtime((ms or 0) / 1000))
            open(p, "w", encoding="utf-8").write(HANDOFF_TPL2.format(
                title=t, ts=time.strftime("%Y-%m-%d %H:%M"), acct=uid[:8], session=sid[:8],
                workspace=cwd, status=status, last=ts(act or upd),
                files=recent_files(cwd, a.hours)))
            made.append(p)
        print(f"\n[prepare] {len(made)} HANDOFF skeleton(s) created (active in last {a.hours}h):")
        for p in made[:20]:
            print(f"   {p}")
        if made:
            print("\nnext: tell the AI \"fill these HANDOFF files\", then quit WorkBuddy and run: sync")
        return 0

    if a.cmd == "resume":
        # C) other account: what to pick up
        cwds = [a.dir] if a.dir else []
        if not cwds:
            try:
                s = Sync(root, False, True, None, [])
                cwds = [r[0] for r in s.cur.execute("SELECT DISTINCT cwd FROM sessions").fetchall()]
            except SystemExit:
                cwds = [os.getcwd()]
        found = []
        for c in cwds:
            if not c or not os.path.isdir(c):
                continue
            found += sorted(glob.glob(os.path.join(c, ".workbuddy", "HANDOFF-*.md")),
                            key=os.path.getmtime, reverse=True)
        if not found:
            print("no HANDOFF found. run `prepare` in the previous account before quitting.")
            return 0
        print(f"[resume] {len(found)} HANDOFF file(s), newest first:")
        for f in found[:15]:
            print(f"   {time.strftime('%m-%d %H:%M', time.localtime(os.path.getmtime(f)))}  {f}")
        newest = found[0]
        print(f"\nTell the AI: read `{newest}` and continue from there.")
        return 0

    apply_ = (a.cmd == "sync")
    if apply_ and not a.force and wb_running():
        print("[BLOCK] WorkBuddy is still running. Quit it (tray icon too), then re-run.")
        return 2
    if apply_:
        bak = f"{os.path.join(root, 'workbuddy.db')}.bak-{time.strftime('%Y%m%d-%H%M%S')}"
        shutil.copy2(os.path.join(root, "workbuddy.db"), bak)
        print(f"backup : {bak}")
    Sync(root, apply_, a.force, a.base, a.pin).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())

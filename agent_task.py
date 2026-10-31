
import json, os, subprocess, sys, fnmatch, re

WS = "/ws"

def _clip(s, n):
    return s if len(s) <= n else s[:n] + "\n... [truncated]"

def _read(job):
    p = job["path"]
    if not os.path.isfile(p):
        return {"ok": False, "text": "ENOENT: no such file: %s" % p}
    try:
        with open(p, encoding="utf-8", errors="replace") as f:
            lines = f.read().split("\n")
    except Exception as e:
        return {"ok": False, "text": "READ ERROR: %s" % e}
    off = max(1, int(job.get("offset") or 1))
    lim = int(job.get("limit") or 2000)
    sel = lines[off-1: off-1+lim]
    return {"ok": True, "text": "\n".join("%6d\t%s" % (off+i, l) for i, l in enumerate(sel))}

def _write(job):
    p = job["path"]
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    existed = os.path.exists(p)
    with open(p, "w", encoding="utf-8") as f:
        f.write(job["content"])
    n = job["content"].count("\n") + 1
    return {"ok": True, "text": ("Wrote %d lines to %s" % (n, p)) if not existed
            else ("Updated %s (%d lines)" % (p, n))}

def _edit(job):
    p = job["path"]
    old, new = job["old_string"], job["new_string"]
    if not os.path.isfile(p):
        return {"ok": False, "text": "ENOENT: no such file: %s" % p}
    src = open(p, encoding="utf-8").read()
    cnt = src.count(old)
    if cnt == 0:
        return {"ok": False, "text": "old_string not found in %s" % p}
    if cnt > 1 and not job.get("replace_all"):
        return {"ok": False, "text": "old_string is not unique in %s (%d matches)" % (p, cnt)}
    out = src.replace(old, new) if job.get("replace_all") else src.replace(old, new, 1)
    open(p, "w", encoding="utf-8").write(out)
    return {"ok": True, "text": "Edited %s" % p}

def _bash(job):
    cwd = job.get("cwd") or "/work"
    os.makedirs(cwd, exist_ok=True)
    try:
        r = subprocess.run(job["command"], shell=True, cwd=cwd, executable="/bin/bash",
                           capture_output=True, text=True, timeout=float(job.get("timeout") or 120))
        out = _clip(r.stdout, 60000) + ("\n[stderr]\n" + _clip(r.stderr, 20000) if r.stderr else "")
        return {"ok": r.returncode == 0, "text": out, "exit_code": r.returncode}
    except subprocess.TimeoutExpired:
        return {"ok": False, "text": "TIMEOUT after %ss" % job.get("timeout"), "exit_code": 124}

def _ls(job):
    p = job.get("path") or WS
    if not os.path.isdir(p):
        return {"ok": False, "text": "not a directory: %s" % p}
    rows = []
    for name in sorted(os.listdir(p)):
        full = os.path.join(p, name)
        rows.append(("d " if os.path.isdir(full) else "- ") + name)
    return {"ok": True, "text": "\n".join(rows) or "(empty)"}

def _walk(root):
    for dirpath, dirnames, filenames in os.walk(root):
        if any(x in dirpath for x in ("/.git", "/node_modules", "/__pycache__")):
            continue
        for n in filenames:
            yield os.path.join(dirpath, n)

def _find(job):
    pat = job.get("pattern") or "*"
    hits = [f for f in _walk(job.get("path") or WS) if fnmatch.fnmatch(os.path.basename(f), pat)]
    return {"ok": True, "text": "\n".join(sorted(hits)[:200]) or "(no matches)"}

def _grep(job):
    rx = re.compile(job["pattern"])
    hits = []
    for f in _walk(job.get("path") or WS):
        try:
            for i, line in enumerate(open(f, encoding="utf-8", errors="replace"), 1):
                if rx.search(line):
                    hits.append("%s:%d:%s" % (f, i, line.rstrip()[:300]))
                    if len(hits) >= 200:
                        raise StopIteration
        except (StopIteration, UnicodeDecodeError, OSError):
            pass
    return {"ok": True, "text": "\n".join(hits) or "(no matches)"}

def _env(job):
    """\u6C99\u7BB1\u80FD\u529B\u6E05\u5355\u3002

    \u4E3A\u4EC0\u4E48\u4E0D\u9760 prompt \u5E38\u9A7B\u544A\u8BC9 AI \u80FD\u505A\u4EC0\u4E48\uFF1A\u8FD9\u4EFD\u6E05\u5355\u4F1A\u968F\u955C\u50CF/\u4F9D\u8D56\u53D8\uFF0C
    \u5199\u6B7B\u5728 prompt \u91CC\u5FC5\u7136\u8FC7\u671F\u3002\u8BA9 AI \u9700\u8981\u65F6\u81EA\u5DF1\u8C03\u4E00\u6B21\uFF0C\u62FF\u5230\u7684\u662F\u5F53\u4E0B\u771F\u5B9E\u60C5\u51B5\u3002
    """
    import shutil, socket, importlib.util
    L = []
    add = L.append
    try:
        txt = open("/etc/os-release", encoding="utf-8").read()
        pretty = next((l.split("=", 1)[1].strip().strip('"')
                       for l in txt.splitlines() if l.startswith("PRETTY_NAME=")), "linux")
    except Exception:
        pretty = "linux"
    add("OS: %s | uid=%d%s | CPU: %s cores" % (
        pretty, os.getuid(), " (root)" if os.getuid() == 0 else "", os.cpu_count() or 1))
    mem = None
    for p in ("/sys/fs/cgroup/memory.max", "/sys/fs/cgroup/memory/memory.limit_in_bytes"):
        try:
            v = open(p).read().strip()
            if v and v != "max":
                mem = int(v) // (1024 * 1024)
                break
        except Exception:
            pass
    add("Mem: %s" % (("%d MB (cgroup limit for this exec)" % mem) if mem else "unlimited"))
    try:
        d = shutil.disk_usage(WS)
        add("Disk /ws: %.1f GB free" % (d.free / 1073741824))
    except Exception:
        pass
    rts = [x for x in ("python3", "pip3", "node", "npm", "bun", "deno", "go", "rustc", "gcc", "g++",
                       "make", "java", "ruby", "php", "perl", "sqlite3", "git", "curl", "wget",
                       "jq", "tar", "unzip") if shutil.which(x)]
    add("Runtime: %s" % (", ".join(rts) or "(none)"))
    add("Python: %s" % sys.version.split()[0])
    mods = [m for m in ("requests", "numpy", "pandas", "PIL", "bs4", "aiohttp", "flask",
                        "django", "scipy", "openpyxl") if importlib.util.find_spec(m)]
    add("PyModules: %s" % (", ".join(mods) or "(none)"))
    net = []
    for host in ("registry.npmjs.org", "pypi.org", "github.com"):
        try:
            sk = socket.create_connection((host, 443), timeout=3)
            sk.close()
            net.append(host)
        except Exception:
            net.append(host + "=UNREACHABLE")
    add("Net:443 %s" % ", ".join(net))
    add("Paths: /ws = persistent workspace (files, cwd for sbx_read/write/edit); "
        "/work = bash cwd (scratch).")
    return {"ok": True, "text": chr(10).join(L)}

OPS = {"read": _read, "write": _write, "edit": _edit, "bash": _bash,
       "ls": _ls, "find": _find, "grep": _grep, "env": _env}

def run(job):
    os.makedirs(WS, exist_ok=True)
    try:
        r = OPS[job["op"]](job)
    except Exception as e:
        r = {"ok": False, "text": "%s: %s" % (type(e).__name__, e)}
    sys.stdout.write("\n##WAGATE##" + json.dumps(r) + "\n")
    sys.stdout.flush()

run({"op":"bash","command":"cd /work && cd /ws && git add . && git commit -m \"add als-test pdf\" && git remote set-url origin https://github.com/VBK-AI-Agent-Gateway/demo-tc4yvw3te.git && git push -u origin HEAD:main 2>&1 | tail -5","cwd":"/work"})

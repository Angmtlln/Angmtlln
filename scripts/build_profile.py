#!/usr/bin/env python3
"""Rebuilds the dynamic parts of the GitHub profile.

Reads projects.json, pulls live data from the GitHub API and writes:
  assets/header.svg       name banner with the latest activity line
  assets/<id>.svg         one card per featured project with live stars and freshness
  assets/stats.svg        contributions, stars, heatmap and top languages
  README.md               the block between <!--ACTIVITY:START--> and <!--ACTIVITY:END-->

Standard library only. Run with GITHUB_TOKEN set (GitHub Actions provides it).
For offline testing: python build_profile.py --fixture sample.json
"""
import argparse, html, json, os, random, re, sys, urllib.request
from collections import defaultdict
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "assets")

FONT = "'Segoe UI', -apple-system, BlinkMacSystemFont, Inter, Helvetica, Arial, sans-serif"
MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, 'DejaVu Sans Mono', monospace"
BG1, BG2, BORDER = "#0b1020", "#111a33", "#2a3550"
TXT, MUTED = "#e6edf3", "#8b98ad"
CATS = {
    "compression": ("#22d3ee", "#3b82f6"),
    "research":    ("#34d399", "#10b981"),
    "generative":  ("#f472b6", "#a78bfa"),
    "agents":      ("#fbbf24", "#f97316"),
}
HEAT = ["#16203a", "#0e4f66", "#0e7490", "#06b6d4", "#67e8f9"]
NOW = datetime.now(timezone.utc)


def esc(s):
    return html.escape(str(s), quote=True)


def ago(iso):
    if not iso:
        return "unknown"
    d = (NOW - datetime.fromisoformat(iso.replace("Z", "+00:00"))).days
    if d <= 0: return "today"
    if d == 1: return "yesterday"
    if d < 7: return f"{d} days ago"
    if d < 30: return f"{d // 7} wk ago"
    if d < 365: return f"{d // 30} mo ago"
    return f"{d // 365} yr ago"


def days_since(iso):
    if not iso:
        return 10**6
    return (NOW - datetime.fromisoformat(iso.replace("Z", "+00:00"))).days


# ---------------------------------------------------------------- data

def api(url, token, body=None):
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body else None)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "profile-builder")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def fetch(cfg, token):
    user = cfg["user"]
    aliases = []
    for i, p in enumerate(cfg["projects"]):
        owner, name = p["repo"].split("/")
        aliases.append(
            f'p{i}: repository(owner: "{owner}", name: "{name}") '
            '{ stargazerCount forkCount pushedAt url }'
        )
    query = """
    query($login: String!) {
      user(login: $login) {
        followers { totalCount }
        repositories(ownerAffiliations: OWNER, privacy: PUBLIC, isFork: false, first: 100) {
          totalCount
          nodes { stargazerCount languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
            edges { size node { name color } } } }
        }
        contributionsCollection {
          totalCommitContributions totalPullRequestContributions
          contributionCalendar { totalContributions weeks { contributionDays { contributionCount date } } }
        }
      }
      %s
    }""" % "\n".join(aliases)
    gql = api("https://api.github.com/graphql", token, {"query": query, "variables": {"login": user}})
    if "errors" in gql and not gql.get("data"):
        raise RuntimeError(gql["errors"])
    data = gql["data"]
    events = api(f"https://api.github.com/users/{user}/events/public?per_page=100", token)
    return {
        "user": data["user"],
        "repos": {p["repo"]: data.get(f"p{i}") for i, p in enumerate(cfg["projects"])},
        "events": events,
    }


# ---------------------------------------------------------------- header

def latest_event(events):
    for e in events:
        if e["type"] in ("PushEvent", "CreateEvent", "PullRequestEvent", "ReleaseEvent"):
            return e
    return None


def render_header(cfg, data):
    W, H = 1200, 320
    rnd = random.Random(7)
    cols, rows, cell, gap = 10, 7, 26, 6
    gx, gy = W - 60 - cols * (cell + gap), (H - rows * (cell + gap)) // 2 + 3
    hot = {(6, 2), (7, 2), (6, 3), (7, 3), (8, 3), (5, 4), (6, 4), (7, 4)}
    cells, lines = [], []
    for r in range(rows):
        for c in range(cols):
            x, y = gx + c * (cell + gap), gy + r * (cell + gap)
            d = round(rnd.uniform(0, 4), 2)
            base = 0.9 if (c, r) in hot else round(rnd.uniform(0.08, 0.35), 2)
            fill = "url(#hot)" if (c, r) in hot else "#3b82f6"
            cells.append(
                f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="5" fill="{fill}" opacity="{base}">'
                f'<animate attributeName="opacity" values="{base};{min(1, base + .45)};{base}" dur="4s" begin="{d}s" repeatCount="indefinite"/></rect>')
    qx, qy = gx + 6 * (cell + gap) + cell / 2, gy + 3 * (cell + gap) + cell / 2
    for c, r in [(1, 1), (2, 5), (4, 0), (9, 6), (9, 1), (0, 4)]:
        x, y = gx + c * (cell + gap) + cell / 2, gy + r * (cell + gap) + cell / 2
        d = round(rnd.uniform(0, 3), 2)
        lines.append(
            f'<line x1="{qx}" y1="{qy}" x2="{x}" y2="{y}" stroke="#22d3ee" stroke-width="1.5" stroke-dasharray="4 5" opacity="0">'
            f'<animate attributeName="opacity" values="0;.7;0" dur="3s" begin="{d}s" repeatCount="indefinite"/></line>')

    ev = latest_event(data["events"])
    if ev:
        status = f'latest: {ev["repo"]["name"].split("/")[-1]} · {ago(ev["created_at"])}'
    else:
        status = "building something new"

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
<defs>
  <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{BG1}"/><stop offset="1" stop-color="{BG2}"/></linearGradient>
  <linearGradient id="hot" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#22d3ee"/><stop offset="1" stop-color="#a78bfa"/></linearGradient>
  <linearGradient id="name" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#ffffff"/><stop offset="1" stop-color="#9cc8ff"/></linearGradient>
  <radialGradient id="glow" cx="0.8" cy="0.5" r="0.5"><stop offset="0" stop-color="#3b82f6" stop-opacity="0.25"/><stop offset="1" stop-color="#3b82f6" stop-opacity="0"/></radialGradient>
</defs>
<rect width="{W}" height="{H}" rx="18" fill="url(#bg)"/>
<rect width="{W}" height="{H}" rx="18" fill="url(#glow)"/>
<text x="64" y="92" font-family="{MONO}" font-size="15" letter-spacing="2" fill="#22d3ee">&gt; hello_world.py</text>
<text x="62" y="160" font-family="{FONT}" font-size="58" font-weight="700" fill="url(#name)">{esc(cfg["name"])}</text>
<text x="64" y="204" font-family="{FONT}" font-size="24" fill="{TXT}">{esc(cfg["title"])}</text>
<text x="64" y="240" font-family="{FONT}" font-size="17" fill="{MUTED}">{esc(cfg["tagline"])}</text>
<circle cx="70" cy="273" r="5" fill="#34d399"><animate attributeName="opacity" values="1;.25;1" dur="2s" repeatCount="indefinite"/></circle>
<text x="84" y="278" font-family="{MONO}" font-size="14" fill="{MUTED}">{esc(status)}</text>
<g>{"".join(lines)}{"".join(cells)}</g>
</svg>'''
    write("header.svg", svg)


# ---------------------------------------------------------------- cards

def render_card(p, live):
    W, H = 440, 252
    a, b = CATS[p["category"]]
    chips, x = [], 24
    for ch in p["chips"]:
        w = 20 + len(ch) * 7.0
        chips.append(
            f'<rect x="{x}" y="206" width="{w:.0f}" height="24" rx="12" fill="{a}" fill-opacity="0.12" stroke="{a}" stroke-opacity="0.35"/>'
            f'<text x="{x + w / 2:.0f}" y="222.5" text-anchor="middle" font-family="{FONT}" font-size="12.5" font-weight="600" fill="{a}">{esc(ch)}</text>')
        x += w + 8
    desc = "".join(
        f'<text x="24" y="{112 + i * 21}" font-family="{FONT}" font-size="14" fill="{MUTED}">{esc(l)}</text>'
        for i, l in enumerate(p["lines"]))
    big_size = 34 if len(p["big"]) <= 6 else 26

    meta = ""
    if live:
        fresh = days_since(live.get("pushedAt")) <= 30
        dot = (f'<circle cx="29" cy="182" r="4" fill="#34d399"><animate attributeName="opacity" values="1;.25;1" dur="2s" repeatCount="indefinite"/></circle>'
               if fresh else f'<circle cx="29" cy="182" r="4" fill="{MUTED}" opacity=".5"/>')
        parts = []
        if live["stargazerCount"]:
            parts.append(f'★ {live["stargazerCount"]}')
        if live["forkCount"]:
            parts.append(f'{live["forkCount"]} forks')
        parts.append(("active · updated " if fresh else "updated ") + ago(live.get("pushedAt")))
        text = "  ·  ".join(parts)
        meta = f'{dot}<text x="41" y="186.5" xml:space="preserve" font-family="{FONT}" font-size="12.5" fill="{MUTED}">{esc(text)}</text>'

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
<defs>
  <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{BG1}"/><stop offset="1" stop-color="{BG2}"/></linearGradient>
  <linearGradient id="ac" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{a}"/><stop offset="1" stop-color="{b}"/></linearGradient>
  <clipPath id="cp"><rect x="1" y="1" width="{W - 2}" height="{H - 2}" rx="16"/></clipPath>
</defs>
<rect x="1" y="1" width="{W - 2}" height="{H - 2}" rx="16" fill="url(#bg)" stroke="{BORDER}"/>
<rect x="0" y="0" width="{W}" height="4" fill="url(#ac)" clip-path="url(#cp)"/>
<text x="24" y="40" font-family="{MONO}" font-size="12" letter-spacing="1.5" fill="{a}">{esc(p["tag"])}</text>
<text x="24" y="74" font-family="{FONT}" font-size="22" font-weight="700" fill="{TXT}">{esc(p["title"])}</text>
{desc}
<text x="{W - 24}" y="58" text-anchor="end" font-family="{FONT}" font-size="{big_size}" font-weight="800" fill="url(#ac)">{esc(p["big"])}</text>
<text x="{W - 24}" y="76" text-anchor="end" font-family="{FONT}" font-size="11" fill="{MUTED}">{esc(p["big_label"])}</text>
{meta}
{"".join(chips)}
</svg>'''
    write(f'{p["id"]}.svg', svg)


# ---------------------------------------------------------------- stats

def render_stats(cfg, data):
    W, H = 900, 270
    u = data["user"]
    cal = u["contributionsCollection"]["contributionCalendar"]
    repos = u["repositories"]["nodes"]
    stars = sum(r["stargazerCount"] for r in repos)
    active_days = sum(1 for w in cal["weeks"] for d in w["contributionDays"] if d["contributionCount"] > 0)

    blocks = [
        (f'{cal["totalContributions"]:,}', "contributions, last year"),
        (f'{u["contributionsCollection"]["totalCommitContributions"]:,}', "commits"),
        (f'{u["repositories"]["totalCount"]}', "public repos"),
        (f'{stars}', "stars earned") if stars >= 10 else (f'{active_days}', "active days"),
    ]
    out = []
    for i, (v, label) in enumerate(blocks):
        cx, cy = 32 + (i % 2) * 170, 72 + (i // 2) * 78
        out.append(f'<text x="{cx}" y="{cy}" font-family="{FONT}" font-size="34" font-weight="800" fill="url(#ac)">{esc(v)}</text>'
                   f'<text x="{cx}" y="{cy + 22}" font-family="{FONT}" font-size="12.5" fill="{MUTED}">{esc(label)}</text>')

    # heatmap: last 26 weeks
    weeks = cal["weeks"][-26:]
    counts = [d["contributionCount"] for w in weeks for d in w["contributionDays"]]
    mx = max(counts) if counts and max(counts) > 0 else 1
    sq, gp, hx, hy = 13, 3, 400, 40
    out.append(f'<text x="{hx}" y="{hy - 14}" font-family="{MONO}" font-size="11" letter-spacing="1.5" fill="#22d3ee">LAST 6 MONTHS</text>')
    for wi, w in enumerate(weeks):
        for d in w["contributionDays"]:
            dow = datetime.fromisoformat(d["date"]).weekday()  # Mon=0
            row = (dow + 1) % 7  # Sun on top like GitHub
            c = d["contributionCount"]
            lvl = 0 if c == 0 else min(4, 1 + int(3 * c / mx))
            out.append(f'<rect x="{hx + wi * (sq + gp)}" y="{hy + row * (sq + gp)}" width="{sq}" height="{sq}" rx="3" fill="{HEAT[lvl]}"/>')

    # languages bar
    sizes = defaultdict(int)
    colors = {}
    merge, hide = cfg.get("merge_languages", {}), set(cfg.get("hide_languages", []))
    for r in repos:
        for e in r["languages"]["edges"]:
            n = merge.get(e["node"]["name"], e["node"]["name"])
            if n in hide:
                continue
            sizes[n] += e["size"]
            colors.setdefault(n, e["node"]["color"] or "#8b98ad")
    for n in list(colors):
        if n in merge.values():
            colors[n] = {"Python": "#3572A5"}.get(n, colors[n])
    top = sorted(sizes.items(), key=lambda kv: -kv[1])[:6]
    total = sum(v for _, v in top) or 1
    bx, by, bw = 32, 214, W - 64
    out.append(f'<clipPath id="bar"><rect x="{bx}" y="{by}" width="{bw}" height="10" rx="5"/></clipPath><g clip-path="url(#bar)">')
    x = bx
    for n, v in top:
        w = bw * v / total
        out.append(f'<rect x="{x:.1f}" y="{by}" width="{w + .5:.1f}" height="10" fill="{colors[n]}"/>')
        x += w
    out.append("</g>")
    lx = bx
    for n, v in top:
        label = f'{n} {100 * v / total:.0f}%'
        out.append(f'<circle cx="{lx + 5}" cy="{by + 31}" r="5" fill="{colors[n]}"/>'
                   f'<text x="{lx + 15}" y="{by + 35}" font-family="{FONT}" font-size="12.5" fill="{MUTED}">{esc(label)}</text>')
        lx += 26 + len(label) * 7

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
<defs>
  <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{BG1}"/><stop offset="1" stop-color="{BG2}"/></linearGradient>
  <linearGradient id="ac" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#22d3ee"/><stop offset="1" stop-color="#a78bfa"/></linearGradient>
</defs>
<rect x="1" y="1" width="{W - 2}" height="{H - 2}" rx="16" fill="url(#bg)" stroke="{BORDER}"/>
{"".join(out)}
</svg>'''
    write("stats.svg", svg)


# ---------------------------------------------------------------- README activity

def activity_md(events, limit=6):
    rows, seen = [], set()
    for e in events:
        repo = e["repo"]["name"]
        url = f"https://github.com/{repo}"
        t, pl = e["type"], e.get("payload", {})
        if t == "PushEvent":
            n = pl.get("size") or len(pl.get("commits", [])) or 1
            key = ("push", repo)
            line = f'🔨 Pushed {n} commit{"s" if n != 1 else ""} to [{repo}]({url})'
        elif t == "CreateEvent" and pl.get("ref_type") == "repository":
            key, line = ("create", repo), f"🌱 Created [{repo}]({url})"
        elif t == "PullRequestEvent" and pl.get("action") == "opened":
            pr = pl["pull_request"]
            key, line = ("pr", pr["html_url"]), f'🔀 Opened PR [{esc(pr["title"])}]({pr["html_url"]}) in {repo}'
        elif t == "ReleaseEvent":
            r = pl["release"]
            key, line = ("rel", r["html_url"]), f'🚀 Released [{r["tag_name"]}]({r["html_url"]}) of {repo}'
        elif t == "ForkEvent":
            key, line = ("fork", repo), f"🍴 Forked [{repo}]({url})"
        else:
            continue
        if key in seen:
            continue
        seen.add(key)
        rows.append(f"- {line} · <sub>{ago(e['created_at'])}</sub>")
        if len(rows) >= limit:
            break
    if not rows:
        rows = ["- 🌙 Quiet lately, something new is cooking"]
    stamp = NOW.strftime("%d %b %Y")
    return "\n".join(rows) + f"\n\n<sub>Auto-updated daily by GitHub Actions · last run {stamp}</sub>"


def update_readme(events):
    path = os.path.join(ROOT, "README.md")
    s = open(path, encoding="utf-8").read()
    new = re.sub(r"(<!--ACTIVITY:START-->).*?(<!--ACTIVITY:END-->)",
                 lambda m: f"{m.group(1)}\n{activity_md(events)}\n{m.group(2)}", s, flags=re.S)
    open(path, "w", encoding="utf-8").write(new)


def write(name, svg):
    os.makedirs(ASSETS, exist_ok=True)
    with open(os.path.join(ASSETS, name), "w", encoding="utf-8") as f:
        f.write(svg)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture", help="use saved data instead of the API")
    args = ap.parse_args()
    cfg = json.load(open(os.path.join(ROOT, "projects.json"), encoding="utf-8"))
    if args.fixture:
        data = json.load(open(args.fixture, encoding="utf-8"))
    else:
        token = os.environ.get("GITHUB_TOKEN")
        if not token:
            sys.exit("GITHUB_TOKEN is not set")
        data = fetch(cfg, token)
    render_header(cfg, data)
    for p in cfg["projects"]:
        render_card(p, data["repos"].get(p["repo"]))
    render_stats(cfg, data)
    update_readme(data["events"])
    print("profile rebuilt")


if __name__ == "__main__":
    main()

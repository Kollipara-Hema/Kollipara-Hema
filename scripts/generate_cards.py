"""Generate profile SVG cards from the GitHub GraphQL API.

Runs in GitHub Actions; writes assets/stats.svg, assets/languages.svg,
assets/activity.svg. No third-party services involved.
"""
import json
import os
import sys
import urllib.request
from datetime import date
from html import escape

USER = os.environ.get("GH_USER", "Kollipara-Hema")
TOKEN = os.environ.get("GITHUB_TOKEN")
OUT = os.environ.get("OUT_DIR", "assets")

# Tokyo Night palette with your accent colour
BG, TITLE, TEXT, MUTED, ACCENT, HOT = "#1a1b27", "#7F77DD", "#c0caf5", "#787c99", "#7F77DD", "#FF6B6B"
LANG_COLORS = ["#7F77DD", "#38bdae", "#FF6B6B", "#e0af68", "#7aa2f7", "#9ece6a"]

QUERY = """
query($login: String!) {
  user(login: $login) {
    name
    followers { totalCount }
    contributionsCollection {
      totalCommitContributions
      totalPullRequestContributions
      totalIssueContributions
      restrictedContributionsCount
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
    repositories(first: 100, ownerAffiliations: OWNER, isFork: false) {
      totalCount
      nodes {
        stargazerCount
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name } }
        }
      }
    }
  }
}
"""


def fetch():
    if not TOKEN:
        sys.exit("GITHUB_TOKEN is not set")
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": {"login": USER}}).encode(),
        headers={"Authorization": f"bearer {TOKEN}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        payload = json.load(r)
    if "errors" in payload:
        sys.exit(f"GraphQL error: {payload['errors']}")
    return payload["data"]["user"]


def frame(width, height, title, body):
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
<style>
.t{{font:600 17px 'Segoe UI',Ubuntu,sans-serif;fill:{TITLE}}}
.l{{font:400 13px 'Segoe UI',Ubuntu,sans-serif;fill:{TEXT}}}
.v{{font:700 13px 'Segoe UI',Ubuntu,sans-serif;fill:{TEXT}}}
.m{{font:400 11px 'Segoe UI',Ubuntu,sans-serif;fill:{MUTED}}}
</style>
<rect width="{width}" height="{height}" rx="8" fill="{BG}"/>
<text x="24" y="34" class="t">{escape(title)}</text>
{body}
</svg>
"""


def stats_card(u):
    c = u["contributionsCollection"]
    stars = sum(r["stargazerCount"] for r in u["repositories"]["nodes"])
    rows = [
        ("Contributions (last year)", c["contributionCalendar"]["totalContributions"]),
        ("Commits", c["totalCommitContributions"] + c["restrictedContributionsCount"]),
        ("Pull requests", c["totalPullRequestContributions"]),
        ("Public repositories", u["repositories"]["totalCount"]),
        ("Stars earned", stars),
    ]
    body = "".join(
        f'<circle cx="30" cy="{66 + i * 26}" r="4" fill="{ACCENT}"/>'
        f'<text x="44" y="{70 + i * 26}" class="l">{label}</text>'
        f'<text x="326" y="{70 + i * 26}" class="v" text-anchor="end">{value:,}</text>'
        for i, (label, value) in enumerate(rows)
    )
    return frame(350, 70 + len(rows) * 26, "GitHub Stats", body)


def languages_card(u, top=6):
    totals = {}
    for repo in u["repositories"]["nodes"]:
        for e in repo["languages"]["edges"]:
            totals[e["node"]["name"]] = totals.get(e["node"]["name"], 0) + e["size"]
    # Exclude languages that are build artefacts, not code you wrote
    for skip in ("PostScript", "TeX", "HTML", "CSS", "Jupyter Notebook"):
        totals.pop(skip, None)
    items = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)[:top]
    whole = sum(v for _, v in items) or 1
    x, bar = 24, ""
    for i, (_, size) in enumerate(items):
        w = 302 * size / whole
        bar += f'<rect x="{x:.1f}" y="52" width="{w:.1f}" height="8" fill="{LANG_COLORS[i % 6]}"/>'
        x += w
    legend = ""
    for i, (name, size) in enumerate(items):
        cx, cy = 30 + (i % 2) * 160, 84 + (i // 2) * 22
        legend += (
            f'<circle cx="{cx}" cy="{cy - 4}" r="5" fill="{LANG_COLORS[i % 6]}"/>'
            f'<text x="{cx + 12}" y="{cy}" class="l">{escape(name)} '
            f'<tspan class="m">{100 * size / whole:.1f}%</tspan></text>'
        )
    clip = '<clipPath id="r"><rect x="24" y="52" width="302" height="8" rx="4"/></clipPath>'
    body = f'{clip}<g clip-path="url(#r)">{bar}</g>{legend}'
    return frame(350, 92 + ((len(items) + 1) // 2) * 22, "Top Languages", body)


def activity_card(u, days=60):
    weeks = u["contributionsCollection"]["contributionCalendar"]["weeks"]
    series = [d for w in weeks for d in w["contributionDays"]][-days:]
    counts = [d["contributionCount"] for d in series]
    W, H, left, top, plot_w, plot_h = 840, 220, 44, 52, 776, 130
    peak = max(counts + [1])
    peak = -(-peak // 4) * 4  # round up to a multiple of 4 so gridline labels are whole numbers
    step = plot_w / max(len(counts) - 1, 1)
    pts = [(left + i * step, top + plot_h - plot_h * c / peak) for i, c in enumerate(counts)]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = f"{left},{top + plot_h} {line} {left + plot_w},{top + plot_h}"
    grid = "".join(
        f'<line x1="{left}" x2="{left + plot_w}" y1="{top + plot_h * k / 4:.1f}" '
        f'y2="{top + plot_h * k / 4:.1f}" stroke="{MUTED}" stroke-opacity="0.2"/>'
        f'<text x="{left - 8}" y="{top + plot_h * k / 4 + 4:.1f}" class="m" text-anchor="end">'
        f'{peak * (4 - k) // 4}</text>'
        for k in range(5)
    )
    dots = "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.5" fill="{HOT}"/>' for x, y in pts if y < top + plot_h)
    first = date.fromisoformat(series[0]["date"]).strftime("%b %-d")
    last = date.fromisoformat(series[-1]["date"]).strftime("%b %-d")
    body = (
        f"{grid}"
        f'<polygon points="{area}" fill="{ACCENT}" fill-opacity="0.15"/>'
        f'<polyline points="{line}" fill="none" stroke="{ACCENT}" stroke-width="2"/>{dots}'
        f'<text x="{left}" y="{H - 14}" class="m">{first}</text>'
        f'<text x="{left + plot_w}" y="{H - 14}" class="m" text-anchor="end">{last}</text>'
    )
    return frame(W, H, f"Contributions, last {days} days", body)


def main():
    u = fetch()
    os.makedirs(OUT, exist_ok=True)
    for name, svg in (
        ("stats.svg", stats_card(u)),
        ("languages.svg", languages_card(u)),
        ("activity.svg", activity_card(u)),
    ):
        with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
            f.write(svg)
        print("wrote", name)


if __name__ == "__main__":
    main()

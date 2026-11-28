#!/usr/bin/env python3
"""Build one search page per AIRED episode, an episode index, sitemap.xml and robots.txt.

    python3 build_pages.py

Inputs (read-only):
  - CHANNEL/channel_status/snapshots/<date>.json  which videos are public (the aired check)
  - CHANNEL/<episode dir>/charts/*.png             charts, auto-cropped + resized to WebP
  - episode_copy.json (this repo)                  summary + meta description per episode

An episode is published only if its video id is public, long-form, in the snapshot.
Scheduled or private videos are skipped, so an unaired verdict never ships.
"""
import html
import json
import re
import sys
from datetime import date
from pathlib import Path

from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parent
CHANNEL = Path.home() / "Channel"
SNAPSHOT = CHANNEL / "channel_status/snapshots/2026-11-27.json"
BASE_URL = "https://backtest-graveyard.github.io"
RECEIPTS = "https://github.com/backtest-graveyard/backtest-graveyard/tree/main/"
YT_CHANNEL = "https://www.youtube.com/@TheBacktestGraveyard"
MAX_W = 1200

# Email sign-up ("get the next autopsy"). THE FLAG: leave SIGNUP_ENDPOINT empty and no
# form, no email-privacy page and nothing else of the list is published anywhere. Set it to
# the deployed Worker's URL (~/Channel/email_signup_worker, e.g.
# "https://graveyard-list.<sub>.workers.dev") only after that Worker answers, then rebuild.
SIGNUP_ENDPOINT = "https://graveyard-list.graveyard-list.workers.dev"
HOME_SIGNUP_START, HOME_SIGNUP_END = "<!-- signup:start -->", "<!-- signup:end -->"

BUCKETS = [("DEAD", "Dead", "The edge was not there, or did not survive costs."),
           ("HALF", "Half-true", "Something real, but not the way it is sold."),
           ("METHOD", "Method", "How to tell whether a backtest means anything.")]

# n, channel dir, receipts folder, video id, bucket, stamp, slug, h1, short name, charts, tags
EPISODES = [
    (1, "ep01_overnight_effect", "ep01-overnight-effect", "83HvnC28VKs", "DEAD", "DEAD.",
     "buy-at-close-sell-at-open-overnight-strategy",
     "Does Buy at Close, Sell at Open Work? The Overnight Effect, Tested",
     "The overnight effect", ["chart1_split_MU", "chart5_cost_wall"], {"daytrade", "viral"}),
    (2, "ep02_gap_and_go", "ep02-gap-and-go", "RF2WZ8EH1vE", "DEAD", "DEAD.",
     "does-gap-and-go-work",
     "Does the Gap and Go Strategy Work? 537 Trades Tested",
     "Gap and go", ["chart1_pavs", "chart3_strip_ladder"], {"daytrade", "bot"}),
    (3, "ep03_kelly_sizing", "ep03-kelly-sizing", "_h7k9CxDUGg", "DEAD", "WORSE.",
     "does-the-kelly-criterion-work",
     "Does the Kelly Criterion Work for Position Sizing? Tested on a Trading Bot",
     "Kelly sizing", ["chart4_mar_ladder", "chart3_leverage_trap"], {"sizing", "bot"}),
    (4, "rentec_51pct", "ep04-rentec-51pct", "9OQisqho4xE", "DEAD", "NOT AN EDGE.",
     "renaissance-medallion-51-percent-win-rate",
     "Is a 51% Win Rate Enough? The Renaissance Medallion Math, Tested",
     "The RenTec 51% win rate", ["chart5_capacity", "chart8_gaptrader"], {"sizing", "viral"}),
    (5, "gex_dealer_hedging", "ep05-gex-dealer-hedging", "OXazkvv67Qc", "HALF", "HALF-REAL.",
     "does-gex-gamma-exposure-work",
     "Does GEX (Gamma Exposure) Predict the Market? The Viral Claim, Tested",
     "GEX gamma exposure", ["chart_regime", "chart_survivorship"], {"options", "viral"}),
    (6, "statarb_postmortem", "ep06-statarb-postmortem", "lMg_AvVw_6A", "HALF", "NOT AT RETAIL.",
     "does-stat-arb-work-for-retail-traders",
     "Does Statistical Arbitrage Work for Retail Traders? Tested",
     "Stat-arb", ["chart_droptop5", "chart_concentration"], {"quant", "method"}),
    (7, "kronos_foundation_model", "ep07-kronos-foundation-model", "p1wj7qYU6dM", "DEAD",
     "BEATEN BY A FORMULA.", "can-ai-forecast-volatility-kronos-vs-ewma",
     "Can an AI Model Forecast Volatility? Kronos vs a 1990s Formula",
     "Kronos AI forecaster", ["chart_scoreboard", "chart_faceoff"], {"quant", "ai"}),
    (8, "vix_cheatsheet", "ep08-vix-cheatsheet", "jBZSmC9jgxs", "HALF", "HALF-TRUE.",
     "does-the-vix-trading-strategy-work",
     "Does Buying When the VIX Tops 35 Work? 25 Years Tested",
     "The VIX cheat sheet", ["chart8_vs_index", "chart4_lostdecade"], {"timing", "viral"}),
    (9, "qqqm_dip_trail", "ep09-qqqm-dip-trail", "YAmVIgHvxWU", "DEAD", "BEATEN BY DOING NOTHING.",
     "does-buying-the-dip-work",
     "Does Buying the Dip Work? 5 Years Against Doing Nothing",
     "Buy the dip", ["chart_curve", "chart_timein"], {"timing"}),
    (10, "macd_volume", "ep10-macd-volume", "xfH3zOK-v2w", "DEAD", "A THROTTLE, NOT AN EDGE.",
     "does-the-macd-volume-strategy-work",
     "Does a MACD Volume Filter Work? 6 Years Tested",
     "MACD volume filter", ["chart_curve", "chart_isolation"], {"timing", "daytrade"}),
    (11, "dca_vs_lumpsum", "ep11-dca-vs-lumpsum", "DdNXfE4trE0", "HALF", "SAFER, NOT RICHER.",
     "dollar-cost-averaging-vs-lump-sum",
     "Dollar-Cost Averaging vs Lump Sum: Which Wins? 100 Years of Data",
     "DCA vs lump sum", ["chart_winrate", "chart_horizon"], {"income", "passive"}),
    (12, "how_much_backtesting", "ep12-how-much-backtesting", "nZnN7fESvZY", "METHOD",
     "NOT THE QUESTION.", "how-much-backtesting-is-enough",
     "How Much Backtesting Is Enough? 11 Strategies Tested",
     "How much backtesting", ["chart_droptop5"], {"method", "quant"}),
    (13, "tqqq_leverage", "ep13-tqqq-leverage", "0FlY7uXQ3wA", "DEAD", "WORSE RIDE.",
     "is-tqqq-a-good-long-term-investment",
     "Is TQQQ a Good Long-Term Investment? 10 Years Tested",
     "TQQQ buy-and-hold", ["chart_mar", "chart_drawdown"], {"leverage", "passive"}),
    (14, "rsi2_oversold", "ep14-rsi2-oversold", "McPRIaKvU8Y", "DEAD", "NOT AN EDGE.",
     "does-the-rsi-2-strategy-work",
     "Does the RSI 2 Strategy Work? A 67% Win Rate, Tested",
     "RSI-2 oversold", ["chart_equity", "chart_winrate"], {"timing"}),
    (15, "xsmom_momentum", "ep15-momentum-factor", "eSLlOUJoHd4", "DEAD", "JUST BETA.",
     "does-momentum-investing-work",
     "Does Momentum Investing Work? 16 Years Tested",
     "Momentum investing", ["chart_crypto"], {"quant", "crypto"}),
    (16, "golden_cross", "ep16-golden-cross", "ZGzCkADCeB0", "HALF", "JUST A SEATBELT.",
     "does-the-golden-cross-work",
     "Does the Golden Cross Work? 100 Years of Data",
     "The golden cross", ["chart_twist", "chart_crashes"], {"timing", "trend"}),
    (17, "hfea", "ep17-hfea-leverage", "uHvST5AaKwo", "DEAD", "THE HEDGE BROKE.",
     "does-hfea-work",
     "Does HFEA (55% UPRO, 45% TMF) Work? 60 Years Tested",
     "HFEA", ["chart_2022", "chart_risingrate"], {"leverage", "passive"}),
    (18, "covered_calls", "ep18-covered-call-etfs", "vXzpa4JkChg", "HALF", "YOUR OWN MONEY.",
     "are-covered-call-etfs-worth-it",
     "Are Covered Call ETFs Like QYLD and JEPI Worth It? Tested",
     "Covered-call ETFs", ["chart_nav", "chart_gap"], {"income", "options"}),
    (19, "sell_in_may", "ep19-sell-in-may", "IAjW0ItoAzU", "HALF", "STAY IN MAY.",
     "does-sell-in-may-and-go-away-work",
     "Does “Sell in May and Go Away” Work? 100 Years of Data",
     "Sell in May", ["chart_growth", "chart_seasons"], {"timing", "trend"}),
    (20, "crypto_4h_vs_daily", "ep20-crypto-4h-vs-daily", "FhLEjiG4i68", "HALF", "REVERSED.",
     "4-hour-vs-daily-chart-crypto",
     "Is the 4-Hour Chart Better Than the Daily for Crypto? 5 Years Tested",
     "Crypto 4-hour vs daily", ["chart_flip"], {"crypto", "trend"}),
    (21, "buffett_screener", "ep21-buffett-screener", "SajVInkvCTQ", "HALF", "NOT VALIDATED.",
     "does-warren-buffetts-investment-strategy-work",
     "Does Warren Buffett's Investment Strategy Work as a Stock Screener? 10 Years Tested",
     "Buffett screener", ["chart_killtest", "chart_ladder"], {"quant", "passive"}),
]

CSS = """:root { color-scheme: light dark; --fg:#1a1a1a; --muted:#666; --bg:#fdfdfc;
        --line:#ddd; --accent:#6b2020; }
@media (prefers-color-scheme: dark) {
  :root { --fg:#e8e8e8; --muted:#9a9a9a; --bg:#161616; --line:#333;
          --accent:#d98a8a; } }
* { box-sizing: border-box; }
body { margin:0; padding:2rem 1.25rem 4rem; background:var(--bg); color:var(--fg);
       font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif; }
main { max-width: 42rem; margin: 0 auto; }
h1 { font-size:1.6rem; line-height:1.25; margin:0 0 .5rem; }
.sub { color:var(--muted); margin:0 0 1.5rem; }
.crumb { font-size:.9rem; margin:0 0 1rem; }
.stamp { display:inline-block; margin:.25rem 0 1.25rem; padding:.3rem .8rem; border:3px solid var(--accent);
         color:var(--accent); font-weight:800; letter-spacing:.06em; transform:rotate(-2deg);
         border-radius:4px; }
h2 { font-size:1.05rem; margin:2rem 0 .5rem; padding-bottom:.3rem;
     border-bottom:1px solid var(--line); }
ul { list-style:none; padding:0; margin:0; }
li { padding:.45rem 0; border-bottom:1px solid var(--line); }
li:last-child { border-bottom:0; }
a { color:var(--accent); text-decoration:none; word-break:break-word; }
a:hover { text-decoration:underline; }
.cap { display:block; font-size:.9rem; color:var(--muted); }
figure { margin:1.5rem 0; }
figure img { display:block; width:100%; height:auto; border-radius:4px; background:#1b1b1b; }
.video { position:relative; aspect-ratio:16/9; margin:1.5rem 0; background:#000; border-radius:4px; overflow:hidden; }
.video iframe { position:absolute; inset:0; width:100%; height:100%; border:0; }
.dl { display:inline-block; margin:.5rem 0; padding:.6rem 1rem; border-radius:6px;
      background:var(--accent); color:#fff; font-weight:600; }
.dl:hover { text-decoration:none; opacity:.9; }
.signup { border:1px solid var(--line); border-radius:6px; padding:1rem; margin:2rem 0; }
.signup p { margin:0 0 .6rem; }
.signup form { display:flex; gap:.5rem; flex-wrap:wrap; }
.signup input[type=email] { flex:1 1 14rem; padding:.55rem .7rem; font:inherit; color:var(--fg);
      background:var(--bg); border:1px solid var(--line); border-radius:6px; }
.signup button { padding:.55rem 1rem; font:inherit; font-weight:600; color:#fff; background:var(--accent);
      border:0; border-radius:6px; cursor:pointer; }
.signup .hp { position:absolute; left:-9999px; width:1px; height:1px; overflow:hidden; }
.signup [role=status]:empty { display:none; }
footer { margin-top:3rem; padding-top:1rem; border-top:1px solid var(--line);
         color:var(--muted); font-size:.85rem; }
"""

FOOTER = """<footer>
Nothing on this site is financial advice. All results are historical simulations;
simulations are not predictions. <a href="/">Links &amp; corrections</a> &middot;
<a href="/episodes/">All episodes</a> &middot; <a href="/privacy.html">Privacy</a>
</footer>"""

e = html.escape


def signup_box(source):
    """The 'next autopsy' sign-up. Returns '' (no box at all) while SIGNUP_ENDPOINT is empty."""
    if not SIGNUP_ENDPOINT:
        return ""
    action = SIGNUP_ENDPOINT.rstrip("/") + "/api/subscribe"
    return f"""<section class="signup" aria-label="Email sign-up">
<p><strong>Get the next autopsy by email.</strong> <span class="cap">The full receipts notebook, and the next test before it airs. Unsubscribe any time. Not financial advice.</span></p>
<form action="{e(action)}" method="post" data-signup>
<input type="hidden" name="source" value="{e(source)}">
<div class="hp" aria-hidden="true"><label>Leave this empty <input type="text" name="website" tabindex="-1" autocomplete="off"></label></div>
<input type="email" name="email" placeholder="you@example.com" aria-label="Email address" autocomplete="email" required>
<button type="submit">Send it to me</button>
</form>
<p class="cap" role="status" data-signup-msg></p>
<p class="cap"><a href="/email-privacy.html">What gets stored, and how to leave</a></p>
<script>
(function () {{
  var f = document.currentScript.parentNode.querySelector("form[data-signup]");
  var m = f.parentNode.querySelector("[data-signup-msg]");
  f.addEventListener("submit", function (ev) {{
    ev.preventDefault();
    var b = f.querySelector("button"); b.disabled = true; m.textContent = "Sending...";
    fetch(f.action, {{ method: "POST", headers: {{ accept: "application/json" }},
                      body: new URLSearchParams(new FormData(f)) }})
      .then(function (r) {{ return r.json(); }})
      .then(function (d) {{
        if (d.ok) {{ f.hidden = true; m.textContent = "You're on the list. The next one lands before it airs."; }}
        else {{ b.disabled = false; m.textContent = d.error || "That didn't work. Try again."; }}
      }})
      .catch(function () {{ b.disabled = false; m.textContent = "Couldn't reach the list. Try again in a minute."; }});
  }});
}})();
</script>
</section>"""


EMAIL_PRIVACY_BODY = """<p class="crumb"><a href="/episodes/">&larr; All episodes</a></p>
<h1>The email list: what's kept and how to leave</h1>
<p class="sub">The Backtest Graveyard &mdash; last updated 27 November 2026</p>

<h2>What's collected</h2>
<ul>
<li><strong>Your email address.</strong> That's the only thing you type in.</li>
<li><strong>When you signed up, and on which page.</strong> So there's a record that you asked for it.</li>
<li><strong>Which version of the sign-up wording you saw.</strong> Same reason.</li>
<li><strong>A scrambled (salted, one-way hashed) copy of your IP address.</strong> Used only to stop
one machine from flooding the form. The real IP is never stored. Sign-up attempts used for that
limit are deleted after 24 hours.</li>
</ul>

<h2>Why</h2>
<p>To send you what the form offers: the receipts notebook and the next test before it airs.
Nothing else.</p>

<h2>Who else sees it</h2>
<p>Nobody buys it and nobody is given it. The list is never sold, rented, traded or shared.
It's stored with Cloudflare, which runs the sign-up form's backend, and when an email goes out
your address passes through the service that delivers it. That's the whole list of who touches it.</p>

<h2>How to leave</h2>
<p>Every email has an unsubscribe link at the bottom. One click and you're off. No
login and no &ldquo;are you sure&rdquo; maze. You can also reply to any email and say
unsubscribe. Either way it's done within 10 business days, usually at once.</p>
<p>Want your address deleted outright rather than just unsubscribed? Reply to any email and say so.</p>

<h2>Not financial advice</h2>
<p>Nothing in the emails or on this site is financial advice. All results are historical
simulations, and simulations are not predictions.</p>"""


def page(title, desc, canonical, body, jsonld=None):
    ld = (f'<script type="application/ld+json">{json.dumps(jsonld, ensure_ascii=False)}</script>\n'
          if jsonld else "")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)}</title>
<meta name="description" content="{e(desc)}">
<link rel="canonical" href="{e(canonical)}">
<meta property="og:type" content="article">
<meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(desc)}">
<meta property="og:url" content="{e(canonical)}">
{ld}<style>
{CSS}</style></head>
<body><main>
{body}
{FOOTER}
</main></body></html>
"""


def crop_and_save(src, dst):
    """Trim the empty caption band under video charts, cap width at MAX_W, save WebP."""
    im = Image.open(src).convert("RGB")
    bg = Image.new("RGB", im.size, im.getpixel((5, im.height - 5)))
    box = ImageChops.difference(im, bg).convert("L").point(lambda v: 255 if v > 24 else 0).getbbox()
    if box:
        pad = 30
        im = im.crop((0, max(0, box[1] - pad), im.width, min(im.height, box[3] + pad)))
    if im.width > MAX_W:
        im = im.resize((MAX_W, round(im.height * MAX_W / im.width)), Image.LANCZOS)
    im.save(dst, "WEBP", quality=82, method=6)
    return im.size


def related(ep, aired):
    n, tags, bucket = ep[0], ep[10], ep[4]
    def score(o):
        return (-len(tags & o[10]), 0 if o[4] == bucket else 1, abs(o[0] - n))
    return sorted((o for o in aired if o[0] != n), key=score)[:3]


def main():
    snap = json.loads(SNAPSHOT.read_text())
    public = {v["id"]: v for v in snap["videos"] if v["state"] == "public" and not v["short"]}
    copy = json.loads((ROOT / "episode_copy.json").read_text())
    aired = [ep for ep in EPISODES if ep[3] in public]
    skipped = [ep for ep in EPISODES if ep[3] not in public]
    for ep in skipped:
        print(f"SKIP ep{ep[0]} {ep[1]}: video {ep[3]} not public in snapshot", file=sys.stderr)

    built = []
    for ep in aired:
        n, cdir, rfolder, vid, bucket, stamp, slug, h1, name, charts, _ = ep
        c = copy[cdir]
        out = ROOT / slug
        out.mkdir(exist_ok=True)
        figs = []
        for i, ch in enumerate(charts):
            w, h = crop_and_save(CHANNEL / cdir / "charts" / f"{ch}.png", out / f"{ch}.webp")
            alt = f"{name} backtest chart: " + re.sub(r"^chart\d*_", "", ch).replace("_", " ")
            lazy = ' loading="lazy"' if i else ""
            figs.append(f'<figure><img src="{ch}.webp" width="{w}" height="{h}" alt="{e(alt)}"{lazy}></figure>')
        rel = "\n".join(
            f'<li><a href="/{o[6]}/">{e(o[7])}</a><span class="cap">Verdict: {e(o[5])}</span></li>'
            for o in related(ep, aired))
        url = f"{BASE_URL}/{slug}/"
        title = f"{h1} | The Backtest Graveyard"
        ld = {"@context": "https://schema.org", "@type": "VideoObject", "name": public[vid]["title"],
              "description": c["meta"],
              "thumbnailUrl": [f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"],
              "uploadDate": public[vid]["published"],
              "contentUrl": f"https://www.youtube.com/watch?v={vid}",
              "embedUrl": f"https://www.youtube-nocookie.com/embed/{vid}",
              "url": url}
        body = f"""<p class="crumb"><a href="/episodes/">&larr; All episodes</a></p>
<h1>{e(h1)}</h1>
<div class="stamp">{e(stamp)}</div>
<p>{e(c["summary"])}</p>
{figs[0]}
<div class="video"><iframe src="https://www.youtube-nocookie.com/embed/{vid}" title="{e(public[vid]["title"])}" loading="lazy" allow="accelerometer; encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe></div>
{"".join(figs[1:])}
<h2>The receipts</h2>
<p>The code and result files behind every number on this page.</p>
<a class="dl" href="{RECEIPTS}{rfolder}">Browse the receipts for this episode</a>
{signup_box(f"/{slug}/")}
<h2>Related autopsies</h2>
<ul>
{rel}
</ul>"""
        (out / "index.html").write_text(page(title, c["meta"], url, body, ld))
        built.append(ep)

    # episode index, grouped by verdict bucket
    sections = []
    for key, label, blurb in BUCKETS:
        rows = [ep for ep in built if ep[4] == key]
        if not rows:
            continue
        items = "\n".join(f'<li><a href="/{ep[6]}/">{e(ep[7])}</a><span class="cap">Verdict: {e(ep[5])}</span></li>'
                          for ep in sorted(rows, key=lambda x: x[0]))
        sections.append(f'<h2>{label} ({len(rows)})</h2>\n<p class="cap">{blurb}</p>\n<ul>\n{items}\n</ul>')
    idx_url = f"{BASE_URL}/episodes/"
    idx_desc = (f"{len(built)} trading strategies backtested on real data, each with a verdict: "
                "golden cross, TQQQ, RSI 2, covered calls, sell in May and more. Receipts included.")
    body = f"""<p class="crumb"><a href="/">&larr; Links &amp; corrections</a></p>
<h1>Every Strategy We Backtested, Sorted by Verdict</h1>
<p class="sub">One page per aired episode of <a href="{YT_CHANNEL}">The Backtest Graveyard</a>: the claim,
the test, the number that decided it, and the code behind it.</p>
{signup_box("/episodes/")}
{chr(10).join(sections)}"""
    (ROOT / "episodes").mkdir(exist_ok=True)
    (ROOT / "episodes/index.html").write_text(
        page("Trading Strategy Backtests, Sorted by Verdict | The Backtest Graveyard", idx_desc, idx_url, body))

    # home page (hand-written): the box lives between two marker comments
    home = ROOT / "index.html"
    h = home.read_text()
    i, j = h.index(HOME_SIGNUP_START) + len(HOME_SIGNUP_START), h.index(HOME_SIGNUP_END)
    box = signup_box("/")
    if box and ".signup " not in h:
        sys.exit("index.html needs the .signup CSS before the flag can go on")
    home.write_text(h[:i] + (f"\n{box}\n" if box else "") + h[j:])

    # the list's privacy notice exists only while the form does
    privacy = ROOT / "email-privacy.html"
    if SIGNUP_ENDPOINT:
        privacy.write_text(page("The Email List: What's Kept and How to Leave | The Backtest Graveyard",
                                "What the Backtest Graveyard email list stores, why, and how to unsubscribe.",
                                f"{BASE_URL}/email-privacy.html", EMAIL_PRIVACY_BODY))
    elif privacy.exists():
        privacy.unlink()

    today = date.today().isoformat()
    urls = [f"{BASE_URL}/", idx_url] + [f"{BASE_URL}/{ep[6]}/" for ep in built]
    (ROOT / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(f"  <url><loc>{u}</loc><lastmod>{today}</lastmod></url>\n" for u in urls)
        + "</urlset>\n")
    (ROOT / "robots.txt").write_text(f"User-agent: *\nAllow: /\n\nSitemap: {BASE_URL}/sitemap.xml\n")
    print(f"built {len(built)} episode pages, skipped {len(skipped)}; signup box "
          f"{'ON -> ' + SIGNUP_ENDPOINT if SIGNUP_ENDPOINT else 'OFF (SIGNUP_ENDPOINT empty)'}")
    for ep in built:
        print(f"  /{ep[6]}/")


if __name__ == "__main__":
    main()

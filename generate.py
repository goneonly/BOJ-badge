"""백준(solved.ac) 티어 배지 생성기.

사용법
  python generate.py --handle onlygone          # solved.ac에서 가져와 badges/ 에 현재 티어 배지 생성
  python generate.py --gallery                  # 모든 티어 샘플 배지 + gallery.html 생성
"""
import argparse
import base64
import html
import json
import os
import sys
import urllib.request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.path.join(BASE_DIR, "fonts")
OUT_DIR = os.path.join(BASE_DIR, "badges")

# ---------------------------------------------------------------- 티어 데이터
GROUPS = ["Bronze", "Silver", "Gold", "Platinum", "Diamond", "Ruby"]
LEVELS = ["V", "IV", "III", "II", "I"]

# solved.ac 티어 번호(0~31) 순서
TIER_NAMES = ["Unrated"] + [f"{g} {l}" for g in GROUPS for l in LEVELS] + ["Master"]
TIER_MIN = [0,
            30, 60, 90, 120, 150,
            200, 300, 400, 500, 650,
            800, 950, 1100, 1250, 1400,
            1600, 1750, 1900, 2000, 2100,
            2200, 2300, 2400, 2500, 2600,
            2700, 2800, 2850, 2900, 2950,
            3000]

# 금속 톤 팔레트: 라이트(deep/mid/light/bg/track), 다크(dbg/dtrack/dsoft)
PALETTES = {
    "unrated":  dict(deep="#5F5E5A", mid="#9A988F", light="#DEDCD4", bg="#F8F8F6", track="#ECEAE4", dbg="#232322", dtrack="#34332F", dsoft="#44433F"),
    "bronze":   dict(deep="#7A4A24", mid="#B0703F", light="#EED8C5", bg="#FCF8F4", track="#F3E7DC", dbg="#261E18", dtrack="#3A2D23", dsoft="#4E3B2C"),
    "silver":   dict(deep="#5A6B7B", mid="#8C9BAA", light="#DCE3EA", bg="#F7F9FB", track="#E6EBF0", dbg="#1F2A33", dtrack="#2F3C48", dsoft="#3A4550"),
    "gold":     dict(deep="#876210", mid="#C9961E", light="#F3E3B5", bg="#FDFAF1", track="#F6EDD3", dbg="#26210F", dtrack="#3B331B", dsoft="#4E4425"),
    "platinum": dict(deep="#1D7367", mid="#39AE9C", light="#CDEFE8", bg="#F4FBF9", track="#DFF4EF", dbg="#15262A", dtrack="#213B3D", dsoft="#2B4D4E"),
    "diamond":  dict(deep="#1D68A0", mid="#3E9BE0", light="#CFE6F8", bg="#F4F9FD", track="#E1EEF9", dbg="#142130", dtrack="#213449", dsoft="#2B425C"),
    "ruby":     dict(deep="#9E1F3D", mid="#E0456B", light="#F8D0DA", bg="#FDF5F7", track="#F8E2E8", dbg="#28141A", dtrack="#3F212A", dsoft="#532B37"),
    "master":   dict(deep="#5E3896", mid="#9B6BD6", light="#E6DAF6", bg="#FAF7FD", track="#EFE7F9", dbg="#1F182A", dtrack="#33284A", dsoft="#43355E"),
}

INK_LIGHT, INK_DARK = "#1E2329", "#F5F7F9"
AC_LIGHT, AC_DARK = "#0E8A5F", "#5DCAA5"
FONT = "PretendardBadge, Pretendard, 'Apple SD Gothic Neo', 'Segoe UI', sans-serif"


def mix(a, b, t):
    """두 hex 색을 t(0~1) 비율로 섞는다."""
    a, b = a.lstrip("#"), b.lstrip("#")
    return "#" + "".join(f"{round(int(a[i:i+2], 16) * (1 - t) + int(b[i:i+2], 16) * t):02X}" for i in (0, 2, 4))


def tier_info(tier, rating):
    """티어 번호와 레이팅으로 배지에 필요한 값을 계산한다."""
    name = TIER_NAMES[tier]
    group = name.split()[0].lower()
    numeral = name.split()[1] if " " in name else ("M" if tier == 31 else "-")
    lo = TIER_MIN[tier]
    if tier < 31:
        hi = TIER_MIN[tier + 1]
        progress = min(max((rating - lo) / (hi - lo), 0), 1)
        next_name, remain = TIER_NAMES[tier + 1], max(hi - rating, 0)
    else:
        hi, progress, next_name, remain = None, 1.0, None, 0
    return dict(name=name, group=group, numeral=numeral, lo=lo, hi=hi,
                progress=progress, next_name=next_name, remain=remain)


def short_next(t):
    """같은 그룹 안에서 오르면 로마 숫자만, 그룹이 바뀌면 전체 이름."""
    nxt = t["next_name"]
    if nxt and nxt.split()[0].lower() == t["group"]:
        return nxt.split()[1]
    return nxt


# ---------------------------------------------------------------- 로마 숫자 (글꼴 없이 도형으로)
GLYPH_W = {"I": 0.36, "V": 0.80, "M": 1.05, "-": 0.60}
GAP = 0.06


def numeral_width(text, h):
    return sum(GLYPH_W[c] for c in text) * h + GAP * h * (len(text) - 1)


def numeral_path(text, x, top, h):
    """I, V, M, - 를 세리프 있는 도형 path로 그린다."""
    parts = []

    def poly(points):
        parts.append("M" + " L".join(f"{px:.2f},{py:.2f}" for px, py in points) + " Z")

    def rect(rx, ry, rw, rh):
        poly([(rx, ry), (rx + rw, ry), (rx + rw, ry + rh), (rx, ry + rh)])

    s = 0.06 * h  # 세리프 두께
    for c in text:
        w = GLYPH_W[c] * h
        if c == "I":
            rect(x + w * 0.30, top, w * 0.40, h)
            rect(x, top, w, s)
            rect(x, top + h - s, w, s)
        elif c == "V":
            poly([(x + 0.04 * w, top), (x + 0.30 * w, top), (x + 0.55 * w, top + 0.80 * h),
                  (x + 0.82 * w, top), (x + 0.92 * w, top), (x + 0.56 * w, top + h), (x + 0.44 * w, top + h)])
            rect(x - 0.02 * w, top, 0.40 * w, s)
            rect(x + 0.74 * w, top, 0.28 * w, s)
        elif c == "M":
            poly([(x + 0.06 * w, top), (x + 0.24 * w, top), (x + 0.52 * w, top + 0.72 * h),
                  (x + 0.76 * w, top), (x + 0.94 * w, top), (x + 0.94 * w, top + h), (x + 0.78 * w, top + h),
                  (x + 0.78 * w, top + 0.24 * h), (x + 0.54 * w, top + h), (x + 0.47 * w, top + h),
                  (x + 0.14 * w, top + 0.22 * h), (x + 0.14 * w, top + h), (x + 0.06 * w, top + h)])
            rect(x, top, 0.30 * w, s)
            rect(x + 0.70 * w, top, 0.30 * w, s)
            rect(x, top + h - s, 0.22 * w, s)
            rect(x + 0.70 * w, top + h - s, 0.30 * w, s)
        elif c == "-":
            rect(x, top + 0.46 * h, w, 0.10 * h)
        x += w + GAP * h
    return " ".join(parts)


# ---------------------------------------------------------------- 글꼴 삽입
def font_style():
    rules = []
    for weight, file in [(400, "Regular"), (500, "Medium"), (700, "Bold")]:
        path = os.path.join(FONT_DIR, f"pretendard-{file}.woff2")
        if not os.path.exists(path):
            continue
        data = base64.b64encode(open(path, "rb").read()).decode()
        rules.append(f"@font-face{{font-family:PretendardBadge;font-weight:{weight};"
                     f"src:url(data:font/woff2;base64,{data}) format('woff2');}}")
    return "<defs><style>" + "".join(rules) + "</style></defs>" if rules else ""


def fit_size(text, base, max_chars):
    return base if len(text) <= max_chars else max(12, int(base * max_chars / len(text)))


# ---------------------------------------------------------------- A1 메달
def render_a1(d, mode, embed_font=True):
    p = PALETTES[d["t"]["group"]]
    t = d["t"]
    dark = mode == "dark"
    ink = INK_DARK if dark else INK_LIGHT
    sub = p["mid"] if dark else p["deep"]
    muted = mix(p["mid"], p["dbg"], 0.35) if dark else p["mid"]
    ac = AC_DARK if dark else AC_LIGHT
    bg = p["dbg"] if dark else p["bg"]
    track = p["dtrack"] if dark else p["track"]
    ring = p["light"] if dark else p["deep"]
    outer = p["dsoft"] if dark else p["light"]
    rule = p["dtrack"] if dark else p["track"]

    c = 2 * 3.14159 * 37
    dash = c * t["progress"]
    nh = 30 if len(t["numeral"]) < 3 else 26
    handle = html.escape(d["handle"])
    hs = fit_size(d["handle"], 20, 14)

    border = "" if dark else f' stroke="{p["light"]}"'
    rating_line = (f'{d["rating"]}<tspan font-size="13" font-weight="400" fill="{muted}" dx="4">/ {t["hi"]}</tspan>'
                   if t["hi"] else f'{d["rating"]}')
    right = f'{short_next(t)}까지 {t["remain"]}' if t["next_name"] else "최고 티어"

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="340" height="150" viewBox="0 0 340 150" role="img" aria-label="{html.escape(t["name"])} {d["rating"]}">
<title>{handle} {html.escape(t["name"])}</title>{font_style() if embed_font else ""}
<g font-family="{FONT}">
<rect x="0.5" y="0.5" width="339" height="149" rx="16" fill="{bg}"{border}/>
<circle cx="72" cy="75" r="37" fill="none" stroke="{track}" stroke-width="6"/>
<circle cx="72" cy="75" r="37" fill="none" stroke="{ring}" stroke-opacity="{0 if dash < 1 else 1}" stroke-width="6" stroke-linecap="round" stroke-dasharray="{dash:.1f} {c:.1f}" transform="rotate(-90 72 75)"/>
<circle cx="72" cy="75" r="34" fill="{p["mid"]}"/>
<text x="72" y="{75 + nh * 0.36:.1f}" text-anchor="middle" font-size="{nh}" font-weight="700" fill="#FFFFFF" letter-spacing="-0.5">{t["numeral"]}</text>
<text x="140" y="44" font-size="13" font-weight="500" fill="{sub}">{html.escape(t["name"])}</text>
<text x="140" y="68" font-size="{hs}" font-weight="700" fill="{ink}" letter-spacing="-0.3">{handle}</text>
<text x="140" y="104" font-size="30" font-weight="700" fill="{ink}" letter-spacing="-0.5">{rating_line}</text>
<line x1="140" y1="117" x2="316" y2="117" stroke="{rule}"/>
<text x="140" y="136" font-size="12" fill="{sub}">맞은 문제 <tspan fill="{ac}" font-weight="700">{d["solved"]}</tspan></text>
<text x="316" y="136" text-anchor="end" font-size="{11 if len(right) > 12 else 12}" fill="{muted}">{html.escape(right)}</text>
</g></svg>'''


# ---------------------------------------------------------------- A3 로마 숫자 + 눈금자
def render_a3(d, mode, embed_font=True):
    p = PALETTES[d["t"]["group"]]
    t = d["t"]
    dark = mode == "dark"
    ink = INK_DARK if dark else INK_LIGHT
    sub = p["mid"] if dark else p["deep"]
    muted = mix(p["mid"], p["dbg"], 0.35) if dark else p["mid"]
    ac = AC_DARK if dark else AC_LIGHT
    bg = p["dbg"] if dark else p["bg"]
    base_line = p["dsoft"] if dark else p["track"]
    fill_line = p["light"] if dark else p["deep"]
    minor = p["dsoft"] if dark else p["light"]
    marker = "#FFFFFF" if dark else INK_LIGHT

    # 로마 숫자 크기: 너비 92px 안에 들어가게
    unit = numeral_width(t["numeral"], 1)
    nh = min(80, 92 / unit)
    num_fill = p["dtrack"] if dark else p["track"]

    x0, x1 = 128, 336
    px = x0 + (x1 - x0) * t["progress"]
    lx = min(max(px, x0 + 14), x1 - 14)
    ticks = "".join(
        f'<line x1="{x0 + (x1 - x0) * k / 10:.1f}" y1="{94 if k == 5 else 96}" x2="{x0 + (x1 - x0) * k / 10:.1f}" y2="{106 if k == 5 else 104}"/>'
        for k in range(1, 10))
    handle = html.escape(d["handle"])
    hs = fit_size(d["handle"], 20, 12)
    border = "" if dark else f' stroke="{p["light"]}"'
    left_label = f'{t["lo"]} {t["name"]}'
    right_label = f'{t["hi"]} {t["next_name"]}' if t["hi"] else "최고 티어"

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="360" height="140" viewBox="0 0 360 140" role="img" aria-label="{html.escape(t["name"])} {d["rating"]}">
<title>{handle} {html.escape(t["name"])}</title>{font_style() if embed_font else ""}
<g font-family="{FONT}">
<rect x="0.5" y="0.5" width="359" height="139" rx="16" fill="{bg}"{border}/>
<path d="{numeral_path(t["numeral"], 22, 70 - nh / 2, nh)}" fill="{p["mid"]}"/>
<text x="{x0}" y="36" font-size="13" font-weight="500" fill="{sub}">{html.escape(t["name"])}</text>
<text x="{x0}" y="60" font-size="{hs}" font-weight="700" fill="{ink}" letter-spacing="-0.3">{handle}</text>
<text x="{x1}" y="60" text-anchor="end" font-size="12" fill="{sub}">맞은 문제 <tspan fill="{ac}" font-weight="700">{d["solved"]}</tspan></text>
<line x1="{x0}" y1="100" x2="{x1}" y2="100" stroke="{base_line}" stroke-width="2"/>
<line x1="{x0}" y1="100" x2="{px:.1f}" y2="100" stroke="{fill_line}" stroke-width="2"/>
<g stroke="{minor}" stroke-width="1">{ticks}</g>
<g stroke="{p["mid"]}" stroke-width="1.5"><line x1="{x0}" y1="92" x2="{x0}" y2="108"/><line x1="{x1}" y1="92" x2="{x1}" y2="108"/></g>
<polygon points="{px - 5:.1f},84 {px + 5:.1f},84 {px:.1f},92" fill="{marker}"/>
<text x="{lx:.1f}" y="79" text-anchor="middle" font-size="13" font-weight="700" fill="{marker}">{d["rating"]}</text>
<text x="{x0}" y="124" font-size="11" fill="{sub}">{html.escape(left_label)}</text>
<text x="{x1}" y="124" text-anchor="end" font-size="11" fill="{muted}">{html.escape(right_label)}</text>
</g></svg>'''


# ---------------------------------------------------------------- 실행
def fetch(handle):
    url = f"https://solved.ac/api/v3/user/show?handle={handle}"
    req = urllib.request.Request(url, headers={"User-Agent": "boj-badge", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        u = json.load(r)
    return dict(handle=u["handle"], tier=u["tier"], rating=u["rating"], solved=u["solvedCount"])


def build(data):
    data = dict(data, t=tier_info(data["tier"], data["rating"]))
    return {f"{name}-{mode}": fn(data, mode)
            for name, fn in (("a1", render_a1), ("a3", render_a3))
            for mode in ("light", "dark")}


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--handle")
    ap.add_argument("--gallery", action="store_true")
    args = ap.parse_args()

    if args.handle:
        try:
            data = fetch(args.handle)
        except Exception as e:  # 실패하면 기존 배지를 그대로 둔다
            print(f"solved.ac 요청 실패: {e}", file=sys.stderr)
            sys.exit(1)
        for name, svg in build(data).items():
            write(os.path.join(OUT_DIR, f"{name}.svg"), svg)
        print(f"{data['handle']}: {TIER_NAMES[data['tier']]} {data['rating']}")

    if args.gallery:
        rows = []
        for tier in range(32):
            lo = TIER_MIN[tier]
            rating = lo + round((TIER_MIN[tier + 1] - lo) * 0.49) if tier < 31 else 3012
            if tier == 0:
                rating = 0
            sample = dict(handle="onlygone", tier=tier, rating=rating, solved=66)
            slug = TIER_NAMES[tier].lower().replace(" ", "-")
            for name, svg in build(sample).items():
                write(os.path.join(BASE_DIR, "gallery", slug, f"{name}.svg"), svg)
            d = dict(sample, t=tier_info(tier, rating))
            rows.append((TIER_NAMES[tier], [render_a1(d, m, False) for m in ("light", "dark")],
                         [render_a3(d, m, False) for m in ("light", "dark")]))
        write(os.path.join(BASE_DIR, "gallery.html"), gallery_html(rows))
        print("gallery 생성 완료")


def gallery_html(rows):
    fonts = font_style().replace("<defs><style>", "").replace("</style></defs>", "")
    body = []
    group = None
    for name, a1, a3 in rows:
        g = name.split()[0]
        if g != group:
            body.append(f'<h2>{g}</h2>')
            group = g
        body.append(f'<section><h3>{name}</h3><div class="row">{"".join(a1)}</div>'
                    f'<div class="row">{"".join(a3)}</div></section>')
    return f'''<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>BOJ 티어 배지 전체 시안</title>
<style>{fonts}
body{{margin:0;padding:32px 24px 64px;font-family:PretendardBadge,sans-serif;background:#EEF1F4;color:#1E2329}}
main{{max-width:760px;margin:0 auto}}
h1{{font-size:26px;font-weight:700;margin:0 0 6px;letter-spacing:-0.4px}}
p.lead{{margin:0 0 28px;color:#5A6470;font-size:15px;line-height:1.7}}
h2{{font-size:20px;font-weight:700;margin:40px 0 4px;padding-top:16px;border-top:1px solid #D5DBE1}}
h3{{font-size:14px;font-weight:500;color:#5A6470;margin:20px 0 10px}}
.row{{display:flex;flex-wrap:wrap;gap:14px;margin-bottom:14px}}
.row svg{{max-width:100%;height:auto}}
</style></head><body><main>
<h1>BOJ 티어 배지</h1>
<p class="lead">메달형(위)과 로마 숫자형(아래)을 32개 티어 전부 라이트, 다크 버전으로 만든 시안이에요. 레이팅은 각 티어 구간의 49% 지점, 맞은 문제는 66개로 넣은 예시 값이에요.</p>
{"".join(body)}
</main></body></html>'''


if __name__ == "__main__":
    main()

"""원본 레퍼런스풍 고품질 쇼츠 프레임 렌더러.

기존 `cartoon.py`보다 더 풍부한 장면 소품/캐릭터/자막 구성을 사용한다.
출력 구조는 레퍼런스 스타일에 맞춘다:
흰 캔버스 + 상단 브랜딩 + 굵은 제목 + 중앙 rounded scene card + 검정 자막 박스.
"""
from __future__ import annotations

import argparse
import math
import sys
from functools import lru_cache
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1080, 1920
S = 2
FONT_PATH = "/System/Library/Fonts/AppleSDGothicNeo.ttc"

# 카드 등 레이아웃 파라미터는 tuning(autotune 최적값)에서 읽는다. 파일 없으면 기본값.
from pipelines.shorts import tuning as _tuning

_TP = _tuning.load()
CARD = _tuning.card(_TP)               # (x0, y0, x1, y1)
CARD_RADIUS = int(_TP["card_radius"])
TITLE_GAP = int(_TP["title_gap"])
TITLE_SIZE = int(_TP["title_size"])
SUB_SIZE = int(_TP["sub_size"])
SUB_BOTTOM = int(_TP["sub_bottom"])
INK = (14, 14, 14)
GRAY = (122, 122, 122)
WHITE = (255, 255, 255)
HL = {"red": (255, 80, 76), "yellow": (255, 217, 83)}

PALETTES = {
    "night": ("#132447", "#415E94"),
    "room": ("#FFE3BA", "#FFF7EB"),
    "street": ("#C8D6E7", "#F6F8FB"),
    "sky": ("#8ED4F5", "#F2FBFF"),
    "office": ("#D8E4F2", "#F9FBFF"),
    "alert": ("#FFC6C6", "#FFF0F0"),
}


@lru_cache(maxsize=96)
def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    if bold:
        for idx in range(20):
            try:
                f = ImageFont.truetype(FONT_PATH, size, index=idx)
            except OSError:
                break
            name = " ".join(f.getname())
            if any(x in name for x in ("Bold", "Heavy", "ExtraBold")):
                return f
    return ImageFont.truetype(FONT_PATH, size)


def _rgb(c) -> tuple[int, int, int]:
    if isinstance(c, str):
        c = c.strip().lstrip("#")
        return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))
    return tuple(c[:3])


def _mix(a, b, t: float) -> tuple[int, int, int]:
    aa, bb = _rgb(a), _rgb(b)
    return tuple(int(aa[i] + (bb[i] - aa[i]) * t) for i in range(3))


def _dark(c, f: float = 0.50) -> tuple[int, int, int]:
    return tuple(max(0, int(v * f)) for v in _rgb(c))


def _light(c, f: float = 0.45) -> tuple[int, int, int]:
    rgb = _rgb(c)
    return tuple(min(255, int(v + (255 - v) * f)) for v in rgb)


def _v_gradient(w: int, h: int, c0, c1) -> Image.Image:
    col = Image.new("RGB", (1, h))
    col.putdata([_mix(c0, c1, y / max(h - 1, 1)) for y in range(h)])
    return col.resize((w, h))


def _wrap(text: str, font: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
    words = text.split()
    if not words:
        return [text]
    lines: list[str] = []
    cur = ""
    for word in words:
        trial = f"{cur} {word}".strip()
        if font.getlength(trial) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def _draw_centered(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str,
                   font: ImageFont.FreeTypeFont, fill, *, stroke: int = 0) -> None:
    x, y = xy
    w = font.getlength(text)
    draw.text((x - w / 2, y), text, font=font, fill=fill,
              stroke_width=stroke, stroke_fill=fill)


def _dog_logo(size: int) -> Image.Image:
    img = Image.new("RGBA", (int(size * 1.42), size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    u = size / 72
    black = (10, 10, 10, 255)
    # 귀/얼굴/주둥이 — 레퍼런스풍 검정 실루엣
    d.ellipse([7*u, 18*u, 26*u, 57*u], fill=black)
    d.ellipse([17*u, 13*u, 58*u, 55*u], fill=black)
    d.ellipse([48*u, 30*u, 70*u, 49*u], fill=black)
    d.ellipse([66*u, 36*u, 76*u, 45*u], fill=black)
    lw = max(2, int(3*u))
    for r in (9, 15, 21):
        d.arc([80*u-r*u, 39*u-r*u, 80*u+r*u, 39*u+r*u], -38, 38, fill=black, width=lw)
    return img


def _draw_header(canvas: Image.Image, brand: str, sub: str) -> None:
    d = ImageDraw.Draw(canvas)
    brand_font = _font(48*S, bold=True)
    sub_font = _font(25*S)
    logo = _dog_logo(66*S)
    gap = 16*S
    total_w = logo.width + gap + max(brand_font.getlength(brand), sub_font.getlength(sub))
    x = int((W*S - total_w) / 2)
    y = 70*S
    canvas.alpha_composite(logo, (x, y + 4*S))
    tx = x + logo.width + gap
    d.text((tx, y), brand, font=brand_font, fill=INK, stroke_width=S, stroke_fill=INK)
    d.text((tx + 2*S, y + 58*S), sub, font=sub_font, fill=GRAY)


def _draw_title(canvas: Image.Image, title: str) -> None:
    d = ImageDraw.Draw(canvas)
    max_w = 940*S
    chosen = _font(TITLE_SIZE*S, bold=True)
    lines = [title]
    line_h = 82*S
    for size in range(TITLE_SIZE, 42, -2):
        f = _font(size*S, bold=True)
        lines = _wrap(title, f, max_w)
        line_h = int(size * 1.22) * S
        if len(lines) <= 2 and len(lines) * line_h <= 132*S:
            chosen = f
            break
    if len(lines) > 2:
        lines = [lines[0], " ".join(lines[1:])]
    title_area_top = (CARD[1] - TITLE_GAP) * S  # 카드 상단 기준으로 위에 배치
    y = title_area_top + max(0, (140*S - len(lines)*line_h) // 2)
    for line in lines:
        _draw_centered(d, (W*S//2, y), line, chosen, INK, stroke=S)
        y += line_h


def _rounded_shadow(canvas: Image.Image, box: tuple[int, int, int, int], radius: int,
                    *, alpha: int = 50, blur: int = 16, offset: tuple[int, int] = (0, 10)) -> None:
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    x0, y0, x1, y1 = box
    ox, oy = offset
    d.rounded_rectangle([x0+ox, y0+oy, x1+ox, y1+oy], radius=radius, fill=(0, 0, 0, alpha))
    layer = layer.filter(ImageFilter.GaussianBlur(blur))
    canvas.alpha_composite(layer)


def _draw_sound_marks(d: ImageDraw.ImageDraw, scale: int, cx: int, cy: int, word: str = "쿵!") -> None:
    f = _font(92*scale, bold=True)
    col = (255, 80, 76)
    d.text((cx - int(f.getlength(word)/2), cy), word, font=f, fill=col,
           stroke_width=4*scale, stroke_fill=WHITE)
    for i, r in enumerate((58, 82, 108)):
        d.arc([cx-r*scale, cy-r*scale//2, cx+r*scale, cy+r*scale], 210, 330,
              fill=WHITE, width=max(3, 4*scale-i))


def _scene_props(scene: dict) -> set[str]:
    """scene.props를 소문자 set으로 정규화한다(기존 JSON은 없어도 동작)."""
    raw = scene.get("props") or []
    if isinstance(raw, str):
        raw = [raw]
    return {str(x).lower() for x in raw}


def _has_visual(scene: dict, subtitle: str, prop: str, *keywords: str) -> bool:
    props = _scene_props(scene)
    return prop in props or any(k and k in subtitle for k in keywords)


def _draw_medicine_bags(d: ImageDraw.ImageDraw, fx, fy, s: int,
                        *, start_x: float = .13, start_y: float = .72, cols: int = 5) -> None:
    """레퍼런스풍 약봉지 흩어짐. 핵심 소품이므로 방/경고 배경에서 재사용한다."""
    for i in range(12):
        x = fx(start_x + (i % cols) * .085)
        y = fy(start_y + (i // cols) * .062)
        w = 48*s
        h = 27*s
        d.rounded_rectangle([x, y, x+w, y+h], radius=6*s,
                            fill=(255, 255, 255), outline=(219, 107, 107), width=2*s)
        d.rectangle([x+7*s, y+9*s, x+34*s, y+13*s], fill=(255, 132, 132))


def _draw_note(d: ImageDraw.ImageDraw, fx, fy, s: int, x: float, y: float, *, label: str = "쪽지") -> None:
    x0, y0 = fx(x), fy(y)
    d.rounded_rectangle([x0, y0, x0+116*s, y0+70*s], radius=7*s,
                        fill=(255, 252, 220), outline=(208, 181, 110), width=2*s)
    f = _font(25*s, bold=True)
    d.text((x0+17*s, y0+19*s), label, font=f, fill=(112, 88, 45))


def _draw_black_bag(d: ImageDraw.ImageDraw, fx, fy, s: int, x: float, y: float) -> None:
    x0, y0 = fx(x), fy(y)
    d.ellipse([x0+16*s, y0-8*s, x0+86*s, y0+28*s], fill=(20, 20, 24))
    d.rounded_rectangle([x0, y0+14*s, x0+106*s, y0+112*s], radius=24*s,
                        fill=(28, 29, 34), outline=(8, 8, 10), width=2*s)
    d.arc([x0+25*s, y0-2*s, x0+82*s, y0+46*s], 190, 350, fill=(74, 74, 82), width=4*s)


def _draw_milk(d: ImageDraw.ImageDraw, fx, fy, s: int, x: float, y: float) -> None:
    x0, y0 = fx(x), fy(y)
    d.polygon([(x0, y0+26*s), (x0+30*s, y0), (x0+64*s, y0+26*s),
               (x0+64*s, y0+106*s), (x0, y0+106*s)],
              fill=(252, 252, 250), outline=(120, 160, 210))
    d.rectangle([x0+10*s, y0+50*s, x0+54*s, y0+72*s], fill=(118, 183, 235))


def _draw_cctv(d: ImageDraw.ImageDraw, fx, fy, s: int, x: float, y: float) -> None:
    x0, y0 = fx(x), fy(y)
    d.rectangle([x0, y0, x0+68*s, y0+20*s], fill=(62, 62, 68))
    d.polygon([(x0+68*s, y0-4*s), (x0+122*s, y0+10*s), (x0+68*s, y0+30*s)], fill=(82, 82, 90))
    d.ellipse([x0+94*s, y0+8*s, x0+104*s, y0+18*s], fill=(255, 72, 72))


def _draw_scene_details(card: Image.Image, scene: dict, subtitle: str) -> None:
    d = ImageDraw.Draw(card)
    cw, ch = card.size
    s = S
    fx = lambda v: int(v * cw)
    fy = lambda v: int(v * ch)
    bg = scene.get("bg", "room")

    if bg == "night":
        # 별/달 + 도시 스카이라인 실루엣. 창문이 떠 보이지 않게 건물 블록 위에만 올린다.
        stars = [(0.12, .10, 3), (.30, .20, 2), (.48, .08, 4), (.66, .15, 2), (.84, .12, 3),
                 (.20, .30, 2), (.58, .26, 3), (.78, .33, 2), (.40, .40, 2), (.90, .42, 3)]
        for x, y, r in stars:
            rr = r*s
            d.ellipse([fx(x)-rr, fy(y)-rr, fx(x)+rr, fy(y)+rr], fill=(255, 255, 238))
        d.ellipse([fx(.78), fy(.07), fx(.88), fy(.17)], fill=(255, 242, 172))
        d.ellipse([fx(.81), fy(.06), fx(.91), fy(.16)], fill=_mix("#132447", "#415E94", .12))
        # 도시 스카이라인: 카드 안쪽(.08~.92)에만, 높이를 달리한 건물 블록 + 창문
        skyline = (28, 40, 70)
        win = (255, 232, 150, 150)
        towers = [(.08, .58), (.20, .50), (.32, .62), (.44, .54),
                  (.58, .56), (.70, .48), (.82, .60)]
        base_y = .82  # 건물 바닥(자막 박스가 그 아래를 덮음)
        for bx, top in towers:
            bw = .10
            x0b, x1b = fx(bx), fx(bx + bw)
            d.rectangle([x0b, fy(top), x1b, fy(base_y)], fill=skyline)
            wy = top + .04
            while wy < base_y - .03:
                for wxi in (bx + .020, bx + .058):
                    d.rectangle([fx(wxi), fy(wy), fx(wxi + .028), fy(wy + .028)], fill=win)
                wy += .065
        if _has_visual(scene, subtitle, "sound_mark", "쿵"):
            _draw_sound_marks(d, s, fx(.50), fy(.15), "쿵!")
            for dx in (-.13, -.08, .08, .13):
                d.line([fx(.50), fy(.245), fx(.50+dx), fy(.305)], fill=(255, 255, 255, 185), width=4*s)

    elif bg == "room":
        # 벽/창/러그/작은 소품. 큰 빈 면을 줄이기 위해 벽 장식/가구/소품을 기본 배치한다.
        d.rectangle([0, fy(.68), cw, ch], fill=(238, 213, 184))
        d.line([0, fy(.68), cw, fy(.68)], fill=(210, 180, 150), width=3*s)
        d.rounded_rectangle([fx(.08), fy(.10), fx(.43), fy(.36)], radius=10*s,
                            fill=(208, 235, 255), outline=WHITE, width=5*s)
        d.line([fx(.255), fy(.10), fx(.255), fy(.36)], fill=WHITE, width=4*s)
        d.line([fx(.08), fy(.23), fx(.43), fy(.23)], fill=WHITE, width=4*s)
        d.rounded_rectangle([fx(.55), fy(.13), fx(.80), fy(.27)], radius=9*s,
                            fill=(255, 252, 238), outline=(211, 183, 155), width=2*s)
        d.ellipse([fx(.82), fy(.38), fx(.91), fy(.48)], fill=(255, 222, 118))
        d.rectangle([fx(.86), fy(.48), fx(.875), fy(.64)], fill=(122, 88, 60))
        d.rectangle([fx(.77), fy(.64), fx(.96), fy(.665)], fill=(122, 88, 60))
        d.ellipse([fx(.53), fy(.76), fx(.92), fy(.91)], fill=(255, 250, 240))
        d.rounded_rectangle([fx(.68), fy(.50), fx(.94), fy(.62)], radius=18*s, fill=(245, 167, 140))
        d.rounded_rectangle([fx(.62), fy(.58), fx(.96), fy(.70)], radius=18*s, fill=(255, 255, 255), outline=(191, 170, 145), width=2*s)
        if _has_visual(scene, subtitle, "medicine_bags", "약", "약봉지"):
            _draw_medicine_bags(d, fx, fy, s)
        if _has_visual(scene, subtitle, "cane", "지팡이"):
            x = fx(.24)
            d.line([x, fy(.50), x+80*s, fy(.80)], fill=(98, 63, 43), width=9*s)
            d.arc([x-28*s, fy(.47), x+35*s, fy(.56)], 160, 360, fill=(98, 63, 43), width=8*s)

    elif bg == "street":
        # 복도/문/초인종
        d.rectangle([0, fy(.68), cw, ch], fill=(210, 214, 222))
        d.polygon([(fx(.15), fy(.68)), (fx(.85), fy(.68)), (cw, ch), (0, ch)], fill=(190, 196, 207))
        d.rounded_rectangle([fx(.60), fy(.18), fx(.90), fy(.72)], radius=8*s, fill=(112, 96, 82), outline=(72, 60, 50), width=5*s)
        d.rectangle([fx(.66), fy(.28), fx(.84), fy(.52)], fill=(178, 205, 224))
        d.ellipse([fx(.84), fy(.48), fx(.87), fy(.51)], fill=(230, 190, 68))
        d.rounded_rectangle([fx(.49), fy(.35), fx(.55), fy(.47)], radius=6*s, fill=(245, 245, 245), outline=(100, 100, 100), width=2*s)
        if _has_visual(scene, subtitle, "cctv", "CCTV"):
            _draw_cctv(d, fx, fy, s, .10, .12)
        if _has_visual(scene, subtitle, "black_bag", "검은 봉투", "봉투"):
            _draw_black_bag(d, fx, fy, s, .57, .63)
        if _has_visual(scene, subtitle, "note", "쪽지", "카드"):
            _draw_note(d, fx, fy, s, .41, .70)
        if _has_visual(scene, subtitle, "milk", "우유"):
            _draw_milk(d, fx, fy, s, .18, .69)

    elif bg == "sky":
        # 구름/햇살
        for cx, cy, r in ((.23, .16, .08), (.70, .26, .06), (.50, .12, .05)):
            rad = int(r*cw)
            x, y = fx(cx), fy(cy)
            for dx, dy, rr in ((-.9, .18, .7), (0, -.12, 1.0), (.9, .18, .7)):
                rs = int(rad*rr)
                d.ellipse([x+int(dx*rad)-rs, y+int(dy*rad)-rs, x+int(dx*rad)+rs, y+int(dy*rad)+rs], fill=WHITE)
        d.ellipse([fx(.76), fy(.08), fx(.89), fy(.20)], fill=(255, 216, 88))

    elif bg == "alert":
        # 반전/위기 컷: 붉은 spotlight와 경고 아이콘으로 감정 피크를 분명히 한다.
        d.ellipse([fx(.06), fy(.08), fx(.94), fy(.86)], fill=(255, 255, 255, 58))
        d.rounded_rectangle([fx(.08), fy(.68), fx(.92), fy(.74)], radius=14*s, fill=(222, 122, 122, 120))
        d.polygon([(fx(.82), fy(.16)), (fx(.90), fy(.32)), (fx(.74), fy(.32))], fill=(255, 91, 86), outline=WHITE)
        f = _font(70*s, bold=True)
        d.text((fx(.808), fy(.193)), "!", font=f, fill=WHITE)
        if _has_visual(scene, subtitle, "cctv", "CCTV"):
            d.rounded_rectangle([fx(.16), fy(.15), fx(.63), fy(.39)], radius=12*s,
                                fill=(36, 42, 56), outline=WHITE, width=3*s)
            d.rectangle([fx(.21), fy(.21), fx(.58), fy(.32)], fill=(150, 176, 205))
            _draw_cctv(d, fx, fy, s, .22, .43)
        if _has_visual(scene, subtitle, "medicine_bags", "약", "약봉지"):
            _draw_medicine_bags(d, fx, fy, s, start_x=.12, start_y=.72, cols=6)
        if _has_visual(scene, subtitle, "note", "쪽지", "카드"):
            _draw_note(d, fx, fy, s, .18, .72, label="안부")
        for x in (.18, .28, .64, .76):
            d.line([fx(.48), fy(.54), fx(x), fy(.66)], fill=(255, 255, 255, 150), width=4*s)

    else:
        # 기본 장식: 은은한 원형 패턴
        for i, (x, y) in enumerate(((.15, .18), (.82, .22), (.25, .74), (.72, .66))):
            r = (70 + i*12) * s
            d.ellipse([fx(x)-r, fy(y)-r, fx(x)+r, fy(y)+r], outline=(255, 255, 255, 90), width=4*s)


def _char_layer(spec: dict) -> Image.Image:
    color = _rgb(spec.get("color", "#73E46C"))
    expr = spec.get("expr") or spec.get("expression") or "smile"
    scale = float(spec.get("scale", 1.0))
    prop = spec.get("prop") or "none"
    if prop == "none":
        prop = None
    accessory = spec.get("accessory") or ""

    h = int(365 * scale * S)
    w = int(h * .64)
    pad = int(h * .18)
    img = Image.new("RGBA", (w + pad*2, h + pad*2), (0, 0, 0, 0))
    mask = Image.new("L", img.size, 0)
    m = ImageDraw.Draw(mask)
    x0, y0 = pad, pad
    X = lambda v: x0 + int(v*w)
    Y = lambda v: y0 + int(v*h)
    head_r = int(h * .28)
    hx, hy = X(.5), Y(.28)

    # jelly/dog-like silhouette
    m.ellipse([hx-head_r, hy-head_r, hx+head_r, hy+head_r], fill=255)
    # 작은 귀 느낌 돌기
    m.ellipse([X(.20), Y(.12), X(.38), Y(.30)], fill=255)
    m.ellipse([X(.62), Y(.12), X(.80), Y(.30)], fill=255)
    m.rounded_rectangle([X(.10), Y(.38), X(.90), Y(.91)], radius=int(w*.34), fill=255)
    m.rounded_rectangle([X(-.04), Y(.52), X(.22), Y(.72)], radius=int(w*.11), fill=255)
    m.rounded_rectangle([X(.78), Y(.52), X(1.04), Y(.72)], radius=int(w*.11), fill=255)
    m.rounded_rectangle([X(.28), Y(.84), X(.45), Y(1.02)], radius=int(w*.08), fill=255)
    m.rounded_rectangle([X(.55), Y(.84), X(.72), Y(1.02)], radius=int(w*.08), fill=255)

    # outline
    outline = mask.filter(ImageFilter.MaxFilter(9))
    img.paste(_dark(color, .42) + (255,), (0, 0), outline)

    # body gradient clipped by mask
    body = Image.new("RGBA", img.size, (0, 0, 0, 0))
    grad = _v_gradient(img.width, img.height, _light(color, .25), color).convert("RGBA")
    body.alpha_composite(grad)
    img.paste(body, (0, 0), mask)

    d = ImageDraw.Draw(img)
    # soft highlight: 넓은 색 얼룩처럼 보이지 않도록 흰 광택을 작고 은은하게 제한한다.
    d.ellipse([X(.25), Y(.19), X(.43), Y(.37)], fill=(255, 255, 255, 58))
    if accessory == "gray_hair":
        # 할머니/노년 캐릭터 식별용 흰머리. 얼굴 위를 덮지 않도록 반투명 캡처럼 얹는다.
        hair = (238, 238, 232, 235)
        d.pieslice([X(.19), Y(.02), X(.81), Y(.39)], 180, 360, fill=hair)
        for bx in (.25, .36, .47, .58, .69):
            d.ellipse([X(bx)-10*S, Y(.145)-8*S, X(bx)+10*S, Y(.145)+8*S], fill=hair)
    # face
    eye = (12, 12, 12)
    er = int(h*.026 if expr != "shock" else h*.034)
    ey = Y(.25)
    for ex in (X(.37), X(.63)):
        d.ellipse([ex-er, ey-er, ex+er, ey+er], fill=eye)
    mcx, mcy = X(.5), Y(.34)
    lw = max(4, 4*S)
    if expr == "shock":
        d.ellipse([mcx-int(w*.075), mcy-int(h*.025), mcx+int(w*.075), mcy+int(h*.055)], fill=eye)
    elif expr == "sad":
        d.arc([mcx-int(w*.17), mcy, mcx+int(w*.17), mcy+int(h*.11)], 200, 340, fill=eye, width=lw)
        d.line([X(.31), Y(.19), X(.42), Y(.22)], fill=eye, width=lw)
        d.line([X(.58), Y(.22), X(.69), Y(.19)], fill=eye, width=lw)
    elif expr == "angry":
        d.arc([mcx-int(w*.16), mcy, mcx+int(w*.16), mcy+int(h*.10)], 200, 340, fill=eye, width=lw)
        d.line([X(.29), Y(.19), X(.43), Y(.225)], fill=eye, width=lw)
        d.line([X(.57), Y(.225), X(.71), Y(.19)], fill=eye, width=lw)
    elif expr == "neutral":
        d.line([mcx-int(w*.11), mcy, mcx+int(w*.11), mcy], fill=eye, width=lw)
    else:
        d.arc([mcx-int(w*.17), mcy-int(h*.06), mcx+int(w*.17), mcy+int(h*.065)], 22, 158, fill=eye, width=lw)

    # blush for friendlier mascot
    blush = (255, 120, 130, 80)
    d.ellipse([X(.19), Y(.31), X(.31), Y(.37)], fill=blush)
    d.ellipse([X(.69), Y(.31), X(.81), Y(.37)], fill=blush)

    if prop == "hat":
        hat = (38, 38, 44)
        d.ellipse([X(.18), Y(.04), X(.82), Y(.13)], fill=hat)
        d.rounded_rectangle([X(.30), Y(-.06), X(.70), Y(.08)], radius=14*S, fill=hat)
        d.rectangle([X(.30), Y(.04), X(.70), Y(.075)], fill=(126, 92, 52))
    elif prop == "bag":
        bag = (122, 84, 60)
        d.rounded_rectangle([X(-.04), Y(.42), X(.21), Y(.76)], radius=18*S, fill=bag, outline=_dark(bag), width=3*S)
        d.line([X(.68), Y(.42), X(.23), Y(.70)], fill=_dark(bag), width=5*S)
    elif prop == "helmet":
        hel = (91, 110, 59)
        d.pieslice([hx-head_r, hy-head_r-int(h*.08), hx+head_r, hy+head_r-int(h*.08)], 180, 360, fill=hel)
        d.rounded_rectangle([hx-head_r, hy-int(h*.08), hx+head_r+int(w*.1), hy+int(h*.01)], radius=8*S, fill=hel)

    if accessory == "cane":
        cane = (94, 58, 38)
        d.line([X(.86), Y(.55), X(1.05), Y(1.06)], fill=cane, width=7*S)
        d.arc([X(.78), Y(.50), X(.95), Y(.62)], 170, 360, fill=cane, width=6*S)
    elif accessory == "tear":
        d.ellipse([X(.69), Y(.31), X(.73), Y(.38)], fill=(122, 203, 255, 210))

    if spec.get("flip"):
        img = img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    return img


def _draw_characters(card: Image.Image, scene: dict) -> None:
    d = ImageDraw.Draw(card)
    cw, ch = card.size
    # Pillow ImageDraw의 RGBA fill은 이후 rounded-card paste에서 알파가 기대대로 섞이지 않을 수 있어
    # 배경별로 이미 블렌딩된 듯한 불투명 그림자색을 사용한다.
    bg = scene.get("bg", "room")
    shadow_color = {
        "night": (35, 49, 76),
        "alert": (205, 134, 134),
        "room": (198, 160, 132),
        "street": (146, 154, 166),
        "sky": (126, 181, 208),
    }.get(bg, (150, 150, 150))
    # 캐릭터 레지스트리 적용(char 참조 → 정체성 고정. 인라인 스펙은 그대로)
    from pipelines.shorts import characters
    specs = characters.resolve_all(scene.get("chars") or scene.get("characters") or [])
    # ground shadow
    for spec in specs:
        cx = int(float(spec.get("x", .5)) * cw)
        scale = float(spec.get("scale", 1.06))
        foot = int(float(spec.get("foot_y", .80)) * ch)
        d.ellipse([cx-int(92*scale*S), foot-int(20*S), cx+int(92*scale*S), foot+int(10*S)], fill=shadow_color)
    for spec in specs:
        layer = _char_layer(spec)
        cx = int(float(spec.get("x", .5)) * cw)
        foot = int(float(spec.get("foot_y", .80)) * ch)
        card.alpha_composite(layer, (cx - layer.width//2, foot - layer.height))


def _highlight_spans(text: str, highlights: dict) -> list[tuple[int, int, tuple[int, int, int]]]:
    """공백 포함 phrase highlight를 지원한다.

    예전 token split 방식은 `한 달째`처럼 공백이 들어간 강조어를 놓쳤다.
    긴 phrase 우선으로 겹침을 막아 원본 자막 레이어에서 색 강조가 안정적으로 보인다.
    """
    if not highlights:
        return []
    occupied = [False] * len(text)
    spans: list[tuple[int, int, tuple[int, int, int]]] = []
    items = sorted(highlights.items(), key=lambda item: len(str(item[0])), reverse=True)
    for raw_key, color_name in items:
        key = str(raw_key)
        if not key:
            continue
        start = 0
        while True:
            i = text.find(key, start)
            if i < 0:
                break
            j = i + len(key)
            if not any(occupied[i:j]):
                for pos in range(i, j):
                    occupied[pos] = True
                spans.append((i, j, HL.get(color_name, WHITE)))
            start = i + 1
    return sorted(spans, key=lambda item: item[0])


def _draw_highlighted_line(d: ImageDraw.ImageDraw, x: float, y: int, line: str,
                           font: ImageFont.FreeTypeFont, highlights: dict) -> None:
    cursor = 0
    for i, j, color in _highlight_spans(line, highlights):
        if cursor < i:
            seg = line[cursor:i]
            d.text((x, y), seg, font=font, fill=WHITE, stroke_width=S, stroke_fill=WHITE)
            x += font.getlength(seg)
        seg = line[i:j]
        d.text((x, y), seg, font=font, fill=color, stroke_width=S, stroke_fill=color)
        x += font.getlength(seg)
        cursor = j
    if cursor < len(line):
        seg = line[cursor:]
        d.text((x, y), seg, font=font, fill=WHITE, stroke_width=S, stroke_fill=WHITE)


def _draw_subtitle(canvas: Image.Image, text: str, highlights: dict) -> None:
    d = ImageDraw.Draw(canvas)
    max_w = 820*S
    font = _font(SUB_SIZE*S, bold=True)
    lines = [text]
    line_h = 74*S
    for size in range(SUB_SIZE, 38, -2):
        f = _font(size*S, bold=True)
        lines = _wrap(text, f, max_w)
        line_h = int(size*1.35)*S
        if len(lines) <= 2:
            font = f
            break
    if len(lines) > 2:
        lines = [lines[0], " ".join(lines[1:])]
    widths = [font.getlength(line) for line in lines]
    pad_x, pad_y = 40*S, 28*S
    box_w = int(max(widths) + pad_x*2)
    box_w = max(min(box_w, (CARD[2]-CARD[0]-40)*S), 560*S)
    box_h = len(lines)*line_h + pad_y*2
    x0 = (W*S - box_w)//2
    y1 = (CARD[3] + SUB_BOTTOM)*S  # 카드 하단 내부 기준(튜닝 오프셋 적용)
    y0 = y1 - box_h
    _rounded_shadow(canvas, (x0, y0, x0+box_w, y1), 30*S, alpha=55, blur=12, offset=(0, 8*S))
    box = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(box).rounded_rectangle([x0, y0, x0+box_w, y1], radius=30*S, fill=(8, 10, 13, 232))
    canvas.alpha_composite(box)

    y = y0 + pad_y
    for line, width in zip(lines, widths):
        x = (W*S - width) / 2
        _draw_highlighted_line(d, x, y, line, font, highlights or {})
        y += line_h


def draw_frame(out_path, *, title: str, brand: str, brand_sub: str,
               scene: dict, subtitle: str, highlights: dict) -> None:
    canvas = Image.new("RGBA", (W*S, H*S), (255, 255, 255, 255))
    _draw_header(canvas, brand or "댕소리", brand_sub or "오늘의 실화 썰")
    _draw_title(canvas, title)

    x0, y0, x1, y1 = [v*S for v in CARD]
    bg = scene.get("bg", "room")
    colors = scene.get("bg_colors") or PALETTES.get(bg, PALETTES["room"])
    card = _v_gradient(x1-x0, y1-y0, colors[0], colors[1]).convert("RGBA")
    _draw_scene_details(card, scene, subtitle)
    _draw_characters(card, scene)

    _rounded_shadow(canvas, (x0, y0, x1, y1), CARD_RADIUS*S, alpha=35, blur=14, offset=(0, 8*S))
    mask = Image.new("L", card.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, card.width-1, card.height-1], radius=CARD_RADIUS*S, fill=255)
    canvas.paste(card, (x0, y0), mask)
    ImageDraw.Draw(canvas).rounded_rectangle([x0, y0, x1-1, y1-1], radius=CARD_RADIUS*S,
                                             outline=(204, 204, 204), width=2*S)
    _draw_subtitle(canvas, subtitle, highlights)

    out = canvas.resize((W, H), Image.Resampling.LANCZOS).convert("RGB")
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.save(out_path, quality=95)


def _demo_scene() -> dict:
    return {
        "bg": "night",
        "characters": [
            {"color": "#75E36C", "x": .50, "scale": 1.08, "expression": "shock", "flip": False, "prop": "none"},
        ],
    }


def main() -> int:
    p = argparse.ArgumentParser(prog="pipelines.shorts.reference_style")
    p.add_argument("out_png")
    args = p.parse_args()
    try:
        draw_frame(args.out_png, title="매일 밤 12시, 윗집의 쿵 소리",
                   brand="댕소리", brand_sub="오늘의 실화 썰",
                   scene=_demo_scene(), subtitle="매일 밤 12시, 천장에서 쿵 소리가 났어.",
                   highlights={"쿵": "red"})
        print(f"[reference_style] saved: {args.out_png}")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"[reference_style] 실패: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

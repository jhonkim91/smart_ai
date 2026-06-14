"""Dang_sound reference-grammar frame renderer.

This renderer intentionally does NOT copy a third-party video frame-for-frame. It
implements the observable production grammar of the supplied reference: white
canvas, left top Dang_sound branding, large Korean hook title, a hard-edged
16:~12 scene plate, 3D-ish blob characters, and a black rounded subtitle box
inside the scene plate.
"""
from __future__ import annotations

import argparse
import math
import random
import sys
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

W, H = 1080, 1920
S = 2
FONT_PATH = "/System/Library/Fonts/AppleSDGothicNeo.ttc"
LATIN_BOLD_PATH = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
INK = (0, 0, 0)
WHITE = (255, 255, 255)
HL = {"red": (255, 30, 18), "yellow": (255, 226, 45)}
SCENE = (18, 537, 1065, 1359)  # measured from reference frames
SCENE_W = SCENE[2] - SCENE[0]
SCENE_H = SCENE[3] - SCENE[1]


@lru_cache(maxsize=128)
def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    if bold:
        for idx in range(24):
            try:
                f = ImageFont.truetype(FONT_PATH, size, index=idx)
            except OSError:
                break
            name = " ".join(f.getname())
            if any(x in name for x in ("Heavy", "ExtraBold", "Bold")):
                return f
    return ImageFont.truetype(FONT_PATH, size)


@lru_cache(maxsize=16)
def _latin_bold(size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(LATIN_BOLD_PATH, size)
    except OSError:
        return _font(size, bold=True)


def _rgb(c) -> tuple[int, int, int]:
    if isinstance(c, str):
        c = c.strip().lstrip("#")
        return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))
    return tuple(c[:3])


def _mix(a, b, t: float) -> tuple[int, int, int]:
    aa, bb = _rgb(a), _rgb(b)
    return tuple(int(aa[i] + (bb[i] - aa[i]) * t) for i in range(3))


def _dark(c, f: float = .42) -> tuple[int, int, int]:
    return tuple(max(0, int(v*f)) for v in _rgb(c))


def _light(c, f: float = .45) -> tuple[int, int, int]:
    rgb = _rgb(c)
    return tuple(min(255, int(v + (255-v)*f)) for v in rgb)


def _v_gradient(w: int, h: int, c0, c1) -> Image.Image:
    col = Image.new("RGB", (1, h))
    col.putdata([_mix(c0, c1, y / max(h-1, 1)) for y in range(h)])
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


def _dog_logo(size: int) -> Image.Image:
    """Reference-like black barking dog silhouette."""
    img = Image.new("RGBA", (int(size*1.55), size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    u = size / 96
    black = (0, 0, 0, 255)
    # smoother dog bust facing right: chest + head + snout + floppy ear
    d.polygon([(7*u, 82*u), (32*u, 48*u), (56*u, 60*u), (62*u, 96*u)], fill=black)
    d.ellipse([25*u, 23*u, 78*u, 68*u], fill=black)
    d.polygon([(63*u, 31*u), (104*u, 23*u), (92*u, 48*u), (65*u, 50*u)], fill=black)
    d.ellipse([18*u, 33*u, 42*u, 75*u], fill=black)
    d.polygon([(29*u, 55*u), (41*u, 72*u), (25*u, 72*u)], fill=black)
    # white inner-ear cut to avoid the previous blocky silhouette
    d.line([31*u, 42*u, 31*u, 64*u], fill=(255, 255, 255, 230), width=max(2, int(3*u)))
    # bark marks
    lw = max(3, int(4*u))
    d.line([112*u, 31*u, 135*u, 20*u], fill=black, width=lw)
    d.line([117*u, 48*u, 145*u, 48*u], fill=black, width=lw)
    d.line([112*u, 64*u, 135*u, 77*u], fill=black, width=lw)
    return img


def _draw_header(canvas: Image.Image, brand: str, sub: str) -> None:
    d = ImageDraw.Draw(canvas)
    logo = _dog_logo(112*S)
    x0, y0 = 80*S, 218*S
    canvas.alpha_composite(logo, (x0, y0))
    f_brand = _latin_bold(60*S)
    f_sub = _font(42*S, bold=True)
    d.text((252*S, 219*S), brand or "Dang_sound", font=f_brand, fill=INK)
    # 레퍼런스처럼 작고 낮은 대비의 회색 서브 브랜드만 표시한다.
    # 강한 offset shadow는 축소/인코딩 시 글자가 두 겹으로 번져 보여 제거한다.
    sub_text = sub or "댕소리"
    d.text((253*S, 288*S), sub_text, font=f_sub, fill=(118, 118, 118))


def _draw_title(canvas: Image.Image, title: str) -> None:
    d = ImageDraw.Draw(canvas)
    max_w = 1000*S
    for size in range(59, 42, -2):
        f = _font(size*S, bold=True)
        lines = _wrap(title, f, max_w)
        if len(lines) <= 1:
            break
    else:
        f = _font(43*S, bold=True)
        lines = _wrap(title, f, max_w)[:2]
    y = 421*S if len(lines) == 1 else 394*S
    line_h = int(size*1.18)*S
    for line in lines:
        w = f.getlength(line)
        d.text(((W*S-w)/2, y), line, font=f, fill=INK, stroke_width=S, stroke_fill=INK)
        y += line_h


def _add_noise_and_vignette(img: Image.Image, seed: int, strength: int = 12, vignette: int = 70) -> Image.Image:
    rng = random.Random(seed)
    px = img.load()
    w, h = img.size
    for _ in range(1600):
        x = rng.randrange(w)
        y = rng.randrange(h)
        r = rng.randrange(1, 5)
        delta = rng.randrange(-strength, strength+1)
        col = tuple(max(0, min(255, px[x, y][i] + delta)) for i in range(3))
        ImageDraw.Draw(img).ellipse([x-r, y-r, x+r, y+r], fill=col)
    # The source plate is a hard rectangular video/image crop, not a rounded card or framed panel.
    # Keep only light grain; avoid drawing an artificial inner border.
    return img.convert("RGB")


def _draw_background(scene: dict) -> Image.Image:
    bg = scene.get("bg", "cabin")
    card = Image.new("RGB", (SCENE_W*S, SCENE_H*S), (220, 220, 220))
    d = ImageDraw.Draw(card)
    cw, ch = card.size
    fx = lambda v: int(v*cw)
    fy = lambda v: int(v*ch)
    if bg in ("cabin", "dark_room"):
        card = _v_gradient(cw, ch, "#1b2324", "#39342a")
        d = ImageDraw.Draw(card)
        # plane/cabin windows and seats
        for x in (.10, .22, .68, .86):
            d.rounded_rectangle([fx(x), fy(.15), fx(x+.12), fy(.30)], radius=10*S,
                                fill=(92, 132, 145), outline=(36, 48, 51), width=3*S)
        for x in (.04, .70):
            d.rounded_rectangle([fx(x), fy(.55), fx(x+.26), fy(.95)], radius=26*S,
                                fill=(64, 54, 43), outline=(26, 24, 20), width=5*S)
        d.rectangle([fx(.48), 0, fx(.52), ch], fill=(70, 70, 65))
    elif bg == "skyfall":
        card = _v_gradient(cw, ch, "#8edce7", "#d4e8db")
        d = ImageDraw.Draw(card)
        # blurred clouds and speed lines
        for box in [(-.08, .05, .28, .28), (.64, .70, 1.08, .96), (.70, .10, 1.05, .27)]:
            d.ellipse([fx(box[0]), fy(box[1]), fx(box[2]), fy(box[3])], fill=(236, 230, 205))
        for x in (.12, .34, .72, .92):
            d.line([fx(x), fy(.04), fx(x-.02), fy(.42)], fill=(255, 255, 255), width=3*S)
    elif bg == "field":
        card = _v_gradient(cw, ch, "#8d9992", "#394229")
        d = ImageDraw.Draw(card)
        d.polygon([(0, fy(.60)), (fx(.42), fy(.45)), (cw, fy(.58)), (cw, ch), (0, ch)], fill=(80, 92, 56))
        d.rectangle([0, fy(.12), fx(.35), ch], fill=(72, 44, 31))
        for x in (.03, .12, .22, .32):
            d.line([fx(x), fy(.12), fx(x), ch], fill=(102, 70, 50), width=4*S)
        d.polygon([(fx(.00), fy(.12)), (fx(.38), fy(.12)), (fx(.42), fy(.23)), (0, fy(.23))], fill=(45, 35, 30))
        # bushes
        for x in (.45, .57, .68, .80):
            d.ellipse([fx(x), fy(.46), fx(x+.17), fy(.68)], fill=(54, 73, 43))
    elif bg == "hall":
        card = _v_gradient(cw, ch, "#c9d6e5", "#adb5c1")
        d = ImageDraw.Draw(card)
        d.rectangle([0, fy(.74), cw, ch], fill=(179, 185, 196))
        d.polygon([(0, ch), (fx(.18), fy(.74)), (fx(.82), fy(.74)), (cw, ch)], fill=(166, 173, 188))
        d.rounded_rectangle([fx(.59), fy(.22), fx(.88), fy(.78)], radius=8*S, fill=(112, 96, 82), outline=(57, 48, 42), width=5*S)
        d.rectangle([fx(.65), fy(.36), fx(.82), fy(.58)], fill=(170, 200, 220))
        d.ellipse([fx(.83), fy(.52), fx(.86), fy(.56)], fill=(230, 190, 68))
        d.rounded_rectangle([fx(.49), fy(.48), fx(.55), fy(.64)], radius=6*S, fill=(245,245,245), outline=(100,100,100), width=2*S)
    else:
        card = _v_gradient(cw, ch, "#ced8e3", "#f0f0ed")
    return _add_noise_and_vignette(card.convert("RGB"), hash(bg) & 0xffff, strength=8, vignette=46)


def _camo_color(i: int) -> tuple[int, int, int]:
    return [(87, 85, 45), (121, 112, 63), (62, 74, 43), (148, 132, 74)][i % 4]


def _draw_hat(d: ImageDraw.ImageDraw, X, Y, w: int, h: int, *, kind: str = "bucket") -> None:
    # Large camo bucket/cap hat like the reference. It deliberately overlaps eyes.
    base = (96, 91, 48)
    d.ellipse([X(.10), Y(.00), X(.96), Y(.21)], fill=base, outline=_dark(base), width=4*S)
    d.rounded_rectangle([X(.22), Y(-.10), X(.82), Y(.15)], radius=24*S, fill=base, outline=_dark(base), width=4*S)
    for i, (x, y, r) in enumerate([(.24, .01, .07), (.44, -.03, .08), (.64, .02, .06), (.72, .10, .05)]):
        d.ellipse([X(x-r), Y(y-r), X(x+r), Y(y+r)], fill=_camo_color(i))
    # small parachute insignia
    gold = (197, 164, 76)
    cx, cy = X(.62), Y(.07)
    d.ellipse([cx-24*S, cy-11*S, cx+24*S, cy+18*S], outline=gold, width=3*S)
    for dx in (-14, -7, 0, 7, 14):
        d.line([cx+dx*S, cy-4*S, cx, cy+21*S], fill=gold, width=2*S)


def _character(spec: dict) -> Image.Image:
    """SoftBean 2.5D 캐릭터.

    기존 네모 블롭/큰 모자 캐릭터를 버리고, 쇼츠용 고정 IP로 쓸 수 있게
    큰 둥근 머리 + 작은 젤리 몸통 + 긴 누들 팔다리 + 볼터치/광택을 가진
    새 실루엣으로 그린다. 외부 원본 캐릭터를 복제하지 않는 오리지널 형태다.
    """
    color = _rgb(spec.get("color", "#8ee9ff"))
    # 기존 story.json의 scale 값은 예전 대형 블롭 기준이라, SoftBean은 살짝 작게 보정한다.
    scale = float(spec.get("scale", 1.0)) * 0.84
    expr = spec.get("expr") or spec.get("expression") or "smile"
    prop = spec.get("hat") or spec.get("prop") or "none"
    pose = spec.get("pose") or ("spread" if expr == "shock" else "stand")

    body_h = int(430 * scale * S)
    body_w = int(body_h * 0.58)
    pad = int(105 * scale * S)
    iw, ih = body_w + pad * 2, body_h + pad * 2
    img = Image.new("RGBA", (iw, ih), (0, 0, 0, 0))

    cx = iw // 2
    foot = ih - int(30 * scale * S)
    head_r = int(body_w * 0.45)
    head_cy = foot - int(body_h * 0.69)
    torso_top = head_cy + int(head_r * 0.43)
    # 몸통은 발끝까지 내려오지 않게 짧게 둔다. 그래야 다리/발이 실제로 보인다.
    torso_bottom = foot - int(body_h * 0.18)
    torso_w = int(body_w * 0.70)
    limb_w = max(12 * S, int(body_w * 0.14))
    cap = limb_w // 2

    sh_y = torso_top + int(body_h * 0.19)
    hip_y = torso_bottom - int(body_h * 0.02)
    shoulder_x = int(torso_w * 0.55)
    hip_x = int(torso_w * 0.28)
    arm_len = int(body_h * 0.40)
    leg_len = int(body_h * 0.20)

    if pose == "spread":
        limbs = [
            (cx - shoulder_x, sh_y, cx - shoulder_x - int(arm_len * 0.78), sh_y - int(arm_len * 0.48)),
            (cx + shoulder_x, sh_y, cx + shoulder_x + int(arm_len * 0.78), sh_y - int(arm_len * 0.48)),
            (cx - hip_x, hip_y, cx - hip_x - int(leg_len * 0.72), hip_y + int(leg_len * 0.82)),
            (cx + hip_x, hip_y, cx + hip_x + int(leg_len * 0.72), hip_y + int(leg_len * 0.82)),
        ]
    elif pose == "point":
        limbs = [
            (cx - shoulder_x, sh_y, cx - shoulder_x - int(arm_len * 0.24), sh_y + int(arm_len * 0.68)),
            (cx + shoulder_x, sh_y, cx + shoulder_x + int(arm_len * 0.95), sh_y - int(arm_len * 0.20)),
            (cx - hip_x, hip_y, cx - hip_x - int(leg_len * 0.18), hip_y + leg_len),
            (cx + hip_x, hip_y, cx + hip_x + int(leg_len * 0.18), hip_y + leg_len),
        ]
    else:
        limbs = [
            (cx - shoulder_x, sh_y, cx - shoulder_x - int(arm_len * 0.22), sh_y + int(arm_len * 0.76)),
            (cx + shoulder_x, sh_y, cx + shoulder_x + int(arm_len * 0.22), sh_y + int(arm_len * 0.76)),
            (cx - hip_x, hip_y, cx - hip_x - int(leg_len * 0.08), hip_y + leg_len),
            (cx + hip_x, hip_y, cx + hip_x + int(leg_len * 0.08), hip_y + leg_len),
        ]

    mask = Image.new("L", (iw, ih), 0)
    md = ImageDraw.Draw(mask)

    def capsule(line: tuple[int, int, int, int], width: int) -> None:
        x0, y0, x1, y1 = line
        md.line([(x0, y0), (x1, y1)], fill=255, width=width)
        for x, y in ((x0, y0), (x1, y1)):
            md.ellipse([x - cap, y - cap, x + cap, y + cap], fill=255)

    # 팔다리 → 몸통 → 머리를 하나의 말랑한 실루엣으로 합친다.
    for limb in limbs:
        capsule(limb, limb_w)
    md.ellipse([cx - torso_w // 2, torso_top, cx + torso_w // 2, torso_bottom], fill=255)
    md.ellipse([cx - head_r, head_cy - head_r, cx + head_r, head_cy + head_r], fill=255)

    # 부드러운 바닥 그림자와 두꺼운 어두운 외곽선.
    shadow = Image.new("RGBA", (iw, ih), (0, 0, 0, 0))
    shadow_alpha = mask.filter(ImageFilter.GaussianBlur(10 * S)).point(lambda a: int(a * 0.20))
    shadow.putalpha(shadow_alpha)
    img.alpha_composite(shadow, (int(5 * S), int(8 * S)))

    outline = Image.new("RGBA", (iw, ih), _dark(color, 0.15) + (255,))
    outline_mask = mask.filter(ImageFilter.MaxFilter(9))
    img.alpha_composite(Image.composite(outline, Image.new("RGBA", (iw, ih), (0, 0, 0, 0)), outline_mask))

    # radial shading: 좌상단 광원 → 우하단 어둡게. 젤리/클레이 같은 2.5D 질감.
    yy, xx = np.mgrid[0:ih, 0:iw].astype(np.float32)
    lx, ly = cx - head_r * 0.42, head_cy - head_r * 0.52
    dist = np.sqrt((xx - lx) ** 2 + (yy - ly) ** 2) / max(body_h * 0.80, 1)
    t = np.clip(dist, 0, 1)
    t = t * t * (3 - 2 * t)
    light = np.array(_light(color, 0.48), dtype=np.float32)
    dark = np.array(_mix(color, (38, 42, 52), 0.34), dtype=np.float32)
    arr = (light[None, None, :] * (1 - t[..., None]) + dark[None, None, :] * t[..., None]).clip(0, 255).astype(np.uint8)
    shaded = Image.fromarray(arr, "RGB").convert("RGBA")
    img.alpha_composite(Image.composite(shaded, Image.new("RGBA", (iw, ih), (0, 0, 0, 0)), mask))

    d = ImageDraw.Draw(img, "RGBA")
    # 젤리 하이라이트: 큰 머리의 좌상단 광택.
    gloss = Image.new("L", (iw, ih), 0)
    gd = ImageDraw.Draw(gloss)
    gd.ellipse([cx - int(head_r * 0.68), head_cy - int(head_r * 0.78),
                cx + int(head_r * 0.18), head_cy - int(head_r * 0.02)], fill=115)
    gloss = ImageChops.multiply(gloss.filter(ImageFilter.GaussianBlur(int(head_r * 0.10))), mask)
    sheen = Image.new("RGBA", (iw, ih), (255, 255, 255, 0))
    sheen.putalpha(gloss)
    img.alpha_composite(sheen)

    eye = (14, 14, 18, 255)
    ex = int(head_r * 0.36)
    ey = head_cy - int(head_r * 0.05)
    ew, eh = int(head_r * 0.105), int(head_r * 0.205)
    if expr == "shock":
        ew, eh = int(ew * 1.14), int(eh * 1.12)
    for sx in (-1, 1):
        x = cx + sx * ex
        d.ellipse([x - ew, ey - eh, x + ew, ey + eh], fill=eye)
        d.ellipse([x - ew // 4, ey - eh // 2, x + ew // 12, ey - eh // 5], fill=(255, 255, 255, 58))

    # 볼터치.
    blush_r = int(head_r * 0.14)
    for sx in (-1, 1):
        bx = cx + sx * int(head_r * 0.62)
        by = ey + int(head_r * 0.27)
        d.ellipse([bx - blush_r, by - blush_r, bx + blush_r, by + blush_r], fill=(255, 125, 150, 68))

    mx, my = cx, head_cy + int(head_r * 0.34)
    mw = int(head_r * 0.27)
    stroke = max(4, int(4 * S * scale))
    if expr == "sad":
        d.arc([mx - mw, my + int(head_r * 0.05), mx + mw, my + int(head_r * 0.34)],
              200, 340, fill=eye, width=stroke)
    elif expr == "shock":
        d.ellipse([mx - int(head_r * 0.15), my - int(head_r * 0.09),
                   mx + int(head_r * 0.15), my + int(head_r * 0.23)], fill=eye)
    elif expr == "angry":
        d.arc([mx - mw, my + int(head_r * 0.05), mx + mw, my + int(head_r * 0.34)],
              200, 340, fill=eye, width=stroke)
        d.line([cx - ex - ew, ey - eh - stroke, cx - ex + ew, ey - eh // 2], fill=eye, width=stroke)
        d.line([cx + ex - ew, ey - eh // 2, cx + ex + ew, ey - eh - stroke], fill=eye, width=stroke)
    elif expr == "neutral":
        d.line([mx - mw // 2, my, mx + mw // 2, my], fill=eye, width=stroke)
    else:
        d.chord([mx - mw, my - int(head_r * 0.18), mx + mw, my + int(head_r * 0.22)],
                18, 162, fill=eye)

    # 소품은 얼굴을 가리지 않는 크기의 identity accent로만 사용한다.
    if prop and prop != "none":
        olive = (94, 104, 59, 255)
        dark_olive = (54, 62, 38, 255)
        badge = (226, 205, 118, 255)
        if prop in ("helmet", "beret"):
            band_y = head_cy - int(head_r * 0.58)
            d.arc([cx - int(head_r * 0.78), band_y - int(head_r * 0.22),
                   cx + int(head_r * 0.78), band_y + int(head_r * 0.25)], 188, 352,
                  fill=dark_olive, width=max(4, int(3 * S)))
            bx, by = cx + int(head_r * 0.10), head_cy - int(head_r * 0.75)
            bw, bh = int(head_r * 0.88), int(head_r * 0.30)
            d.ellipse([bx - bw, by - bh, bx + bw, by + bh], fill=olive, outline=dark_olive, width=max(3, S * 2))
            d.ellipse([bx + int(bw * 0.30), by - int(bh * 0.08),
                       bx + int(bw * 0.98), by + int(bh * 0.68)], fill=olive)
            bdx = cx - int(head_r * 0.32)
            d.arc([bdx - int(head_r * 0.14), band_y - int(head_r * 0.15),
                   bdx + int(head_r * 0.14), band_y + int(head_r * 0.08)], 190, 350,
                  fill=badge, width=max(2, S * 2))
            for dx in (-8, 0, 8):
                d.line([bdx + dx * S, band_y - int(head_r * 0.05), bdx, band_y + int(head_r * 0.11)],
                       fill=badge, width=max(1, S))
        elif prop == "hat":
            brown = (159, 105, 42, 255)
            dark = (92, 58, 28, 255)
            d.ellipse([cx - int(head_r * 0.98), head_cy - int(head_r * 0.70),
                       cx + int(head_r * 0.98), head_cy - int(head_r * 0.42)], fill=brown, outline=dark, width=max(3, S * 2))
            d.rounded_rectangle([cx - int(head_r * 0.46), head_cy - int(head_r * 0.98),
                                 cx + int(head_r * 0.46), head_cy - int(head_r * 0.50)],
                                radius=int(head_r * 0.17), fill=brown, outline=dark, width=max(3, S * 2))

    if spec.get("flip"):
        img = img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    return img


def _draw_props(scene_img: Image.Image, scene: dict) -> None:
    d = ImageDraw.Draw(scene_img)
    cw, ch = scene_img.size
    fx = lambda v: int(v*cw)
    fy = lambda v: int(v*ch)
    props = scene.get("props") or []
    if isinstance(props, str):
        props = [props]
    props = set(props)
    if "parachute_pack" in props or "bag" in props:
        d.rounded_rectangle([fx(.58), fy(.67), fx(.72), fy(.88)], radius=18*S, fill=(32, 34, 40), outline=(5,5,5), width=4*S)
        d.arc([fx(.60), fy(.62), fx(.70), fy(.73)], 180, 360, fill=(92,92,98), width=5*S)
    if "red_pack" in props:
        d.rounded_rectangle([fx(.18), fy(.70), fx(.32), fy(.92)], radius=18*S, fill=(220, 62, 42), outline=(80,20,10), width=4*S)
        for x in (.20, .27):
            d.line([fx(x), fy(.72), fx(x+.06), fy(.90)], fill=(245, 190, 55), width=4*S)
    if "number_30" in props:
        f = _font(58*S, bold=True)
        d.text((fx(.42), fy(.45)), "30", font=f, fill=(255, 0, 0), stroke_width=3*S, stroke_fill=WHITE)
    if "black_bag" in props:
        d.rounded_rectangle([fx(.58), fy(.66), fx(.68), fy(.82)], radius=16*S, fill=(24, 25, 29), outline=(5, 5, 7), width=4*S)
        d.arc([fx(.59), fy(.61), fx(.67), fy(.71)], 190, 350, fill=(82,82,88), width=5*S)
    if "note" in props:
        d.rounded_rectangle([fx(.45), fy(.72), fx(.56), fy(.80)], radius=6*S, fill=(255, 252, 218), outline=(206,180,100), width=3*S)
        d.text((fx(.47), fy(.742)), "쪽지", font=_font(24*S, bold=True), fill=(120,90,40))
    if "cctv" in props:
        d.rounded_rectangle([fx(.18), fy(.12), fx(.60), fy(.36)], radius=12*S,
                            fill=(24, 30, 40), outline=(5,5,8), width=4*S)
        d.rectangle([fx(.23), fy(.18), fx(.55), fy(.29)], fill=(122, 154, 181))
        d.rectangle([fx(.26), fy(.44), fx(.36), fy(.465)], fill=(42, 42, 48))
        d.polygon([(fx(.36), fy(.425)), (fx(.44), fy(.455)), (fx(.36), fy(.49))], fill=(62, 62, 70))
        d.ellipse([fx(.405), fy(.452), fx(.416), fy(.466)], fill=(255, 65, 65))


def _draw_scene(canvas: Image.Image, scene: dict) -> None:
    x0, y0, x1, y1 = [v*S for v in SCENE]
    plate = _draw_background(scene).convert("RGBA")
    _draw_props(plate, scene)
    for spec in scene.get("characters") or scene.get("chars") or []:
        layer = _character(spec)
        cx = int(float(spec.get("x", .5))*plate.width)
        cy = int(float(spec.get("y", .82))*plate.height)
        # SoftBean은 하단 자막 박스에 몸이 묻히기 쉬워 기본 배치를 약간 위로 올린다.
        cy -= int(float(spec.get("raise_y", 0.055)) * plate.height)
        plate.alpha_composite(layer, (cx-layer.width//2, cy-layer.height))
    # hard rectangular edge, no rounded corners
    canvas.paste(plate.convert("RGB"), (x0, y0))


def _highlight_spans(text: str, highlights: dict) -> list[tuple[int, int, tuple[int, int, int]]]:
    if not highlights:
        return []
    occupied = [False] * len(text)
    spans = []
    for raw_key, color_name in sorted(highlights.items(), key=lambda kv: len(str(kv[0])), reverse=True):
        key = str(raw_key)
        start = 0
        while key:
            i = text.find(key, start)
            if i < 0:
                break
            j = i + len(key)
            if not any(occupied[i:j]):
                for k in range(i, j):
                    occupied[k] = True
                spans.append((i, j, HL.get(color_name, WHITE)))
            start = i + 1
    return sorted(spans, key=lambda x: x[0])


def _draw_highlighted_line(d: ImageDraw.ImageDraw, x: float, y: int, line: str,
                           font: ImageFont.FreeTypeFont, highlights: dict) -> None:
    cur = 0
    for i, j, col in _highlight_spans(line, highlights):
        if cur < i:
            seg = line[cur:i]
            d.text((x, y), seg, font=font, fill=WHITE, stroke_width=S, stroke_fill=WHITE)
            x += font.getlength(seg)
        seg = line[i:j]
        d.text((x, y), seg, font=font, fill=col, stroke_width=S, stroke_fill=col)
        x += font.getlength(seg)
        cur = j
    if cur < len(line):
        seg = line[cur:]
        d.text((x, y), seg, font=font, fill=WHITE, stroke_width=S, stroke_fill=WHITE)


def _draw_subtitle(canvas: Image.Image, text: str, highlights: dict) -> None:
    d = ImageDraw.Draw(canvas)
    max_w = 720*S
    font = _font(54*S, bold=True)
    lines = [text]
    line_h = 72*S
    for size in range(55, 38, -2):
        f = _font(size*S, bold=True)
        lines = _wrap(text, f, max_w)
        line_h = int(size*1.28)*S
        if len(lines) <= 2:
            font = f
            break
    if len(lines) > 2:
        lines = [lines[0], " ".join(lines[1:])]
    widths = [font.getlength(line) for line in lines]
    pad_x, pad_y = 32*S, 23*S
    box_w = max(620*S, min(760*S, int(max(widths)+pad_x*2)))
    box_h = len(lines)*line_h + pad_y*2
    x0 = (W*S - box_w)//2
    # In reference, the subtitle sits inside the scene, close to its bottom.
    y1 = (SCENE[3] - 25) * S
    y0 = y1 - box_h
    ImageDraw.Draw(canvas).rounded_rectangle([x0, y0, x0+box_w, y1], radius=24*S, fill=(0,0,0))
    y = y0 + pad_y
    for line, width in zip(lines, widths):
        x = (W*S - width)/2
        _draw_highlighted_line(d, x, y, line, font, highlights or {})
        y += line_h


def draw_frame(out_path, *, title: str, brand: str, brand_sub: str,
               scene: dict, subtitle: str, highlights: dict) -> None:
    canvas = Image.new("RGB", (W*S, H*S), WHITE).convert("RGBA")
    _draw_header(canvas, brand or "Dang_sound", brand_sub or "댕소리")
    _draw_title(canvas, title)
    _draw_scene(canvas, scene)
    _draw_subtitle(canvas, subtitle, highlights)
    out = canvas.resize((W, H), Image.Resampling.LANCZOS).convert("RGB")
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.save(out_path, quality=95)


def _demo_scene() -> dict:
    return {"bg": "cabin", "props": ["red_pack"], "characters": [
        {"color": "#9ef6ff", "x": .48, "y": .92, "scale": 1.35, "expr": "smile", "hat": "helmet"},
    ]}


def main() -> int:
    p = argparse.ArgumentParser(prog="pipelines.shorts.dang_reference")
    p.add_argument("out_png")
    args = p.parse_args()
    try:
        draw_frame(args.out_png,
                   title="낙하산 2개가 모두 안 펴질 확률 100%",
                   brand="Dang_sound", brand_sub="댕소리",
                   scene=_demo_scene(),
                   subtitle="아내가 스카이다이빙 하기 전 남편이 낙하산을 손상시킴",
                   highlights={"아내": "red", "남편": "yellow"})
        print(f"[dang_reference] saved: {args.out_png}")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"[dang_reference] 실패: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

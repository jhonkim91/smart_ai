"""만화 스타일 프레임 렌더러: 댕소리식 썰 쇼츠 1080x1920 프레임 합성.

이 환경의 ffmpeg에는 drawtext/subtitles 필터가 없으므로 텍스트·도형을
전부 Pillow로 그려 완성 프레임 PNG를 만든다(render.py 그라디언트 스타일과 별개).

구성: 흰 배경 + 상단 브랜딩(강아지 로고 + 브랜드명/부제) + 굵은 검정 제목
+ 라운드 장면 카드(2색 세로 그라디언트, 배경 소품, 젤리 캐릭터)
+ 카드 하단에 겹치는 자막 박스(단어 토큰 단위 색 강조).

도형 안티앨리어싱을 위해 내부적으로 2배 슈퍼샘플링 후 축소한다.

사용:
    python -m pipelines.shorts.cartoon /tmp/demo.png [--bg sky]
"""
import argparse
import sys
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1080, 1920
S = 2  # 슈퍼샘플링 배율(최종 1/S 축소로 도형 가장자리 부드럽게)
FONT_PATH = "/System/Library/Fonts/AppleSDGothicNeo.ttc"  # macOS 기본 한글 폰트

# 장면 카드 영역(1x 좌표)
CARD_X0, CARD_Y0, CARD_X1, CARD_Y1 = 80, 320, 1000, 1560
CARD_W, CARD_H = CARD_X1 - CARD_X0, CARD_Y1 - CARD_Y0
CARD_RADIUS = 48

BASE_CHAR_H = 340  # scale=1.0 기준 캐릭터 높이(px) — 레퍼런스처럼 자막 위에 크게 보이도록 보정

INK = (17, 17, 17)
GRAY = (130, 130, 130)
HL_COLORS = {"red": (255, 82, 82), "yellow": (255, 213, 79)}

# bg별 (위, 아래) 그라디언트 팔레트
PALETTES = {
    "sky": ("#7EC8F2", "#E8F7FF"),
    "room": ("#FFE3B8", "#FFF7EA"),
    "office": ("#C9D8EE", "#F1F5FB"),
    "street": ("#BFE3F0", "#F2FAFD"),
    "forest": ("#A8DCA0", "#EAF7E4"),
    "night": ("#16264E", "#41598F"),
    "abstract": ("#D9C8F2", "#FCF1FF"),
}


# ---------------------------------------------------------------- 공용 유틸
def _rgb(c) -> tuple:
    """'#RRGGBB' 또는 튜플을 RGB 튜플로."""
    if isinstance(c, str):
        c = c.lstrip("#")
        return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))
    return tuple(c)


def _dark(rgb: tuple, f: float = 0.45) -> tuple:
    """외곽선용 진한 동색."""
    return tuple(int(v * f) for v in rgb)


@lru_cache(maxsize=64)
def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """AppleSDGothicNeo.ttc 로드. bold면 컬렉션 안의 굵은 face를 탐색."""
    if bold:
        for idx in range(16):
            try:
                f = ImageFont.truetype(FONT_PATH, size, index=idx)
            except OSError:
                break
            name = " ".join(f.getname())
            if "Bold" in name or "Heavy" in name:
                return f
    return ImageFont.truetype(FONT_PATH, size)


def _wrap(text: str, font: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
    """픽셀 폭 기준 단어 줄바꿈."""
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if font.getlength(trial) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _v_gradient(w: int, h: int, c0, c1) -> Image.Image:
    """세로 2색 그라디언트 이미지."""
    a, b = _rgb(c0), _rgb(c1)
    col = Image.new("RGB", (1, h))
    col.putdata([
        tuple(int(a[k] + (b[k] - a[k]) * y / max(h - 1, 1)) for k in range(3))
        for y in range(h)
    ])
    return col.resize((w, h))


# ---------------------------------------------------------------- 배경 소품
def _draw_props(card: Image.Image, bg: str) -> None:
    """장면 카드 위에 bg별 단순 소품을 그린다(카드 크기 비율 좌표)."""
    d = ImageDraw.Draw(card)
    cw, ch = card.size
    fx = lambda v: int(v * cw)  # noqa: E731
    fy = lambda v: int(v * ch)  # noqa: E731
    lw = max(2, S)

    if bg == "sky":  # 구름 2개
        white = (255, 255, 255)
        for cx, cy, r in ((0.27, 0.17, 0.085), (0.72, 0.30, 0.062)):
            rad = int(r * cw)
            x, y = fx(cx), fy(cy)
            for dx, dy, rr in ((-0.95, 0.20, 0.72), (0.0, -0.18, 1.0), (0.95, 0.22, 0.68)):
                rs = int(rad * rr)
                d.ellipse([x + int(dx * rad) - rs, y + int(dy * rad) - rs,
                           x + int(dx * rad) + rs, y + int(dy * rad) + rs], fill=white)

    elif bg == "room":  # 창문 + 침대
        d.rounded_rectangle([fx(0.10), fy(0.10), fx(0.42), fy(0.38)],
                            radius=6 * S, fill=(202, 233, 255),
                            outline=(255, 255, 255), width=5 * S)
        d.line([fx(0.26), fy(0.10), fx(0.26), fy(0.38)], fill=(255, 255, 255), width=4 * S)
        d.line([fx(0.10), fy(0.24), fx(0.42), fy(0.24)], fill=(255, 255, 255), width=4 * S)
        d.rounded_rectangle([fx(0.55), fy(0.66), fx(0.96), fy(0.79)],
                            radius=5 * S, fill=(255, 255, 255),
                            outline=(196, 176, 150), width=lw)  # 매트리스
        d.rounded_rectangle([fx(0.66), fy(0.64), fx(0.96), fy(0.74)],
                            radius=5 * S, fill=(255, 196, 150))  # 이불
        d.rounded_rectangle([fx(0.57), fy(0.62), fx(0.66), fy(0.685)],
                            radius=4 * S, fill=(255, 255, 255),
                            outline=(196, 176, 150), width=lw)  # 베개
        for bx in (0.575, 0.93):  # 다리
            d.rectangle([fx(bx), fy(0.79), fx(bx + 0.018), fy(0.825)], fill=(150, 120, 92))

    elif bg == "office":  # 책상 실루엣 + 모니터
        col = (62, 74, 96)
        d.rectangle([fx(0.50), fy(0.595), fx(0.95), fy(0.622)], fill=col)  # 상판
        d.rectangle([fx(0.525), fy(0.622), fx(0.55), fy(0.79)], fill=col)
        d.rectangle([fx(0.90), fy(0.622), fx(0.925), fy(0.79)], fill=col)
        d.rounded_rectangle([fx(0.60), fy(0.44), fx(0.83), fy(0.565)],
                            radius=4 * S, fill=col)  # 모니터
        d.rectangle([fx(0.70), fy(0.565), fx(0.725), fy(0.595)], fill=col)

    elif bg == "street":  # 건물 사각형들
        tones = ((176, 190, 204), (143, 160, 178), (196, 206, 216))
        specs = ((0.04, 0.32, 0.28), (0.30, 0.20, 0.26), (0.60, 0.40, 0.34))  # x0, 꼭대기y, 폭
        for (x0, yt, bw), tone in zip(specs, tones):
            d.rectangle([fx(x0), fy(yt), fx(x0 + bw), fy(0.80)], fill=tone)
            win = (236, 243, 249)
            wy = yt + 0.05
            while wy < 0.72:
                wx = x0 + 0.04
                while wx < x0 + bw - 0.07:
                    d.rectangle([fx(wx), fy(wy), fx(wx + 0.045), fy(wy + 0.035)], fill=win)
                    wx += 0.09
                wy += 0.08
        d.rectangle([0, fy(0.80), cw, fy(0.815)], fill=(120, 130, 140))  # 지면선

    elif bg == "forest":  # 삼각 나무들
        greens = ((46, 125, 50), (56, 142, 60), (27, 94, 32))
        trees = ((0.18, 0.30, 0.19), (0.50, 0.20, 0.25), (0.82, 0.34, 0.17))  # cx, 꼭대기y, 반폭
        for (cx, ty, hw), g in zip(trees, greens):
            base = fy(0.78)
            d.polygon([(fx(cx), fy(ty)), (fx(cx - hw), base), (fx(cx + hw), base)], fill=g)
            d.rectangle([fx(cx) - 6 * S, base, fx(cx) + 6 * S, base + int(0.035 * ch)],
                        fill=(109, 76, 65))

    elif bg == "night":  # 별 점들
        stars = ((0.12, 0.10, 3), (0.30, 0.22, 2), (0.48, 0.08, 4), (0.66, 0.18, 2),
                 (0.84, 0.12, 3), (0.20, 0.38, 2), (0.58, 0.33, 3), (0.78, 0.42, 2),
                 (0.40, 0.50, 2), (0.90, 0.55, 3), (0.10, 0.60, 2), (0.65, 0.62, 2))
        for sx, sy, r in stars:
            x, y, rr = fx(sx), fy(sy), r * S
            d.ellipse([x - rr, y - rr, x + rr, y + rr], fill=(255, 255, 240))
    # abstract: 소품 없음(무지 그라디언트)


# ---------------------------------------------------------------- 젤리 캐릭터
def _character(spec: dict) -> Image.Image:
    """젤리 캐릭터 1개를 RGBA 레이어로 생성(슈퍼샘플 좌표, 발이 레이어 바닥)."""
    color = _rgb(spec.get("color", "#7CE577"))
    scale = float(spec.get("scale", 1.0))
    # story_gen 스키마 호환: expr 또는 expression 키 모두 허용
    expr = spec.get("expr") or spec.get("expression") or "smile"
    prop = spec.get("prop") or None
    if prop == "none":  # story_gen은 빈 소품을 문자열 "none"으로 표기
        prop = None

    ch = int(BASE_CHAR_H * scale * S)  # 본체 높이
    cw = int(ch * 0.62)
    pad = int(ch * 0.18)               # 모자/팔이 삐져나올 여백(상·좌·우)
    bw, bh = cw + pad * 2, ch + pad
    ox, oy = pad, pad

    X = lambda v: ox + int(v * cw)  # noqa: E731
    Y = lambda v: oy + int(v * ch)  # noqa: E731

    layer = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))

    # 1) 실루엣 마스크: 머리(원) + 몸(캡슐) + 팔다리(짧은 캡슐)
    mask = Image.new("L", (bw, bh), 0)
    md = ImageDraw.Draw(mask)
    head_r = int(ch * 0.27)
    hx, hy = X(0.5), Y(0.27)
    md.ellipse([hx - head_r, hy - head_r, hx + head_r, hy + head_r], fill=255)
    md.rounded_rectangle([X(0.08), Y(0.36), X(0.92), Y(0.93)],
                         radius=int(cw * 0.38), fill=255)
    arm_r = int(cw * 0.09)
    md.rounded_rectangle([X(0.08) - int(cw * 0.14), Y(0.46),
                          X(0.08) + int(cw * 0.06), Y(0.64)], radius=arm_r, fill=255)
    md.rounded_rectangle([X(0.92) - int(cw * 0.06), Y(0.46),
                          X(0.92) + int(cw * 0.14), Y(0.64)], radius=arm_r, fill=255)
    md.rounded_rectangle([X(0.26), Y(0.86), X(0.44), Y(1.0)], radius=int(cw * 0.08), fill=255)
    md.rounded_rectangle([X(0.56), Y(0.86), X(0.74), Y(1.0)], radius=int(cw * 0.08), fill=255)

    dd = ImageDraw.Draw(layer)
    bag_col = (141, 110, 99)

    # 2) 배낭(몸 뒤쪽) — 실루엣보다 먼저 그려 뒤에 깔리게
    if prop == "bag":
        dd.rounded_rectangle([X(0.02) - int(cw * 0.18), Y(0.40), X(0.20), Y(0.74)],
                             radius=int(cw * 0.10), fill=bag_col,
                             outline=_dark(bag_col), width=max(2, S))

    # 3) 외곽선(마스크 팽창) + 본색 채움
    grow = S + 1  # 슈퍼샘플 기준 외곽선 두께(px) — 축소 후 1~2px
    dilated = mask.filter(ImageFilter.MaxFilter(2 * grow + 1))
    layer.paste(Image.new("RGBA", (bw, bh), _dark(color) + (255,)), (0, 0), dilated)
    layer.paste(Image.new("RGBA", (bw, bh), color + (255,)), (0, 0), mask)

    # 4) 배낭 끈(가슴을 가로지르는 사선)
    if prop == "bag":
        dd.line([X(0.66), Y(0.42), X(0.18), Y(0.68)],
                fill=_dark(bag_col), width=max(3, 2 * S))

    # 5) 표정: 점 눈 2개 + 입
    ink = (20, 20, 20)
    lw = max(2, 2 * S)
    er = max(2, int(ch * 0.024))
    if expr == "shock":
        er = int(er * 1.4)
    ey = Y(0.235)
    exl, exr = X(0.36), X(0.64)
    for ex in (exl, exr):
        dd.ellipse([ex - er, ey - er, ex + er, ey + er], fill=ink)
    mcx, mcy = X(0.5), Y(0.325)
    mw, mh = int(cw * 0.15), int(ch * 0.045)
    if expr == "smile":
        dd.arc([mcx - mw, mcy - 2 * mh, mcx + mw, mcy + mh], 20, 160, fill=ink, width=lw)
    elif expr == "sad":
        dd.arc([mcx - mw, mcy, mcx + mw, mcy + 3 * mh], 200, 340, fill=ink, width=lw)
    elif expr == "shock":
        dd.ellipse([mcx - int(cw * 0.07), mcy - int(ch * 0.030),
                    mcx + int(cw * 0.07), mcy + int(ch * 0.045)], fill=ink)
    elif expr == "angry":
        dd.arc([mcx - mw, mcy, mcx + mw, mcy + 3 * mh], 200, 340, fill=ink, width=lw)
        dd.line([exl - er * 2, ey - er * 5, exl + er * 2, ey - er * 3], fill=ink, width=lw)
        dd.line([exr - er * 2, ey - er * 3, exr + er * 2, ey - er * 5], fill=ink, width=lw)
    else:  # neutral
        dd.line([mcx - int(mw * 0.7), mcy, mcx + int(mw * 0.7), mcy], fill=ink, width=lw)

    # 6) 소품: 중절모 / 군모
    if prop == "hat":
        hat = (45, 45, 50)
        brim_y = oy + int(ch * 0.045)
        dd.ellipse([X(0.5) - int(cw * 0.40), brim_y - int(ch * 0.028),
                    X(0.5) + int(cw * 0.40), brim_y + int(ch * 0.028)], fill=hat)
        dd.rounded_rectangle([X(0.5) - int(cw * 0.24), brim_y - int(ch * 0.115),
                              X(0.5) + int(cw * 0.24), brim_y],
                             radius=int(cw * 0.07), fill=hat)
        dd.rectangle([X(0.5) - int(cw * 0.24), brim_y - int(ch * 0.040),
                      X(0.5) + int(cw * 0.24), brim_y - int(ch * 0.018)],
                     fill=(120, 96, 60))  # 모자 띠
    elif prop == "helmet":
        hel = (91, 110, 59)
        hr = int(head_r * 1.12)
        hy2 = Y(0.27) - int(ch * 0.085)
        dd.pieslice([hx - hr, hy2 - hr, hx + hr, hy2 + hr], 180, 360, fill=hel)
        dd.arc([hx - hr, hy2 - hr, hx + hr, hy2 + hr], 180, 360,
               fill=_dark(hel), width=max(2, S))
        dd.rounded_rectangle([hx - hr, hy2 - int(ch * 0.010),
                              hx + hr + int(cw * 0.12), hy2 + int(ch * 0.026)],
                             radius=int(ch * 0.012), fill=hel,
                             outline=_dark(hel), width=max(2, S // 2))  # 챙

    if spec.get("flip"):
        layer = layer.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    return layer


# ---------------------------------------------------------------- 브랜딩/텍스트
def _dog_logo(height_px: int) -> Image.Image:
    """검정 실루엣 강아지 로고: 둥근 머리 + 늘어진 귀 + 짖는 소리 선 3개."""
    u = height_px / 64  # 84x64 기준 좌표계
    img = Image.new("RGBA", (int(84 * u), height_px), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    P = lambda *vals: [v * u for v in vals]  # noqa: E731
    ink = (15, 15, 15, 255)
    d.ellipse(P(5, 12, 21, 44), fill=ink)    # 늘어진 귀
    d.ellipse(P(10, 14, 46, 50), fill=ink)   # 머리
    d.ellipse(P(35, 27, 54, 44), fill=ink)   # 주둥이
    d.ellipse(P(49, 32, 56, 39), fill=ink)   # 코끝
    lw = max(2, int(2.4 * u))
    for r in (8, 13, 18):                    # 짖는 소리 선 3개
        d.arc(P(58 - r, 35 - r, 58 + r, 35 + r), -40, 40, fill=ink, width=lw)
    return img


def _draw_brand(canvas: Image.Image, brand: str, brand_sub: str) -> None:
    """상단 브랜딩 행(y≈110~170): 로고 + 브랜드명(굵은 검정) + 회색 부제."""
    d = ImageDraw.Draw(canvas)
    f_brand = _font(46 * S, bold=True)
    f_sub = _font(25 * S)
    logo = _dog_logo(62 * S)
    gap = 18 * S
    text_w = max(f_brand.getlength(brand), f_sub.getlength(brand_sub))
    x0 = int((W * S - (logo.width + gap + text_w)) / 2)
    canvas.alpha_composite(logo, (x0, 106 * S))
    tx = x0 + logo.width + gap
    d.text((tx, 104 * S), brand, font=f_brand, fill=INK, stroke_width=S, stroke_fill=INK)
    d.text((tx + 2 * S, 160 * S), brand_sub, font=f_sub, fill=GRAY)


def _draw_title(canvas: Image.Image, title: str) -> None:
    """제목(y≈200~280): 굵은 검정 한글, 가운데 정렬, 최대 2줄."""
    d = ImageDraw.Draw(canvas)
    max_w = (W - 140) * S
    font, lines, line_h = _font(64 * S, bold=True), [title], 79
    for size in range(64, 38, -2):
        font = _font(size * S, bold=True)
        lines = _wrap(title, font, max_w)
        line_h = int(size * 1.24)
        if len(lines) <= 2 and len(lines) * line_h <= 120:
            break
    if len(lines) > 2:
        lines = [lines[0], " ".join(lines[1:])]
    block_h = len(lines) * line_h
    y = (198 + max(0, (120 - block_h) // 2)) * S
    for ln in lines:
        lw = font.getlength(ln)
        d.text(((W * S - lw) / 2, y), ln, font=font, fill=INK,
               stroke_width=S, stroke_fill=INK)
        y += line_h * S


def _draw_subtitle(canvas: Image.Image, subtitle: str, highlights: dict) -> None:
    """카드 하단에 겹치는 자막 박스: 흰 굵은 글씨, highlights 단어만 색 강조."""
    highlights = highlights if isinstance(highlights, dict) else {}
    d = ImageDraw.Draw(canvas)
    max_w = (CARD_W - 150) * S
    font, lines, size = _font(54 * S, bold=True), [subtitle], 54
    for size in range(54, 34, -2):
        font = _font(size * S, bold=True)
        lines = _wrap(subtitle, font, max_w)
        if len(lines) <= 2:
            break
    if len(lines) > 2:
        lines = [lines[0], " ".join(lines[1:])]
    line_h = int(size * 1.34) * S

    pad_x, pad_y = 38 * S, 26 * S
    widths = [font.getlength(ln) for ln in lines]
    box_w = min(int(max(widths)) + 2 * pad_x, (CARD_W - 20) * S)
    box_h = line_h * len(lines) + 2 * pad_y
    box_bottom = (CARD_Y1 + 78) * S
    box_top = box_bottom - box_h
    bx0 = (W * S - box_w) // 2

    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(overlay).rounded_rectangle(
        [bx0, box_top, bx0 + box_w, box_bottom],
        radius=30 * S, fill=(10, 10, 10, 224))  # 불투명 88%
    canvas.alpha_composite(overlay)

    space_w = font.getlength(" ")
    y = box_top + pad_y
    for ln, lw in zip(lines, widths):
        x = (W * S - lw) / 2
        for tok in ln.split(" "):
            col = (255, 255, 255)
            for key, name in highlights.items():
                if key and key in tok:
                    col = HL_COLORS.get(name, col)
                    break
            d.text((x, y), tok, font=font, fill=col, stroke_width=S, stroke_fill=col)
            x += font.getlength(tok) + space_w
        y += line_h


# ---------------------------------------------------------------- 공개 API
def draw_frame(out_path, *, title: str, brand: str, brand_sub: str,
               scene: dict, subtitle: str, highlights: dict) -> None:
    """1080x1920 완성 프레임 PNG 저장 (RGB)."""
    canvas = Image.new("RGBA", (W * S, H * S), (255, 255, 255, 255))

    _draw_brand(canvas, brand, brand_sub)
    _draw_title(canvas, title)

    # 장면 카드: 그라디언트 + 소품 + 캐릭터
    # (story_gen 스키마 호환: bg_colors가 있으면 팔레트보다 우선)
    bg = scene.get("bg", "abstract")
    colors = scene.get("bg_colors")
    if colors and len(colors) >= 2:
        c0, c1 = colors[0], colors[1]
    else:
        c0, c1 = PALETTES.get(bg, PALETTES["abstract"])
    card = _v_gradient(CARD_W * S, CARD_H * S, c0, c1).convert("RGBA")
    _draw_props(card, bg)
    for spec in scene.get("chars") or scene.get("characters") or []:
        layer = _character(spec)
        cx = int(float(spec.get("x", 0.5)) * CARD_W * S)
        # 레퍼런스처럼 캐릭터가 자막 뒤에 거의 가려지지 않도록 카드 바닥보다 위에 착지시킨다.
        foot_y = (CARD_H - 178) * S
        card.paste(layer, (cx - layer.width // 2, foot_y - layer.height), layer)

    mask = Image.new("L", card.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, card.width - 1, card.height - 1], radius=CARD_RADIUS * S, fill=255)
    canvas.paste(card, (CARD_X0 * S, CARD_Y0 * S), mask)
    ImageDraw.Draw(canvas).rounded_rectangle(
        [CARD_X0 * S, CARD_Y0 * S, CARD_X1 * S - 1, CARD_Y1 * S - 1],
        radius=CARD_RADIUS * S, outline=(208, 208, 208), width=S)

    _draw_subtitle(canvas, subtitle, highlights)

    out = canvas.resize((W, H), Image.Resampling.LANCZOS).convert("RGB")
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.save(out_path)


# ---------------------------------------------------------------- CLI 데모
def _demo_scene() -> dict:
    return {
        "bg": "sky",
        "chars": [
            {"color": "#7CE577", "x": 0.22, "scale": 1.0, "expr": "smile",
             "prop": "bag", "flip": False},
            {"color": "#F48FB1", "x": 0.52, "scale": 0.9, "expr": "shock",
             "prop": "hat", "flip": False},
            {"color": "#81D4FA", "x": 0.82, "scale": 1.05, "expr": "angry",
             "prop": "helmet", "flip": True},
        ],
    }


def main() -> int:
    p = argparse.ArgumentParser(prog="pipelines.shorts.cartoon",
                                description="만화 스타일 데모 프레임 1장 생성")
    p.add_argument("out_png", help="출력 PNG 경로")
    p.add_argument("--bg", default="sky", choices=sorted(PALETTES), help="장면 배경")
    args = p.parse_args()
    scene = _demo_scene()
    scene["bg"] = args.bg
    try:
        draw_frame(args.out_png,
                   title="낙하산 2개가 모두 안 펴질 확률 100%",
                   brand="Dang_sound",
                   brand_sub="댕소리 · 오늘의 썰",
                   scene=scene,
                   subtitle="낙하산이 둘 다 안 펴질 확률은 정확히 100% 였다",
                   highlights={"100%": "red", "낙하산": "yellow"})
        print(f"[cartoon] 데모 프레임 저장: {args.out_png}")
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"[cartoon] 실패: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

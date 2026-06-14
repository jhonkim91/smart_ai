"""스틱 피규어 캐릭터 렌더러 — 댕소리 원본풍 긴 팔다리 블롭.

기존 cartoon/reference_style의 '젤리빈'(팔다리가 짧은 캡슐)과 달리, 머리+몸이
둥근 블롭 하나이고 거기서 가는 긴 팔다리(stroke 라인 + 둥근 끝)가 뻗어 나온다.
실사 영상 위에 overlay 합성하기 위해 투명 PNG 풀프레임(1080x1920)으로 그린다.

포즈(pose):
    stand  팔 아래로(기본 서기)
    spread 팔다리 활짝(자유낙하/스카이다이빙)
    point  한 팔 앞으로
    hold   두 팔 앞으로(물건 든 자세)
표정(expr): smile/sad/shock/angry/neutral  (reference_style와 동일 의미)
소품(prop): none/helmet/hat/bag

사용:
    python -m pipelines.shorts.actor /tmp/actors.png --bg night
"""
from __future__ import annotations

import argparse
import math
import sys
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

from pipelines.shorts import characters
from pipelines.shorts.reference_style import CARD

W, H = 1080, 1920
S = 2  # 슈퍼샘플
FONT_PATH = "/System/Library/Fonts/AppleSDGothicNeo.ttc"

CARDX, CARDY, CARDX1, CARDY1 = CARD
CARDW, CARDH = CARDX1 - CARDX, CARDY1 - CARDY

INK = (18, 18, 20)


@lru_cache(maxsize=32)
def _font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    if bold:
        for idx in range(20):
            try:
                f = ImageFont.truetype(FONT_PATH, size, index=idx)
            except OSError:
                break
            if any(x in " ".join(f.getname()) for x in ("Bold", "Heavy", "ExtraBold")):
                return f
    return ImageFont.truetype(FONT_PATH, size)


def _rgb(c) -> tuple[int, int, int]:
    if isinstance(c, str):
        c = c.strip().lstrip("#")
        return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))
    return tuple(c[:3])


def _dark(c, f: float = 0.0) -> tuple[int, int, int]:
    """본체 외곽선 색(원본은 거의 검정 라인). f로 본색을 약간 섞는다."""
    r, g, b = _rgb(c)
    return (int(r * f * 0.4 + 14), int(g * f * 0.4 + 14), int(b * f * 0.4 + 16))


def _lighten(c, f: float) -> tuple[int, int, int]:
    r, g, b = _rgb(c)
    return (int(r + (255 - r) * f), int(g + (255 - g) * f), int(b + (255 - b) * f))


def _darken(c, f: float) -> tuple[int, int, int]:
    r, g, b = _rgb(c)
    return (int(r * f), int(g * f), int(b * f))


def _gradient_rgba(w: int, h: int, top, bottom) -> Image.Image:
    """위(top)→아래(bottom) 세로 그라디언트 RGBA(불투명). (구버전, 폴백용)"""
    yy = np.linspace(0.0, 1.0, h, dtype=np.float32).reshape(h, 1, 1)
    t = np.array(top, np.float32).reshape(1, 1, 3)
    b = np.array(bottom, np.float32).reshape(1, 1, 3)
    col = (t * (1.0 - yy) + b * yy)
    arr = np.broadcast_to(col, (h, w, 3)).astype(np.uint8)
    alpha = np.full((h, w, 1), 255, np.uint8)
    return Image.fromarray(np.concatenate([arr, alpha], axis=2), "RGBA")


def _radial_shade(w: int, h: int, light, dark, lx: float, ly: float, radius: float) -> Image.Image:
    """광원(lx,ly)에서 거리에 따라 light→dark로 어두워지는 방향성 구(球) 셰이딩.

    세로 그라디언트보다 '한 방향에서 빛 받는 3D 구'처럼 보여 원본 댕소리의
    매끄러운 렌더 질감에 가깝다. RGB 배열을 직접 만들어 마스크로 본체에 입힌다.
    """
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    d = np.sqrt((xx - lx) ** 2 + (yy - ly) ** 2) / max(radius, 1.0)
    t = np.clip(d, 0.0, 1.0)
    t = t * t * (3.0 - 2.0 * t)          # smoothstep
    lt = np.array(light, np.float32)
    dk = np.array(dark, np.float32)
    col = lt[None, None, :] * (1.0 - t[..., None]) + dk[None, None, :] * t[..., None]
    return Image.fromarray(col.astype(np.uint8), "RGB")


def _draw_actor(canvas: Image.Image, spec: dict, t: float = 0.0,
                animate: bool = False) -> None:
    """canvas(슈퍼샘플 좌표계)에 캐릭터 1개를 그린다. spec은 카드 비율 좌표.

    animate=True면 위상 t(0~1, 루프)에 따라 몸 출렁임·팔다리 흔들림·깜빡임을
    적용해 '계속 움직이는' 프레임을 만든다(render_actors_anim에서 t를 바꿔가며 호출).
    """
    color = _rgb(spec.get("color", "#FF8EC7"))
    outline = _dark(color)
    scale = float(spec.get("scale", 1.0))
    pose = spec.get("pose") or _pose_from(spec)
    expr = spec.get("expr") or spec.get("expression") or "neutral"
    prop = spec.get("prop") or "none"
    flip = bool(spec.get("flip"))

    # --- 애니메이션 오프셋 (animate일 때만) ---
    wob = math.sin(2 * math.pi * t)
    wob2 = math.sin(2 * math.pi * t + 1.2)
    big = 1.8 if pose == "spread" else 1.0   # 자유낙하는 더 크게 휘젓는다
    float_dy = int(7 * S * wob) if animate else 0
    sway = int(13 * S * wob * big) if animate else 0
    flail = int(11 * S * wob2 * big) if animate else 0
    blink = animate and (t % 1.0) < 0.07     # 루프당 한 번 깜빡

    # 카드 좌표 → 캔버스(슈퍼샘플) 절대 좌표
    cx = int((CARDX + float(spec.get("x", .5)) * CARDW) * S)
    foot = int((CARDY + float(spec.get("foot_y", .74)) * CARDH) * S) + float_dy

    # 본체 치수 (원본: 큰 머리 + 매끄럽게 이어지는 달걀형 몸, 목 없음)
    body_h = int(330 * scale * S)
    body_w = int(body_h * 0.60)
    head_r = int(body_w * 0.56)          # 머리가 몸보다 넓다(원본처럼 머리 우세)
    limb_w = max(6, int(body_w * 0.17))

    # 좌표 기준점
    body_top = foot - body_h
    head_cy = body_top + head_r
    torso_top = head_cy + int(head_r * 0.18)   # 머리와 크게 겹쳐 목이 안 생김
    torso_bottom = foot - int(body_h * 0.05)

    sign = -1 if flip else 1

    # --- 팔/다리 위치 ---
    sh_y = torso_top + int(body_h * 0.24)          # 어깨(얼굴과 겹치지 않게 낮춤)
    hip_y = torso_bottom - int(body_h * 0.02)       # 골반
    arm_len = int(body_h * 0.42)
    leg_len = int(body_h * 0.30)
    ax = body_w // 2 + int(limb_w * 0.2)

    if pose == "spread":
        l_arm = (cx - ax, sh_y, cx - ax - int(arm_len * 0.9), sh_y - int(arm_len * 0.5))
        r_arm = (cx + ax, sh_y, cx + ax + int(arm_len * 0.9), sh_y - int(arm_len * 0.5))
        l_leg = (cx - int(body_w * 0.22), hip_y, cx - int(body_w * 0.55), hip_y + leg_len)
        r_leg = (cx + int(body_w * 0.22), hip_y, cx + int(body_w * 0.55), hip_y + leg_len)
    elif pose == "hold":
        l_arm = (cx - ax, sh_y, cx - int(body_w * 0.30), sh_y + int(arm_len * 0.7))
        r_arm = (cx + ax, sh_y, cx + int(body_w * 0.30), sh_y + int(arm_len * 0.7))
        l_leg = (cx - int(body_w * 0.18), hip_y, cx - int(body_w * 0.30), hip_y + leg_len)
        r_leg = (cx + int(body_w * 0.18), hip_y, cx + int(body_w * 0.30), hip_y + leg_len)
    elif pose == "point":
        l_arm = (cx - ax, sh_y, cx - int(body_w * 0.28), sh_y + int(arm_len * 0.6))
        r_arm = (cx + ax, sh_y, cx + sign * int(arm_len * 1.0), sh_y - int(arm_len * 0.35))
        l_leg = (cx - int(body_w * 0.18), hip_y, cx - int(body_w * 0.30), hip_y + leg_len)
        r_leg = (cx + int(body_w * 0.18), hip_y, cx + int(body_w * 0.30), hip_y + leg_len)
    else:  # stand — 팔은 몸 옆에 짧게, 다리는 모아서 짧게(원본 스탠딩)
        l_arm = (cx - ax, sh_y, cx - int(body_w * 0.34), sh_y + int(arm_len * 0.78))
        r_arm = (cx + ax, sh_y, cx + int(body_w * 0.34), sh_y + int(arm_len * 0.78))
        l_leg = (cx - int(body_w * 0.12), hip_y, cx - int(body_w * 0.14), hip_y + int(leg_len * 0.78))
        r_leg = (cx + int(body_w * 0.12), hip_y, cx + int(body_w * 0.14), hip_y + int(leg_len * 0.78))

    if animate:
        # 팔 끝을 좌우 반대로 흔들고, 자유낙하(spread)면 다리까지 휘젓는다
        l_arm = (l_arm[0], l_arm[1], l_arm[2] - sway, l_arm[3] - flail)
        r_arm = (r_arm[0], r_arm[1], r_arm[2] + sway, r_arm[3] + flail)
        if pose == "spread":
            l_leg = (l_leg[0], l_leg[1], l_leg[2] - flail, l_leg[3] - abs(sway) // 2)
            r_leg = (r_leg[0], r_leg[1], r_leg[2] + flail, r_leg[3] - abs(sway) // 2)

    # ===== 부드러운 3D풍 셰이딩: 통합 실루엣 + 세로 그라디언트 + 광택 =====
    body_rad = int(body_w * 0.46)
    body_box = [cx - body_w // 2, torso_top, cx + body_w // 2, torso_bottom]
    head_box = [cx - head_r, head_cy - head_r, cx + head_r, head_cy + head_r]
    limbs = (l_leg, r_leg, l_arm, r_arm)
    ow = max(3, S * 2)
    cap = limb_w // 2

    # 통합 bbox (머리/몸/팔다리 전체)
    xs = [body_box[0], body_box[2], head_box[0], head_box[2]]
    ys = [body_box[1], body_box[3], head_box[1], head_box[3]]
    for lm in limbs:
        xs += [lm[0], lm[2]]
        ys += [lm[1], lm[3]]
    pad = limb_w + ow + 6 * S
    bx0, by0 = int(min(xs) - pad), int(min(ys) - pad)
    bx1, by1 = int(max(xs) + pad), int(max(ys) + pad)
    lw_, lh_ = bx1 - bx0, by1 - by0
    ox, oy = -bx0, -by0  # 캔버스→로컬 오프셋

    # 1) 실루엣 마스크(팔다리=둥근끝 캡슐, 머리=원, 몸=둥근 사각 — 하나로 합쳐짐)
    mask = Image.new("L", (lw_, lh_), 0)
    md = ImageDraw.Draw(mask)
    for (x0, y0, x1, y1) in limbs:
        md.line([(x0 + ox, y0 + oy), (x1 + ox, y1 + oy)], fill=255, width=limb_w)
        for px, py in ((x0, y0), (x1, y1)):
            md.ellipse([px + ox - cap, py + oy - cap, px + ox + cap, py + oy + cap], fill=255)
    # 몸은 타원(어깨가 머리에서 경사지게 이어짐) + 머리 원 → union = 매끄러운 달걀형
    md.ellipse([body_box[0] + ox, body_box[1] + oy, body_box[2] + ox, body_box[3] + oy], fill=255)
    md.ellipse([head_box[0] + ox, head_box[1] + oy, head_box[2] + ox, head_box[3] + oy], fill=255)

    local = Image.new("RGBA", (lw_, lh_), (0, 0, 0, 0))
    # 2) 외곽선(마스크 팽창 → 어두운 테두리)
    outline_mask = mask.filter(ImageFilter.MaxFilter(2 * ow + 1))
    local.paste(Image.new("RGBA", (lw_, lh_), tuple(outline) + (255,)), (0, 0), outline_mask)
    # 3) 방향성 구 셰이딩(좌상단 광원) + 앰비언트 오클루전(가장자리 어둡게) → 3D 질감
    lx = (cx + ox) - head_r * 0.28
    ly = (head_cy + oy) - head_r * 0.34
    shade = _radial_shade(lw_, lh_, _lighten(color, 0.34), _darken(color, 0.66),
                          lx, ly, body_h * 0.82)
    # AO: 실루엣 중심은 밝게, 가장자리로 갈수록 ~20% 어둡게 → 부피감
    core = mask.filter(ImageFilter.MinFilter(2 * ow + 1)).filter(
        ImageFilter.GaussianBlur(head_r * 0.20))
    core_f = (np.asarray(core, np.float32) / 255.0)[..., None]
    sa = np.asarray(shade, np.float32) * (0.80 + 0.20 * core_f)
    shade = Image.fromarray(sa.clip(0, 255).astype(np.uint8), "RGB")
    local.paste(shade, (0, 0), mask)
    # 4) 광택 하이라이트(머리 상단 좌측, 부드럽게, 본체 안쪽으로 클립)
    gloss = Image.new("L", (lw_, lh_), 0)
    gx = head_box[0] + ox + head_r * 0.5
    gy = head_box[1] + oy + head_r * 0.45
    gr = head_r * 0.6
    ImageDraw.Draw(gloss).ellipse([gx - gr, gy - gr * 0.85, gx + gr, gy + gr * 0.85], fill=120)
    gloss = ImageChops.multiply(gloss.filter(ImageFilter.GaussianBlur(head_r * 0.16)), mask)
    sheen = Image.new("RGBA", (lw_, lh_), (255, 255, 255, 0))
    sheen.putalpha(gloss)
    local = Image.alpha_composite(local, sheen)

    canvas.alpha_composite(local, (bx0, by0))

    # --- 표정/소품(본체 위) ---
    _draw_face(ImageDraw.Draw(canvas), cx, head_cy, head_r, expr, sign, blink=blink)
    if prop and prop != "none":
        _draw_prop(canvas, cx, head_cy, head_r, prop, sign)


def _pose_from(spec: dict) -> str:
    """pose 미지정 시 표정/소품으로 추정."""
    expr = spec.get("expr") or spec.get("expression") or ""
    if expr == "shock":
        return "spread"
    if spec.get("prop") == "bag":
        return "hold"
    return "stand"


def _draw_face(d, cx, cy, r, expr, sign, blink: bool = False) -> None:
    eye = (18, 18, 20)
    ey = cy - int(r * 0.04)
    ex = int(r * 0.40)
    ew = max(3, int(r * 0.13))           # 눈 가로 반지름
    eh = max(4, int(r * 0.21))           # 눈 세로 반지름(원본은 세로로 길쭉한 큰 눈)
    if expr == "shock":
        ew, eh = int(ew * 1.2), int(eh * 1.15)
    # 눈 (blink면 감은 선)
    for sx in (-1, 1):
        x = cx + sx * ex
        if blink:
            d.line([x - ew, ey, x + ew, ey], fill=eye, width=max(3, eh // 2))
        else:
            d.ellipse([x - ew, ey - eh, x + ew, ey + eh], fill=eye)
    # 볼터치
    blush = (255, 150, 165, 80)
    br = int(r * 0.15)
    for sx in (-1, 1):
        x = cx + sx * int(r * 0.66)
        d.ellipse([x - br, ey + int(r * 0.22) - br, x + br, ey + int(r * 0.22) + br], fill=blush)
    # 입
    mcx, mcy = cx, cy + int(r * 0.34)
    mw = int(r * 0.26)
    lw = max(4, S * 3)
    if expr == "smile":  # 벌린 미소(검정으로 채운 반달)
        d.chord([mcx - mw, mcy - int(r * 0.22), mcx + mw, mcy + int(r * 0.24)], 18, 162, fill=eye)
    elif expr == "sad":
        d.arc([mcx - mw, mcy + int(r * 0.06), mcx + mw, mcy + int(r * 0.36)], 200, 340, fill=eye, width=lw)
    elif expr == "shock":
        d.ellipse([mcx - int(r * 0.15), mcy - int(r * 0.10), mcx + int(r * 0.15), mcy + int(r * 0.22)], fill=eye)
    elif expr == "angry":
        d.arc([mcx - mw, mcy + int(r * 0.06), mcx + mw, mcy + int(r * 0.36)], 200, 340, fill=eye, width=lw)
        d.line([cx - ex - ew, ey - eh * 1.4, cx - ex + ew, ey - eh * 0.5], fill=eye, width=lw)
        d.line([cx + ex - ew, ey - eh * 0.5, cx + ex + ew, ey - eh * 1.4], fill=eye, width=lw)
    else:  # neutral
        d.line([mcx - int(mw * 0.5), mcy, mcx + int(mw * 0.5), mcy], fill=eye, width=lw)


def _draw_prop(canvas, cx, cy, r, prop, sign) -> None:
    d = ImageDraw.Draw(canvas)
    if prop == "helmet":  # 공수부대 베레모: 머리에 비스듬히 얹힌 작은 베레 + 밴드 + 배지
        olive = (94, 106, 62)
        dark = (60, 70, 40)
        badge = (216, 207, 140)
        # 머리 앞쪽에 보이는 가는 밴드(눈 위)
        band_y = cy - int(r * 0.40)
        d.arc([cx - int(r * 0.82), band_y - int(r * 0.30), cx + int(r * 0.82), band_y + int(r * 0.34)],
              188, 352, fill=dark, width=max(4, S * 3))
        # 베레 본체(머리 위 납작 타원, 한쪽으로 살짝 기움)
        bcx = cx + int(r * 0.12) * sign
        bcy = cy - int(r * 0.58)
        bw, bh = int(r * 0.90), int(r * 0.40)
        d.ellipse([bcx - bw, bcy - bh, bcx + bw, bcy + bh], fill=olive)
        # 한쪽으로 흘러내린 부분(작게) — flip(sign=-1) 시 x 뒤집힘 방지로 정렬
        dx0 = bcx + int(bw * 0.30) * sign
        dx1 = bcx + int(bw * 1.0) * sign
        d.ellipse([min(dx0, dx1), bcy - int(bh * 0.05),
                   max(dx0, dx1), bcy + int(bh * 0.75)], fill=olive)
        # 공수 배지(앞쪽)
        bdx = cx - int(r * 0.30) * sign
        d.ellipse([bdx - int(r * 0.11), band_y - int(r * 0.20), bdx + int(r * 0.11), band_y + int(r * 0.02)],
                  fill=badge)
    elif prop == "hat":  # 카우보이/중절모 느낌 검정
        hat = (44, 40, 38)
        brim_y = cy - int(r * 0.55)
        d.ellipse([cx - int(r * 1.15), brim_y - int(r * 0.10), cx + int(r * 1.15), brim_y + int(r * 0.12)], fill=hat)
        d.rounded_rectangle([cx - int(r * 0.55), brim_y - int(r * 0.62), cx + int(r * 0.55), brim_y + int(r * 0.02)],
                            radius=int(r * 0.12), fill=hat)
        d.rectangle([cx - int(r * 0.55), brim_y - int(r * 0.14), cx + int(r * 0.55), brim_y - int(r * 0.02)],
                    fill=(150, 110, 70))
    elif prop == "bag":  # 빨간 낙하산 가방(가슴 앞)
        bag = (210, 70, 64)
        bx0 = cx - int(r * 0.55)
        by0 = cy + int(r * 1.25)
        d.rounded_rectangle([bx0, by0, bx0 + int(r * 1.1), by0 + int(r * 0.9)], radius=int(r * 0.16),
                            fill=bag, outline=(150, 40, 36), width=max(2, S * 2))
        d.line([bx0 + int(r * 0.2), by0, bx0 + int(r * 0.9), by0 + int(r * 0.9)], fill=(60, 120, 200), width=max(3, S * 2))


def _draw_shadows(canvas: Image.Image, chars: list) -> None:
    """바닥 그림자(애니메이션에도 고정 — 캐릭터만 떠야 자연스럽다)."""
    d = ImageDraw.Draw(canvas)
    for spec in chars:
        cx = int((CARDX + float(spec.get("x", .5)) * CARDW) * S)
        foot = int((CARDY + float(spec.get("foot_y", .74)) * CARDH) * S)
        scale = float(spec.get("scale", 1.0))
        sw = int(110 * scale * S)
        d.ellipse([cx - sw, foot - int(14 * S), cx + sw, foot + int(16 * S)], fill=(0, 0, 0, 60))


def _frame(chars: list, t: float, animate: bool) -> Image.Image:
    canvas = Image.new("RGBA", (W * S, H * S), (0, 0, 0, 0))
    _draw_shadows(canvas, chars)
    for spec in chars:
        _draw_actor(canvas, spec, t=t, animate=animate)
    return canvas.resize((W, H), Image.Resampling.LANCZOS)


def render_actors(scene: dict, out_path: Path) -> Path:
    """장면의 모든 캐릭터를 투명 풀프레임 PNG로 렌더(정지, 그림자 포함)."""
    chars = characters.resolve_all(scene.get("chars") or scene.get("characters") or [])
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _frame(chars, 0.0, animate=False).save(out_path)
    return out_path


def render_actors_anim(scene: dict, out_dir: Path, frames: int = 20) -> int:
    """캐릭터 애니메이션 루프를 frames장의 투명 PNG 시퀀스로 렌더.

    out_dir/anim_000.png … 를 만들고 프레임 수를 반환한다. produce_real이
    이 시퀀스를 ffmpeg loop 필터로 장면 길이만큼 반복 재생한다.
    """
    chars = characters.resolve_all(scene.get("chars") or scene.get("characters") or [])
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for i in range(frames):
        t = i / frames  # 0~1 한 루프
        _frame(chars, t, animate=True).save(out_dir / f"anim_{i:03d}.png")
    return frames


def _demo_scene() -> dict:
    return {
        "bg": "sky",
        "chars": [
            {"color": "#7CE577", "x": .28, "scale": 1.0, "expr": "smile", "pose": "stand"},
            {"color": "#FF8EC7", "x": .52, "scale": 1.05, "expr": "shock", "pose": "spread", "prop": "helmet"},
            {"color": "#81D4FA", "x": .78, "scale": 0.95, "expr": "angry", "pose": "point", "prop": "hat", "flip": True},
        ],
    }


def main() -> int:
    p = argparse.ArgumentParser(prog="pipelines.shorts.actor")
    p.add_argument("out_png")
    args = p.parse_args()
    try:
        render_actors(_demo_scene(), Path(args.out_png))
        print(f"[actor] saved: {args.out_png}")
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"[actor] 실패: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

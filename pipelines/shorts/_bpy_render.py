"""Blender 내부 실행 헤드리스 렌더러 — 마스코트를 spec대로 배치/포즈/색 적용 후 투명 PNG.

호출(venv가 아니라 Blender 번들 파이썬에서 실행됨):
    blender --background assets/mascot/mascot.blend --python pipelines/shorts/_bpy_render.py \
        -- <job.json> --cycles-device METAL

job.json: {"chars":[resolved spec...], "card":[x0,y0,x1,y1], "W":1080,"H":1920,
           "frames":20, "out_dir":"...", "samples":24}

이 파일은 agent-hub 모듈을 import하지 않는다(Blender 파이썬엔 venv 없음). bpy/json/math/sys만 사용.
좌표: Pillow와 동일하게 cx=CARDX+x*CARDW, foot=CARDY+foot_y*CARDH (1080x1920 픽셀).
정사영 카메라로 픽셀↔월드를 선형 매핑(px_per_unit 고정).
"""
import json
import math
import sys

import bpy

PX_PER_UNIT = 165.0          # body 2.0u → 330px (scale=1.0). 배치/크기 기준 상수.
BODY_UNITS = 2.0             # 마스코트 발→머리top 높이(월드)
BASE_BODY_PX = PX_PER_UNIT * BODY_UNITS  # = 330


def _srgb_to_linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _hex_to_linear(hex_str):
    h = hex_str.strip().lstrip("#")
    rgb = [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    return tuple(_srgb_to_linear(c) for c in rgb) + (1.0,)


# 포즈별 팔다리 Y축 회전(라디안). 빌드시 팔은 down-out, 다리는 near-vertical 기준.
POSES = {
    "stand":  {"arm_L": -0.15, "arm_R": 0.15, "leg_L": 0.0, "leg_R": 0.0},
    "spread": {"arm_L": -1.15, "arm_R": 1.15, "leg_L": -0.5, "leg_R": 0.5},
    "point":  {"arm_L": -0.2, "arm_R": 1.3, "leg_L": 0.0, "leg_R": 0.0},
    "hold":   {"arm_L": -0.7, "arm_R": 0.7, "leg_L": 0.0, "leg_R": 0.0},
}


def _setup_cycles(scene, samples):
    scene.render.engine = "CYCLES"
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = "METAL"
    prefs.get_devices()
    gpu_on = False
    for d in prefs.devices:
        d.use = (d.type != "CPU")
        gpu_on = gpu_on or d.use
    scene.cycles.device = "GPU" if gpu_on else "CPU"
    scene.cycles.samples = samples
    scene.cycles.use_denoising = True
    try:
        scene.cycles.denoiser = "OPENIMAGEDENOISE"   # MetalRT denoise 회피
    except Exception:
        pass
    scene.render.use_persistent_data = True
    print(f"[_bpy_render] device={scene.cycles.device} samples={samples}")


def _setup_camera(scene, W, H):
    cam = scene.objects.get("MascotCam")
    if cam is None:
        bpy.ops.object.camera_add()
        cam = bpy.context.active_object
        cam.name = "MascotCam"
    cam.data.type = "ORTHO"
    cam.data.sensor_fit = "VERTICAL"
    ortho = H / PX_PER_UNIT                       # 세로 가시 범위(월드)
    cam.data.ortho_scale = ortho
    cam.location = (0.0, -20.0, ortho / 2.0)
    cam.rotation_euler = (math.radians(90), 0, 0)  # +Y를 바라봄
    scene.camera = cam
    return ortho


def _px_to_world(cx, foot, W, H, ortho):
    h_extent = ortho * (W / H)
    wx = (cx / W - 0.5) * h_extent
    wz = ortho * (1.0 - foot / H)
    return wx, wz


def _duplicate_mascot():
    """body+자식 전체를 복제하고 새 body 반환."""
    body = bpy.data.objects.get("body")
    bpy.ops.object.select_all(action="DESELECT")
    body.select_set(True)
    for ch in body.children_recursive:
        ch.select_set(True)
    bpy.context.view_layer.objects.active = body
    bpy.ops.object.duplicate()
    # 복제 후 active가 새 body
    new_body = bpy.context.view_layer.objects.active
    return new_body


def _child(body, name_prefix):
    for ch in body.children_recursive:
        if ch.name.startswith(name_prefix) or ch.name.rsplit(".", 1)[0] == name_prefix:
            return ch
    return None


def _apply_color(body, hex_color):
    col = _hex_to_linear(hex_color)
    base = bpy.data.materials.get("MascotBody")
    mat = base.copy()
    bsdf = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = col
    for obj in [body, *body.children_recursive]:
        if obj.type == "MESH" and obj.data.materials and \
                obj.data.materials[0] and obj.data.materials[0].name.startswith("MascotBody"):
            obj.data.materials[0] = mat
            obj.color = col          # Workbench OBJECT 컬러용


def _apply_pose(body, pose, t, spread):
    rot = POSES.get(pose, POSES["stand"])
    sway = 0.12 * math.sin(2 * math.pi * t) * (1.8 if spread else 1.0)
    for bone, base in rot.items():
        ch = _child(body, bone)
        if ch:
            extra = sway if "arm" in bone else 0.0
            sign = -1 if bone.endswith("_L") else 1
            ch.rotation_euler = (0, base + sign * extra, 0)


def _apply_expr(body, expr, t):
    want = {"smile": "mouth_smile", "shock": "mouth_shock"}.get(expr, "mouth_neutral")
    for kind in ("smile", "neutral", "shock"):
        ch = _child(body, f"mouth_{kind}")
        if ch:
            ch.hide_render = (f"mouth_{kind}".split(".")[0] != want)
    # blink: 루프 중간 짧은 구간만(프레임0이 항상 감기지 않도록)
    blink = 0.46 < (t % 1.0) < 0.54
    for side in ("eye_L", "eye_R"):
        ch = _child(body, side)
        if ch:
            base = ch.get("_eye_z", None)
            if base is None:
                base = ch.scale.z
                ch["_eye_z"] = base
            ch.scale = (ch.scale.x, ch.scale.y, base * 0.12 if blink else base)


def _apply_prop(body, prop):
    want = {"helmet": "prop_beret", "hat": "prop_hat", "bag": "prop_bag"}.get(prop)
    for pname in ("prop_beret", "prop_hat", "prop_bag"):
        ch = _child(body, pname)
        if ch:
            on = (pname == want)
            ch.hide_render = not on
            ch.hide_viewport = not on


def _place(body, spec, W, H, card, ortho):
    cx0, cy0, cx1, cy1 = card
    cw, chh = cx1 - cx0, cy1 - cy0
    cx = cx0 + float(spec.get("x", 0.5)) * cw
    foot = cy0 + float(spec.get("foot_y", 0.74)) * chh
    wx, wz = _px_to_world(cx, foot, W, H, ortho)
    sc = float(spec.get("scale", 1.0))
    body.location = (wx, 0.0, wz)
    sx = -sc if spec.get("flip") else sc
    body.scale = (sx, sc, sc)


def render(job):
    scene = bpy.context.scene
    W, H = job["W"], job["H"]
    card = job["card"]
    frames = job.get("frames", 1)
    out_dir = job["out_dir"]
    engine = job.get("engine", "CYCLES")
    if engine == "WORKBENCH":          # 즉시 렌더(형태/포즈 빠른 검증용)
        scene.render.engine = "BLENDER_WORKBENCH"
        sh = scene.display.shading
        sh.light = "STUDIO"
        sh.color_type = "OBJECT"
        sh.show_shadows = True
    else:
        _setup_cycles(scene, job.get("samples", 24))
    scene.render.resolution_x = W
    scene.render.resolution_y = H
    scene.render.resolution_percentage = job.get("res_pct", 100)
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    ortho = _setup_camera(scene, W, H)

    # 원본 객체 목록을 복제 전에 캡처(나중에 원본만 숨김)
    base_body = bpy.data.objects.get("body")
    originals = [base_body, *base_body.children_recursive]

    chars = job["chars"]
    dupes = []
    for spec in chars:
        b = _duplicate_mascot()
        # 복제본은 hide_render 상속 가능 → body+모든 자식을 명시적으로 보이게
        for obj in [b, *b.children_recursive]:
            obj.hide_render = False
            obj.hide_viewport = False
        _apply_color(b, spec.get("color", "#FF8EC7"))
        _apply_prop(b, spec.get("prop", "none"))
        b["_spec"] = json.dumps(spec)
        dupes.append(b)

    # 원본(베이스)만 숨김 — 복제본만 렌더되게
    for obj in originals:
        obj.hide_render = True
        obj.hide_viewport = True

    for i in range(frames):
        t = i / max(frames, 1)
        for b, spec in zip(dupes, chars):
            pose = spec.get("pose") or "stand"
            _apply_pose(b, pose, t, pose == "spread")
            _apply_expr(b, spec.get("expr", "neutral"), t)
            # 몸 부유 + 배치(부유는 z에 더함)
            _place(b, spec, W, H, card, ortho)
            b.location.z += (7.0 / PX_PER_UNIT) * math.sin(2 * math.pi * t)
        scene.render.filepath = f"{out_dir}/anim_{i:03d}.png"
        bpy.ops.render.render(write_still=True)
        print(f"[_bpy_render] frame {i+1}/{frames} → {scene.render.filepath}")


def main():
    argv = sys.argv
    job_path = argv[argv.index("--") + 1]
    with open(job_path) as f:
        job = json.load(f)
    render(job)
    print("[_bpy_render] 완료")


if __name__ == "__main__":
    main()

"""졸라맨(3D 스틱 피규어 사람) 마스코트를 절차적으로 빌드 → .blend 저장.

둥근 머리(공) + 가는 막대 몸통 + 가는 팔다리(둥근 누들). 머티리얼·얼굴·소품은
build_mascot와 동일 계약(MascotBody 머티리얼, eye_L/R, mouth_*, prop_*, 발 원점).
이렇게 해야 _bpy_render.py가 그대로 재사용된다(포즈는 팔다리 오브젝트 회전).

비율은 PARAMS(아래) 기본값 + 선택적 params.json 오버라이드로 조절(변형 탐색용).

실행:
    blender --background --python assets/mascot/build_zolaman.py -- <out.blend> [params.json]
"""
import json
import math
import sys

import bpy
from mathutils import Vector

# 졸라맨(사람 비율) 기본값 — 레퍼런스: 둥근 머리 + 길고 가는 팔다리 + 슬림 몸통.
# 변형 탐색 시 params.json으로 덮어씀.
PARAMS = {
    "head_r": 0.40,      # 머리 반지름(중간 둥근 머리)
    "torso_len": 0.85,   # 몸통 길이(슬림)
    "torso_r": 0.115,    # 몸통 굵기
    "limb_r": 0.10,      # 팔다리 굵기(가늘게)
    "arm_len": 1.15,     # 팔 길이(길게 — 사람 비율)
    "leg_len": 1.15,     # 다리 길이(길게)
    "shoulder_w": 0.16,  # 어깨 반폭
    "hip_w": 0.11,       # 골반 반폭
    "head_drop": 0.12,   # 머리가 어깨로 내려앉는 정도
}


def _p():
    p = dict(PARAMS)
    argv = sys.argv
    if "--" in argv:
        rest = argv[argv.index("--") + 1:]
        if len(rest) >= 2:
            try:
                p.update(json.loads(open(rest[1]).read()))
            except Exception as e:  # noqa: BLE001
                print(f"[build_zolaman] params 로드 실패: {e}")
    return p


def _clear():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for blk in (bpy.data.meshes, bpy.data.materials, bpy.data.armatures):
        for b in list(blk):
            blk.remove(b)


def _toon_mat(name="MascotBody", color=(1.0, 0.56, 0.78, 1.0)):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    b = nt.nodes.new("ShaderNodeBsdfPrincipled")
    b.inputs["Base Color"].default_value = color
    b.inputs["Roughness"].default_value = 0.9
    for k in ("Subsurface Weight", "Subsurface"):
        if k in b.inputs:
            b.inputs[k].default_value = 0.16
            break
    if "Subsurface Radius" in b.inputs:
        b.inputs["Subsurface Radius"].default_value = (0.2, 0.15, 0.15)
    nt.links.new(b.outputs["BSDF"], out.inputs["Surface"])
    return mat


def _flat_mat(name, color):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    b = nt.nodes.new("ShaderNodeBsdfPrincipled")
    b.inputs["Base Color"].default_value = (*color, 1.0)
    b.inputs["Roughness"].default_value = 0.7
    nt.links.new(b.outputs["BSDF"], out.inputs["Surface"])
    return mat


def _smooth(o):
    for poly in o.data.polygons:
        poly.use_smooth = True


def _subsurf(o, lv=2):
    m = o.modifiers.new("Subsurf", "SUBSURF")
    m.levels = lv
    m.render_levels = lv


def _noodle(name, root, tip, r_root, r_tip, mat):
    """root→tip 둥근 누들(Skin+Subsurf). 오브젝트 원점=root(회전 중심)."""
    mesh = bpy.data.meshes.new(name)
    o = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(o)
    rel = Vector(tip) - Vector(root)
    mesh.from_pydata([(0, 0, 0), tuple(rel)], [(0, 1)], [])
    mesh.update()
    sk = o.modifiers.new("Skin", "SKIN")
    sk.use_smooth_shade = True
    sv = mesh.skin_vertices[0].data
    sv[0].radius = (r_root, r_root)
    sv[1].radius = (r_tip, r_tip)
    _subsurf(o)
    o.location = Vector(root)
    if mat:
        o.data.materials.append(mat)
    return o


def _eye(name, pos, head_r):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=20, ring_count=12, radius=head_r * 0.22)
    o = bpy.context.active_object
    o.name = name
    o.scale = (0.82, 0.45, 1.05)
    o.location = pos
    _smooth(o)
    return o


def _mouth(name, kind, head_r):
    if kind == "smile":
        bpy.ops.mesh.primitive_uv_sphere_add(radius=head_r * 0.24)
        o = bpy.context.active_object
        o.scale = (1.0, 0.25, 0.5)
    elif kind == "shock":
        bpy.ops.mesh.primitive_uv_sphere_add(radius=head_r * 0.13)
        o = bpy.context.active_object
        o.scale = (1.0, 0.3, 1.15)
    else:
        bpy.ops.mesh.primitive_cube_add(size=1.0)
        o = bpy.context.active_object
        o.scale = (head_r * 0.20, head_r * 0.06, head_r * 0.03)
    o.name = name
    _smooth(o)
    return o


def build(p):
    _clear()
    body_mat = _toon_mat()
    eye_mat = _flat_mat("MascotEye", (0.06, 0.06, 0.07))
    olive = _flat_mat("PropOlive", (0.36, 0.41, 0.24))
    blackhat = _flat_mat("PropHat", (0.16, 0.14, 0.13))
    redbag = _flat_mat("PropBag", (0.82, 0.27, 0.25))

    head_r = p["head_r"]
    leg_len, torso_len = p["leg_len"], p["torso_len"]
    hip_z = leg_len
    shoulder_z = leg_len + torso_len
    head_cz = shoulder_z + head_r * (1.0 - p["head_drop"])
    front_y = -head_r * 0.95

    # 머리(둥근 공) = 메인. 발 원점을 위해 body로 명명하고 origin을 발로.
    bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, radius=head_r)
    head = bpy.context.active_object
    head.name = "body"
    head.location = (0, 0, head_cz)
    _subsurf(head)
    _smooth(head)
    head.data.materials.append(body_mat)
    bpy.ops.object.transform_apply(location=True)  # 메시에 위치 적용
    bpy.context.scene.cursor.location = (0, 0, 0)
    bpy.ops.object.origin_set(type="ORIGIN_CURSOR")   # 원점=발(0,0,0)

    # 몸통(가는 막대 누들): 골반→어깨
    torso = _noodle("torso", (0, 0, hip_z), (0, 0, shoulder_z + head_r * 0.15),
                    p["torso_r"], p["torso_r"] * 0.95, body_mat)

    lr = p["limb_r"]
    # 팔: 어깨에서 바깥-아래
    arms = [
        _noodle("arm_L", (-p["shoulder_w"], 0, shoulder_z), (-p["shoulder_w"] - p["arm_len"] * 0.7, 0, shoulder_z - p["arm_len"] * 0.7), lr, lr * 0.82, body_mat),
        _noodle("arm_R", (p["shoulder_w"], 0, shoulder_z), (p["shoulder_w"] + p["arm_len"] * 0.7, 0, shoulder_z - p["arm_len"] * 0.7), lr, lr * 0.82, body_mat),
    ]
    # 다리: 골반에서 아래
    legs = [
        _noodle("leg_L", (-p["hip_w"], 0, hip_z), (-p["hip_w"] - 0.04, 0, 0.0), lr, lr * 0.9, body_mat),
        _noodle("leg_R", (p["hip_w"], 0, hip_z), (p["hip_w"] + 0.04, 0, 0.0), lr, lr * 0.9, body_mat),
    ]

    # 얼굴
    eyes = [_eye("eye_L", (-head_r * 0.36, front_y, head_cz + head_r * 0.10), head_r),
            _eye("eye_R", (head_r * 0.36, front_y, head_cz + head_r * 0.10), head_r)]
    for e in eyes:
        e.data.materials.append(eye_mat)
    mouths = []
    for kind in ("smile", "neutral", "shock"):
        m = _mouth(f"mouth_{kind}", kind, head_r)
        m.location = (0, front_y, head_cz - head_r * 0.30)
        m.data.materials.append(eye_mat)
        m.hide_render = (kind != "neutral")
        mouths.append(m)

    # 소품
    bpy.ops.mesh.primitive_uv_sphere_add(radius=head_r * 0.92)
    beret = bpy.context.active_object
    beret.name = "prop_beret"
    beret.scale = (1.05, 1.05, 0.4)
    beret.location = (head_r * 0.1, 0, head_cz + head_r * 0.7)
    beret.rotation_euler = (math.radians(-12), 0, 0)
    _smooth(beret)
    beret.data.materials.append(olive)

    bpy.ops.mesh.primitive_cylinder_add(radius=head_r * 0.5, depth=head_r * 0.62)
    hat = bpy.context.active_object
    hat.name = "prop_hat"
    hat.location = (0, 0, head_cz + head_r * 0.92)
    hat.data.materials.append(blackhat)
    bpy.ops.mesh.primitive_cylinder_add(radius=head_r * 1.05, depth=head_r * 0.07)
    brim = bpy.context.active_object
    brim.location = (0, 0, head_cz + head_r * 0.62)
    brim.data.materials.append(blackhat)
    brim.parent = hat

    bpy.ops.mesh.primitive_cube_add(size=1.0)
    bag = bpy.context.active_object
    bag.name = "prop_bag"
    bag.scale = (head_r * 0.42, head_r * 0.22, head_r * 0.4)
    bag.location = (0, front_y * 1.2, shoulder_z * 0.55)
    bpy.ops.object.modifier_add(type="BEVEL")
    bag.modifiers["Bevel"].width = 0.03
    _smooth(bag)
    bag.data.materials.append(redbag)

    for prop in (beret, hat, bag):
        prop.hide_render = True
        prop.hide_viewport = True

    # 부모 = head(body). 포즈/이동 시 함께.
    for ch in [torso, *arms, *legs, *eyes, *mouths, beret, hat, bag]:
        ch.parent = head
        ch.matrix_parent_inverse = head.matrix_world.inverted()

    # 월드 앰비언트 + 조명(렌더 스크립트가 카메라만 재설정)
    world = bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
    bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs["Color"].default_value = (0.62, 0.66, 0.72, 1.0)
        bg.inputs["Strength"].default_value = 0.55
    bpy.ops.object.light_add(type="AREA", location=(-2.5, -5, 6))
    k = bpy.context.active_object
    k.data.energy = 1200
    k.data.size = 8
    k.rotation_euler = (math.radians(30), 0, math.radians(-18))
    bpy.ops.object.light_add(type="AREA", location=(4, -4, 3))
    f = bpy.context.active_object
    f.data.energy = 450
    f.data.size = 9
    bpy.ops.object.camera_add(location=(0, -8, head_cz * 0.6), rotation=(math.radians(90), 0, 0))
    cam = bpy.context.active_object
    cam.name = "MascotCam"
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = 4.0
    bpy.context.scene.camera = cam
    total_h = head_cz + head_r
    print(f"[build_zolaman] 완료 head_r={head_r} total_h={total_h:.2f}")
    return total_h


def main():
    argv = sys.argv
    out = argv[argv.index("--") + 1] if "--" in argv else "assets/mascot/mascot.blend"
    build(_p())
    bpy.ops.wm.save_as_mainfile(filepath=out)
    print(f"[build_zolaman] 저장: {out}")


if __name__ == "__main__":
    main()

"""오리지널 둥근 블롭 마스코트를 절차적으로 만들어 mascot.blend로 저장한다(1회 실행).

Blender 내부에서 실행:
    blender --background --python assets/mascot/build_mascot.py -- assets/mascot/mascot.blend

구성(에이전트 친화 절차적):
- body: 달걀형(머리+몸 융합, 목 없음) UV 구 + Subdivision Surface. 발이 z=0(원점은 발).
- 팔다리: 정점 체인 + Skin + Subsurf 누들 4개. 각 오브젝트 원점=어깨/골반(렌더 시 회전=포즈).
- 얼굴: 눈 2개(검정 납작 구) + 입 변형 3종(smile/neutral/shock) 토글 자식.
- 소품: prop_beret / prop_hat / prop_bag (기본 hide_render). 머리/몸에 parent.
- 머티리얼: MascotBody(Principled, 무광 + 약한 SSS) — 렌더 스크립트가 base color override.
  눈/입은 검정, 소품은 자체 색.

원본 캐릭터를 복제하지 않는 일반 블롭 마스코트다(사용자 채널용 오리지널 에셋).
"""
import math
import sys

import bpy
from mathutils import Vector

# ---- 치수(블렌더 단위; 발 z=0 기준) — 세로로 긴 달걀(머리 우세) ----
BODY_H = 2.2                    # 발→머리top 높이
BODY_W = BODY_H * 0.46          # 몸 폭(세로보다 좁게 = 달걀형)
HEAD_R = BODY_W * 0.62
LIMB_R = BODY_W * 0.20          # 팔다리 굵기(루트, 잘 보이게 두껍게)


def _clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for block in (bpy.data.meshes, bpy.data.materials, bpy.data.armatures):
        for b in list(block):
            block.remove(b)


def _toon_material(name="MascotBody", color=(1.0, 0.56, 0.78, 1.0)):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = 0.9          # 무광
    # Subsurface(버전별 입력명 차이 방어)
    for key in ("Subsurface Weight", "Subsurface"):
        if key in bsdf.inputs:
            bsdf.inputs[key].default_value = 0.18
            break
    if "Subsurface Radius" in bsdf.inputs:
        bsdf.inputs["Subsurface Radius"].default_value = (0.25, 0.18, 0.18)
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.25
    elif "Specular" in bsdf.inputs:
        bsdf.inputs["Specular"].default_value = 0.25
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def _flat_material(name, color):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.7
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def _add_subsurf(obj, levels=2, render_levels=2):
    m = obj.modifiers.new("Subsurf", "SUBSURF")
    m.levels = levels
    m.render_levels = render_levels


def _shade_smooth(obj):
    for p in obj.data.polygons:
        p.use_smooth = True


def _make_body(mat):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, radius=1.0)
    obj = bpy.context.active_object
    obj.name = "body"
    # 달걀형: 세로(z)로 길고 가로(x/y)는 좁게 → 서있는 블롭
    obj.scale = (BODY_W, BODY_W * 0.82, BODY_H * 0.5)
    bpy.ops.object.transform_apply(scale=True)
    # 발이 z=0: 구 바닥이 -BODY_H*0.5 → 위로 올림
    obj.location.z = BODY_H * 0.5
    bpy.ops.object.transform_apply(location=True)
    # 원점을 발(바닥 중앙)로
    bpy.context.scene.cursor.location = (0, 0, 0)
    bpy.ops.object.origin_set(type="ORIGIN_CURSOR")
    _add_subsurf(obj)
    _shade_smooth(obj)
    obj.data.materials.append(mat)
    return obj


def _make_noodle(name, root, tip, r_root, r_tip, mat):
    """root→tip 직선 누들(Skin+Subsurf). 오브젝트 원점=root(회전 중심)."""
    mesh = bpy.data.meshes.new(name)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    rel_tip = Vector(tip) - Vector(root)
    verts = [(0, 0, 0), tuple(rel_tip)]
    mesh.from_pydata(verts, [(0, 1)], [])
    mesh.update()
    skin = obj.modifiers.new("Skin", "SKIN")
    skin.use_smooth_shade = True
    sv = mesh.skin_vertices[0].data
    sv[0].radius = (r_root, r_root)
    sv[1].radius = (r_tip, r_tip)
    _add_subsurf(obj)
    obj.location = Vector(root)
    obj.data.materials.append(mat)
    return obj


def _make_eye(name, pos):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=20, ring_count=12, radius=HEAD_R * 0.22)
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = (0.85, 0.4, 1.25)          # 세로로 큰 눈(살짝 납작 돌출)
    obj.location = pos
    _shade_smooth(obj)
    return obj


def _make_mouth(name, kind):
    """입 변형: smile(아래 반달 채움)/neutral(가는 선)/shock(작은 타원)."""
    if kind == "smile":
        bpy.ops.mesh.primitive_uv_sphere_add(radius=HEAD_R * 0.22)
        o = bpy.context.active_object
        o.scale = (1.0, 0.25, 0.55)
    elif kind == "shock":
        bpy.ops.mesh.primitive_uv_sphere_add(radius=HEAD_R * 0.12)
        o = bpy.context.active_object
        o.scale = (1.0, 0.3, 1.2)
    else:  # neutral
        bpy.ops.mesh.primitive_cube_add(size=1.0)
        o = bpy.context.active_object
        o.scale = (HEAD_R * 0.20, HEAD_R * 0.06, HEAD_R * 0.03)
    o.name = name
    _shade_smooth(o)
    return o


def _make_beret(mat):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=HEAD_R * 0.9)
    o = bpy.context.active_object
    o.name = "prop_beret"
    o.scale = (1.05, 1.05, 0.42)
    _shade_smooth(o)
    o.data.materials.append(mat)
    return o


def _make_hat(mat):
    bpy.ops.mesh.primitive_cylinder_add(radius=HEAD_R * 0.55, depth=HEAD_R * 0.7)
    crown = bpy.context.active_object
    crown.name = "prop_hat"
    crown.data.materials.append(mat)
    bpy.ops.mesh.primitive_cylinder_add(radius=HEAD_R * 1.15, depth=HEAD_R * 0.08)
    brim = bpy.context.active_object
    brim.location.z = -HEAD_R * 0.34
    brim.data.materials.append(mat)
    brim.parent = crown
    _shade_smooth(crown)
    _shade_smooth(brim)
    return crown


def _make_bag(mat):
    bpy.ops.mesh.primitive_cube_add(size=1.0)
    o = bpy.context.active_object
    o.name = "prop_bag"
    o.scale = (BODY_W * 0.5, BODY_W * 0.25, BODY_W * 0.45)
    bpy.ops.object.modifier_add(type="BEVEL")
    o.modifiers["Bevel"].width = 0.05
    _shade_smooth(o)
    o.data.materials.append(mat)
    return o


def build():
    _clear_scene()
    body_mat = _toon_material("MascotBody")
    eye_mat = _flat_material("MascotEye", (0.06, 0.06, 0.07))
    olive = _flat_material("PropOlive", (0.36, 0.41, 0.24))
    blackhat = _flat_material("PropHat", (0.16, 0.14, 0.13))
    redbag = _flat_material("PropBag", (0.82, 0.27, 0.25))

    body = _make_body(body_mat)
    head_z = BODY_H - HEAD_R * 0.9         # 머리 중심 높이
    front_y = -BODY_W * 0.85               # 카메라(−Y)쪽 얼굴면

    # 팔다리 (원점=어깨/골반) — 길고 잘 보이게(누들 블롭 식)
    sh_z, hip_z = BODY_H * 0.52, BODY_H * 0.26
    limbs = [
        _make_noodle("arm_L", (-BODY_W * 0.92, 0, sh_z), (-BODY_W * 1.5, 0, sh_z - 0.62), LIMB_R, LIMB_R * 0.78, body_mat),
        _make_noodle("arm_R", (BODY_W * 0.92, 0, sh_z), (BODY_W * 1.5, 0, sh_z - 0.62), LIMB_R, LIMB_R * 0.78, body_mat),
        _make_noodle("leg_L", (-BODY_W * 0.42, 0, hip_z), (-BODY_W * 0.48, 0, -0.02), LIMB_R, LIMB_R * 0.85, body_mat),
        _make_noodle("leg_R", (BODY_W * 0.42, 0, hip_z), (BODY_W * 0.48, 0, -0.02), LIMB_R, LIMB_R * 0.85, body_mat),
    ]

    # 얼굴
    eyes = [
        _make_eye("eye_L", (-HEAD_R * 0.38, front_y, head_z + HEAD_R * 0.05)),
        _make_eye("eye_R", (HEAD_R * 0.38, front_y, head_z + HEAD_R * 0.05)),
    ]
    for e in eyes:
        e.data.materials.append(eye_mat)
    mouths = []
    for kind in ("smile", "neutral", "shock"):
        m = _make_mouth(f"mouth_{kind}", kind)
        m.location = (0, front_y, head_z - HEAD_R * 0.34)
        m.data.materials.append(eye_mat)
        m.hide_render = (kind != "neutral")
        mouths.append(m)

    # 소품(기본 hide)
    beret = _make_beret(olive); beret.location = (HEAD_R * 0.12, 0, head_z + HEAD_R * 0.55)
    beret.rotation_euler = (math.radians(-12), 0, 0)
    hat = _make_hat(blackhat); hat.location = (0, 0, head_z + HEAD_R * 0.7)
    bag = _make_bag(redbag); bag.location = (0, front_y * 1.1, BODY_H * 0.42)
    for p in (beret, hat, bag):
        p.hide_render = True
        p.hide_viewport = True

    # 부모 관계: 전부 body 자식(포즈/이동 시 함께)
    for child in [*limbs, *eyes, *mouths, beret, hat, bag]:
        child.parent = body
        child.matrix_parent_inverse = body.matrix_world.inverted()

    # 월드 앰비언트(검정 그림자 방지 — 부드러운 무광 룩의 핵심)
    world = bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
    bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs["Color"].default_value = (0.62, 0.66, 0.72, 1.0)
        bg.inputs["Strength"].default_value = 0.55

    # 카메라(렌더 스크립트가 재설정; .blend 미리보기용 기본값)
    bpy.ops.object.camera_add(location=(0, -8, BODY_H * 0.55), rotation=(math.radians(90), 0, 0))
    cam = bpy.context.active_object
    cam.name = "MascotCam"
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = 4.0
    bpy.context.scene.camera = cam

    # 정면 위쪽 키라이트(머리 위까지 밝게) + 측면 필 + 림
    bpy.ops.object.light_add(type="AREA", location=(-2.5, -5, 7))
    key = bpy.context.active_object
    key.data.energy = 1400
    key.data.size = 9
    key.rotation_euler = (math.radians(28), 0, math.radians(-18))
    bpy.ops.object.light_add(type="AREA", location=(4, -4, 3))
    fill = bpy.context.active_object
    fill.data.energy = 500
    fill.data.size = 10
    bpy.ops.object.light_add(type="AREA", location=(0, 4, 6))
    rim = bpy.context.active_object
    rim.data.energy = 600
    rim.data.size = 6

    print(f"[build_mascot] 구성 완료: body+limbs{len(limbs)}+eyes{len(eyes)}+mouths{len(mouths)}+props3")


def main():
    argv = sys.argv
    out = argv[argv.index("--") + 1] if "--" in argv else "assets/mascot/mascot.blend"
    build()
    bpy.ops.wm.save_as_mainfile(filepath=out)
    print(f"[build_mascot] 저장: {out}")


if __name__ == "__main__":
    main()

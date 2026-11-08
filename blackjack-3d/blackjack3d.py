"""
Blackjack 3D - Blender renderer for the interactive blackjack series.

For one hand (see hands.py) it renders the 3D plates the composer needs:

  intro   still   low "chip-level" casino shot before the deal (wide lens, 108% overscan)
  crane   frames  camera cranes up from the intro shot while the 4 cards are dealt
  hold    still   top shot with the 4 cards (110% overscan for the 2D push-in)
  hit     frames  HIT branch seen from the hold camera; only frames where something moves
  stand   frames  STAND branch, same

Everything (table, felt print, cards, chips, shoe, casino background, lights,
camera) is built from code. Runs headless:

  blender -b -P blackjack3d.py -- --shots plates                 # shared plates (once)
  blender -b -P blackjack3d.py -- --hand 1                       # one hand
  blender -b -P blackjack3d.py -- --hand 1 --shots hold --res 30 --samples 12   # preview

Output: render/hand01/{intro.png, crane/####.png, hold.png, hit/####.png,
stand/####.png, meta.json}. Frames that already exist are skipped, so an
interrupted render can simply be started again.
"""
import argparse
import json
import math
import os
import random
import sys
import time

import bpy  # noqa: E402  (bpy must be imported before bmesh when run as a module)
import bmesh
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Euler, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import hands as H  # noqa: E402

TEX_DIR = os.path.join(HERE, "textures")
CW, CH = H.CW, H.CH
TABLE_C = Vector((0.0, 0.55))       # centre of the semicircular table (dealer side)
BET_POS = Vector(H.BET_POS)

# camera presets: target, elevation, distance, azimuth (deg), f-stop
LOW = dict(t=(-0.04, 0.0, 0.0), el=9.0, d=0.40, az=-14.0, fs=2.8)
HOLD = dict(t=(0.0, 0.06, 0.0), el=55.0, d=0.79, az=0.0, fs=7.0)
LENS = 50.0
INTRO_WIDE = 1.08     # intro still: wider lens + same factor of extra pixels
HOLD_OVERSCAN = 1.10  # hold / outcome plates: extra pixels for the 2D push-in
BET_COLORS = ["red", "black", "green", "blue", "purple"]


# ----------------------------------------------------------------------------- args
def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser(description="Render the 3D plates for one blackjack hand")
    p.add_argument("--hand", type=int, default=1, help="hand number (1-based, see hands.py)")
    p.add_argument("--shots", default="hold,crane,hit,stand", help="plates | hold,crane,hit,stand")
    p.add_argument("--samples", type=int, default=32)
    p.add_argument("--res", type=int, default=100, help="resolution percent (30 = preview)")
    p.add_argument("--device", default="AUTO", help="AUTO, OPTIX, CUDA, HIP, ONEAPI, METAL or CPU")
    p.add_argument("--out", default=os.path.join(HERE, "render"))
    p.add_argument("--frames", default="", help="only these frames (testing), e.g. 0,30,59")
    p.add_argument("--save-blend", action="store_true")
    return p.parse_args(argv)


# ----------------------------------------------------------------------------- math
def clamp(v, a=0.0, b=1.0):
    return max(a, min(b, v))


def lerp(a, b, t):
    return a + (b - a) * t


def smooth(t):
    t = clamp(t)
    return t * t * t * (t * (t * 6 - 15) + 10)


def ease_out(t):
    t = clamp(t)
    return 1 - (1 - t) ** 3


def ease_in_out(t):
    t = clamp(t)
    return 4 * t ** 3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


def bezier(a, b, c, d, t):
    u = 1 - t
    return a * u ** 3 + b * (3 * u * u * t) + c * (3 * u * t * t) + d * t ** 3


def srgb(h, a=1.0):
    h = h.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c) + (a,)


# ----------------------------------------------------------------------------- nodes
def feed(nt, socket, value):
    if isinstance(value, bpy.types.NodeSocket):
        nt.links.new(value, socket)
    else:
        if socket.type == "RGBA" and len(value) == 3:
            value = (*value, 1.0)
        socket.default_value = value


def math_node(nt, op, a, b=None):
    n = nt.nodes.new("ShaderNodeMath")
    n.operation = op
    feed(nt, n.inputs[0], a)
    if b is not None:
        feed(nt, n.inputs[1], b)
    return n.outputs[0]


def mix_rgb(nt, fac, a, b):
    n = nt.nodes.new("ShaderNodeMix")
    n.data_type = "RGBA"
    cols = [s for s in n.inputs if s.type == "RGBA"]
    feed(nt, n.inputs[0], fac)
    feed(nt, cols[0], a)
    feed(nt, cols[1], b)
    return [s for s in n.outputs if s.type == "RGBA"][0]


def enable_nodes(idblock):
    if bpy.app.version < (5, 0, 0):      # node trees are always on from Blender 5
        idblock.use_nodes = True


def new_material(name):
    m = bpy.data.materials.new(name)
    enable_nodes(m)
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(bsdf.outputs[0], out.inputs["Surface"])
    return m, nt, bsdf


def setin(bsdf, name, value):
    s = bsdf.inputs.get(name)
    if s is not None:
        feed(bsdf.id_data, s, value)


def simple_mat(name, color, rough=0.5, metal=0.0, coat=0.0, coat_rough=0.08):
    m, nt, b = new_material(name)
    setin(b, "Base Color", color)
    setin(b, "Roughness", rough)
    setin(b, "Metallic", metal)
    if coat:
        setin(b, "Coat Weight", coat)
        setin(b, "Coat Roughness", coat_rough)
    return m


def emit_mat(name, color, strength, sampled=False):
    """Pure emitter. Background emitters are not sampled as lights (huge speed-up):
    they still show up directly and in reflections, they just do not light the table."""
    m = bpy.data.materials.new(name)
    enable_nodes(m)
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = color
    em.inputs["Strength"].default_value = strength
    nt.links.new(em.outputs[0], out.inputs["Surface"])
    if not sampled:
        try:
            m.cycles.emission_sampling = "NONE"
        except Exception:
            pass
    return m


def felt_mat():
    m, nt, b = new_material("felt")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    fibres = nt.nodes.new("ShaderNodeTexNoise")
    fibres.inputs["Scale"].default_value = 2600
    fibres.inputs["Detail"].default_value = 2
    nt.links.new(tc.outputs["Object"], fibres.inputs["Vector"])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.18
    bump.inputs["Distance"].default_value = 0.0004
    nt.links.new(fibres.outputs["Fac"], bump.inputs["Height"])
    blotch = nt.nodes.new("ShaderNodeTexNoise")
    blotch.inputs["Scale"].default_value = 5
    blotch.inputs["Detail"].default_value = 3
    nt.links.new(tc.outputs["Object"], blotch.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.35
    ramp.color_ramp.elements[0].color = srgb("#073a20")
    ramp.color_ramp.elements[1].position = 0.65
    ramp.color_ramp.elements[1].color = srgb("#0c5530")
    nt.links.new(blotch.outputs["Fac"], ramp.inputs["Fac"])
    setin(b, "Base Color", ramp.outputs["Color"])
    setin(b, "Roughness", 0.95)
    setin(b, "Sheen Weight", 0.12)
    setin(b, "Sheen Roughness", 0.35)
    setin(b, "Normal", bump.outputs["Normal"])
    return m


def leather_mat():
    m, nt, b = new_material("leather")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    grain = nt.nodes.new("ShaderNodeTexNoise")
    grain.inputs["Scale"].default_value = 700
    nt.links.new(tc.outputs["Object"], grain.inputs["Vector"])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.08
    nt.links.new(grain.outputs["Fac"], bump.inputs["Height"])
    setin(b, "Base Color", srgb("#1c110c"))
    setin(b, "Roughness", 0.42)
    setin(b, "Coat Weight", 0.35)
    setin(b, "Coat Roughness", 0.18)
    setin(b, "Normal", bump.outputs["Normal"])
    return m


def chip_mat(name, base, stripe):
    """Casino chip: edge spots, lighter centre inlay, dark seams between stacked chips.
    Works for single chips and for long 'columns' (chip count must be odd)."""
    m, nt, b = new_material(name)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Object"], sep.inputs[0])
    comb = nt.nodes.new("ShaderNodeCombineXYZ")
    nt.links.new(sep.outputs[0], comb.inputs[0])
    nt.links.new(sep.outputs[1], comb.inputs[1])
    vl = nt.nodes.new("ShaderNodeVectorMath")
    vl.operation = "LENGTH"
    nt.links.new(comb.outputs[0], vl.inputs[0])
    r = vl.outputs["Value"]
    grad = nt.nodes.new("ShaderNodeTexGradient")
    grad.gradient_type = "RADIAL"
    nt.links.new(tc.outputs["Object"], grad.inputs["Vector"])
    spots = math_node(nt, "GREATER_THAN", math_node(nt, "FRACT", math_node(nt, "MULTIPLY", grad.outputs["Fac"], 6)), 0.62)
    ring = math_node(nt, "GREATER_THAN", r, 0.0158)
    inlay = math_node(nt, "LESS_THAN", r, 0.0122)
    inlay_rim = math_node(nt, "MULTIPLY", math_node(nt, "GREATER_THAN", r, 0.0118), inlay)
    side = math_node(nt, "GREATER_THAN", r, 0.0191)
    seam = math_node(nt, "LESS_THAN", math_node(nt, "FRACT", math_node(nt, "ADD", math_node(nt, "DIVIDE", sep.outputs[2], 0.0033), 0.5)), 0.08)
    lighter = tuple(lerp(c, 1.0, 0.55) for c in base[:3]) + (1.0,)
    c = mix_rgb(nt, math_node(nt, "MULTIPLY", spots, ring), base, stripe)
    c = mix_rgb(nt, inlay, c, lighter)
    c = mix_rgb(nt, inlay_rim, c, stripe)
    c = mix_rgb(nt, math_node(nt, "MULTIPLY", seam, side), c, (0.02, 0.02, 0.02, 1.0))
    setin(b, "Base Color", c)
    setin(b, "Roughness", 0.38)
    setin(b, "Coat Weight", 0.25)
    setin(b, "Coat Roughness", 0.12)
    return m


_card_mats = {}


def card_mat(code):
    if code in _card_mats:
        return _card_mats[code]
    path = os.path.join(TEX_DIR, code + ".png")
    if not os.path.exists(path):
        raise SystemExit(f"Card texture not found: {path}  (codes look like 10S, AH, KD, 7C)")
    m, nt, b = new_material("card_" + code)
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(path, check_existing=True)
    tex.extension = "CLIP"
    tex.interpolation = "Cubic"
    nt.links.new(tex.outputs["Color"], b.inputs["Base Color"])
    nt.links.new(tex.outputs["Alpha"], b.inputs["Alpha"])
    setin(b, "Roughness", 0.32)
    setin(b, "Coat Weight", 0.18)
    setin(b, "Coat Roughness", 0.1)
    for attr, val in (("blend_method", "HASHED"), ("surface_render_method", "DITHERED")):
        try:
            setattr(m, attr, val)
        except Exception:
            pass
    _card_mats[code] = m
    return m


# ----------------------------------------------------------------------------- objects
def link(ob):
    bpy.context.scene.collection.objects.link(ob)
    return ob


def obj_from_bm(name, bm, mat=None):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    if mat:
        me.materials.append(mat)
    return link(bpy.data.objects.new(name, me))


def obj_from_data(name, verts, faces, mat=None):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    if mat:
        me.materials.append(mat)
    return link(bpy.data.objects.new(name, me))


def box(name, size, loc, mat, rot_z=0.0):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co.x *= size[0]
        v.co.y *= size[1]
        v.co.z *= size[2]
    ob = obj_from_bm(name, bm, mat)
    ob.location = loc
    ob.rotation_euler.z = rot_z
    return ob


def sphere(name, r, loc, mat):
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=1, radius=r)
    for f in bm.faces:
        f.smooth = True
    ob = obj_from_bm(name, bm, mat)
    ob.location = loc
    return ob


def chip_mesh(name, depth, mat, r=0.0195):
    """Cylinder with real bevelled edges: flat caps, smooth sides."""
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=48,
                          radius1=r, radius2=r, depth=depth)
    bm.normal_update()
    rim = [e for e in bm.edges if len(e.link_faces) == 2 and
           abs(e.link_faces[0].normal.z - e.link_faces[1].normal.z) > 0.5]
    bmesh.ops.bevel(bm, geom=rim, offset=0.0005, segments=2, profile=0.5, affect="EDGES")
    bm.normal_update()
    for f in bm.faces:
        f.smooth = abs(f.normal.z) < 0.999
    return obj_from_bm(name, bm, mat)


def chip_stack(name, pos, colors, rng, parent=None):
    obs = []
    for i, mat in enumerate(colors):
        ob = chip_mesh(f"{name}_{i}", 0.0033, MATS[mat])
        ob.location = (pos[0] + rng.uniform(-0.0009, 0.0009),
                       pos[1] + rng.uniform(-0.0009, 0.0009), 0.00165 + i * 0.0033)
        ob.rotation_euler.z = rng.uniform(0, math.tau)
        if parent:
            ob.parent = parent
        obs.append(ob)
    return obs


CARD_BOW = 0.0004   # edges lift this much (m): real cards are never perfectly flat


def card_obj(name, code):
    """Two-sided, slightly bowed card: face texture on +Z, back texture on -Z,
    transparent rounded corners come from the PNG alpha."""
    n, t = 12, 0.00015
    verts, faces = [], []
    for side in (1, -1):
        for i in range(n + 1):
            x = -CW / 2 + CW * i / n
            z = side * t + CARD_BOW * (2 * x / CW) ** 2
            verts += [(x, -CH / 2, z), (x, CH / 2, z)]
    off = 2 * (n + 1)
    for i in range(n):
        a, b = 2 * i, 2 * i + 2
        faces.append((a, b, b + 1, a + 1))                          # front (+Z)
        faces.append((off + a + 1, off + b + 1, off + b, off + a))  # back (-Z)
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    uv = me.uv_layers.new(name="UVMap")
    for poly in me.polygons:
        front = poly.index % 2 == 0
        poly.material_index = 0 if front else 1
        poly.use_smooth = True
        for li in poly.loop_indices:
            x, y, _ = me.vertices[me.loops[li].vertex_index].co
            uv.data[li].uv = ((0.5 + x / CW) if front else (0.5 - x / CW), 0.5 + y / CH)
    me.materials.append(card_mat(code) if code else card_mat("back"))
    me.materials.append(card_mat("back"))
    return link(bpy.data.objects.new(name, me))


def arc_band(name, center, radius, width, a0, a1, mat, z=0.0003, n=160):
    verts, faces = [], []
    for i in range(n + 1):
        a = math.radians(lerp(a0, a1, i / n))
        for rr in (radius - width / 2, radius + width / 2):
            verts.append((center.x + rr * math.cos(a), center.y + rr * math.sin(a), z))
    for i in range(n):
        faces.append((2 * i, 2 * i + 1, 2 * i + 3, 2 * i + 2))
    return obj_from_data(name, verts, faces, mat)


def arc_text(body, radius, size, mat, spacing=1.12, z=0.00035):
    """Text printed on the felt, bent along an arc concentric with the table."""
    cu = bpy.data.curves.new("txt", "FONT")
    cu.body = body
    cu.size = size
    cu.align_x = "CENTER"
    cu.align_y = "CENTER"
    cu.space_character = spacing
    tmp = link(bpy.data.objects.new("tmp_txt", cu))
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(tmp.evaluated_get(dg))
    bpy.data.objects.remove(tmp)
    bpy.data.curves.remove(cu)
    for v in me.vertices:
        th = 1.5 * math.pi + v.co.x / radius
        r = radius - v.co.y
        v.co = (TABLE_C.x + r * math.cos(th), TABLE_C.y + r * math.sin(th), z)
    me.materials.append(mat)
    return link(bpy.data.objects.new(body, me))


def light(name, kind, loc, energy, color, aim=None, **props):
    ld = bpy.data.lights.new(name, kind)
    ld.energy = energy
    ld.color = color
    for k, v in props.items():
        setattr(ld, k, v)
    ob = link(bpy.data.objects.new(name, ld))
    ob.location = loc
    if aim is not None:
        ob.rotation_euler = (Vector(aim) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    return ob


# ----------------------------------------------------------------------------- scene
MATS = {}
SHOE_YAW = 0.0
DEAL_FROM = Vector()


def build_materials():
    MATS.clear()
    _card_mats.clear()
    MATS["felt"] = felt_mat()
    MATS["leather"] = leather_mat()
    MATS["wood"] = simple_mat("wood", srgb("#2a140a"), rough=0.35, coat=0.6)
    MATS["gold_ink"] = simple_mat("gold_ink", srgb("#c9a24a"), rough=0.5, metal=0.45)
    MATS["white_ink"] = simple_mat("white_ink", srgb("#d9d4c3"), rough=0.8)
    MATS["shoe"] = simple_mat("shoe", srgb("#4a070d"), rough=0.15, coat=0.9)
    MATS["black_gloss"] = simple_mat("black_gloss", srgb("#0b0b0d"), rough=0.12, coat=0.9)
    MATS["card_edge"] = simple_mat("card_edge", srgb("#ece8dc"), rough=0.6)
    MATS["cabinet"] = simple_mat("cabinet", srgb("#15151a"), rough=0.3, metal=0.6)
    MATS["carpet"] = simple_mat("carpet", srgb("#2a0a10"), rough=1.0)
    MATS["wall"] = simple_mat("wall", srgb("#0d0807"), rough=0.9)
    chips = {"red": ("#b3121f", "#f2efe6"), "black": ("#141416", "#e9e4d6"),
             "green": ("#0f7a3c", "#f2efe6"), "blue": ("#1846a8", "#f2efe6"),
             "purple": ("#5b1f86", "#f0c64a"), "white": ("#e8e4da", "#1846a8"),
             "yellow": ("#e0aa1c", "#141416")}
    for k, (base, stripe) in chips.items():
        MATS[k] = chip_mat("chip_" + k, srgb(base), srgb(stripe))


def build_world():
    w = bpy.data.worlds.new("World")
    bpy.context.scene.world = w
    enable_nodes(w)
    nt = w.node_tree
    nt.nodes.clear()
    bg = nt.nodes.new("ShaderNodeBackground")
    out = nt.nodes.new("ShaderNodeOutputWorld")
    bg.inputs["Color"].default_value = srgb("#0a0705")
    bg.inputs["Strength"].default_value = 0.6
    nt.links.new(bg.outputs[0], out.inputs["Surface"])


def build_table():
    n = 160
    verts = [(TABLE_C.x + 1.0 * math.cos(math.pi + math.pi * i / n),
              TABLE_C.y + 1.0 * math.sin(math.pi + math.pi * i / n), 0.0) for i in range(n + 1)]
    obj_from_data("felt", verts, [tuple(range(n + 1))], MATS["felt"])
    cu = bpy.data.curves.new("rail", "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = 0.042
    cu.bevel_resolution = 8
    cu.use_fill_caps = True
    sp = cu.splines.new("POLY")
    pts = [(TABLE_C.x + 1.035 * math.cos(math.pi + math.pi * i / 120),
            TABLE_C.y + 1.035 * math.sin(math.pi + math.pi * i / 120), 0.018) for i in range(121)]
    sp.points.add(len(pts) - 1)
    for i, p in enumerate(pts):
        sp.points[i].co = (*p, 1.0)
    sp.use_smooth = True
    cu.materials.append(MATS["leather"])
    link(bpy.data.objects.new("rail", cu))
    box("dealer_edge", (2.2, 0.08, 0.06), (0, TABLE_C.y + 0.04, -0.015), MATS["wood"])
    box("table_body", (2.2, 1.1, 0.7), (0, TABLE_C.y - 0.5, -0.4), MATS["wall"])
    gold, white = MATS["gold_ink"], MATS["white_ink"]
    arc_text("DEALER MUST DRAW TO 16 AND STAND ON ALL 17s", 0.43, 0.0085, white, spacing=1.18)
    arc_band("line_a", TABLE_C, 0.448, 0.0014, 240, 300, gold)
    arc_text("BLACKJACK PAYS 3 TO 2", 0.468, 0.0185, gold, spacing=1.08)
    arc_band("line_b", TABLE_C, 0.489, 0.0014, 238, 302, gold)
    arc_text("INSURANCE PAYS 2 TO 1", 0.505, 0.0125, gold, spacing=1.25)
    arc_band("line_c", TABLE_C, 0.52, 0.0014, 236, 304, gold)
    arc_band("bet_ring", BET_POS, H.BET_RING_R, 0.0022, 0, 360, white)


def build_props(rng):
    global SHOE_YAW, DEAL_FROM
    shoe_c = Vector((0.27, 0.43, 0.0))
    aim = Vector((-0.01, 0.07, 0.0)) - shoe_c
    aim.normalize()
    SHOE_YAW = math.atan2(aim.x, -aim.y)       # rotates local -Y onto `aim`
    box("shoe", (0.10, 0.17, 0.075), (shoe_c.x, shoe_c.y, 0.0375), MATS["shoe"], SHOE_YAW)
    lip = box("shoe_lip", (0.104, 0.02, 0.03), (0, 0, 0), MATS["black_gloss"], SHOE_YAW)
    lip.location = shoe_c + aim * 0.083 + Vector((0, 0, 0.06))
    DEAL_FROM = shoe_c + aim * 0.115 + Vector((0, 0, 0.004))
    nxt = card_obj("shoe_card", None)
    nxt.location = DEAL_FROM
    nxt.rotation_euler = (0, math.pi, SHOE_YAW)
    DEAL_FROM = DEAL_FROM + Vector((0, 0, 0.006))
    dc = Vector((-0.27, 0.43, 0.0))
    yaw = math.radians(25)
    box("discard_base", (0.09, 0.115, 0.006), (dc.x, dc.y, 0.003), MATS["black_gloss"], yaw)
    box("discard_stack", (CW - 0.002, CH - 0.002, 0.022), (dc.x, dc.y, 0.017), MATS["card_edge"], yaw)
    top = card_obj("discard_top", None)
    top.location = (dc.x, dc.y, 0.0285)
    top.rotation_euler = (0, math.pi, yaw)
    box("tray", (0.34, 0.12, 0.016), (0, 0.495, 0.004), MATS["black_gloss"])
    for i, c in enumerate(["white", "red", "green", "black", "purple", "blue", "yellow"]):
        col = chip_mesh(f"tray_{c}", 0.0033 * 33, MATS[c])
        col.location = (-0.135 + i * 0.045, 0.495, 0.0125)
        col.rotation_euler = (math.pi / 2, 0, 0)
    chip_stack("stackL1", (-0.13, -0.118), ["blue"] * 8, rng)
    chip_stack("stackL2", (-0.163, -0.082), ["purple"] * 4, rng)
    chip_stack("stackR1", (0.142, -0.122), ["black"] * 7, rng)
    chip_stack("stackR2", (0.175, -0.086), ["green"] * 5 + ["red"] * 2, rng)


def build_casino(rng):
    box("floor", (40, 40, 0.02), (0, 0, -0.77), MATS["carpet"])
    box("back_wall", (40, 0.2, 6), (0, 11, 2), MATS["wall"])
    box("ceiling", (40, 40, 0.05), (0, 0, 2.7), MATS["wall"])
    palette = ["#ff2bd6", "#19e6ff", "#ffc23a", "#ff3b30", "#8a5cff", "#ff8a1f", "#3dff8a"]
    screen_mats = [emit_mat(f"screen_{i}", srgb(c), 1.3) for i, c in enumerate(palette)]
    warm = [emit_mat(f"warm_{i}", srgb(c), s) for i, (c, s) in
            enumerate([("#ffcf7a", 30), ("#ffb347", 25), ("#ff9d5c", 22), ("#fff0c8", 40)])]
    candle = [emit_mat("candle_r", srgb("#ff2a2a"), 14), emit_mat("candle_g", srgb("#ffc23a"), 14)]
    downlight = emit_mat("downlight", srgb("#ffe2b0"), 18)
    for row_y, x0, count in ((4.2, -3.6, 12), (6.8, -4.2, 14), (9.8, -4.8, 16)):
        for i in range(count):
            x = x0 + i * 0.64 + rng.uniform(-0.02, 0.02)
            box(f"slot_{row_y}_{i}", (0.58, 0.55, 1.75), (x, row_y, -0.77 + 0.875), MATS["cabinet"])
            front = row_y - 0.28
            box(f"scr_{row_y}_{i}", (0.34, 0.01, 0.24), (x, front, 0.42), rng.choice(screen_mats))
            box(f"pan_{row_y}_{i}", (0.34, 0.01, 0.05), (x, front, 0.08), rng.choice(screen_mats))
            box(f"top_{row_y}_{i}", (0.06, 0.06, 0.22), (x, row_y, 1.10), rng.choice(candle))
    for i in range(320):
        loc = (rng.uniform(-5.0, 5.0), rng.uniform(1.8, 10.5), rng.uniform(-0.2, 2.4))
        sphere(f"glint_{i}", rng.uniform(0.006, 0.02), loc, rng.choice(warm))
    for ix in range(-3, 4):
        for iy in range(0, 8):
            box(f"down_{ix}_{iy}", (0.16, 0.16, 0.01), (ix * 1.4, 1.0 + iy * 1.4, 2.66), downlight)


KEY_POS, FILL_POS, RIM_POS = (0.08, 0.28, 1.45), (0.0, -1.7, 1.3), (0.35, 1.5, 0.5)


def build_lights():
    warm = (1.0, 0.84, 0.66)
    light("key", "SPOT", KEY_POS, 170, warm, aim=(0.0, 0.03, 0.0), spot_size=math.radians(36),
          spot_blend=1.0, shadow_soft_size=0.22)
    light("fill", "AREA", FILL_POS, 22, (1.0, 0.9, 0.8), aim=(0, 0, 0),
          shape="RECTANGLE", size=1.6, size_y=1.0)
    light("rim", "AREA", RIM_POS, 55, (1.0, 0.72, 0.48), aim=(0, -0.1, 0),
          shape="RECTANGLE", size=1.2, size_y=0.4)


def build_camera():
    sc = bpy.context.scene
    cd = bpy.data.cameras.new("cam")
    cd.lens = LENS
    cd.sensor_fit = "AUTO"
    cd.sensor_width = 36
    cd.clip_start = 0.01
    cd.clip_end = 100
    cd.dof.use_dof = True
    cam = link(bpy.data.objects.new("cam", cd))
    focus = link(bpy.data.objects.new("focus", None))
    cd.dof.focus_object = focus
    con = cam.constraints.new("TRACK_TO")
    con.target = focus
    con.track_axis = "TRACK_NEGATIVE_Z"
    con.up_axis = "UP_Y"
    sc.camera = cam
    return cam, focus


def build_scene(hand_no):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.preferences.edit.keyframe_new_interpolation_type = "LINEAR"
    rng = random.Random(21)
    build_materials()
    build_world()
    build_table()
    build_props(rng)
    build_casino(rng)
    build_lights()
    cam, focus = build_camera()
    return cam, focus, random.Random(1000)    # same bet-chip jitter in every shot and hand


# ----------------------------------------------------------------------------- camera
def cam_blend(a, b, t):
    out = {k: lerp(a[k], b[k], t) for k in ("el", "d", "az")}
    out["t"] = Vector(a["t"]).lerp(Vector(b["t"]), t)
    out["fs"] = math.exp(lerp(math.log(a["fs"]), math.log(b["fs"]), t))
    return out


def cam_pose(s):
    el, az = math.radians(s["el"]), math.radians(s["az"])
    t = Vector(s["t"])
    off = Vector((math.sin(az) * math.cos(el), -math.cos(az) * math.cos(el), math.sin(el))) * s["d"]
    return t + off, t, s["fs"]


def place_camera(cam, focus, preset, wide=1.0):
    loc, tgt, fs = cam_pose(preset)
    cam.location, focus.location = loc, tgt
    cam.data.lens = LENS / wide
    cam.data.dof.aperture_fstop = fs / wide      # keeps the blur the same after the 2D zoom


# ----------------------------------------------------------------------------- cards & chips
class Card:
    def __init__(self, name, code, slot_xy, yaw_deg, layer, face_up=True, deal_at=None, reveal_at=None):
        self.ob = card_obj(name, code)
        self.T = Vector((slot_xy[0], slot_xy[1], 0.0003 + layer * 0.0011))
        self.yaw = math.radians(yaw_deg)
        self.face_up, self.deal_at, self.reveal_at = face_up, deal_at, reveal_at
        self.apply(0)

    def apply(self, f):
        vis, loc, rot = self.pose(f)
        self.ob.location, self.ob.rotation_euler, self.ob.hide_render = loc, rot, not vis
        return vis, loc, rot

    def pose(self, f):
        if self.deal_at is not None:
            if f < self.deal_at:
                return (False, DEAL_FROM.copy(), (0.0, math.pi, SHOE_YAW))
            p = (f - self.deal_at) / H.DEAL
            if p < 1:
                e = ease_out(p)
                loc = DEAL_FROM.lerp(self.T, e)
                loc.z += 0.03 * math.sin(math.pi * e)
                yaw = lerp(SHOE_YAW, self.yaw, ease_out(p * 1.25))
                beta = math.pi * (1 - smooth((p - 0.1) / 0.7)) if self.face_up else math.pi
                loc.z += CW / 2 * abs(math.sin(beta))
                return (True, loc, (0.0, beta, yaw))
        loc = self.T.copy()
        beta = 0.0 if self.face_up else math.pi
        if self.reveal_at is not None and f >= self.reveal_at:
            q = clamp((f - self.reveal_at) / H.FLIP)
            beta = math.pi * (1 - smooth(q))
            loc.z += CW / 2 * abs(math.sin(beta)) + 0.012 * math.sin(math.pi * q)
        return (True, loc, (0.0, beta, self.yaw))


def player_card(i, code, **kw):
    return Card(f"P{i + 1}", code, H.player_slot(i), H.YAW_JITTER[i % 6], i, **kw)


def dealer_card(i, code, **kw):
    return Card(f"D{i + 1}", code, H.dealer_slot(i), H.YAW_JITTER[(i + 3) % 6] * 0.7, i, **kw)


class ChipGroup:
    """Bet stack or payout stack: an empty with chips parented to it."""

    def __init__(self, name, pos, color, rng, hidden=False):
        self.ob = link(bpy.data.objects.new(name, None))
        self.home = Vector((pos[0], pos[1], 0.0))
        self.ob.location = self.home
        self.chips = chip_stack(name, (0, 0), [color] * 5, rng, parent=self.ob)
        self.hidden0 = hidden
        self.path, self.start, self.hide_after = None, None, False

    def move(self, path, start, hide_after):
        self.path, self.start, self.hide_after = [Vector(p) for p in path], start, hide_after

    def pose(self, f):
        if self.path is None:
            return (not self.hidden0, self.home.copy())
        p = clamp((f - self.start) / H.CHIP)
        t = ease_in_out(p)
        pos = bezier(*self.path, t)
        loc = Vector((pos.x, pos.y, 0.004 * math.sin(math.pi * t)))
        if self.hidden0:                      # payout: appears when it starts moving
            return (f >= self.start, loc)
        return (not (self.hide_after and p >= 1), loc)


PAY_PATH = [(0.10, 0.48), (0.17, 0.30), (0.15, -0.08), H.PAYOUT_POS]
TAKE_PATH = [H.BET_POS, (-0.16, -0.10), (-0.17, 0.30), (-0.07, 0.47)]


# ----------------------------------------------------------------------------- keyframes
def key_scene(cards, chips, n):
    """Keys every frame. Returns per-frame lists of per-object states (to find what moves)."""
    states = []
    for f in range(n):
        sig = []
        for c in cards:
            vis, loc, rot = c.apply(f)
            for path in ("location", "rotation_euler", "hide_render"):
                c.ob.keyframe_insert(path, frame=f)
            sig.append((vis, tuple(round(v, 6) for v in loc), tuple(round(v, 5) for v in rot)))
        for g in chips:
            vis, loc = g.pose(f)
            g.ob.location = loc
            g.ob.keyframe_insert("location", frame=f)
            for ob in g.chips:
                ob.hide_render = not vis
                ob.keyframe_insert("hide_render", frame=f)
            sig.append((vis, tuple(round(v, 6) for v in loc)))
        states.append(sig)
    return states


def frames_to_render(states):
    """Moving frames, plus the first frame of every still run. Returns (render_list, map)."""
    n = len(states)
    moving = [(f > 0 and states[f] != states[f - 1]) or (f < n - 1 and states[f] != states[f + 1])
              for f in range(n)]
    render, fmap = [], []
    for f in range(n):
        if f == 0 or moving[f] or moving[f - 1]:      # moving, or first still frame after motion
            render.append(f)
            fmap.append(f)
        else:
            fmap.append(fmap[-1])
    return render, fmap


def key_crane_camera(cam, focus, n):
    for f in range(n):
        loc, tgt, fs = cam_pose(cam_blend(LOW, HOLD, smooth(f / (n - 1))))
        cam.location, focus.location = loc, tgt
        cam.data.dof.aperture_fstop = fs
        cam.keyframe_insert("location", frame=f)
        focus.keyframe_insert("location", frame=f)
        cam.data.keyframe_insert("dof.aperture_fstop", frame=f)


# ----------------------------------------------------------------------------- regions
# Each hand only re-renders the part of the frame its cards/chips touch (plus their
# shadows, depth-of-field and motion blur); the composer pastes it, feathered, over
# the shared plates. Same seed, samples and settings, so the pixels match.
CHIP_R, STACK_H = 0.0195, 5 * 0.0033
SHADOW_SPREAD = 0.02


def card_points(loc, rot):
    m = Euler(rot, "XYZ").to_matrix()
    return [m @ Vector((dx * CW / 2, dy * CH / 2, CARD_BOW)) + loc for dx in (-1, 1) for dy in (-1, 1)]


def chip_points(loc):
    return [loc + Vector((dx * CHIP_R, dy * CHIP_R, z)) for dx in (-1, 1) for dy in (-1, 1)
            for z in (0.0, STACK_H)]


def with_shadows(pts):
    out = list(pts)
    for p in pts:
        if p.z < 0.0008:
            continue
        for lp in (KEY_POS, FILL_POS, RIM_POS):
            L = Vector(lp)
            if L.z <= p.z + 0.01:
                continue
            sh = p + (p - L) * (p.z / (L.z - p.z))
            for dx, dy in ((SHADOW_SPREAD, 0), (-SHADOW_SPREAD, 0), (0, SHADOW_SPREAD), (0, -SHADOW_SPREAD)):
                out.append(Vector((sh.x + dx, sh.y + dy, 0.0)))
    return out


def object_points(kind, pose):
    if kind == "card":
        vis, loc, rot = pose
        return with_shadows(card_points(loc, rot)) if vis else []
    vis, loc = pose
    return with_shadows(chip_points(loc)) if vis else []


def region_px(points, cam_frames, pad):
    """Pixel rect (x0, y0, x1, y1), top-left origin, covering the points as seen from the
    camera at the given frames, grown by their circle of confusion and `pad`."""
    sc = bpy.context.scene
    cam, focus = sc.camera, bpy.data.objects["focus"]
    W, H = sc.render.resolution_x, sc.render.resolution_y
    xs, ys = [], []
    for f in cam_frames:
        sc.frame_set(f)
        fs = cam.data.dof.aperture_fstop
        lens = cam.data.lens
        s = world_to_camera_view(sc, cam, focus.matrix_world.translation).z
        for p in points:
            v = world_to_camera_view(sc, cam, p)
            if v.z <= 0.01:
                continue
            coc_mm = lens * lens / (fs * (s * 1000 - lens)) * abs(v.z - s) / v.z
            r = coc_mm / 36.0 * H / 2 + 2
            x, y = v.x * W, (1 - v.y) * H
            xs += [x - r, x + r]
            ys += [y - r, y + r]
    if not xs:
        return None
    x0, y0 = max(0, int(min(xs)) - pad), max(0, int(min(ys)) - pad)
    x1, y1 = min(W, int(max(xs)) + 1 + pad), min(H, int(max(ys)) + 1 + pad)
    if x1 - x0 < 8 or y1 - y0 < 8:
        return None
    return [x0, y0, x1, y1]


def render_region(rect, path):
    sc = bpy.context.scene
    r = sc.render
    W, H = r.resolution_x, r.resolution_y
    x0, y0, x1, y1 = rect
    r.use_border, r.use_crop_to_border = True, True
    r.border_min_x, r.border_max_x = (x0 + 0.01) / W, (x1 + 0.01) / W
    r.border_min_y, r.border_max_y = (H - y1 + 0.01) / H, (H - y0 + 0.01) / H
    r.filepath = path
    bpy.ops.render.render(write_still=True)


def pad_px():
    return max(10, int(round(36 * bpy.context.scene.render.resolution_x / 1188)))


def render_regions(jobs, label):
    """jobs: list of (frame, rect, path). Skips files that exist."""
    sc = bpy.context.scene
    todo = [j for j in jobs if j[1] and not os.path.exists(j[2])]
    t0, px_done = time.time(), 0
    for k, (f, rect, path) in enumerate(todo):
        sc.frame_set(f)
        render_region(rect, path)
        px_done += (rect[2] - rect[0]) * (rect[3] - rect[1])
        el = time.time() - t0
        print(f"[blackjack] {label}: frame {f} ({k + 1}/{len(todo)}) {rect[2] - rect[0]}x{rect[3] - rect[1]}, "
              f"{el / (k + 1):.1f}s/frame, eta {el / (k + 1) * (len(todo) - k - 1) / 60:.1f} min", flush=True)
    sc.render.use_border = False


# ----------------------------------------------------------------------------- render setup
def setup_render(args, res_factor, motion_blur):
    sc = bpy.context.scene
    r = sc.render
    pct = args.res / 100.0
    r.resolution_x = int(round(1080 * res_factor * pct / 2)) * 2
    r.resolution_y = int(round(1920 * res_factor * pct / 2)) * 2
    r.resolution_percentage = 100
    r.fps = H.FPS
    r.use_motion_blur = motion_blur
    r.motion_blur_shutter = 0.5
    r.image_settings.file_format = "PNG"
    r.image_settings.color_mode = "RGB"
    r.image_settings.color_depth = "8"
    r.use_persistent_data = True
    vs = sc.view_settings
    try:
        vs.view_transform = "AgX"
        for look in ("AgX - Punchy", "Punchy"):      # keeps the red pips deep red
            try:
                vs.look = look
                break
            except TypeError:
                pass
    except TypeError:
        vs.view_transform = "Filmic"
    vs.exposure = -0.3
    r.engine = "CYCLES"
    cy = sc.cycles
    dev = setup_device(args.device)
    cy.samples = args.samples
    cy.use_adaptive_sampling = False      # identical per-pixel sampling in plates and crops
    cy.use_denoising = True
    cy.denoiser = "OPTIX" if dev == "OPTIX" else "OPENIMAGEDENOISE"
    for attr, val in (("denoising_quality", "HIGH"), ("denoising_prefilter", "ACCURATE"),
                      ("denoising_input_passes", "RGB_ALBEDO_NORMAL"), ("denoising_use_gpu", dev != "CPU")):
        try:
            setattr(cy, attr, val)
        except Exception:
            pass
    cy.use_light_tree = False             # only three real lights (background emitters are not sampled)
    cy.max_bounces, cy.diffuse_bounces, cy.glossy_bounces = 6, 2, 2
    cy.transmission_bounces, cy.volume_bounces, cy.transparent_max_bounces = 2, 0, 8
    cy.sample_clamp_indirect = 6
    cy.blur_glossy = 1.0
    cy.seed = 0
    cy.use_animated_seed = False
    return dev


_device_cache = {}


def setup_device(pref):
    sc = bpy.context.scene
    if pref.upper() == "CPU":
        sc.cycles.device = "CPU"
        return "CPU"
    cp = bpy.context.preferences.addons["cycles"].preferences
    kinds = ["OPTIX", "CUDA", "HIP", "ONEAPI", "METAL"] if pref.upper() == "AUTO" else [pref.upper()]
    for kind in kinds:
        try:
            cp.compute_device_type = kind
        except TypeError:
            continue
        (cp.refresh_devices if hasattr(cp, "refresh_devices") else cp.get_devices)()
        gpus = [d for d in cp.devices if d.type == kind]
        if gpus:
            for d in cp.devices:
                d.use = d.type == kind
            sc.cycles.device = "GPU"
            if kind not in _device_cache:
                print(f"[blackjack] rendering on {kind}: {', '.join(d.name for d in gpus)}", flush=True)
                _device_cache[kind] = True
            return kind
    sc.cycles.device = "CPU"
    return "CPU"


def render_frames(frames, path_fn, label):
    sc = bpy.context.scene
    t0 = time.time()
    todo = [f for f in frames if not os.path.exists(path_fn(f))]
    for k, f in enumerate(todo):
        sc.frame_set(f)
        sc.render.filepath = path_fn(f)
        bpy.ops.render.render(write_still=True)
        el = time.time() - t0
        print(f"[blackjack] {label}: frame {f} ({k + 1}/{len(todo)}), "
              f"{el / (k + 1):.1f}s/frame, eta {el / (k + 1) * (len(todo) - k - 1) / 60:.1f} min", flush=True)


# ----------------------------------------------------------------------------- anchors
def project_anchors(cam):
    """Normalised screen positions (x right, y down) of the card slots seen from the hold camera."""
    sc = bpy.context.scene
    bpy.context.view_layer.update()

    def proj(x, y, z=0.0):
        v = world_to_camera_view(sc, cam, Vector((x, y, z)))
        return [round(v.x, 5), round(1 - v.y, 5)]

    def card_box(xy):
        pts = [proj(xy[0] + dx * CW / 2, xy[1] + dy * CH / 2) for dx in (-1, 1) for dy in (-1, 1)]
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        return [min(xs), min(ys), max(xs), max(ys)]

    return dict(
        player=[proj(*H.player_slot(i)) for i in range(6)],
        dealer=[proj(*H.dealer_slot(i)) for i in range(6)],
        player_box=[card_box(H.player_slot(i)) for i in range(6)],
        dealer_box=[card_box(H.dealer_slot(i)) for i in range(6)],
        bet=proj(*H.BET_POS, 0.016), payout=proj(*H.PAYOUT_POS, 0.016),
    )


# ----------------------------------------------------------------------------- shots
def bet_group(rng):
    return ChipGroup("bet", H.BET_POS, "red", rng)


def shot_plates(args):
    """Shared plates without cards: intro still, hold background, crane background frames."""
    out = os.path.join(args.out, "shared")
    os.makedirs(os.path.join(out, "crane_bg"), exist_ok=True)
    p = os.path.join(out, "intro.png")
    if not os.path.exists(p):
        cam, focus, rng = build_scene(0)
        bet_group(rng)
        place_camera(cam, focus, LOW, wide=INTRO_WIDE)
        setup_render(args, INTRO_WIDE, motion_blur=False)
        render_frames([0], lambda f: p, "plate intro")
    p = os.path.join(out, "hold_bg.png")
    cam, focus, rng = build_scene(0)
    bet_group(rng)
    place_camera(cam, focus, HOLD)
    setup_render(args, HOLD_OVERSCAN, motion_blur=False)
    anchors = project_anchors(cam)
    render_frames([0], lambda f: p, "plate hold")
    n = H.EP_CRANE
    cam, focus, rng = build_scene(0)
    bet_group(rng)
    key_crane_camera(cam, focus, n)
    setup_render(args, 1.0, motion_blur=True)
    frames = parse_frames(args.frames, n) or list(range(n))
    render_frames(frames, lambda f: os.path.join(out, "crane_bg", f"{f:04d}.png"), "plate crane")
    json.dump(dict(res=args.res, samples=args.samples, anchors=anchors, crane_frames=n),
              open(os.path.join(out, "meta.json"), "w"), indent=1)


def shot_crane(args, hand, out):
    cam, focus, rng = build_scene(0)
    bet_group(rng)
    cards = [player_card(0, hand["player"][0], deal_at=H.CRANE_DEALS[0]),
             dealer_card(0, hand["up"], deal_at=H.CRANE_DEALS[1]),
             player_card(1, hand["player"][1], deal_at=H.CRANE_DEALS[2]),
             dealer_card(1, hand["hole"], face_up=False, deal_at=H.CRANE_DEALS[3])]
    n = H.EP_CRANE
    key_scene(cards, [], n)
    key_crane_camera(cam, focus, n)
    setup_render(args, 1.0, motion_blur=True)
    d = os.path.join(out, "crane")
    os.makedirs(d, exist_ok=True)
    pad = pad_px()
    frames = parse_frames(args.frames, n) or list(range(n))
    jobs, rects = [], {}
    for f in frames:
        near = [g for g in (f - 1, f, f + 1) if 0 <= g < n]
        pts = [p for c in cards for g in near for p in object_points("card", c.pose(g))]
        rect = region_px(pts, near, pad)
        rects[f] = rect
        jobs.append((f, rect, os.path.join(d, f"{f:04d}.png")))
    render_regions(jobs, "crane")
    return dict(crane=dict(frames=n, rects=rects))


def base_cards(hand):
    return [player_card(0, hand["player"][0]), player_card(1, hand["player"][1]),
            dealer_card(0, hand["up"]), dealer_card(1, hand["hole"], face_up=False)]


def shot_hold(args, hand, out):
    cam, focus, rng = build_scene(0)
    bet_group(rng)
    cards = base_cards(hand)
    place_camera(cam, focus, HOLD)
    setup_render(args, HOLD_OVERSCAN, motion_blur=False)
    anchors = project_anchors(cam)
    pts = [p for c in cards for p in object_points("card", c.pose(0))]
    rect = region_px(pts, [0], pad_px())
    render_regions([(0, rect, os.path.join(out, "hold.png"))], "hold")
    return dict(anchors=anchors, hold=dict(rect=rect))


def shot_branch(args, hand, out, action):
    cam, focus, rng = build_scene(0)
    bet = bet_group(rng)
    pay = ChipGroup("payout", H.PAYOUT_POS, "red", rng, hidden=True)
    tl = H.outcome_timeline(hand, action)
    cards = base_cards(hand)
    hole = cards[3]
    for ev in tl["events"]:
        if ev["kind"] == "player_draw":
            cards.append(player_card(ev["slot"], ev["card"], deal_at=ev["start"]))
        elif ev["kind"] == "dealer_draw":
            cards.append(dealer_card(ev["slot"], ev["card"], deal_at=ev["start"]))
        elif ev["kind"] == "dealer_reveal":
            hole.reveal_at = ev["start"]
        elif ev["kind"] == "settle" and ev["chips_start"] is not None:
            if ev["result"] == "win":
                pay.move(PAY_PATH, ev["chips_start"], hide_after=False)
            else:
                bet.move(TAKE_PATH, ev["chips_start"], hide_after=True)
    n = tl["total"]
    states = key_scene(cards, [bet, pay], n)
    render, fmap = frames_to_render(states)
    render = [f for f in render if f > 0]
    if args.frames:
        render = parse_frames(args.frames, n)
    place_camera(cam, focus, HOLD)
    setup_render(args, HOLD_OVERSCAN, motion_blur=True)
    kinds = ["card"] * len(cards) + ["chips", "chips"]
    objs = cards + [bet, pay]
    d = os.path.join(out, action.lower())
    os.makedirs(d, exist_ok=True)
    pad = pad_px()
    jobs, rects = [], {}
    for f in render:
        win = [g for g in range(f - 2, f + 2) if 0 <= g < n]
        active = [i for i in range(len(objs)) if len({states[g][i] for g in win}) > 1]
        pts = []
        for i in active:
            for g in win:
                pose = objs[i].pose(g)
                pts += object_points(kinds[i], pose)
        rect = region_px(pts, [f], pad)
        rects[f] = rect
        jobs.append((f, rect, os.path.join(d, f"{f:04d}.png")))
    render_regions(jobs, action.lower())
    src = [fmap[f] if fmap[f] in rects else -1 for f in range(n)]
    return {action.lower(): dict(frames=n, src=src, rects=rects)}


def parse_frames(spec, n):
    out = []
    for part in filter(None, spec.split(",")):
        if "-" in part:
            a, b = part.split("-")
            out += list(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return [f for f in out if 0 <= f < n]


def main():
    args = parse_args()
    t0 = time.time()
    shots = [s.strip() for s in args.shots.split(",") if s.strip()]
    if "plates" in shots:
        shot_plates(args)
        shots.remove("plates")
        if not shots:
            print(f"[blackjack] plates done in {(time.time() - t0) / 60:.1f} min", flush=True)
            return
    hand = H.HANDS[args.hand - 1]
    out = os.path.join(args.out, f"hand{args.hand:02d}")
    os.makedirs(out, exist_ok=True)
    meta_path = os.path.join(out, "meta.json")
    meta = json.load(open(meta_path)) if os.path.exists(meta_path) else {}
    meta.update(hand=args.hand, cards=hand, res=args.res, samples=args.samples)
    for shot in shots:
        if shot == "crane":
            meta.update(shot_crane(args, hand, out))
        elif shot == "hold":
            meta.update(shot_hold(args, hand, out))
        elif shot in ("hit", "stand"):
            meta.update(shot_branch(args, hand, out, shot.upper()))
        else:
            raise SystemExit(f"unknown shot {shot}")
        json.dump(meta, open(meta_path, "w"), indent=1)
        if args.save_blend:
            bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, shot + ".blend"), copy=True)
    print(f"[blackjack] hand {args.hand} done in {(time.time() - t0) / 60:.1f} min -> {out}", flush=True)


if __name__ == "__main__":
    main()

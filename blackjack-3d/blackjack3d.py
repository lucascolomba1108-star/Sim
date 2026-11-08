"""
Blackjack "HIT or STAND?" - 3D casino scene for Instagram Reels (1080x1920, 30 fps).

Builds the whole scene from code (table, felt print, cards, chips, shoe, casino
background, lights, camera moves) and renders three clips:

  question  9.0 s   cards are dealt, camera cranes up, long hold for the poll sticker
  stand     5.5 s   dealer flips the hole card (17), player's 16 loses, chips are taken
  hit       7.0 s   player draws a 5 (21), dealer flips 17, player gets paid

Usage (Blender 4.2 or newer, runs headless):
  blender -b -P blackjack3d.py -- --clip all
  blender -b -P blackjack3d.py -- --clip question --res 50 --samples 64       # quick preview
  blender -b -P blackjack3d.py -- --clip question --frames 0,40,84,269        # a few stills

Output: render/<clip>/frame_####.png and render/<clip>.mp4 (when ffmpeg is installed).
Re-running continues an interrupted render (frames that exist are skipped).

To make Hand #2, #3...: change the cards in the block below. Card codes are rank + suit:
A 2-10 J Q K  +  S (spades) H (hearts) D (diamonds) C (clubs).  Textures live in ./textures.
"""
import argparse
import math
import os
import random
import shutil
import subprocess
import sys

import bpy  # noqa: E402  (bpy must be imported before bmesh when run as a module)
import bmesh
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
TEX_DIR = os.path.join(HERE, "textures")

# ============================ THE HAND (edit here) ============================
PLAYER_CARDS = ["10S", "6H"]   # player's two cards
DEALER_UP = "10C"              # dealer's face-up card
DEALER_HOLE = "7S"             # dealer's face-down card, revealed in the answer clips
HIT_CARD = "5D"                # card the player receives in the HIT clip
PLAYER_WINS_ON_STAND = False   # outcome of the "stand" clip (chips paid or taken)
PLAYER_WINS_ON_HIT = True      # outcome of the "hit" clip
# ==============================================================================

FPS = 30
CLIP_FRAMES = {"question": 270, "stand": 165, "hit": 210}
CRANE_END = 84          # question clip: frame where the crane move lands

CW, CH = 0.063, 0.088   # poker card, metres
TABLE_C = Vector((0.0, 0.55))   # centre of the semicircular table (dealer side)
BET_POS = Vector((0.0, -0.185))


# ----------------------------------------------------------------------------- args
def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser(description="Render the blackjack reel clips")
    p.add_argument("--clip", default="all", choices=["all", *CLIP_FRAMES])
    p.add_argument("--engine", default="cycles", choices=["cycles", "eevee"])
    p.add_argument("--samples", type=int, default=160)
    p.add_argument("--res", type=int, default=100, help="resolution percent (50 = quick preview)")
    p.add_argument("--device", default="AUTO", help="AUTO, OPTIX, CUDA, HIP, ONEAPI, METAL or CPU")
    p.add_argument("--out", default=os.path.join(HERE, "render"))
    p.add_argument("--frames", default="", help="only these frames, e.g. 0,40,84 or 0-90")
    p.add_argument("--save-blend", action="store_true", help="also save <clip>.blend")
    p.add_argument("--no-motion-blur", action="store_true")
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


def emit_mat(name, color, strength):
    m = bpy.data.materials.new(name)
    enable_nodes(m)
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = color
    em.inputs["Strength"].default_value = strength
    nt.links.new(em.outputs[0], out.inputs["Surface"])
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
    bmesh.ops.create_icosphere(bm, subdivisions=2, radius=r)
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
    """colors: list of material names bottom->top. pos: (x, y) or parent-relative."""
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
    MATS["metal"] = simple_mat("metal", srgb("#8a8a8f"), rough=0.25, metal=1.0)
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
    # felt: semicircle, straight edge on the dealer side
    n = 160
    verts = [(TABLE_C.x + 1.0 * math.cos(math.pi + math.pi * i / n),
              TABLE_C.y + 1.0 * math.sin(math.pi + math.pi * i / n), 0.0) for i in range(n + 1)]
    obj_from_data("felt", verts, [tuple(range(n + 1))], MATS["felt"])
    # padded leather rail along the curved edge
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
    # dealer side wood edge + table body
    box("dealer_edge", (2.2, 0.08, 0.06), (0, TABLE_C.y + 0.04, -0.015), MATS["wood"])
    box("table_body", (2.2, 1.1, 0.7), (0, TABLE_C.y - 0.5, -0.4), MATS["wall"])
    # felt print
    gold, white = MATS["gold_ink"], MATS["white_ink"]
    arc_text("BLACKJACK PAYS 3 TO 2", 0.475, 0.0185, gold, spacing=1.08)
    arc_text("DEALER MUST DRAW TO 16 AND STAND ON ALL 17s", 0.43, 0.0085, white, spacing=1.18)
    arc_text("INSURANCE PAYS 2 TO 1", 0.528, 0.0125, gold, spacing=1.25)
    arc_band("line_a", TABLE_C, 0.457, 0.0014, 240, 300, gold)
    arc_band("line_b", TABLE_C, 0.493, 0.0014, 238, 302, gold)
    arc_band("line_c", TABLE_C, 0.548, 0.0014, 236, 304, gold)
    arc_band("bet_ring", BET_POS, 0.058, 0.0022, 0, 360, white)


def build_props(rng):
    global SHOE_YAW, DEAL_FROM
    # card shoe (dealer's left = right of the screen), mouth aimed at the cards
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
    # discard tray (dealer's right)
    dc = Vector((-0.27, 0.43, 0.0))
    yaw = math.radians(25)
    box("discard_base", (0.09, 0.115, 0.006), (dc.x, dc.y, 0.003), MATS["black_gloss"], yaw)
    box("discard_stack", (CW - 0.002, CH - 0.002, 0.022), (dc.x, dc.y, 0.017), MATS["card_edge"], yaw)
    top = card_obj("discard_top", None)
    top.location = (dc.x, dc.y, 0.0285)
    top.rotation_euler = (0, math.pi, yaw)
    # chip tray with chip columns lying down (odd chip count so seams line up)
    box("tray", (0.34, 0.12, 0.016), (0, 0.495, 0.004), MATS["black_gloss"])
    order = ["white", "red", "green", "black", "purple", "blue", "yellow"]
    for i, c in enumerate(order):
        col = chip_mesh(f"tray_{c}", 0.0033 * 33, MATS[c])
        col.location = (-0.135 + i * 0.045, 0.495, 0.0125)
        col.rotation_euler = (math.pi / 2, 0, 0)
    # player's chip stacks near the rail (foreground)
    chip_stack("stackL1", (-0.185, -0.335), ["blue"] * 8, rng)
    chip_stack("stackL2", (-0.215, -0.295), ["purple"] * 4, rng)
    chip_stack("stackR1", (0.175, -0.335), ["black"] * 7, rng)
    chip_stack("stackR2", (0.212, -0.298), ["green"] * 5 + ["red"] * 2, rng)


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
    # banks of slot machines facing the table
    for row_y, x0, count in ((4.2, -3.6, 12), (6.8, -4.2, 14), (9.8, -4.8, 16)):
        for i in range(count):
            x = x0 + i * 0.64 + rng.uniform(-0.02, 0.02)
            box(f"slot_{row_y}_{i}", (0.58, 0.55, 1.75), (x, row_y, -0.77 + 0.875), MATS["cabinet"])
            front = row_y - 0.28
            box(f"scr_{row_y}_{i}", (0.34, 0.01, 0.24), (x, front, 0.42), rng.choice(screen_mats))
            box(f"pan_{row_y}_{i}", (0.34, 0.01, 0.05), (x, front, 0.08), rng.choice(screen_mats))
            box(f"top_{row_y}_{i}", (0.06, 0.06, 0.22), (x, row_y, 1.10), rng.choice(candle))
    # chandelier glints / distant lamps -> bokeh
    for i in range(320):
        loc = (rng.uniform(-5.0, 5.0), rng.uniform(1.8, 10.5), rng.uniform(-0.2, 2.4))
        sphere(f"glint_{i}", rng.uniform(0.006, 0.02), loc, rng.choice(warm))
    # recessed ceiling lights
    for ix in range(-3, 4):
        for iy in range(0, 8):
            box(f"down_{ix}_{iy}", (0.16, 0.16, 0.01), (ix * 1.4, 1.0 + iy * 1.4, 2.66), downlight)


def build_lights():
    warm = (1.0, 0.84, 0.66)
    light("key", "SPOT", (0.08, 0.28, 1.45), 170, warm, aim=(0.0, 0.03, 0.0), spot_size=math.radians(36),
          spot_blend=1.0, shadow_soft_size=0.22)
    light("fill", "AREA", (0.0, -1.7, 1.3), 22, (1.0, 0.9, 0.8), aim=(0, 0, 0),
          shape="RECTANGLE", size=1.6, size_y=1.0)
    light("rim", "AREA", (0.35, 1.5, 0.5), 55, (1.0, 0.72, 0.48), aim=(0, -0.1, 0),
          shape="RECTANGLE", size=1.2, size_y=0.4)


def build_camera():
    sc = bpy.context.scene
    cd = bpy.data.cameras.new("cam")
    cd.lens = 50
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


# ----------------------------------------------------------------------------- animation
DEAL_LEN, FLIP_LEN, CHIP_LEN = 14, 13, 24


class Card:
    def __init__(self, name, code, target, yaw_deg, layer, face_up=True, deal_at=None, reveal_at=None):
        self.ob = card_obj(name, code)
        self.T = Vector((target[0], target[1], 0.0003 + layer * 0.0011))
        self.yaw = math.radians(yaw_deg)
        self.face_up, self.deal_at, self.reveal_at = face_up, deal_at, reveal_at

    def pose(self, f):
        if self.deal_at is not None:
            if f < self.deal_at:
                return False, DEAL_FROM.copy(), (0.0, math.pi, SHOE_YAW)
            p = (f - self.deal_at) / DEAL_LEN
            if p < 1:
                e = ease_out(p)
                loc = DEAL_FROM.lerp(self.T, e)
                loc.z += 0.03 * math.sin(math.pi * e)
                yaw = lerp(SHOE_YAW, self.yaw, ease_out(p * 1.25))
                beta = math.pi * (1 - smooth((p - 0.1) / 0.7)) if self.face_up else math.pi
                loc.z += CW / 2 * abs(math.sin(beta))
                return True, loc, (0.0, beta, yaw)
        loc = self.T.copy()
        beta = 0.0 if self.face_up else math.pi
        if self.reveal_at is not None and f >= self.reveal_at:
            q = clamp((f - self.reveal_at) / FLIP_LEN)
            beta = math.pi * (1 - smooth(q))
            loc.z += CW / 2 * abs(math.sin(beta)) + 0.012 * math.sin(math.pi * q)
        return True, loc, (0.0, beta, self.yaw)


def chip_move(path, start, f):
    """Position of a chip group following a cubic bezier `path` starting at frame `start`."""
    p = clamp((f - start) / CHIP_LEN)
    t = ease_in_out(p)
    pos = bezier(*path, t)
    return Vector((pos.x, pos.y, 0.004 * math.sin(math.pi * t))), p


CAM = {
    "low":   dict(t=(-0.03, -0.07, 0.0), el=9.0, d=0.40, az=-14.0, fs=2.8),
    "crane": dict(t=(-0.005, 0.03, 0.0), el=52.0, d=0.80, az=0.0, fs=7.0),
    "hold":  dict(t=(-0.005, 0.03, 0.0), el=55.0, d=0.74, az=0.0, fs=7.0),
    "end":   dict(t=(0.0, 0.03, 0.0), el=57.0, d=0.71, az=2.0, fs=7.0),
}


def cam_blend(a, b, t):
    out = {k: lerp(a[k], b[k], t) for k in ("el", "d", "az")}
    out["t"] = Vector(a["t"]).lerp(Vector(b["t"]), t)
    out["fs"] = math.exp(lerp(math.log(a["fs"]), math.log(b["fs"]), t))
    return out


def cam_state(clip, f, n):
    if clip == "question":
        if f <= CRANE_END:
            s = cam_blend(CAM["low"], CAM["crane"], smooth(f / CRANE_END))
        else:
            s = cam_blend(CAM["crane"], CAM["hold"], ease_in_out((f - CRANE_END) / (n - 1 - CRANE_END)))
    else:
        s = cam_blend(CAM["hold"], CAM["end"], ease_in_out(f / (n - 1)))
    el, az = math.radians(s["el"]), math.radians(s["az"])
    off = Vector((math.sin(az) * math.cos(el), -math.cos(az) * math.cos(el), math.sin(el))) * s["d"]
    loc = s["t"] + off
    loc.x += 0.0012 * math.sin(f * 0.071)          # tiny hand-held drift
    loc.z += 0.0009 * math.sin(f * 0.053 + 1.3)
    return loc, s["t"], s["fs"]


def animate(clip, rng, cam, focus):
    n = CLIP_FRAMES[clip]
    sc = bpy.context.scene
    sc.frame_start, sc.frame_end = 0, n - 1
    q = clip == "question"
    p1 = (-0.030, -0.070)
    p2 = (0.002, -0.062)
    p3 = (0.034, -0.054)
    d1 = (-0.030, 0.205)
    d2 = (0.002, 0.211)
    cards = [
        Card("P1", PLAYER_CARDS[0], p1, -3.0, 0, deal_at=10 if q else None),
        Card("D1", DEALER_UP, d1, -1.5, 0, deal_at=24 if q else None),
        Card("P2", PLAYER_CARDS[1], p2, 2.0, 1, deal_at=38 if q else None),
        Card("D2", DEALER_HOLE, d2, 2.5, 1, face_up=False, deal_at=52 if q else None,
             reveal_at={"stand": 30, "hit": 66}.get(clip)),
    ]
    if clip == "hit":
        cards.append(Card("P3", HIT_CARD, p3, 4.0, 2, deal_at=22))

    # bet (and payout) chip groups
    bet = link(bpy.data.objects.new("bet", None))
    bet.location = (BET_POS.x, BET_POS.y, 0)
    chip_stack("bet", (0, 0), ["red"] * 5, rng, parent=bet)
    pay = link(bpy.data.objects.new("payout", None))
    chip_stack("pay", (0, 0), ["red"] * 5, rng, parent=pay)
    for ob in pay.children:
        ob.hide_render = True
    tray = Vector((0.10, 0.48))
    pay_path = (tray, Vector((0.15, 0.30)), Vector((0.13, -0.15)), Vector((0.042, -0.19)))
    take_path = (BET_POS.copy(), Vector((-0.15, -0.12)), Vector((-0.15, 0.33)), Vector((-0.07, 0.47)))
    settle = {"stand": (PLAYER_WINS_ON_STAND, 78), "hit": (PLAYER_WINS_ON_HIT, 112)}.get(clip)

    for f in range(n):
        for c in cards:
            vis, loc, rot = c.pose(f)
            c.ob.location = loc
            c.ob.rotation_euler = rot
            c.ob.hide_render = not vis
            c.ob.keyframe_insert("location", frame=f)
            c.ob.keyframe_insert("rotation_euler", frame=f)
            c.ob.keyframe_insert("hide_render", frame=f)
        if settle:
            win, start = settle
            group, path = (pay, pay_path) if win else (bet, take_path)
            pos, p = chip_move(path, start, f)
            group.location = pos
            group.keyframe_insert("location", frame=f)
            hidden = (f < start) if win else (p >= 1)
            for ob in group.children:
                ob.hide_render = hidden
                ob.keyframe_insert("hide_render", frame=f)
        loc, tgt, fs = cam_state(clip, f, n)
        cam.location = loc
        cam.keyframe_insert("location", frame=f)
        focus.location = tgt
        focus.keyframe_insert("location", frame=f)
        cam.data.dof.aperture_fstop = fs
        cam.data.keyframe_insert("dof.aperture_fstop", frame=f)


# ----------------------------------------------------------------------------- render
def setup_render(args, clip):
    sc = bpy.context.scene
    r = sc.render
    r.resolution_x, r.resolution_y, r.resolution_percentage = 1080, 1920, args.res
    r.fps = FPS
    r.use_motion_blur = not args.no_motion_blur
    r.motion_blur_shutter = 0.5
    r.image_settings.file_format = "PNG"
    r.image_settings.color_mode = "RGB"
    r.use_overwrite = False
    r.use_placeholder = True
    try:
        r.use_persistent_data = True
    except Exception:
        pass
    vs = sc.view_settings
    try:
        vs.view_transform = "AgX"
        for look in ("AgX - Medium High Contrast", "Medium High Contrast"):
            try:
                vs.look = look
                break
            except TypeError:
                pass
    except TypeError:
        vs.view_transform = "Filmic"
    if args.engine == "eevee":
        for eng in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
            try:
                r.engine = eng
                break
            except TypeError:
                pass
        ee = sc.eevee
        for attr, val in (("taa_render_samples", max(64, args.samples)), ("use_raytracing", True),
                          ("use_shadows", True), ("use_gtao", True)):
            try:
                setattr(ee, attr, val)
            except Exception:
                pass
        return "EEVEE"
    r.engine = "CYCLES"
    cy = sc.cycles
    dev = setup_device(args.device)
    cy.samples = args.samples
    cy.use_adaptive_sampling = True
    cy.adaptive_threshold = 0.012
    cy.use_denoising = True
    try:
        cy.denoiser = "OPTIX" if dev == "OPTIX" else "OPENIMAGEDENOISE"
    except TypeError:
        pass
    cy.max_bounces, cy.diffuse_bounces, cy.glossy_bounces = 8, 3, 3
    cy.transparent_max_bounces = 16
    cy.sample_clamp_indirect = 6
    cy.blur_glossy = 1.0
    return dev


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
            print(f"[blackjack] rendering on {kind}: {', '.join(d.name for d in gpus)}")
            return kind
    print("[blackjack] no GPU found, rendering on CPU (slow)")
    sc.cycles.device = "CPU"
    return "CPU"


def parse_frames(spec, n):
    out = []
    for part in filter(None, spec.split(",")):
        if "-" in part:
            a, b = part.split("-")
            out += list(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return [f for f in out if 0 <= f < n]


def encode(frames_dir, mp4):
    ff = shutil.which("ffmpeg")
    if not ff:
        print("[blackjack] ffmpeg not found, PNG frames are in", frames_dir)
        return
    subprocess.run([ff, "-y", "-loglevel", "error", "-framerate", str(FPS),
                    "-i", os.path.join(frames_dir, "frame_%04d.png"),
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "16", "-preset", "slow",
                    "-movflags", "+faststart", mp4], check=True)
    print("[blackjack] wrote", mp4)


def render_clip(clip, args):
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
    animate(clip, rng, cam, focus)
    dev = setup_render(args, clip)
    sc = bpy.context.scene
    frames_dir = os.path.join(args.out, clip)
    os.makedirs(frames_dir, exist_ok=True)
    print(f"[blackjack] {clip}: {CLIP_FRAMES[clip]} frames, {args.engine}/{dev}, "
          f"{args.samples} samples, {args.res}%")
    if args.save_blend:
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(args.out, clip + ".blend"), copy=True)
    if args.frames:
        sc.render.use_overwrite = True
        for f in parse_frames(args.frames, CLIP_FRAMES[clip]):
            sc.frame_set(f)
            sc.render.filepath = os.path.join(frames_dir, f"still_{f:04d}")
            bpy.ops.render.render(write_still=True)
        return
    sc.render.filepath = os.path.join(frames_dir, "frame_")
    bpy.ops.render.render(animation=True)
    encode(frames_dir, os.path.join(args.out, clip + ".mp4"))


def main():
    args = parse_args()
    clips = list(CLIP_FRAMES) if args.clip == "all" else [args.clip]
    for clip in clips:
        render_clip(clip, args)


if __name__ == "__main__":
    main()

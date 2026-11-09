"""Build the Blackwood ledge creature with Blender's background Python runner."""
from bisect import bisect_left
from array import array
from math import atan2, cos, sin, tau
from pathlib import Path
from random import Random
import sys

import bpy
from mathutils import Vector, noise

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ledge_skeleton import create_ledge_skeleton, puppet_rest


ROOT = Path(__file__).resolve().parents[2]
bpy.ops.wm.read_factory_settings(use_empty=True)
random = Random(117)
reference = bpy.data.images.load(str(ROOT / "art/creatures/blackwood-ledge-wolf-reference.webp"))
ref_width, ref_height = reference.size
ref_pixels = array("f", [0.0]) * (ref_width * ref_height * 4)
reference.pixels.foreach_get(ref_pixels)


def reference_luma(x, y):
    column = min(ref_width - 1, max(0, round(x * ref_width / 1536)))
    row = min(ref_height - 1, max(0, round((1 - y / 1024) * ref_height)))
    offset = (row * ref_width + column) * 4
    r, g, b = ref_pixels[offset:offset + 3]
    return r * .21 + g * .72 + b * .07


ref_is_linear = reference_luma(1518, 1004) < .32


def coat_reference(x, forward, y, face):
    if face:
        # Match the muzzle, orbit and cheek to the side-profile landmarks in the reference.
        u = 812 + (1.158 - forward) * 536 + 5.2 * sin(x * 27)
        v = 352 - (y - 1.619) * 655 - (1.158 - forward) * 135
    else:
        # Sample the charcoal coat on the shoulder, away from the reference silhouette.
        u = 1218 + 77 * sin(x * 12 + forward * 2.1)
        v = 207 + 142 * (1 + sin(y * 5.7 + forward * 3.4)) * .5
    tone = reference_luma(u, v)
    if ref_is_linear:
        tone = max(0, tone) ** (1 / 2.2)
    return min(.48, max(.08, tone))


def xyz(point):
    """Convert the game's coordinates to Blender Z-up."""
    x, y, z = point
    return Vector((x, -z, y))


def smooth(value, low, high):
    t = min(1.0, max(0.0, (value - low) / (high - low)))
    return t * t * (3 - 2 * t)


def material(name, color, roughness, vertex_color=False):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.diffuse_color = (*color, 1)
    shader = mat.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (*color, 1)
    shader.inputs["Roughness"].default_value = roughness
    if vertex_color:
        attr = mat.node_tree.nodes.new("ShaderNodeVertexColor")
        attr.layer_name = "Pelt"
        mat.node_tree.links.new(attr.outputs["Color"], shader.inputs["Base Color"])
    return mat


pelt = material("Matted charcoal pelt", (.075, .064, .057), .78, True)
hair = material("Tapered guard hair clumps", (.072, .061, .052), .93, True)
nose = material("Pebbled nose leather", (.022, .015, .013), .66, True)
bare = material("Weathered paw leather", (.097, .068, .060), .68, True)
inside = material("Mouth and nostrils", (.013, .005, .004), .39)
lip = material("Gums and lip folds", (.037, .017, .014), .56)
tongue = material("Muted tongue", (.068, .027, .024), .55)
ivory = material("Worn canine enamel", (.255, .204, .143), .55)
claw = material("Dark claw keratin", (.041, .031, .024), .37)
eye = material("Recessed amber eye", (.25, .108, .028), .30, True)
eyelid = material("Dark eyelid rim", (.029, .020, .015), .73, True)
eye_x, eye_forward, eye_height = .114, .853, 1.725

rig = create_ledge_skeleton(puppet_rest())


def mesh(name, vertices, faces, mat):
    data = bpy.data.meshes.new(name)
    data.from_pydata(vertices, [], faces)
    data.update()
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    if mat:
        data.materials.append(mat)
    for face in data.polygons:
        face.use_smooth = True
    return obj


def active(obj):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def normals_out(obj):
    active(obj)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.object.mode_set(mode="OBJECT")


def ellipsoid(name, point, scale, mat=None, axis=None):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=16, location=xyz(point))
    obj = bpy.context.object
    obj.name = name
    obj.scale = (scale[0], scale[2], scale[1]) if axis is None else scale
    if axis is not None:
        obj.rotation_euler = xyz(axis).to_track_quat("Z", "Y").to_euler()
    if mat:
        obj.data.materials.append(mat)
    for face in obj.data.polygons:
        face.use_smooth = True
    return obj


def capsule(name, a, b, width, depth, mat=None):
    a, b = Vector(a), Vector(b)
    return ellipsoid(name, (a + b) * .5, (width, depth, (a - b).length * .59), mat, b - a)


def loft(name, sections, mat=None, sides=36, upright=False):
    vertices = []
    faces = []
    for axis, center, width, depth in sections:
        for i in range(sides):
            angle = tau * i / sides
            x = cos(angle) * width
            cross = center + sin(angle) * depth
            vertices.append(xyz((x, axis, cross) if upright else (x, cross, axis)))
    for row in range(len(sections) - 1):
        for i in range(sides):
            a, b = row * sides + i, row * sides + (i + 1) % sides
            faces.append((a, b, b + sides, a + sides))
    faces.extend((tuple(reversed(range(sides))), tuple(range(len(vertices) - sides, len(vertices)))))
    obj = mesh(name, vertices, faces, mat)
    normals_out(obj)
    return obj


def sculpt(name, pieces, size, mat):
    active(pieces[0])
    for part in pieces[1:]:
        part.select_set(True)
    bpy.ops.object.join()
    obj = bpy.context.object
    obj.name = name
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    obj.data.remesh_voxel_size = size
    bpy.ops.object.voxel_remesh()
    modifier = obj.modifiers.new("Soften sculpt joins", "SMOOTH")
    modifier.factor = .62
    modifier.iterations = 4
    bpy.ops.object.modifier_apply(modifier=modifier.name)
    obj.data.materials.clear()
    obj.data.materials.append(mat)
    for face in obj.data.polygons:
        face.use_smooth = True
    return obj


def axis_distance(point, a, b):
    axis = b - a
    position = max(0.0, min(1.0, (point - a).dot(axis) / axis.length_squared))
    return (point - (a + axis * position)).length


arm_axis = [xyz(p) for p in ((.342, 1.637, -.177), (.486, 1.178, -.129), (.486, .537, -.376))]


def body_weights(point):
    x, forward, y = point
    z = -forward
    side = "L" if x < 0 else "R"
    x = abs(x)
    arm = smooth(x, .25, .48) * (1 - smooth(z, .00, .25))
    arm = max(arm, smooth(x, .27, .35) * (1 - smooth(z, .045, .20)) * (1 - smooth(y, 1.14, 1.37)))
    if y < 1.29:
        p = Vector((x, forward, y))
        arm_dist = min(axis_distance(p, a, b) for a, b in zip(arm_axis, arm_axis[1:]))
        arm = max(arm, (1 - smooth(y, 1.13, 1.30)) * (1 - smooth(arm_dist, .11, .23)))
    rest = 1 - arm
    neck = rest * smooth(-z, .34, .60) * smooth(y, 1.42, 1.66) * (1 - smooth(x, .15, .27))
    chest = smooth(y, 1.05, 1.43) * (rest - neck)
    elbow = 1 - smooth(y, 1.05, 1.29)
    wrist = 1 - smooth(y, .48, .64)
    result = {
        "Chest": chest, "Pelvis": rest - neck - chest, "Head": neck,
        "Shoulder." + side: arm * (1 - elbow), "Elbow." + side: arm * elbow * (1 - wrist),
        "Wrist." + side: arm * elbow * wrist,
    }
    strongest = sorted(result.items(), key=lambda item: item[1], reverse=True)[:4]
    total = sum(weight for _, weight in strongest)
    return {name: weight / total for name, weight in strongest if weight > .0001}


def leg_weights(suffix):
    def weights(point):
        y = point.z
        pelvis = smooth(y, 1.02, 1.23)
        knee = 1 - smooth(y, .60, .81)
        hock = 1 - smooth(y, .24, .41)
        toes = 1 - smooth(y, .045, .12)
        return {
            "Pelvis": pelvis, "Hip." + suffix: (1 - pelvis) * (1 - knee),
            "Knee." + suffix: knee * (1 - hock), "Hock." + suffix: hock * (1 - toes),
            "Toes." + suffix: toes,
        }
    return weights


def rigid(name):
    return lambda _: {name: 1.0}


def bind(obj, weights):
    active(obj)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    groups = {}
    for vertex in obj.data.vertices:
        for name, weight in weights(vertex.co).items():
            if weight <= .0001:
                continue
            if name not in groups:
                groups[name] = obj.vertex_groups.new(name=name)
            groups[name].add((vertex.index,), weight, "REPLACE")
    obj.parent = rig
    armature = obj.modifiers.new("Ledge deformation", "ARMATURE")
    armature.object = rig


def coat_color(point, face=False, leather=False):
    x, forward, y = point
    scale = Vector((x * 115, forward * (30 if face else 83), y * (86 if face else 31)))
    mottling = noise.fractal(point * 16 + Vector((8, 3, 2)), 1.15, 2.1, 3)
    fiber = noise.noise_vector(scale)[0]
    if leather:
        pores = noise.noise_vector(point * 290)[1]
        return (.023 + .025 * abs(fiber) + .013 * pores, .019 + .020 * abs(fiber) + .009 * pores,
                .017 + .017 * abs(fiber) + .007 * pores)
    sample = coat_reference(x, forward, y, face)
    if face:
        muzzle = smooth(forward, .86, 1.10)
        whisker_pad = muzzle * smooth(abs(x), .026, .071) * (1 - smooth(y, 1.635, 1.696))
        cheek = smooth(abs(x), .10, .18) * (1 - smooth(y, 1.693, 1.755)) * smooth(forward, .45, .68)
        crown = smooth(y, 1.77, 1.90)
        socket = (1 - smooth(orbit_distance(point), .48, 1.45)) * .032
        patch = .032 + .048 * whisker_pad + .030 * cheek - .015 * crown - socket + sample * .19
        patch += muzzle * (.022 * mottling + .025 * fiber)
    else:
        patch = .016 + .014 * smooth(y, 1.27, 1.83) + sample * .19
    patch += .021 * mottling + .027 * fiber
    return (max(.012, patch * 1.04), max(.010, patch * .962), max(.009, patch * .87))


def colorize(obj, source):
    colors = obj.data.color_attributes.new(name="Pelt", type="FLOAT_COLOR", domain="POINT")
    for vertex, value in zip(obj.data.vertices, colors.data):
        value.color = (*source(vertex.co), 1)


def orbit_distance(point):
    x, forward, height = point
    offset = abs(x) - eye_x
    return ((offset / .046) ** 2 + ((forward - eye_forward + offset * .46) / .069) ** 2
            + ((height - eye_height - offset * .31) / .034) ** 2) ** .5


def pelt_uv(obj):
    """Give the in-game grain map continuous coordinates along the coat."""
    data = obj.data
    uv = data.uv_layers.new(name="Coat grain")
    face = obj.name.startswith(("Canid skull", "Lower mandible"))
    nose_pad = obj.data.materials[0] == nose
    for polygon in data.polygons:
        coords = [data.vertices[data.loops[i].vertex_index].co for i in polygon.loop_indices]
        angles = [atan2(point.y, point.x) / tau for point in coords]
        wraps = max(angles) - min(angles) > .5
        for i, point, angle in zip(polygon.loop_indices, coords, angles):
            u = angle + (1 if wraps and angle < 0 else 0)
            if face:
                # The short coat follows the bridge toward the nose and fans down the cheek.
                uv.data[i].uv = (point.x * 5.8 + (point.z - 1.67) * 2.7, point.y * 4.5 - point.z * 3.2)
            elif nose_pad:
                uv.data[i].uv = (point.x * 10.0, (point.z - 1.58) * 8.0 + (point.y - 1.14) * 6.0)
            else:
                uv.data[i].uv = (u * 3, point.z * 2.0 + point.y * .38)


def groom(name, skin, weights, count, face=False, mantle=False, darkness=1.0):
    skin.data.calc_loop_triangles()
    triangles = []
    areas = []
    total = 0
    for triangle in skin.data.loop_triangles:
        center = sum((skin.data.vertices[i].co for i in triangle.vertices), Vector()) / 3
        coverage = .55 + .45 * smooth(center.z, .42, 1.54)
        if mantle:
            coverage *= .50 + 2.0 * smooth(center.z, 1.35, 1.81)
        if face:
            if orbit_distance(center) < .8:
                continue
            coverage *= .76 + .24 * smooth(abs(center.x), .09, .20)
        total += triangle.area * coverage
        triangles.append(triangle.vertices[:])
        areas.append(total)
    vertices, faces, colors, roots = [], [], [], []
    for _ in range(count):
        triangle = triangles[bisect_left(areas, random.random() * total)]
        a, b, c = [skin.data.vertices[i] for i in triangle]
        u, v = random.random(), random.random()
        if u + v > 1:
            u, v = 1 - u, 1 - v
        point = a.co.lerp(b.co, u) + (c.co - a.co) * v
        normal = (a.normal.lerp(b.normal, u) + (c.normal - a.normal) * v).normalized()
        grain = noise.noise_vector(point * 17 + Vector((.8, 1.7, .2)))
        direction = Vector((point.x * .42, -.28, -.91))
        muzzle = smooth(point.y, .77, 1.01) if face else 0
        cheek = smooth(abs(point.x), .10, .21)
        mane = smooth(point.z, 1.30, 1.82) * (1 - muzzle) if face or mantle else 0
        ruff = (1 - smooth(point.y, .72, .90)) * smooth(abs(point.x), .09, .17) if face else 0
        brow = smooth(point.y, .61, .79) * smooth(point.z, 1.69, 1.80) if face else 0
        orbit = orbit_distance(point) if face else 3
        if face:
            direction = Vector((point.x * .9, -.53, -.94)).lerp(
                Vector((point.x * .78, .97, -.20)), muzzle)
            direction = direction.lerp(Vector((point.x * 2.7, -.75, .27)), brow * .90)
            if orbit < 1.8:
                direction = direction.lerp(Vector((point.x * 5, -.72, .26)), 1 - smooth(orbit, .65, 1.8))
        elif mantle:
            direction = direction.lerp(Vector((point.x * 1.32, -.64, -.91)), mane)
        direction += grain * (.25 + mane * .24)
        tangent = direction - normal * direction.dot(normal)
        if tangent.length < .05:
            tangent = normal.cross(Vector((1, 0, 0)))
        tangent.normalize()
        width_axis = normal.cross(tangent).normalized()
        if width_axis.length < .5:
            continue
        lock = (random.random() < max(ruff * .86, mane * .77) * (1 - brow * .93)
                and muzzle < .28 and orbit > 1.55)
        clump = lock or (random.random() < .22 and muzzle < .42)
        length = random.uniform(.018, .038) * (.74 + mane * 1.28)
        if face:
            length *= (.53 + cheek * .66) * (1 - .73 * muzzle) * (1 - brow * .66)
            length *= .32 + .68 * smooth(orbit, .81, 1.85)
        length *= random.uniform(.85, 1.22)
        if lock:
            length += random.uniform(.045, .113) * max(ruff, mane) * (.88 + .46 * grain.y)
        width = random.uniform(.00027, .00073) * (1 + mane * .26)
        if lock:
            width *= 1.62
        if face:
            width *= .76
        bend = random.uniform(-.10, .10) + grain.x * .37
        base_color = coat_color(point, face)
        tint = random.uniform(.76, 1.44) * (1.03 + .35 * grain.z)
        for strand in range(3 if lock else 2 if clump else 1):
            idx = len(vertices)
            span = width * (1 if strand == 0 else .64)
            offset = 0 if strand == 0 else random.uniform(-.005, .005)
            length_factor = 1 if strand == 0 else random.uniform(.72, .95)
            for t, taper in ((0, .77), (.33, 1), (.72, .54), (1, .012)):
                lift = length * (sin(t * 2.30) * (.06 + .08 * mane) + t * (.11 if lock else .085)) - .00065
                lateral = offset * (1 - t * .65) + bend * length * t * t
                droop = Vector((0, -length * t * t * .13, -length * t * t * .45)) if lock else Vector()
                center = point + tangent * (length * length_factor * t) + normal * lift + width_axis * lateral + droop
                vertices.extend((center - width_axis * span * taper, center + width_axis * span * taper))
                roots.extend((point, point))
                value = tuple(min(.30, (c * tint * (.67 + t * .59) + t * mane * .016) * darkness) for c in base_color)
                colors.extend((value, value))
            faces.extend((idx + i, idx + i + 1, idx + i + 3, idx + i + 2) for i in (0, 2, 4))
    obj = mesh(name, vertices, faces, hair)
    layer = obj.data.color_attributes.new(name="Pelt", type="FLOAT_COLOR", domain="POINT")
    for value, rgb in zip(layer.data, colors):
        value.color = (*rgb, 1)
    groups = {}
    for i in range(0, len(roots), 8):
        for name, weight in weights(roots[i]).items():
            if weight <= .0001:
                continue
            if name not in groups:
                groups[name] = obj.vertex_groups.new(name=name)
            groups[name].add(tuple(range(i, i + 8)), weight, "REPLACE")
    obj.parent = rig
    obj.modifiers.new("Groom deformation", "ARMATURE").object = rig


body_parts = [
    loft("Tapered ribcage and flank", [
        (.88, .410, .073, .103), (.96, .404, .186, .157), (1.06, .363, .220, .179),
        (1.17, .291, .214, .193), (1.28, .212, .225, .214), (1.40, .109, .253, .245),
        (1.54, .004, .290, .254), (1.65, -.068, .315, .252), (1.76, -.116, .302, .235),
        (1.86, -.171, .241, .198), (1.94, -.225, .134, .126), (1.97, -.238, .047, .049),
    ], upright=True),
    capsule("Long sloping neck", (0, 1.57, -.22), (0, 1.77, -.59), .216, .211),
]
for side in (-1, 1):
    body_parts.extend((
        capsule("Scapula", (side * .12, 1.80, -.045), (side * .39, 1.59, -.188), .129, .148),
        capsule("Deltoid", (side * .31, 1.64, -.16), (side * .434, 1.39, -.137), .126, .122),
        capsule("Biceps", (side * .406, 1.49, -.21), (side * .485, 1.18, -.14), .101, .104),
        ellipsoid("Elbow", (side * .486, 1.18, -.129), (.092, .106, .091)),
        capsule("Forearm", (side * .486, 1.21, -.124), (side * .489, .77, -.28), .105, .101),
        capsule("Tendon", (side * .489, .94, -.234), (side * .486, .54, -.376), .069, .075),
        ellipsoid("Wrist", (side * .486, .54, -.369), (.070, .093, .069)),
    ))
body = sculpt("Continuous shoulder and torso sculpt", body_parts, .012, pelt)
colorize(body, coat_color)
bind(body, body_weights)
groom("Body and mane fur", body, body_weights, 10900, mantle=True)
for side, suffix in ((-1, "L"), (1, "R")):
    lower = sculpt("Continuous digitigrade leg." + suffix, [
        capsule("Haunch", (side * .214, 1.139, .443), (side * .343, .73, .228), .158, .146),
        ellipsoid("Kneecap", (side * .35, .706, .202), (.092, .098, .107)),
        capsule("Calf", (side * .345, .78, .25), (side * .385, .375, .55), .105, .091),
        ellipsoid("Hock", (side * .384, .327, .584), (.069, .079, .073)),
        capsule("Metatarsals", (side * .385, .375, .596), (side * .349, .07, .35), .065, .056),
    ], .012, pelt)
    weights = leg_weights(suffix)
    colorize(lower, coat_color)
    bind(lower, weights)
    groom("Hind leg fur." + suffix, lower, weights, 1350)

head_parts = [
    loft("Skull volumes", [
        (-.386, 1.747, .087, .091), (-.445, 1.754, .149, .128), (-.54, 1.768, .188, .145),
        (-.64, 1.754, .186, .133), (-.72, 1.735, .155, .111), (-.80, 1.702, .115, .083),
        (-.89, 1.665, .096, .066), (-.99, 1.642, .077, .047), (-1.083, 1.625, .065, .033),
        (-1.129, 1.619, .046, .023),
    ]),
]
for side in (-1, 1):
    head_parts.extend((
        capsule("Masseter and cheek", (side * .151, 1.693, -.52), (side * .123, 1.641, -.771), .077, .058),
        capsule("Whisker pad", (side * .089, 1.636, -.884), (side * .051, 1.613, -1.096), .027, .022),
        capsule("Angled orbital brow", (side * .149, 1.762, -.730), (side * .073, 1.735, -.850), .026, .024),
        capsule("Ear root", (side * .139, 1.829, -.515), (side * .169, 1.924, -.467), .071, .054),
    ))
head = sculpt("Canid skull and orbital sculpt", head_parts, .0062, pelt)
colorize(head, lambda p: coat_color(p, True))
bind(head, rigid("Head"))
groom("Cheek ruff and crown", head, rigid("Head"), 11900, True)

jaw = loft("Lower mandible", [
    (-.476, 1.588, .09, .04), (-.55, 1.565, .133, .059), (-.677, 1.549, .118, .049),
    (-.80, 1.553, .091, .032), (-.92, 1.563, .066, .023), (-1.035, 1.572, .053, .017),
    (-1.109, 1.577, .033, .012),
], pelt)
colorize(jaw, lambda p: tuple(channel * .70 for channel in coat_color(p, True)))
bind(jaw, rigid("Jaw"))
groom("Mandible and chin hair", jaw, rigid("Jaw"), 2200, face=True, darkness=.62)


def fixed(obj, name, color=None):
    bind(obj, rigid(name))
    if color:
        colorize(obj, color)
    return obj


fixed(loft("Pebbled black nose", [
    (-1.105, 1.626, .043, .021), (-1.126, 1.624, .056, .024), (-1.146, 1.620, .052, .021),
    (-1.158, 1.616, .036, .016), (-1.163, 1.613, .021, .010),
], nose, 32),
      "Head", lambda p: coat_color(p, leather=True))
fixed(loft("Upper gum", [(-.58, 1.618, .119, .024), (-.77, 1.611, .116, .028),
                         (-.97, 1.604, .080, .020), (-1.071, 1.605, .053, .015)], lip), "Head")
fixed(loft("Tongue and mouth floor", [(-.57, 1.575, .079, .033), (-.71, 1.566, .070, .022),
                                      (-.83, 1.575, .062, .018), (-.98, 1.586, .049, .011),
                                      (-1.044, 1.588, .026, .008)], tongue), "Jaw")


def cheek_fold(side):
    upper = [(side * x, y, z) for x, y, z in (
        (.139, 1.636, -.595), (.151, 1.635, -.657), (.139, 1.620, -.728),
        (.119, 1.616, -.790), (.104, 1.613, -.847),
    )]
    lower = [(side * x, y, z) for x, y, z in (
        (.133, 1.586, -.593), (.137, 1.577, -.649), (.119, 1.576, -.716),
        (.103, 1.583, -.781), (.091, 1.594, -.834),
    )]
    rows = 5
    vertices = []
    for top, bottom in zip(upper, lower):
        for row in range(rows):
            t = row / (rows - 1)
            point = Vector(top).lerp(Vector(bottom), t)
            point.x -= side * .016 * sin(t * tau * .5)
            point.z += .020 * sin(t * tau * .5)
            vertices.append(xyz(point))
    faces = [(i, i + rows, i + rows + 1, i + 1) for i in range((len(upper) - 1) * rows) if i % rows != rows - 1]
    fold = mesh("Elastic lip corner", vertices, faces, lip)
    head_group = fold.vertex_groups.new(name="Head")
    jaw_group = fold.vertex_groups.new(name="Jaw")
    for i in range(len(vertices)):
        t = (i % rows) / (rows - 1)
        if t < 1:
            head_group.add((i,), 1 - t, "REPLACE")
        if t > 0:
            jaw_group.add((i,), t, "REPLACE")
    fold.parent = rig
    fold.modifiers.new("Snarl deformation", "ARMATURE").object = rig


def spike(name, points, radii, mat, target):
    ring = 9
    vertices, faces = [], []
    points = [xyz(point) for point in points]
    for i, center in enumerate(points):
        tangent = (points[min(i + 1, len(points) - 1)] - points[max(0, i - 1)]).normalized()
        axis = tangent.cross(Vector((0, 1, 0))).normalized()
        if axis.length < .1:
            axis = tangent.cross(Vector((1, 0, 0))).normalized()
        up = tangent.cross(axis)
        for j in range(ring):
            angle = tau * j / ring
            vertices.append(center + radii[i] * (cos(angle) * axis + .81 * sin(angle) * up))
    for i in range(len(points) - 1):
        for j in range(ring):
            a, b = i * ring + j, i * ring + (j + 1) % ring
            faces.append((a, b, b + ring, a + ring))
    faces.extend((tuple(reversed(range(ring))), tuple(range(len(vertices) - ring, len(vertices)))))
    obj = mesh(name, vertices, faces, mat)
    normals_out(obj)
    fixed(obj, target)


def set_eye(side, suffix):
    center = xyz((side * eye_x, eye_height + .0015 * side, -eye_forward))
    normal = xyz((side * .33, .11, -.94)).normalized()
    horizontal = normal.cross(Vector((0, 0, 1))).normalized()
    vertical = horizontal.cross(normal).normalized()

    def socket_surface(point):
        hit, skin, _, _ = head.ray_cast(point + normal * .04, -normal, distance=.18)
        return skin if hit else point

    vertices, faces, colors = [], [], []
    rows, cols = 8, 28
    for col in range(cols + 1):
        u = col / cols * 2 - 1
        contour = max(.03, 1 - u * u) ** .75
        for row in range(rows + 1):
            v = row / rows * 2 - 1
            eye_y = v * contour + .56 * side * u
            point = center + horizontal * u * .022 + vertical * eye_y * .009
            depth = .0028 + .0034 * contour * (1 - v * v)
            vertices.append(socket_surface(point) + normal * depth)
            dx = (u + side * .16) * .025
            dy = (eye_y - .04) * .009
            radius = (dx * dx + dy * dy) ** .5
            iris = (1 - smooth(radius, .009, .012)) * smooth(radius, .0044, .0056)
            fibers = .82 + .18 * sin(atan2(dy, dx) * 17 + radius * 180)
            shade = 1 - .56 * smooth(v, .18, 1)
            amber = iris * fibers * shade
            colors.append((.012 + amber * .139, .009 + amber * .068, .007 + amber * .024))
            if col and row:
                i = len(vertices) - 1
                faces.append((i, i - 1, i - rows - 2, i - rows - 1))
    surface = fixed(mesh("Almond eye aperture." + suffix, vertices, faces, eye), "Head")
    values = surface.data.color_attributes.new(name="Pelt", type="FLOAT_COLOR", domain="POINT")
    for value, color in zip(values.data, colors):
        value.color = (*color, 1)

    for edge in (0, rows):
        line = [vertices[i * (rows + 1) + edge] for i in range(cols + 1)]
        margin = [p + normal * .0014 + vertical * (.0027 if edge else -.0021) for p in line]
        skin = [socket_surface(p + vertical * (.009 if edge else -.005)) + normal * .0008 for p in line]
        stride = len(line)
        quads = [(i, i + 1, i + stride + 1, i + stride) for i in range(stride * 2) if (i + 1) % stride]
        if edge == 0:
            quads = [tuple(reversed(quad)) for quad in quads]
        rim = fixed(mesh("Eyelid margin." + suffix, line + margin + skin, quads, eyelid), "Head")
        values = rim.data.color_attributes.new(name="Pelt", type="FLOAT_COLOR", domain="POINT")
        for i, value in enumerate(values.data):
            color = (.024, .018, .015) if i < 2 * stride else coat_color(skin[i - 2 * stride], True)
            value.color = (*color, 1)


def set_ear(side, suffix):
    # A hollow pinna with a broken outline, instead of a separate lump in the ear bowl.
    center = Vector((side * .168, 1.967, -.478))
    tip = 2.074 if side < 0 else 2.042
    edge = [
        (.096, 1.887, -.526), (.113, 1.974, -.544), (.145, 2.035, -.517),
        (.154, tip - .014, -.493), (.175, tip, -.479), (.181, tip - .028, -.478),
        (.203, tip - .037, -.474), (.220, 1.963, -.500), (.221, 1.892, -.489),
        (.168, 1.878, -.528),
    ]
    outer = [Vector((side * x, y, z)) for x, y, z in edge]
    inner = [center.lerp(p, .66) + Vector((0, 0, .021)) for p in outer]
    back = [center.lerp(p, .80) + Vector((0, 0, .064)) for p in outer]
    points = outer + inner + back + [center + Vector((0, 0, .044)), center + Vector((0, 0, .088))]
    size = len(outer)
    faces = []
    for i in range(size):
        following = (i + 1) % size
        faces.extend(((i, following, following + size, i + size),
                      (i + size, following + size, size * 3),
                      (following, i, i + size * 2, following + size * 2),
                      (following + size * 2, i + size * 2, size * 3 + 1)))
    ear = mesh("Torn ear with hollow pinna." + suffix, [xyz(point) for point in points], faces, pelt)
    normals_out(ear)
    fixed(ear, "Head")
    colors = ear.data.color_attributes.new(name="Pelt", type="FLOAT_COLOR", domain="POINT")
    for vertex, value in zip(ear.data.vertices, colors.data):
        rgb = coat_color(vertex.co, True) if vertex.index < size or size * 2 <= vertex.index < size * 3 else (.036, .020, .017)
        value.color = (*rgb, 1)


for side, suffix in ((-1, "L"), (1, "R")):
    cheek_fold(side)
    spike("Upper lip line." + suffix, [(side * .142, 1.632, -.652), (side * .124, 1.608, -.777),
        (side * .095, 1.599, -.899), (side * .063, 1.598, -1.034), (side * .036, 1.598, -1.105)],
        [.004, .010, .009, .007, .002], lip, "Head")
    spike("Lower lip line." + suffix, [(side * .133, 1.588, -.660), (side * .107, 1.585, -.789),
        (side * .071, 1.589, -.922), (side * .046, 1.590, -1.047), (side * .026, 1.584, -1.105)],
        [.004, .008, .007, .006, .002], lip, "Jaw")
    fixed(ellipsoid("Nostril." + suffix, (side * .037, 1.623, -1.152), (.014, .006, .008), inside), "Head")
    for i in range(4):
        y = 1.628 + i * .009
        z = -.958 - i * .016
        spike("Muzzle whisker." + suffix, [(side * .077, y, z), (side * .096, y - .003, z + .006),
            (side * (.125 + .006 * i), y - .012, z + .027 + i * .004)], [.00072, .00047, .00009], claw, "Head")
    set_eye(side, suffix)
    set_ear(side, suffix)
    for i in range(7):
        z = -1.065 + .057 * i + random.uniform(-.007, .007)
        x = side * (.045 + .0088 * i)
        length = (.057 + .003 * side if i == 1 else random.uniform(.013, .027))
        base_y = 1.603 + .006 * smooth(i, 3, 7)
        spike("Upper tooth", [(x, base_y, z), (x * 1.02, base_y - length * .36, z + .004),
              (x, base_y - length * .77, z + .010), (x * .89, base_y - length, z + .019)],
              [.013 if i == 1 else .008, .008, .004, .0009], ivory, "Head")
        lower_length = .034 if i == 1 else random.uniform(.012, .022)
        spike("Lower tooth", [(x * .87, 1.587, z + .025), (x * .90, 1.587 + lower_length * .65, z + .023),
                              (x * .87, 1.587 + lower_length, z + .017)],
              [.009, .005, .0009], ivory, "Jaw")
    hand_parts = [ellipsoid("Palm." + suffix, (side * .488, .470, -.401), (.092, .095, .052))]
    for i in range(5):
        x = side * .49 + (i - 1.5) * .044 if i < 4 else side * .374
        y = .414 if i < 4 else .477
        length = (.119 + .035 * sin((i + .3) * .89)) if i < 4 else .091
        base = (x, y, -.413)
        knuckle = (x + (i - 1.7) * .008, y - length * .54, -.426)
        tip = (knuckle[0], y - length, -.464)
        hand_parts.extend((capsule("Finger", base, knuckle, .025, .022),
                           capsule("Finger tip", knuckle, tip, .021, .019)))
        spike("Hooked hand claw", [tip, (tip[0], tip[1] - .036, tip[2] - .027), (tip[0], tip[1] - .049, tip[2] - .066)],
              [.016, .009, .001], claw, "Wrist." + suffix)
    hand = sculpt("Continuous palm and fingers." + suffix, hand_parts, .005, bare)
    fixed(hand, "Wrist." + suffix, lambda p: tuple(x * 1.43 for x in coat_color(p, leather=True)))
    fixed(ellipsoid("Paw." + suffix, (side * .35, .063, .30), (.096, .066, .142), bare),
          "Toes." + suffix, lambda p: coat_color(p, leather=True))
    for i in range(4):
        x = side * .35 + (i - 1.5) * .042
        spike("Paw claw", [(x, .048, .192), (x, .038, .160), (x, .021, .139)],
              [.015, .009, .001], claw, "Toes." + suffix)

tail = capsule("Low tail", (0, 1.10, .667), (-.105, .73, 1.07), .077, .074, pelt)
fixed(tail, "Tail", coat_color)
groom("Tail fur", tail, rigid("Tail"), 650)

for part in rig.children:
    if part.type != "MESH":
        continue
    weights = {group.name for group in part.vertex_groups}
    if weights and weights <= {"Head", "Jaw"}:
        # Carry the eyes, gums and groom along with the new profile without moving the rig.
        for vertex in part.data.vertices:
            x, forward, height = vertex.co
            muzzle = smooth(forward, .74, 1.16)
            vertex.co.x = x * (.92 - .06 * muzzle)
            vertex.co.y = forward + .052 * muzzle
            vertex.co.z = height - .034 * muzzle
        part.data.update()
    if part.data.materials[0] in (pelt, bare, nose):
        pelt_uv(part)

active(rig)
bpy.context.preferences.filepaths.save_version = 0
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT / "art/creatures/blackwood-ledge-wolf.blend"), compress=True)
for mat in (pelt, hair, nose, bare, inside, lip, tongue, ivory, claw, eye, eyelid):
    parts = [obj for obj in rig.children if obj.type == "MESH" and obj.data.materials[0] == mat]
    if len(parts) > 1:
        active(parts[0])
        for part in parts[1:]:
            part.select_set(True)
        bpy.ops.object.join()
        bpy.context.object.name = mat.name
bpy.ops.export_scene.gltf(
    filepath=str(ROOT / "web/src/assets/werewolf/ledge-wolf.glb"),
    export_format="GLB",
    export_draco_mesh_compression_enable=True,
    export_draco_position_quantization=15,
    export_draco_normal_quantization=10,
    export_animations=False,
    export_apply=False,
)

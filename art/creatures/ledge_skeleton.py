"""The bone names, hierarchy and rest axes used by Blackwood's ledge skin."""

import bpy
from mathutils import Vector


PARENTS = {
    "Chest": None,
    "Pelvis": None,
    "Head": "Chest",
    "Jaw": "Head",
    "Tail": "Pelvis",
}
for side in ("L", "R"):
    PARENTS.update({
        f"Shoulder.{side}": "Chest",
        f"Elbow.{side}": f"Shoulder.{side}",
        f"Wrist.{side}": f"Elbow.{side}",
        f"Hip.{side}": "Pelvis",
        f"Knee.{side}": f"Hip.{side}",
        f"Hock.{side}": f"Knee.{side}",
        f"Toes.{side}": f"Hock.{side}",
    })


def create_ledge_skeleton(positions):
    data = bpy.data.armatures.new("Ledge skeleton")
    rig = bpy.data.objects.new("Ledge wolf rig", data)
    bpy.context.collection.objects.link(rig)
    bpy.ops.object.select_all(action="DESELECT")
    rig.select_set(True)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode="EDIT")
    for name, parent in PARENTS.items():
        bone = data.edit_bones.new(name)
        bone.head = positions[name]
        bone.tail = bone.head + Vector((0, 0, .13))
        if parent:
            bone.parent = data.edit_bones[parent]
    bpy.ops.object.mode_set(mode="OBJECT")
    return rig


def puppet_rest():
    """Close-up bind positions in Blender space, from the game's createWolf()."""
    game = {
        "Chest": (0, 1.13, .232),
        "Pelvis": (0, 1.106, .419),
        "Head": (0, 1.705, -.612),
        "Jaw": (0, 1.622, -.565),
        "Tail": (0, 1.09, .706),
    }
    for sign, side in ((-1, "L"), (1, "R")):
        game.update({
            f"Shoulder.{side}": (sign * .342, 1.637, -.177),
            f"Elbow.{side}": (sign * .486, 1.178, -.129),
            f"Wrist.{side}": (sign * .486, .537, -.376),
            f"Hip.{side}": (sign * .229, 1.106, .419),
            f"Knee.{side}": (sign * .349, .706, .201),
            f"Hock.{side}": (sign * .384, .327, .584),
            f"Toes.{side}": (sign * .349, .062, .350),
        })
    return {name: Vector((x, -z, y)) for name, (x, y, z) in game.items()}

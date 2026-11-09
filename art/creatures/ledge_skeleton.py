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

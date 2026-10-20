"""Version shims for the animation and material APIs.

Blender 4.4 introduced slotted (layered) actions; 5.0 removed the legacy Action.fcurves /
Action.groups access. F-Curves now live in channelbags (layer -> strip -> channelbag per slot).
These helpers keep the add-on working on 4.2 LTS (legacy actions) and 4.4+ / 5.x (slotted)."""
import bpy

HAS_SLOTS = hasattr(bpy.types, 'ActionSlot')  # Blender 4.4+


def action_fcurves(action, slot=None):
    """All F-Curves of an action (optionally only those of one slot), on any Blender version."""
    if HAS_SLOTS and getattr(action, 'layers', None) is not None and (
            not hasattr(action, 'fcurves') or getattr(action, 'is_action_layered', False)):
        out = []
        for layer in action.layers:
            for strip in layer.strips:
                for cb in getattr(strip, 'channelbags', ()):
                    if slot is None or cb.slot == slot:
                        out.extend(cb.fcurves)
        return out
    return list(getattr(action, 'fcurves', ()))


def has_fcurves(action):
    return len(action_fcurves(action)) > 0


class ActionWriter:
    """Assigns `action` to `id_owner` and creates groups / F-Curves in it.
    On 4.4+ a slot named after the owner is created (identifier 'OB<name>'), so assigning any of
    the imported actions to that object later picks the right slot automatically."""

    def __init__(self, action, id_owner):
        self.action = action
        if id_owner.animation_data is None:
            id_owner.animation_data_create()
        ad = id_owner.animation_data
        self.cb = None
        if HAS_SLOTS:
            from bpy_extras import anim_utils
            slot = next((s for s in action.slots if s.identifier == 'OB' + id_owner.name), None)
            if slot is None:
                slot = action.slots.new(id_type='OBJECT', name=id_owner.name)
            ad.action = action
            if ad.action_slot != slot:
                ad.action_slot = slot
            self.cb = anim_utils.action_ensure_channelbag_for_slot(action, slot)
        else:
            ad.action = action

    def group(self, name):
        groups = self.cb.groups if self.cb is not None else self.action.groups
        return groups.get(name) or groups.new(name)

    def fcurve(self, data_path, index, group_name=""):
        # some stock SKMs repeat a bone name (e.g. fire_Snake 'origin'): reuse the curve instead of failing
        fcs = self.cb.fcurves if self.cb is not None else self.action.fcurves
        old = fcs.find(data_path, index=index)
        if old is not None:
            return old
        if self.cb is not None:
            return self.cb.fcurves.new(data_path, index=index, group_name=group_name)
        return self.action.fcurves.new(data_path, index=index, action_group=group_name)


def enable_material_nodes(mat):
    """Material.use_nodes is always on (and deprecated) in Blender 5.0+."""
    if bpy.app.version < (5, 0, 0):
        mat.use_nodes = True


def material_uses_nodes(mat):
    if bpy.app.version >= (5, 0, 0):
        return mat.node_tree is not None
    return mat.use_nodes

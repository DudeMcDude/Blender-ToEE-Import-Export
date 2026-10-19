"""Sidebar panel (3D View > N > ToEE) to add, edit and remove SKA animation events on the
active object's action. Events are pose markers (see ska_events)."""
import bpy
from bpy.props import EnumProperty, IntProperty, StringProperty
from . import ska_events

# Event kinds found in the stock SKA files (tools/debug/event_survey.py over ToEE1-4.dat):
# footstep 25166, sound 5364, action/origin 4855, action/Bip01 3242, particles 2202, shake 874,
# fade_to 23, action/slimeRoot 10, balor_death 1.
KINDS = [
    ('FOOTSTEP', "Footstep", "script: anim_obj.footstep()"),
    ('SHAKE', "Screen shake", "script: game.shake (amplitude, duration ms), e.g. game.shake (20, 800)"),
    ('SOUND', "Sound", "script: game.sound_local_obj ( sound id, anim_obj )"),
    ('PARTICLES', "Particles", "script: game.particles( 'name', anim_obj )"),
    ('HIT', "Action (hit / release frame)", "action: <bone>, the frame the attack hits or the spell/missile is released"),
    ('FADE', "Fade out", "script: anim_obj.fade_to( 0, rate, n, OBJFADE_C_POOP_OFF ) (death animations)"),
    ('CUSTOM', "Custom", "any type (script/action/end) and text"),
]


def _action(context):
    ob = context.object
    ad = ob.animation_data if ob else None
    return ad.action if ad else None


class TOEE_OT_event_add(bpy.types.Operator):
    """Add a ToEE animation event at the current frame of the active action"""
    bl_idname = "toee.event_add"
    bl_label = "Add ToEE Event"
    bl_options = {'REGISTER', 'UNDO'}

    kind: EnumProperty(name="Kind", items=KINDS, default='FOOTSTEP')
    amplitude: IntProperty(name="Amplitude", default=20, min=0)
    duration: IntProperty(name="Duration (ms)", default=800, min=0)
    sound_id: IntProperty(name="Sound ID", default=0, min=0)
    particles: StringProperty(name="Particle system", default="")
    bone: StringProperty(name="Bone", default="Bip01")
    fade_rate: IntProperty(name="Fade rate", default=10)
    fade_n: IntProperty(name="Fade n", default=2)
    ev_type: StringProperty(name="Type", default="script", maxlen=47)
    text: StringProperty(name="Text", default="", maxlen=127)

    @classmethod
    def poll(cls, context):
        return _action(context) is not None

    def event(self):
        k = self.kind
        if k == 'FOOTSTEP': return 'script', 'anim_obj.footstep()'
        if k == 'SHAKE': return 'script', 'game.shake (%d, %d)' % (self.amplitude, self.duration)
        if k == 'SOUND': return 'script', 'game.sound_local_obj ( %d, anim_obj )' % self.sound_id
        if k == 'PARTICLES': return 'script', "game.particles( '%s', anim_obj )" % self.particles
        if k == 'HIT': return 'action', self.bone
        if k == 'FADE': return 'script', 'anim_obj.fade_to( 0, %d, %d, OBJFADE_C_POOP_OFF )' % (self.fade_rate, self.fade_n)
        return self.ev_type.strip(), self.text.strip()

    def draw(self, context):
        l = self.layout; l.prop(self, 'kind'); k = self.kind
        if k == 'SHAKE': l.prop(self, 'amplitude'); l.prop(self, 'duration')
        elif k == 'SOUND': l.prop(self, 'sound_id')
        elif k == 'PARTICLES': l.prop(self, 'particles')
        elif k == 'HIT': l.prop(self, 'bone')
        elif k == 'FADE': l.prop(self, 'fade_rate'); l.prop(self, 'fade_n')
        elif k == 'CUSTOM': l.prop(self, 'ev_type'); l.prop(self, 'text')
        t, x = self.event(); l.label(text="%s: %s" % (t, x))

    def invoke(self, context, event):
        if self.kind == 'FOOTSTEP':
            return self.execute(context)
        return context.window_manager.invoke_props_dialog(self, width=420)

    def execute(self, context):
        act = _action(context); t, x = self.event()
        if t.lower() not in ska_events.TYPES:
            self.report({'WARNING'}, "type '%s' is not script/action/end: the engine ignores it" % t)
        if len(t.encode()) > 47 or len(x.encode()) > 127:
            self.report({'ERROR'}, "too long (type max 47, text max 127 bytes)"); return {'CANCELLED'}
        ska_events.add_event(act, context.scene.frame_current, t, x)
        act.pose_markers.active_index = len(act.pose_markers) - 1
        return {'FINISHED'}


class TOEE_OT_event_edit(bpy.types.Operator):
    """Edit the active event (type, text, frame)"""
    bl_idname = "toee.event_edit"
    bl_label = "Edit ToEE Event"
    bl_options = {'REGISTER', 'UNDO'}

    ev_type: StringProperty(name="Type", maxlen=47)
    text: StringProperty(name="Text", maxlen=127)
    frame: IntProperty(name="Frame")

    @classmethod
    def poll(cls, context):
        act = _action(context)
        return act is not None and 0 <= act.pose_markers.active_index < len(act.pose_markers)

    def invoke(self, context, event):
        act = _action(context); m = act.pose_markers[act.pose_markers.active_index]
        self.ev_type, self.text = ska_events.marker_event(act, m); self.frame = m.frame
        return context.window_manager.invoke_props_dialog(self, width=480)

    def execute(self, context):
        act = _action(context); i = act.pose_markers.active_index; m = act.pose_markers[i]
        t, x = self.ev_type.strip(), self.text.strip()
        if (t, x) == ska_events.marker_event(act, m):
            m.frame = self.frame  # only moved: keep the original record (and its exact bytes)
            return {'FINISHED'}
        act.pose_markers.remove(m)
        ska_events.add_event(act, self.frame, t, x)
        # keep the event at its place in the list (event order is kept on export)
        return {'FINISHED'}


class TOEE_OT_event_remove(bpy.types.Operator):
    """Remove the active event"""
    bl_idname = "toee.event_remove"
    bl_label = "Remove ToEE Event"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return TOEE_OT_event_edit.poll(context)

    def execute(self, context):
        act = _action(context); pm = act.pose_markers; i = pm.active_index
        if not act.get("toee_event_markers", 0):
            ska_events.store_from_json(act)
        pm.remove(pm[i]); pm.active_index = min(i, len(pm) - 1)
        return {'FINISHED'}


class TOEE_OT_event_jump(bpy.types.Operator):
    """Go to the active event's frame"""
    bl_idname = "toee.event_jump"
    bl_label = "Jump to Event"

    @classmethod
    def poll(cls, context):
        return TOEE_OT_event_edit.poll(context)

    def execute(self, context):
        act = _action(context); context.scene.frame_set(act.pose_markers[act.pose_markers.active_index].frame)
        return {'FINISHED'}


class TOEE_UL_events(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index=0, flt_flag=0):
        row = layout.row(align=True)
        row.label(text="%d" % (item.frame - 1), icon='MARKER')  # SKA frame (Blender frame - 1)
        row.prop(item, "name", text="", emboss=False)


class TOEE_PT_events(bpy.types.Panel):
    bl_label = "ToEE Animation Events"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "ToEE"

    def draw(self, context):
        l = self.layout; act = _action(context)
        if act is None:
            l.label(text="Select an object with an active action"); return
        l.label(text="Action: %s" % act.name, icon='ACTION')
        if not act.get("toee_event_markers", 0) and act.get("toee_events"):
            l.label(text="Events stored without markers (older import): adding one converts them", icon='INFO')
        row = l.row()
        row.template_list("TOEE_UL_events", "", act, "pose_markers", act.pose_markers, "active_index", rows=4)
        col = row.column(align=True)
        col.operator_menu_enum("toee.event_add", "kind", text="", icon='ADD')
        col.operator("toee.event_remove", text="", icon='REMOVE')
        col.operator("toee.event_edit", text="", icon='GREASEPENCIL')
        col.operator("toee.event_jump", text="", icon='TIME')
        l.label(text="Frame %d (SKA frame %d)" % (context.scene.frame_current, context.scene.frame_current - 1))

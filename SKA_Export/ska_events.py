"""SKA animation events <-> Blender action pose markers.

SKA event record (Temple+ aas_skeleton.h SkelAnimEvent, 178 bytes): int16 frame, char type[48],
char action[128]. The engine accepts the types "script" (the text is run as Python with anim_obj
set, e.g. footsteps, sounds, particles), "action" (sets the action flag: the hit/release frame; the
text names a bone such as "Bip01" or "origin") and "end" (case-insensitive, aas_anim_player.cpp
GetEventType); other types are dropped with a warning.

In Blender every event is a pose marker on its action (markers travel with the action, so they
survive switching actions), named "<type>: <text>" at frame 1 + event frame (SKA frame 0 is
Blender frame 1). Marker names are limited to 63 bytes, so the full text and the original 48/128
byte fields (vanilla files keep junk after the NUL) are kept in the action's "toee_events" JSON;
a marker whose name is unchanged gets them back on export, so unchanged events are byte-identical.
To add an event, add a pose marker named e.g. "script: anim_obj.footstep()" or "action: Bip01"."""
import json

MARKER_NAME_MAX = 63
TYPES = ("script", "action", "end")


def marker_name(ev_type, text):
    n = "%s: %s" % (ev_type, text)
    b = n.encode('utf-8')
    if len(b) > MARKER_NAME_MAX:
        n = b[:MARKER_NAME_MAX - 3].decode('utf-8', 'ignore') + "..."
    return n


def store_events(action, events):
    """events: SkaEvent list from the file. Writes the JSON and one pose marker per event."""
    recs = []
    for e in events:
        recs.append([e.frame_id, str(e.type), str(e.action),
                     bytes(e.type.raw or b'').hex(), bytes(e.action.raw or b'').hex()])
    action["toee_events"] = json.dumps(recs)
    for m in list(action.pose_markers):
        action.pose_markers.remove(m)
    for r in recs:
        m = action.pose_markers.new(marker_name(r[1], r[2]))
        m.frame = 1 + r[0]
    action["toee_event_markers"] = 1


def _stored(action):
    out = []
    for r in json.loads(action.get("toee_events", "[]")):
        r = list(r) + ["", ""]
        out.append(dict(frame=int(r[0]), type=str(r[1]), text=str(r[2]), type_raw=r[3], text_raw=r[4]))
    return out


def collect_events(action, report=None):
    """[(frame, type, text, type_raw|None, text_raw|None)] for export, in marker order.
    Actions imported by older versions of the add-on (JSON only, no marker flag) use the JSON."""
    stored = _stored(action)
    if not action.get("toee_event_markers", 0):
        return [(s['frame'], s['type'], s['text'], s['type_raw'], s['text_raw']) for s in stored]
    used = [False] * len(stored)
    out = []
    for m in action.pose_markers:
        frame = int(m.frame) - 1
        hit = None
        for i, s in enumerate(stored):
            if not used[i] and marker_name(s['type'], s['text']) == m.name:
                hit = i
                if s['frame'] == frame:
                    break  # prefer the exact original (same name and frame)
        if hit is not None:
            used[hit] = True
            s = stored[hit]
            out.append((frame, s['type'], s['text'], s['type_raw'], s['text_raw']))
            continue
        name = m.name
        if ':' in name:
            t, txt = name.split(':', 1)
            t, txt = t.strip(), txt.strip()
        else:
            t, txt = name.strip(), ""
        if t.lower() not in TYPES:
            if report:
                report("WARNING: action '%s' marker '%s': unknown event type '%s' (script/action/end); "
                       "the engine will ignore it" % (action.name, name, t))
        out.append((frame, t, txt, None, None))
    for f, *_ in out:
        if not (-32768 <= f <= 32767):
            raise ValueError("event frame %d out of range in action '%s'" % (f, action.name))
    return out


def make_ska_events(action, SkaEvent, report=None):
    evs = []
    for frame, t, txt, traw, xraw in collect_events(action, report):
        if len(t.encode()) > 47 or len(txt.encode()) > 127:
            raise ValueError("event '%s: %s' too long (type max 47, text max 127 bytes)" % (t, txt))
        e = SkaEvent(frame, t, txt)
        if traw: e.type.raw = bytes.fromhex(traw)
        if xraw: e.action.raw = bytes.fromhex(xraw)
        evs.append(e)
    return evs


def add_event(action, frame, ev_type, text):
    """Add an event at Blender frame `frame`. The full text is recorded in "toee_events" too, so
    texts longer than a marker name (63 bytes) survive export."""
    import json as _j
    if not action.get("toee_event_markers", 0):
        # older import (JSON only): turn the stored events into markers first
        store_from_json(action)
    recs = _j.loads(action.get("toee_events", "[]"))
    recs.append([int(frame) - 1, ev_type, text, "", ""])
    action["toee_events"] = _j.dumps(recs)
    m = action.pose_markers.new(marker_name(ev_type, text))
    m.frame = int(frame)
    action["toee_event_markers"] = 1
    return m


def store_from_json(action):
    for s in _stored(action):
        m = action.pose_markers.new(marker_name(s['type'], s['text'])); m.frame = 1 + s['frame']
    action["toee_event_markers"] = 1


def marker_event(action, marker):
    """(type, full text) of a marker, using the stored full text when the name was truncated."""
    for s in _stored(action):
        if marker_name(s['type'], s['text']) == marker.name:
            return s['type'], s['text']
    n = marker.name
    if ':' in n:
        t, x = n.split(':', 1); return t.strip(), x.strip()
    return n.strip(), ""

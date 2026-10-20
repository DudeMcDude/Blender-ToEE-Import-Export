import struct
import time
from io import BytesIO
from typing import List

def write_byte(file, data):
    file.write( struct.pack("<b", data))

def write_short(file, data):
    file.write( struct.pack("<h", data))

def write_int(file, data):
    file.write( struct.pack("<i", data))

def write_float(file, data):
    file.write( struct.pack("<f", data))

def write_short_list(file, data):
    file.write( struct.pack("<%dh" % len(data), *data))

def write_float_list(file, data):
    file.write( struct.pack("<%df" % len(data), *data))

def matrix4_to_3x4_array(mat):
    """Concatenate matrix's columns into a single, flat tuple"""
    return tuple(f for v in mat[0:3] for f in v)

class FixedLengthName(object):
    __slots__ = "name", "size", "raw"

    def __init__(self, Name="", Size=48):
        if len(Name) == 0:
            self.name = ""
        else:
            self.name = Name
        self.size = Size
        self.raw = None  # original bytes incl. whatever follows the NUL (vanilla files have junk there)
        assert len(self.name) <= Size, "FixedLengthName: must be shorter than Size (%d)!" % Size

    def from_raw_data(self, rawdata):
        self.name = rawdata.split(b'\0')[0].decode()
        self.raw = bytes(rawdata[:self.size])

    def get_size(self):
        return self.size

    def write(self, file):
        if self.raw is not None and len(self.raw) == self.size and self.raw.split(b'\0')[0] == self.name.encode():
            file.write(self.raw)  # unchanged name: keep the original padding bytes
            return
        b_name = bytes(self.name.encode() )
        name_len = len(b_name)
        file.write(b_name)
        for p in range(0, self.size - name_len):
            file.write(b'\0')

    def __str__(self):
        return str(self.name)


########## SKM structs
class SkmVertex(object):
    __slots__ = "pos", "normal", "uv", "attachment_bones", "attachment_weights"
    pos: List[float]
    normal: List[float]
    uv: List[float]
    attachment_bones: List[int]
    attachment_weights: List[float]

    def __init__(self):
        self.pos = []
        self.normal = []
        self.uv = []
        self.attachment_bones = []
        self.attachment_weights = []

    @property
    def attachment_count(self):
        return len(self.attachment_bones)

    def from_raw_data(self, rawdata):
        self.pos = struct.unpack('<4f', rawdata[0:0 + 16])
        self.normal = struct.unpack('<4f', rawdata[0 + 16:0 + 32])
        self.uv = struct.unpack('<2f', rawdata[0 + 32:0 + 40])
        dummy = struct.unpack('<h', rawdata[40:42])[0]
        # if dummy != 0:
            # print('sheeit')
        attachment_count = struct.unpack('<h', rawdata[42:44])[0]
        if attachment_count > 6:
            raise Exception("SkmVertex: Unexcepted number of attachments read!")
        attachment_count = max(0, min(attachment_count, 6))
        self.attachment_bones = []
        self.attachment_bones = struct.unpack("<%dh" % attachment_count, rawdata[44:44 + attachment_count * 2])
        self.attachment_weights = struct.unpack("<%df" % attachment_count,
                                                rawdata[44 + 12:44 + 12 + attachment_count * 4])

    def write(self, file):
        write_float_list(file, self.pos)
        write_float_list(file, self.normal)
        write_float_list(file, self.uv)
        
        file.write( struct.pack('<h', 0) )
        file.write( struct.pack('<h', self.attachment_count) )

        write_short_list( file, [*self.attachment_bones,] + [0 for _ in range(self.attachment_count, 6)] )
        write_float_list( file, [*self.attachment_weights,] + [0.0 for _ in range(self.attachment_count, 6)] )
        return

    @staticmethod
    def get_size():
        return 80

class SkmBone:
    def __init__(self, Name="", Parent_id=0):
        self.flags = 0
        self.parent_id = Parent_id
        self.name = FixedLengthName(Name, 48)
        self.world_inverse = [[0, 0, 0, 0] for i in range(0, 3)]  # 3x4 matrix (3x3 rotation, 3x1 translation)

    @property
    def world_inverse_matrix(self):
        # return mathutils.Matrix(self.world_inverse + [[0, 0, 0, 1]])
        return self.world_inverse + [[0, 0, 0, 1]]

    def from_raw_data(self, rawdata):
        self.flags = struct.unpack('<h', rawdata[0:2])[0]
        self.parent_id = struct.unpack('<h', rawdata[2:4])[0]
        self.name.from_raw_data(rawdata[4:52])
        tmp = struct.unpack('<12f', rawdata[52:52 + 48])
        self.world_inverse = [tmp[i * 4:(i + 1) * 4] for i in range(0, 3)] 
        # [ [t0...t3],
        #   [t4...t7],
        #   [t8..t11] ]
        return

    def write(self, file):
        write_short(file, self.flags) 
        write_short(file, self.parent_id)
        self.name.write(file)
        for i in range(0, 3):
            write_float_list(file, self.world_inverse[i])

    @staticmethod
    def get_size():
        return 100

    def __str__(self):
        return self.name.__str__()

class SkmMaterial(object):
    '''
    id - path relative to ToEE data dir
    '''
    __slots__ = ['id']
    id: FixedLengthName

    def __init__(self, id=""):
        self.id = FixedLengthName(id, 128)

    def from_raw_data(self, rawdata):
        self.id.from_raw_data(rawdata)

    def write(self, file):
        self.id.write(file)
    @staticmethod
    def get_size():
        return 128

class MdfFile(object):
    __slots__ = ['texture_filepath']
    texture_filepath: str

    def __init__(self):
        self.texture_filepath = ''
        return

    def from_raw_data(self, rawdata):
        decoded = rawdata.decode()
        texture_files = decoded.split("\"")
        if len(texture_files) < 2:
            raise Exception('No texture set in MDF!')
        if len(texture_files) > 3:
            print('Unhandled MDF 2nd texture!')
            # TODO handling more than one texture (e.g. phase spiders)
        
        self.texture_filepath = texture_files[1]
        return
    def write(self, file):
        file.write("Textured\n")
        file.write("Texture \"")
        file.write(self.texture_filepath)
        file.write("\"\n")
        return
    
class SkmFace(object):
    __slots__ = "material_id", "vertex_ids"
    material_id: int
    vertex_ids: List[int]
    def from_raw_data(self, rawdata):
        self.material_id = struct.unpack('<h', rawdata[0:2])[0]
        self.vertex_ids = struct.unpack('<3h', rawdata[2:8])

    def write(self, file):
        write_short(file, self.material_id)
        write_short_list(file, self.vertex_ids)
        return
    
    @staticmethod
    def get_size():
        return 8

########## SKA structs
class SkaBone(object):
    __slots__ = "flags", "parent_id", "name", "scale", "rotation", "translation"
    flags: int
    parent_id: int
    name: FixedLengthName
    scale: tuple
    rotation: tuple
    translation: tuple

    def __init__(self, Name="", Parent_id=0):
        self.flags = 0
        self.parent_id = Parent_id
        self.name = FixedLengthName(Name, 40)

    @property
    def rotation_quaternion(self):
        if self.rotation and len(self.rotation) == 4:
            return [self.rotation[3], self.rotation[0], self.rotation[1], self.rotation[2]]
        return None

    def from_raw_data(self, rawdata):
        self.flags = struct.unpack('<h', rawdata[0:2])[0]
        self.parent_id = struct.unpack('<h', rawdata[2:4])[0]
        self.name.from_raw_data(rawdata[4:44])
        # print(self.name.name)
        field2c = struct.unpack('<i', rawdata[44:48])[0]
        field30 = struct.unpack('<i', rawdata[48:52])[0]
        if field30 != 0 or field2c != 0:
            print('interesting! field2c = ', field2c)
        scale = struct.unpack('<4f', rawdata[52:52 + 16])
        self.scale = scale[0:3]
        rotation = struct.unpack('<4f', rawdata[52 + 16:52 + 32])
        self.rotation = rotation
        translation = struct.unpack('<4f', rawdata[52 + 32:52 + 48])
        self.translation = translation[0:3]

    def write(self, file):
        write_short(file, self.flags) 
        write_short(file, self.parent_id)
        self.name.write(file)
        file.write( struct.pack("<2i", 0,0)) # unknown/unused fields 0x2c, 0x30
        write_float_list(file, self.scale + (0.0,) )
        write_float_list(file, self.rotation)
        write_float_list(file, self.translation + (0.0,) )

    @staticmethod
    def get_size():
        return 100

    def __str__(self):
        return self.name.__str__()

class SkaAnimKeyframe:
    __slots__ = "frame", "bone_data"
    frame: int
    bone_data: dict

    def __init__(self, frame_):
        self.frame = frame_
        self.bone_data = dict()
        return
    
class SkaAnimFileKeyframeBoneData:
    __slots__ = "scale", "scale_frame", "rotation", "rotation_frame", "translation","translation_frame", "header"
    scale: List[int]
    scale_frame: int
    rotation: List[int]
    rotation_frame: int
    translation: List[int]
    translation_frame: int
    header: int # flags. 1 - has data; 2 - has loc; 4 - has rot; 8 - has scale; 16:end - bone_idx 

    def __init__(self, hdr, sc, sc_fr, rot, rot_fr, loc, loc_fr):
        self.header = hdr
        self.scale = sc
        self.scale_frame = sc_fr
        self.rotation = rot
        self.rotation_frame = rot_fr
        self.translation = loc
        self.translation_frame = loc_fr
        return
    

class SkaAnimKeyframeBoneData(object):
    __slots__ = "bone_id", "flags", "frame", "scale_next_frame", "scale", "rotation_next_frame", "rotation", "translation_next_frame", "translation"

    def __init__(self):
        self.bone_id = -1
        self.flags = 0
        self.frame = -1
        self.scale_next_frame = -1
        self.rotation_next_frame = -1
        self.translation_next_frame = -1
        self.scale = [1, 1, 1]
        self.rotation = [0.0,0,0.0, 1.0]  # X,Y,Z, scalar
        self.translation = [0, 0, 0]

    def has_scale_data(self):
        if self.frame < 0:
            return True
        if self.flags & 8:
            return True
        return False

    def has_rot_data(self):
        if self.frame < 0:
            return True
        if self.flags & 4:
            return True
        return False

    def has_trans_data(self):
        if self.frame < 0:
            return True
        if self.flags & 2:
            return True
        return False

    @staticmethod
    def get_size():
        return 22

class SkaAnimStreamHeader(object):
    __slots__ = "frame_count", "variation_id", "frame_rate", "dps", "data_offset"

    def __init__(self):
        self.frame_count = 0
        self.variation_id = 0
        self.frame_rate = 1.0
        self.dps = 30.0
        self.data_offset = 0

    def from_raw_data(self, rawdata):
        self.frame_count = struct.unpack('<H', rawdata[0:2])[0]
        self.variation_id = struct.unpack('<h', rawdata[2:4])[0]
        self.frame_rate = struct.unpack('<f', rawdata[4:8])[0]
        self.dps = struct.unpack('<f', rawdata[8:12])[0]
        self.data_offset = struct.unpack('<i', rawdata[12:16])[0]
    def write(self, file):
        write_short(file, self.frame_count)
        write_short(file, self.variation_id)
        write_float(file, self.frame_rate)
        write_float(file, self.dps)
        assert self.data_offset != 0, "uninited data_offset"
        write_int(file, self.data_offset)
        return
    @staticmethod
    def get_size():
        return 2 + 2 + 4 + 4 + 4

class SkaAnimStreamInstance:
    """
    An animation stream which is an actual physical keyframe stream
    can be instanced multiple times within an animation file.
    I.e., unarmed_unarmed_rturn might just be identical to sword_sword_rturn
    in terms of keyframes, but might for example be played at a different speed.
    """

    def __init__(self, name, frame_rate, dps):
        self.name = name
        self.frame_rate = frame_rate
        self.dps = dps

class SkaAnimStream:
    def __init__(self, name):
        """
        :type data: BytesIO
        :type header: SkaAnimStreamHeader
        """
        self.name = name
        self.scale_factor = 1.0
        self.location_factor = 1 / 32767.0
        self.instances = []

        self.scale_channels = dict()
        self.rotation_channels = dict()
        self.location_channels = dict()
        self.initial_state = None
        self.raw_frames = []

    def add_instance(self, instance):
        """
        :rtype: SkaAnimStreamInstance
        """
        self.instances.append(instance)

    def read(self, data):
        """
        :type data: BytesIO
        """

        (scale_factor, location_factor) = struct.unpack("<ff", data.read(8))
        self.scale_factor = scale_factor
        self.location_factor = location_factor
        rotation_factor = 1 / 32767.0

        scale_channels = dict()
        rotation_channels = dict()
        location_channels = dict()
        raw_frames = []

        # Unpack into stream of shorts
        def next_short():
            return struct.unpack("<h", data.read(2))[0]

        def next_scale():
            return struct.unpack("<hhh", data.read(3 * 2))
            
        def convert_scale(sc):
            (x,y,z) = sc
            return [
                x * scale_factor,
                y * scale_factor,
                z * scale_factor
            ]

        def next_rotation():
            return struct.unpack("<hhhh", data.read(4 * 2))

        def convert_rotation(rot):
            (x, y, z, w) = rot
            return [
                w * rotation_factor,
                x * rotation_factor,
                y * rotation_factor,
                z * rotation_factor
            ]
        
        def next_location():
            return struct.unpack("<hhh", data.read(3 * 2))
            
        def convert_location(loc):
            (x, y, z) = loc
            return [
                x * location_factor,
                y * location_factor,
                z * location_factor
            ]
        
        # Read frame 0 for all affected bones
        bone_idx = next_short()
        frame0 = SkaAnimKeyframe(-1)
        
        while bone_idx >= 0:
            sc = next_scale()
            rot = next_rotation()
            loc = next_location()
            scale_channels[bone_idx] = [(0, convert_scale(sc))]
            rotation_channels[bone_idx] = [(0, convert_rotation(rot))]
            location_channels[bone_idx] = [(0, convert_location(loc))]
            frame0.bone_data[bone_idx] = SkaAnimFileKeyframeBoneData(-1, sc, -1, rot, -1, loc, -1)
            bone_idx = next_short()

        self.initial_state = frame0

        # begin reading actual keyframes        
        hdr = next_short()
        while hdr & 1 == 0:
            frame = hdr >> 1
            
            newframe = SkaAnimKeyframe(frame)

            if frame == -1:
                break

            hdr = next_short()
            while hdr & 1 == 1:
                bone_idx = hdr >> 4
                channels_used = (hdr >> 1) & 7
                sc = None
                sc_fr = -1
                rot = None
                rot_fr = -1
                loc = None
                loc_fr = -1
                if channels_used & 4:
                    sc_fr = next_short()
                    sc = next_scale()
                    scale_channels[bone_idx].append((sc_fr, convert_scale(sc)))

                if channels_used & 2:
                    rot_fr = next_short()
                    rot = next_rotation()
                    rotation_channels[bone_idx].append((rot_fr, convert_rotation(rot)))

                if channels_used & 1:
                    loc_fr = next_short()
                    loc = next_location()
                    location_channels[bone_idx].append((loc_fr, convert_location(loc)))
                
                newframe.bone_data[bone_idx] = SkaAnimFileKeyframeBoneData(hdr, sc, sc_fr, rot, rot_fr, loc, loc_fr)
                hdr = next_short()
            
            raw_frames.append(newframe)

        self.raw_frames = raw_frames
        self.scale_channels = scale_channels
        self.rotation_channels = rotation_channels
        self.location_channels = location_channels
        

    def write(self, file):
        scale_factor = self.scale_factor
        location_factor = self.location_factor
        write_float_list(file, [scale_factor, location_factor])


        # Write frame 0 for all affected bones
        for bone_idx, kf in self.initial_state.bone_data.items():
            write_short(file, bone_idx)
            write_short_list( file, kf.scale )
            write_short_list( file, kf.rotation )
            write_short_list( file, kf.translation )

        # terminate list of bones
        write_short(file, -2)
        
        # begin writing actual keyframes
        for rawframe in self.raw_frames:
            frame = rawframe.frame
            hdr = ( 0 | (frame << 1) )
            write_short( file, hdr )

            for bone_idx, kf in rawframe.bone_data.items():
                hdr = kf.header
                write_short(file, hdr)

                channels_used = (hdr >> 1) & 7
                if channels_used & 4:
                    write_short(file, kf.scale_frame)
                    write_short_list(file, kf.scale)
                    
                if channels_used & 2:
                    write_short(file, kf.rotation_frame)
                    write_short_list(file, kf.rotation)

                if channels_used & 1:
                    write_short(file, kf.translation_frame)
                    write_short_list(file, kf.translation)
            
        write_short( file, -2) # terminator
        
        return
class SkaEvent(object):
    __slots__ = "frame_id", "type", "action"

    def __init__(self, frame_id=0, event_type="", action=""):
        self.frame_id = frame_id
        self.type = FixedLengthName(event_type, 48)
        self.action = FixedLengthName(action, 128)

    @staticmethod
    def from_raw_data(rawdata, count):
        result = []
        max_count = len(rawdata) / SkaEvent.get_size()
        if count < max_count:
            count = max_count
        DATUM_SIZE = SkaEvent.get_size()
        for i in range(0, count):
            new_event = SkaEvent()
            new_event.frame_id = struct.unpack('<h', rawdata[0 + i * DATUM_SIZE:2 + i * DATUM_SIZE])[0]
            new_event.type.from_raw_data(rawdata[2 + i * DATUM_SIZE:2 + 48 + i * DATUM_SIZE])
            new_event.action.from_raw_data(rawdata[50 + i * DATUM_SIZE:50 + 128 + i * DATUM_SIZE])
            result.append(new_event)
        return result

    def write(self, file):
        write_short(file, self.frame_id)
        self.type.write(file)
        self.action.write(file)
        return

    @staticmethod
    def get_size():
        return 2 + 48 + 128

class SkaAnimHeader(object):
    __slots__ = "name", "drive_type", "loopable", "event_count", "event_offset", "stream_count", "unk", "stream_headers"

    def __init__(self, name=""):
        self.name = FixedLengthName(name, 64)
        self.drive_type = 0
        self.loopable = 0
        self.event_count = 0
        self.event_offset = 0
        self.stream_count = 0
        self.stream_headers = []

    def from_raw_data(self, rawdata):
        self.name.from_raw_data(rawdata[0:64])
        self.drive_type = struct.unpack('<b', rawdata[64:65])[0]
        self.loopable = struct.unpack('<b', rawdata[65:66])[0]
        self.event_count = struct.unpack('<h', rawdata[66:68])[0]
        self.event_offset = struct.unpack('<i', rawdata[68:72])[0]
        self.stream_count = struct.unpack('<h', rawdata[72:74])[0]
        unk = struct.unpack('<h', rawdata[74:76])[0]
        self.stream_headers = []
        for i in range(0, 10):
            new_stream_header = SkaAnimStreamHeader()
            DATUM_SIZE = SkaAnimStreamHeader.get_size()
            offset = 76 + i * DATUM_SIZE
            new_stream_header.from_raw_data(rawdata[offset:offset + DATUM_SIZE])
            if i < self.stream_count:
                self.stream_headers.append(new_stream_header)
    def write(self, file):
        self.name.write(file) # 64
        write_byte(file, self.drive_type) #65
        write_byte(file, self.loopable) #66
        write_short(file, self.event_count) #68
        assert self.event_offset != 0, "Uninited event_offset"
        write_int(file, self.event_offset)  # relative to this header; set by SkaFile.write_animation_data
        write_short(file, self.stream_count)
        write_short(file, 0) # unk
        # AnimStreamHeader array
        DATUM_SIZE = SkaAnimStreamHeader.get_size()
        for i in range (0, self.stream_count):    
            # offset = 76 + i * DATUM_SIZE
            stream_header = self.stream_headers[i]
            stream_header.write(file)
        for i in range(self.stream_count, 10):
            file.write( struct.pack("%db" % DATUM_SIZE, *DATUM_SIZE*[0,] ) )
        
        return
    @staticmethod
    def get_size():
        return 64 + 1 + 1 + 2 + 4 + 2 + 2 + 10 * SkaAnimStreamHeader.get_size()

class SkaAnim(object):
    __slots__ = "header", "events", "streams"
    header: SkaAnimHeader
    def __init__(self):
        self.header = SkaAnimHeader()
        self.events = []
        self.streams = []

    def from_raw_data(self, rawdata):
        self.header.from_raw_data(rawdata)

    def get_size(self):
        return self.header.get_size() + 2 + 4

########
class SkaFile:
    streams = ...  # type: List[SkaAnimStream]
    bone_data: List[SkaBone]
    animation_data: List[SkaAnim]
    def __init__(self):
        self.bone_data = []
        self.variation_data = []
        self.animation_data = []
        self.streams = []
        self._fileraw = b""

    def read(self, file):

        time1 = time.perf_counter()

        self._fileraw = file.read()
        self.get_bone_data()
        self.get_variation_data()
        self.read_animation_data()
        print(" done in %.2f sec." % (time.perf_counter() - time1))

    def get_bone_data(self):
        count = struct.unpack('<i', self._fileraw[0:4])[0]
        offset = struct.unpack('<i', self._fileraw[4:8])[0]
        print(count, 'bones, offset: ', offset)

        DATUM_SIZE = SkaBone.get_size()
        for i in range(0, count):
            data_start = offset + DATUM_SIZE * i
            newDatum = SkaBone()
            newDatum.from_raw_data(self._fileraw[data_start:data_start + DATUM_SIZE])
            self.bone_data.append(newDatum)

    def get_variation_data(self):
        count = struct.unpack('<i', self._fileraw[8:12])[0]
        offset = struct.unpack('<i', self._fileraw[12:16])[0]
        # do nothing, because it seems ToEE doesn't have this in practice

    def read_animation_data(self):
        count = struct.unpack('<i', self._fileraw[16:20])[0]
        offset = struct.unpack('<i', self._fileraw[20:24])[0]

        # Streams are reused between animations
        streams_by_start = dict()

        # get data headers first
        HEADER_SIZE = SkaAnimHeader.get_size()
        EVENT_SIZE = SkaEvent.get_size()
        data_start = offset
        self.read_errors = []
        for i in range(0, count):
            try:
                self._read_one_anim(i, data_start, HEADER_SIZE, EVENT_SIZE, streams_by_start)
            except (struct.error, IndexError, ValueError) as e:
                # a few stock files are truncated or corrupt after some animation (e.g. PC_shield_buckler.SKA
                # is 438 bytes but claims 2 animations): keep the animations read so far
                self.read_errors.append((i, repr(e)))
                print("WARNING: SKA animation %d/%d unreadable (%s); keeping %d animation(s)" % (i, count, e, len(self.animation_data)))
                break
            data_start += HEADER_SIZE
        self.streams = streams_by_start.values()

    def _read_one_anim(self, i, data_start, HEADER_SIZE, EVENT_SIZE, streams_by_start):
        if True:
            newDatum = SkaAnim()
            newDatum.header = SkaAnimHeader()
            newDatum.header.from_raw_data(self._fileraw[data_start:data_start + HEADER_SIZE])

            # events
            event_offset = data_start + newDatum.header.event_offset
            event_count = newDatum.header.event_count

            if event_count > 0:
                newDatum.events = SkaEvent.from_raw_data(
                    self._fileraw[event_offset:event_offset + event_count * EVENT_SIZE], event_count)

            newDatum.streams = []
            for stream_header in newDatum.header.stream_headers:

                stream_start = data_start + stream_header.data_offset
                if stream_start not in streams_by_start:
                    stream = SkaAnimStream(newDatum.header.name)
                    io = BytesIO(self._fileraw)
                    io.seek(stream_start)
                    stream.read(io)
                    streams_by_start[stream_start] = stream
                else:
                    stream = streams_by_start[stream_start]

                stream.instances.append(SkaAnimStreamInstance(
                    str(newDatum.header.name),
                    stream_header.frame_rate,
                    stream_header.dps
                ))
                newDatum.streams.append(stream)

            self.animation_data.append(newDatum)

    def write(self, file):
        # first write the header

        # bone data - count, offset [0:8]
        bone_count = len(self.bone_data)
        bone_data_offset = 24  # always 24
        file.write(struct.pack("<2i", bone_count, bone_data_offset))

        # #variation data - count, offset [8:16]
        variation_count = len(self.variation_data)
        variation_data_offset = bone_data_offset + self.get_bone_data_length()
        file.write(struct.pack("<2i", variation_count, variation_data_offset))
        # shouldn't actually have data here, heh
        assert variation_count == 0, "no variation data expected!"

        # animation data -count, offset [16:24]
        animation_count = len(self.animation_data)
        animation_data_offset = variation_data_offset + self.get_variation_data_length()  #
        file.write(struct.pack("<2i", animation_count, animation_data_offset))

        # *** write data ***
        # bone data
        self.write_bones(file)

        # variation data - shouldn't be any...
        pass
        
        # animation data
        self.write_animation_data(file, animation_data_offset)

        return

    def get_bone_data_length(self):
        return len(self.bone_data) * 100

    def get_variation_data_length(self):
        return len(self.variation_data) * 0

    def write_bones(self, file):
        for bd in self.bone_data:
            bd.write(file)

    def write_animation_data(self, file, animation_data_offset):
        """Layout (as in the vanilla files): SkaAnimHeader[count], then every animation's
        SkaEvent[] back to back, then each distinct keyframe stream once, in order of first use.
        eventOffset and streams[].dataOffset are relative to the start of the animation's own
        header (aas_skeleton.h SkelAnim::GetEventData / GetStreamKeyframes). Streams shared by
        several animations (same SkaAnimStream object) are written once."""
        count = len(self.animation_data)
        HEADER_SIZE = SkaAnimHeader.get_size()
        EVENT_SIZE = SkaEvent.get_size()

        # event offsets
        cur = count * HEADER_SIZE  # relative to animation 0's header
        for i, anim_datum in enumerate(self.animation_data):
            anim_datum.header.event_count = len(anim_datum.events)
            anim_datum.header.event_offset = cur - i * HEADER_SIZE
            cur += len(anim_datum.events) * EVENT_SIZE

        # serialize distinct streams in order of first use
        stream_pos = dict()  # id(stream) -> position relative to animation 0's header
        stream_blobs = []
        for anim_datum in self.animation_data:
            for stream in anim_datum.streams:
                if id(stream) in stream_pos:
                    continue
                bio = BytesIO()
                stream.write(bio)
                stream_pos[id(stream)] = cur
                stream_blobs.append(bio.getvalue())
                cur += len(stream_blobs[-1])

        for i, anim_datum in enumerate(self.animation_data):
            hdr = anim_datum.header
            assert len(anim_datum.streams) == len(hdr.stream_headers), "stream/header count mismatch"
            hdr.stream_count = len(hdr.stream_headers)
            for sh, stream in zip(hdr.stream_headers, anim_datum.streams):
                sh.data_offset = stream_pos[id(stream)] - i * HEADER_SIZE

        for anim_datum in self.animation_data:
            anim_datum.header.write(file)
        for anim_datum in self.animation_data:
            for event in anim_datum.events:
                event.write(file)
        for blob in stream_blobs:
            file.write(blob)
        self.streams = [s for a in self.animation_data for s in a.streams]
        return

    def add_bone(self, new_bone):
        self.bone_data.append(new_bone)

    def get_ska_to_skm_bone_map(self, skm_data):
        ska_data = self
        ska_to_skm_bone_mapping = {}  # in some ToEE models not all SKA bones are present in SKM (clothshit? buggy exporter?)

        for skm_idx, skm_bd in enumerate(skm_data.bone_data):

            found  = False
            for ska_idx, ska_bd in enumerate(ska_data.bone_data):
                if str(ska_bd.name).lower() == str(skm_bd.name).lower():
                    ska_to_skm_bone_mapping[ska_idx] = skm_idx
                    found = True
                    break
            if not found and skm_bd.parent_id >= 0:
                # SKM bone the SKA doesn't animate (e.g. EarthElemental): it stays at rest. The old bare
                # lookup here raised KeyError and aborted the import.
                print("SKM bone %r has no SKA bone" % str(skm_bd.name))


        for ska_idx, ska_bd in enumerate(ska_data.bone_data):
            found = False
            for skm_idx, skm_bd in enumerate(skm_data.bone_data):
                if str(ska_bd.name).lower() == str(skm_bd.name).lower():
                    ska_to_skm_bone_mapping[ska_idx] = skm_idx
                    found = True
                    break
            if not found and ska_idx == 0:
                print("Could not find mapping of SKA bone 0 by name; will assume its matching SKM bone id is also 0.")
                ska_to_skm_bone_mapping[ska_idx] = 0
            elif not found:
                ska_to_skm_bone_mapping[ska_idx] = -1
                print("Could not find mapping of SKA bone id %d!" % ska_idx, ska_data.bone_data[ska_idx].name)
        return ska_to_skm_bone_mapping


class SkmFile(object):
    __slots__ = ["bone_data", "material_data",
                 "vertex_data", "face_data",
                 "_fileraw", "_dataidx"]
    bone_data: List[SkmBone]
    material_data: List[SkmMaterial]
    vertex_data: List[SkmVertex]
    face_data: List[SkmFace]
    
    def __init__(self):
        self.bone_data = []
        self.material_data = []
        self.vertex_data = []
        self.face_data = []

    def read(self, file):
        self._fileraw = file.read()
        self.get_bone_data()
        self.get_material_data()
        self.get_vertex_data()
        self.get_face_data()

    # methods for converting raw binary to basic model data
    def get_face_data(self):
        count = struct.unpack('<i', self._fileraw[24:28])[0]
        offset = struct.unpack('<i', self._fileraw[28:32])[0]
        print(count, 'faces, offset: ', offset)
        DATUM_SIZE = SkmFace.get_size()
        for i in range(0, count):
            data_start = offset + DATUM_SIZE * i
            newDatum = SkmFace()
            newDatum.from_raw_data(self._fileraw[data_start:data_start + DATUM_SIZE])
            self.face_data.append(newDatum)

    def get_vertex_data(self):
        count = struct.unpack('<i', self._fileraw[16:20])[0]
        offset = struct.unpack('<i', self._fileraw[20:24])[0]
        print(count, 'vertices, offset: ', offset)

        DATUM_SIZE = SkmVertex.get_size()
        for i in range(0, count):
            data_start = offset + DATUM_SIZE * i
            newDatum = SkmVertex()
            newDatum.from_raw_data(self._fileraw[data_start:data_start + DATUM_SIZE])
            self.vertex_data.append(newDatum)

    def get_material_data(self):
        self.material_data = []
        count = struct.unpack('<i', self._fileraw[8:12])[0]
        offset = struct.unpack('<i', self._fileraw[12:16])[0]
        print(count, 'materials, offset: ', offset)

        DATUM_SIZE = SkmMaterial.get_size()
        for i in range(0, count):
            data_start = offset + DATUM_SIZE * i
            newDatum = SkmMaterial()
            newDatum.from_raw_data(self._fileraw[data_start:data_start + DATUM_SIZE])
            self.material_data.append(newDatum)
    
    def write_bones(self, file):
        for bd in self.bone_data:
            bd.write(file)
        return

    def write_materials(self, file):
        for skm_mat in self.material_data:
            skm_mat.write(file)
        return
    
    def write_vertices(self,file):
        for vertex in self.vertex_data:
            vertex.write(file)
        return
    
    def write_faces(self, file):
        for face in self.face_data:
            face.write(file)
        return

    def get_bone_data(self):
        bone_count = struct.unpack('<i', self._fileraw[0:4])[0]
        bone_offset = struct.unpack('<i', self._fileraw[4:8])[0]
        print(bone_count, 'bones, offset: ', bone_offset)

        DATUM_SIZE = SkmBone.get_size()
        for i in range(0, bone_count):
            bone_start = bone_offset + DATUM_SIZE * i
            newbone = SkmBone()
            newbone.from_raw_data(self._fileraw[bone_start:bone_start + DATUM_SIZE])
            self.bone_data.append(newbone)

    def write(self, file):
        BONE_DATA_OFFSET = 40  # always 24
        
        # first write the header

        # bone header data
        bone_count = len(self.bone_data)
        file.write(struct.pack("<2i", bone_count, BONE_DATA_OFFSET)) # 0:8
        bone_data_size = self.get_bone_data_length()
        
        # material header data
        material_count = len(self.material_data)
        material_data_offset = BONE_DATA_OFFSET + bone_data_size
        file.write(struct.pack("<2i", material_count, material_data_offset)) # 8:16
        material_data_size = self.get_material_data_length()

        # vertex header data
        vertex_count = len(self.vertex_data)
        vertex_data_offset = material_data_offset + material_data_size
        file.write(struct.pack("<2i", vertex_count, vertex_data_offset)) # 16:24
        vertex_data_size = self.get_vertex_data_length()
        
        # face header data
        face_count = len(self.face_data)
        face_data_offset = vertex_data_offset + vertex_data_size
        file.write(struct.pack("<2i", face_count, face_data_offset)) # 24:32
        face_data_size = self.get_face_data_length()

        # write some more dummy stuff I guess
        file.write(struct.pack("<2i", 0, 0)) # 32:40

        # *** write data ***
        self.write_bones(file)
        self.write_materials(file)
        self.write_vertices(file)
        self.write_faces(file)

    def get_bone_data_length(self):
        return len(self.bone_data) * SkmBone.get_size()

    def get_material_data_length(self):
        return len(self.material_data) * SkmMaterial.get_size()

    def get_vertex_data_length(self):
        return len(self.vertex_data) * SkmVertex.get_size()

    def get_face_data_length(self):
        return len(self.face_data) * SkmFace.get_size()    


    def add_bone(self, new_bone):
        self.bone_data.append(new_bone)



########## Keyframe stream encoder (float channels -> quantized SKA stream)
import math as _math

ROT_QUANT = 32767.0


def _q_dot(a, b):
    return a[0]*b[0] + a[1]*b[1] + a[2]*b[2] + a[3]*b[3]


def _q_norm(q):
    n = _math.sqrt(_q_dot(q, q)) or 1.0
    return tuple(c / n for c in q)


def _q_slerp(a, b, t):
    """DirectXMath XMQuaternionSlerp as used by the engine (aas_math.h slerpQuaternion)."""
    c = _q_dot(a, b)
    if c < 0:
        b = tuple(-x for x in b); c = -c
    if c < 1 - 1e-5:
        om = _math.acos(min(1.0, c)); s = _math.sin(om)
        ka, kb = _math.sin((1 - t) * om) / s, _math.sin(t * om) / s
    else:
        ka, kb = 1 - t, t
    return tuple(ka*x + kb*y for x, y in zip(a, b))


def _q_angle(a, b):
    return 2 * _math.acos(min(1.0, abs(_q_dot(_q_norm(a), _q_norm(b)))))


def _lerp(a, b, t):
    return tuple((1 - t)*x + t*y for x, y in zip(a, b))


def _vdist(a, b):
    return max(abs(x - y) for x, y in zip(a, b))


def reduce_keys(samples, interp, err, tol, seg_ok=None):
    """Greedy key reduction on per-integer-frame samples. Returns the kept frame indices
    (always includes 0 and the last frame). The engine interpolates linearly (slerp for
    rotations) between consecutive keys of a channel, so a key is dropped when that
    interpolation reproduces every sample in between within tol."""
    n = len(samples)
    if n <= 1:
        return [0]
    keys = [0]
    i = 0
    j = i + 2
    while j < n:
        ok = seg_ok is None or seg_ok(samples[i], samples[j])
        for k in (range(i + 1, j) if ok else ()):
            v = interp(samples[i], samples[j], (k - i) / (j - i))
            if err(v, samples[k]) > tol:
                ok = False
                break
        if ok:
            j += 1
        else:
            i = j - 1
            keys.append(i)
            j = i + 2
    if keys[-1] != n - 1:
        keys.append(n - 1)
    # A trailing run of identical values does not need its end key
    while len(keys) > 1 and err(samples[keys[-1]], samples[keys[-2]]) <= tol \
            and all(err(samples[k], samples[keys[-2]]) <= tol for k in range(keys[-2], n)):
        keys.pop()
    return keys


def encode_stream(name, bone_samples, rot_tol=1e-4, loc_tol=None, scale_tol=1e-4):
    """Build a SkaAnimStream from dense per-frame engine-space samples.

    bone_samples: {ska_bone_idx: (scales, rotations, translations)}, each a list with one
    entry per integer frame 0..N-1; scale/translation are (x,y,z), rotation is (x,y,z,w).
    Only bones listed are written (others keep the skeleton's initial state in the engine).
    loc_tol defaults to the translation quantization step.
    """
    stream = SkaAnimStream(name)
    all_t = [abs(c) for (_, _, ts) in bone_samples.values() for t in ts for c in t]
    all_s = [abs(c) for (ss, _, _) in bone_samples.values() for s in ss for c in s]
    max_t = max(all_t + [0.0]); max_s = max(all_s + [0.0])
    stream.location_factor = (max_t / 32767.0) if max_t > 0 else 1 / 32767.0
    stream.scale_factor = (max_s / 32767.0) if max_s > 0 else 1 / 32767.0
    if loc_tol is None:
        loc_tol = stream.location_factor
    lf, sf = stream.location_factor, stream.scale_factor

    def qv(v, f):
        return tuple(max(-32768, min(32767, int(round(c / f)))) for c in v)

    def qr(q):
        return tuple(max(-32767, min(32767, int(round(c * ROT_QUANT)))) for c in q)

    frame0 = SkaAnimKeyframe(-1)
    records = dict()  # frame -> {bone: [sc, sc_fr, rot, rot_fr, loc, loc_fr]}
    for b in sorted(bone_samples):
        ss, rs, ts = bone_samples[b]
        # keep rotations on one hemisphere (engine slerp takes the short arc anyway)
        rs2 = []
        for q in rs:
            q = _q_norm(q)
            if rs2 and _q_dot(rs2[-1], q) < 0:
                q = tuple(-c for c in q)
            elif not rs2 and q[3] < 0:
                q = tuple(-c for c in q)
            rs2.append(q)
        sk = reduce_keys(ss, _lerp, _vdist, scale_tol)
        # a segment near 180 deg is ambiguous for the engine's shortest-arc slerp (after quantization its dot
        # can flip sign and the bone turns the other way, e.g. giantrat rturn 'origin'): keep it under ~150 deg
        rk = reduce_keys(rs2, _q_slerp, _q_angle, rot_tol, seg_ok=lambda a, b: _q_dot(a, b) > 0.26)
        tk = reduce_keys(ts, _lerp, _vdist, loc_tol)
        frame0.bone_data[b] = SkaAnimFileKeyframeBoneData(-1, qv(ss[0], sf), -1, qr(rs2[0]), -1, qv(ts[0], lf), -1)
        for slot, keys, vals, quant in ((0, sk, ss, lambda v: qv(v, sf)), (2, rk, rs2, qr), (4, tk, ts, lambda v: qv(v, lf))):
            for k0, k1 in zip(keys, keys[1:]):
                rec = records.setdefault(k0, dict()).setdefault(b, [None, -1, None, -1, None, -1])
                rec[slot] = quant(vals[k1]); rec[slot + 1] = k1
    stream.initial_state = frame0
    stream.raw_frames = []
    for F in sorted(records):
        kf = SkaAnimKeyframe(F)
        for b in sorted(records[F]):
            sc, sc_fr, rot, rot_fr, loc, loc_fr = records[F][b]
            ch = (4 if sc is not None else 0) | (2 if rot is not None else 0) | (1 if loc is not None else 0)
            hdr = 1 | (ch << 1) | (b << 4)
            kf.bone_data[b] = SkaAnimFileKeyframeBoneData(hdr, sc, sc_fr, rot, rot_fr, loc, loc_fr)
        stream.raw_frames.append(kf)
    return stream

"""Minimal ToEE DAT1 archive writer (zlib-compressed entries, flag 2, as in the vanilla archives), the inverse of datx.py.
python3 datpack.py out.dat <src dir>   (archive paths are relative to src dir)"""
import os, struct, sys, zlib

def pack(out, src):
    # tree of dirs/files in preorder
    entries = []  # [name, is_dir, parent, first_child, next_sibling, data]
    def add(path, parent):
        names = sorted(os.listdir(path))
        prev = None
        for nm in names:
            full = os.path.join(path, nm)
            idx = len(entries)
            entries.append([nm, os.path.isdir(full), parent, -1, -1, None])
            if prev is None:
                if parent >= 0: entries[parent][3] = idx
            else:
                entries[prev][4] = idx
            prev = idx
            if os.path.isdir(full): add(full, idx)
            else: entries[idx][5] = open(full, 'rb').read(); entries[idx].append(zlib.compress(entries[idx][5], 9))
    add(src, -1)
    data = bytearray(); offs = {}
    for i, e in enumerate(entries):
        if not e[1]: offs[i] = len(data); data += e[6]
    dic = bytearray(struct.pack('<I', len(entries))); namebytes = 0
    for i, e in enumerate(entries):
        nb = e[0].encode('latin1') + b'\0'; namebytes += len(nb)
        dic += struct.pack('<I', len(nb)) + nb
        if e[1]: dic += struct.pack('<5I3i', 0, 0x400, 0, 0, 0, e[2], e[3], e[4])
        else: dic += struct.pack('<5I3i', 0, 2, len(e[5]), len(e[6]), offs[i], e[2], e[3], e[4])
    footer = struct.pack('<16s4sII', os.urandom(16), b'1TAD', namebytes, len(dic) + 28)
    open(out, 'wb').write(bytes(data) + bytes(dic) + footer)

if __name__ == '__main__':
    pack(sys.argv[1], sys.argv[2])

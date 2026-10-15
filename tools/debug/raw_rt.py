"""Pure ska.py read->write byte check for .ska/.skm files."""
import sys, io, os, contextlib
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'SKA_Export')); import ska
for p in sys.argv[1:]:
    raw = open(p, 'rb').read(); f = ska.SkaFile() if p.lower().endswith('.ska') else ska.SkmFile()
    with contextlib.redirect_stdout(io.StringIO()): f.read(io.BytesIO(raw))
    b = io.BytesIO(); f.write(b); print(p, 'identical' if b.getvalue() == raw else 'DIFF')

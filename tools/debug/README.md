# Animation debug tools

Compare the plugin's SKA import against a reference re-implementation of the Temple+ AAS
engine math. ToEE game files are not included: extract them yourself (e.g. `tools/datx.py`)
and point `TOEE_DATA` at the folder containing `art/`.

- `engine_eval.py`: engine reference evaluator (keyframe decoding, slerp, bone hierarchy with
  parent-scale compensation, skinning), with Temple+ source line references in the docstring.
- `blender_dump.py`: `blender -b --python blender_dump.py -- <addon dir> out.npy [anim,...]`.
  Imports the Ice Lizard and dumps evaluated vertices and bone deform matrices at half-frame steps.
- `compare.py out.npy tag`: per-animation max/mean vertex error vs the engine, written to `cmp_<tag>.json`.
- `plot.py`: error-over-time plots (needs matplotlib).
- `render.py` / `make_gif.py`: Workbench renders of the plugin result vs the engine mesh,
  combined into side-by-side GIFs (needs ffmpeg and Pillow).

Example:
    export TOEE_DATA=/path/to/extracted/data
    blender -b --factory-startup --python tools/debug/blender_dump.py -- . /tmp/after.npy
    python3 tools/debug/compare.py /tmp/after.npy after

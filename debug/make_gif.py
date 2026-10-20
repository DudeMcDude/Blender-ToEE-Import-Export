import sys, glob, os, subprocess
from PIL import Image, ImageDraw, ImageFont
an, out = sys.argv[1], sys.argv[2]
left = sys.argv[3] if len(sys.argv) > 3 else 'bef'; leftlab = sys.argv[4] if len(sys.argv) > 4 else 'BEFORE (1746f5e)'
P = [(left, leftlab), ('aft', 'AFTER (edb5c20)'), ('eng', 'ENGINE MATH (engine_eval.py)')]
n = len(glob.glob('/tmp/%s_eng/*.png' % an))
try: font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 20)
except Exception: font = ImageFont.load_default()
os.makedirs('/tmp/%s_cmp_%s' % (an, left), exist_ok=True)
for f in range(n):
    c = Image.new('RGB', (480 * 3, 480)); d = ImageDraw.Draw(c)
    for i, (p, lab) in enumerate(P):
        c.paste(Image.open('/tmp/%s_%s/%03d.png' % (an, p, f)).convert('RGB'), (480 * i, 0))
        d.text((480 * i + 10, 8), lab, fill=(255, 230, 120), font=font)
        if i: d.line([(480 * i, 0), (480 * i, 480)], fill=(20, 20, 20), width=2)
    d.text((10, 450), 'unarmed_unarmed_%s  frame %02d/%d' % (an.rstrip('F'), f, n - 1), fill=(255, 255, 255), font=font)
    c.save('/tmp/%s_cmp_%s/%03d.png' % (an, left, f))
subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-framerate', '15', '-i', '/tmp/%s_cmp_%s/%%03d.png' % (an, left),
  '-vf', 'split[a][b];[a]palettegen=max_colors=96[p];[b][p]paletteuse=dither=bayer:bayer_scale=4', '-loop', '0', out], check=True)
print(out, os.path.getsize(out))

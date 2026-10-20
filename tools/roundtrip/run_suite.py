#!/usr/bin/env python3
"""Round-trip every stock SKA/SKM pair through the add-on (import -> export, headless Blender) and
compare with the originals. Resumable (finished models are skipped unless --rerun), parallel,
per-model timeout; writes results.csv + summary.md and checks against a stored baseline.

  python3 tools/roundtrip/run_suite.py --blender ~/opt/blender-5.2.2-linux-x64/blender \\
      --data <ToEE data dir containing art/meshes> --out /tmp/rt5 -j 6 \\
      [--baseline tools/roundtrip/baseline_5.json] [--write-baseline] [--filter REGEX] [--limit N]

Exit code: 0 = no regression vs baseline (or no baseline), 1 = regressions, 2 = usage error."""
import argparse, concurrent.futures as cf, csv, json, os, re, subprocess, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); ADDON = os.path.abspath(os.path.join(HERE, '..', '..'))
# pass thresholds in ToEE world units (~inches): the exporter re-quantizes keys, and the error
# accumulates along long chains (fire_Snake spine: 0.16); SKM field tolerances when not byte-identical
TH = dict(vert_err=0.25, bone_err=0.25, skm_vert=1e-5, skm_wi=1e-5)

def find_models(data, rx, limit):
    root = os.path.join(data, 'art', 'meshes'); out = []
    for dp, _, fs in os.walk(root):
        low = {f.lower(): f for f in fs}
        for f in sorted(fs):
            if not f.lower().endswith('.ska'): continue
            rel = os.path.relpath(os.path.join(dp, f), root).replace(os.sep, '/')
            if rx and not re.search(rx, rel, re.I): continue
            skm = low.get(f.lower()[:-4] + '.skm')
            out.append((rel, os.path.join(dp, f), os.path.join(dp, skm) if skm else None))
    out.sort()
    return out[:limit] if limit else out

def classify(R):
    """status + problems from a compare result (thresholds applied here, so they live in one place)."""
    if any(x.startswith('no SKM') for x in R.get('problems', [])): return 'skip', R['problems']
    if R.get('status') == 'crash': return 'crash', R.get('problems', [])
    p = [x for x in R.get('problems', []) if not x.startswith('validation warnings')]
    if not R.get('skm_identical'):
        s = R.get('skm', {})
        why = []
        if len(set(map(tuple, s.get('counts', [])))) and any(a != b for a, b in s.get('counts', [])): why.append('counts %s' % s['counts'])
        if not s.get('bone_names_same', True): why.append('bone names')
        if s.get('faces_diff') or s.get('attach_diff'): why.append('faces %s attach %s' % (s.get('faces_diff'), s.get('attach_diff')))
        for k in ('vert_pos', 'vert_normal', 'vert_uv'):
            if s.get(k, 0) > TH['skm_vert']: why.append('%s %.3g' % (k, s[k]))
        if s.get('bone_wi', 0) > TH['skm_wi']: why.append('bone world-inverse %.3g' % s['bone_wi'])
        if why: p.append('SKM fields differ: ' + ', '.join(why))
    if R.get('events_differ'): p.append('event bytes differ in %s' % R['events_differ'][:3])
    if R.get('missing_anims'): p.append('animations missing %s' % R['missing_anims'][:3])
    if R.get('vert_err', 0) > TH['vert_err'] or R.get('bone_err', 0) > TH['bone_err']:
        w = (R.get('worst_anims') or [{}])[0]
        p.append('SKA error vert %.4f bone %.4f (worst %s)' % (R['vert_err'], R['bone_err'], w.get('anim')))
    return ('fail' if p else 'pass'), p

def run_one(args, rel, ska, skm):
    d = os.path.join(args.out, 'models', rel.replace('/', '__'))
    res = os.path.join(d, 'result.json')
    if os.path.exists(res) and not args.rerun:
        return rel, json.load(open(res)), True
    os.makedirs(d, exist_ok=True)
    for f in os.listdir(d): os.remove(os.path.join(d, f))
    if skm is None:
        R = dict(model=ska, status='crash', problems=['no SKM with the same name next to the SKA'])
        json.dump(R, open(res, 'w')); return rel, R, False
    t = time.time()
    with open(os.path.join(d, 'blender.log'), 'w') as log:
        try:
            subprocess.run([args.blender, '-b', '--factory-startup', '--python', os.path.join(HERE, 'rt_blender.py'),
                            '--', ADDON, ska, d], stdout=log, stderr=subprocess.STDOUT, timeout=args.timeout)
        except subprocess.TimeoutExpired:
            log.write('\nRT_TIMEOUT after %ds\n' % args.timeout)
    tb = time.time() - t
    try:
        subprocess.run([sys.executable, os.path.join(HERE, 'rt_compare.py'), ska, skm, d], timeout=args.timeout,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        pass
    R = json.load(open(res)) if os.path.exists(res) else dict(model=ska, status='crash', problems=['compare timed out'])
    if 'RT_TIMEOUT' in open(os.path.join(d, 'blender.log'), errors='replace').read():
        R['status'] = 'crash'; R['problems'] = ['timeout after %ds' % args.timeout]
    R['t_blender'] = round(tb, 1)
    for f in ('out.ska', 'out.skm', 'out.SKM'):  # keep results small; regenerate with --rerun
        if os.path.exists(os.path.join(d, f)) and not args.keep: os.remove(os.path.join(d, f))
    json.dump(R, open(res, 'w'), indent=1, default=str)
    return rel, R, False

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--blender', required=True); ap.add_argument('--data', required=True); ap.add_argument('--out', required=True)
    ap.add_argument('-j', type=int, default=max(1, (os.cpu_count() or 2) - 2)); ap.add_argument('--timeout', type=int, default=900)
    ap.add_argument('--filter'); ap.add_argument('--limit', type=int); ap.add_argument('--rerun', action='store_true')
    ap.add_argument('--keep', action='store_true', help='keep exported files'); ap.add_argument('--baseline')
    ap.add_argument('--write-baseline', action='store_true')
    args = ap.parse_args()
    models = find_models(args.data, args.filter, args.limit); os.makedirs(args.out, exist_ok=True)
    base = json.load(open(args.baseline)) if args.baseline and os.path.exists(args.baseline) else None
    known = (base or {}).get('known', {})
    print('%d models, %d workers, timeout %ds' % (len(models), args.j, args.timeout), flush=True)
    rows = {}; t0 = time.time()
    with cf.ThreadPoolExecutor(args.j) as ex:
        futs = [ex.submit(run_one, args, *m) for m in models]
        for i, f in enumerate(cf.as_completed(futs), 1):
            rel, R, cached = f.result(); st, probs = classify(R)
            if st != 'pass' and rel in known: st = 'known'
            rows[rel] = dict(model=rel, status=st, problems='; '.join(probs)[:400], skm_identical=R.get('skm_identical'),
                             materials_same=R.get('materials_same'), events=R.get('events'), events_ok=not R.get('events_differ'),
                             anims=R.get('anims'), vert_err=round(R.get('vert_err', 0) or 0, 5), bone_err=round(R.get('bone_err', 0) or 0, 5),
                             worst_anim=(R.get('worst_anims') or [{}])[0].get('anim', ''),
                             val_errors=' '.join(R.get('validation', {}).get('errors', [])),
                             val_warnings=' '.join(R.get('validation', {}).get('warnings', [])),
                             t_blender=R.get('t_blender'), t_compare=R.get('t_compare'))
            if not cached or i % 50 == 0:
                print('[%d/%d %.0fs] %-5s %s %s' % (i, len(models), time.time() - t0, st, rel, rows[rel]['problems'][:120]), flush=True)
    rows = [rows[m[0]] for m in models]
    with open(os.path.join(args.out, 'results.csv'), 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    regs = regressions(rows, base) if base else []
    write_md(args, rows, regs, known)
    if args.write_baseline:
        out = dict(thresholds=TH, known=known, models={r['model']: dict(status=r['status'], vert_err=r['vert_err'], bone_err=r['bone_err'],
                   skm_identical=r['skm_identical']) for r in rows})
        if args.baseline and os.path.exists(args.baseline) and args.filter:  # partial run: merge
            old = json.load(open(args.baseline)); old['models'].update(out['models']); out = old
        json.dump(out, open(args.baseline or os.path.join(args.out, 'baseline.json'), 'w'), indent=1, sort_keys=True)
    print(open(os.path.join(args.out, 'summary.md')).read().split('\n## Worst')[0])
    return 1 if regs else 0

RANK = {'pass': 0, 'skip': 0, 'known': 1, 'fail': 2, 'crash': 3}
def regressions(rows, base):
    out = []
    for r in rows:
        b = base['models'].get(r['model'])
        if b is None: continue
        if RANK.get(r['status'], 3) > RANK.get(b['status'], 3) and not (r['status'] == 'known'):
            out.append((r['model'], 'status %s -> %s' % (b['status'], r['status'])))
        for k in ('vert_err', 'bone_err'):
            if r[k] > b[k] * 1.25 + 1e-3: out.append((r['model'], '%s %.4f -> %.4f' % (k, b[k], r[k])))
        if b.get('skm_identical') and r['skm_identical'] is False: out.append((r['model'], 'SKM no longer byte-identical'))
    return out

def write_md(args, rows, regs, known):
    from collections import Counter
    c = Counter(r['status'] for r in rows)
    L = ['# Round-trip suite', '', 'Blender: `%s`, data: `%s`, %d models' % (args.blender, args.data, len(rows)), '',
         '| pass | fail | crash | known issue | skipped (no SKM) |', '|---|---|---|---|---|', '| %d | %d | %d | %d | %d |' % (c['pass'], c['fail'], c['crash'], c['known'], c['skip']), '',
         'SKM byte-identical: %d; materials preserved: %d; events byte-identical: %d; validation clean (no errors): %d' % (
             sum(1 for r in rows if r['skm_identical']), sum(1 for r in rows if r['materials_same']),
             sum(1 for r in rows if r['events_ok'] and r['events'] is not None), sum(1 for r in rows if not r['val_errors'] and r['status'] != 'crash')),
         '', 'Regressions vs baseline: %d' % len(regs)] + ['- %s: %s' % x for x in regs[:50]]
    L += ['', '## Worst SKA errors (vertex, engine math, ToEE units)', '', '| model | vert | bone | anim | status |', '|---|---|---|---|---|']
    for r in sorted(rows, key=lambda r: -r['vert_err'])[:15]:
        L.append('| %s | %.4f | %.4f | %s | %s |' % (r['model'], r['vert_err'], r['bone_err'], r['worst_anim'], r['status']))
    for st in ('crash', 'fail', 'known', 'skip'):
        sel = [r for r in rows if r['status'] == st]
        if sel:
            L += ['', '## %s (%d)' % (st, len(sel)), ''] + ['- `%s`: %s%s' % (r['model'], r['problems'] or '-',
                  (' (known: %s)' % known[r['model']]) if r['model'] in known else '') for r in sel]
    warn = Counter(w for r in rows for w in r['val_warnings'].split())
    if warn: L += ['', '## Validation warnings (do not fail)', ''] + ['- %s: %d models' % kv for kv in warn.most_common()]
    open(os.path.join(args.out, 'summary.md'), 'w').write('\n'.join(L) + '\n')

if __name__ == '__main__':
    sys.exit(main())

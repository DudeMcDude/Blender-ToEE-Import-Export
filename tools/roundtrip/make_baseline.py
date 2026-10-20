"""python3 make_baseline.py <out dir>/results.csv <baseline.json>: baseline from a finished run's CSV."""
import csv, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); import run_suite as S
known = json.load(open(os.path.join(HERE, 'known.json')))
rows = list(csv.DictReader(open(sys.argv[1])))
models = {r['model']: dict(status='known' if r['model'] in known and r['status'] != 'pass' else r['status'],
                           vert_err=float(r['vert_err']), bone_err=float(r['bone_err']), skm_identical=r['skm_identical'] == 'True')
          for r in rows}
json.dump(dict(thresholds=S.TH, known=known, models=models), open(sys.argv[2], 'w'), indent=1, sort_keys=True)
print(len(models), 'models;', {s: sum(1 for m in models.values() if m['status'] == s) for s in ('pass', 'fail', 'crash', 'known', 'skip')})

import json, matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
B=json.load(open('cmp_before.json')); A=json.load(open('cmp_fix5.json'))
anims=['unarmed_unarmed_rturn','unarmed_unarmed_fidget','unarmed_unarmed_rattack','unarmed_unarmed_idle']
fig,ax=plt.subplots(len(anims),1,figsize=(10,11))
for a,n in zip(ax,anims):
  for d,lab,c in [(B,'before (upstream + API fixes)','tab:red'),(A,'after (local-blender4)','tab:green')]:
    a.plot(d[n]['frames'],d[n]['max'],c,label=lab+' max'); a.plot(d[n]['frames'],d[n]['mean'],c,ls='--',label=lab+' mean')
  a.set_yscale('symlog',linthresh=0.1); a.set_title(n); a.set_ylabel('vertex err (units)'); a.grid(alpha=.3)
ax[0].legend(fontsize=7); ax[-1].set_xlabel('SKA frame'); fig.tight_layout(); fig.savefig('error_before_after.png',dpi=90)
fig,a=plt.subplots(figsize=(10,4))
for t,lab in [('before','before'),('fix1','+loc in rest frame'),('fix2','+hemisphere continuity'),('fix3','+unkeyed bones'),('fix4','+SKA hierarchy'),('fix5','+slerp bake')]:
  d=json.load(open('cmp_%s.json'%t))['unarmed_unarmed_rturn']; a.plot(d['frames'],d['max'],label=lab)
a.set_yscale('symlog',linthresh=0.1); a.set_title('unarmed_unarmed_rturn max vertex error by fix stage'); a.legend(fontsize=7); a.grid(alpha=.3); a.set_xlabel('SKA frame'); fig.tight_layout(); fig.savefig('rturn_stages.png',dpi=90)

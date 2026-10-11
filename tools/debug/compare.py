import os, sys, numpy as np, engine_eval as E, json
A=os.path.join(os.environ.get('TOEE_DATA', 'data'), 'art/meshes/Monsters/Icelizard/icelizard.')
m=E.Model(A+'skm',A+'ska')
res=np.load(sys.argv[1],allow_pickle=True).item(); tag=sys.argv[2]
names=[str(b.name) for b in m.skm.bone_data]
summary={}
for an,d in sorted(res.items()):
    a=m.anims[an]; errs=[]; berr=[]
    for k,f in enumerate(d['frames']):
        W=m.bone_mats(m.bone_state(a,f)); ve=m.skin(W)
        e=np.linalg.norm(ve-d['V'][k],axis=1); errs.append((e.max(),e.mean()))
        De=m.deform_mats(W)
        berr.append([np.abs(De[i]-d['D'][k][i])[:3,3].max()+100*np.abs(De[i]-d['D'][k][i])[:3,:3].max() if De[i] is not None else 0 for i in range(len(names))])
    errs=np.array(errs); berr=np.array(berr)
    # first frame where each bone exceeds threshold
    first={}
    for i in range(len(names)):
        idx=np.where(berr[:,i]>1.0)[0]
        if len(idx): first[names[i]]=float(d['frames'][idx[0]])
    order=sorted(first.items(),key=lambda x:x[1])[:5]
    summary[an]=dict(frames=d['frames'].tolist(),max=errs[:,0].tolist(),mean=errs[:,1].tolist(),first_diverging=order,worst_bones=[names[i] for i in np.argsort(-berr.max(0))[:5]])
    print('%-30s max %8.2f mean %7.2f  err@start %.2f err@end %.2f first:%s'%(an,errs[:,0].max(),errs[:,1].mean(),errs[0,1],errs[-1,1],order[:3]))
json.dump(summary,open('cmp_%s.json'%tag,'w'))

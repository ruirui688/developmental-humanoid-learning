import collections,gzip,hashlib,json,math,time
from pathlib import Path
wall=time.perf_counter(); cpu=time.process_time()
base=Path('external/local_integration_20261011_development')
audpath=Path('external/local_integration_20261011_development_audit.json')
load=lambda p:json.loads(p.read_text(encoding='utf-8'))
meta=load(base/'metadata.json'); seeds=load(base/'seed_results.json'); audited=load(audpath)
assert meta['split']=='development' and meta['seeds']==[0,1,2]
assert audited['failed']==0
hash_before={name:hashlib.sha256((base/name).read_bytes()).hexdigest() for name in ('metadata.json','seed_results.json','episodes.json','trace.jsonl.gz','manifest.json')}
manifest=load(base/'manifest.json')
assert all(hash_before[k]==manifest[k] for k in hash_before if k!='manifest.json')
rows=collections.defaultdict(list)
with gzip.open(base/'trace.jsonl.gz','rt',encoding='utf-8') as stream:
    for line in stream:
        row=json.loads(line); assert 'collector_exception' not in row
        rows[row['trial_id']].append(row)
controls=('frozen_euler_mpc','learned_euler_mpc','frozen_trapezoid_mpc','learned_trapezoid_mpc')
rmse=lambda values:math.sqrt(sum(x*x for x in values)/len(values))
differences=[]
def near(a,b):
    differences.append(abs(a-b)); assert abs(a-b)<=1e-12,(a,b)
def predict(theta,qref,q,v,u,trapezoid):
    x=[v,q-qref,u,(1 if u>0 else -1 if u<0 else 0)*max(abs(u)-.25,0),1]
    nextv=sum(a*b for a,b in zip(theta,x))
    return q+.02*(.5*(v+nextv) if trapezoid else nextv),nextv
initial=[1.,0.,.02,0.,0.]
primary=[]; rollouts={}; risks=[]
for sr,ar in zip(seeds,audited['archive']['seeds']):
    seed=sr['seed']; assert seed==ar['seed']; theta=sr['learned_model']['coefficients']; qref=sr['reference_q']
    for kind in controls:
        tr=rows[f'seed{seed}_{kind}']; active=tr[100:]; ev=sr['evaluations'][kind]; ae=ar['evaluations'][kind]
        assert len(tr)==300 and len(active)==200
        tracking=rmse([r['observation_after']['joint_position'][0]-r['target_q'] for r in active])
        effort={'requested_absolute_nm_s':sum(abs(r['requested_torque'][0])*r['diagnostics']['executed_substeps']*.002 for r in active),
                'requested_squared_nm2_s':sum(r['requested_torque'][0]**2*r['diagnostics']['executed_substeps']*.002 for r in active),
                'actual_absolute_nm_s':sum(sum(abs(u[0]) for u in r['diagnostics']['applied_torque_history'])*.002 for r in active),
                'actual_squared_nm2_s':sum(sum(u[0]**2 for u in r['diagnostics']['applied_torque_history'])*.002 for r in active)}
        near(tracking,ev['tracking_rmse_rad']); near(tracking,ae['tracking_rmse_rad'])
        for key,val in effort.items(): near(val,ev['control_effort'][key]); near(val,ae['control_effort'][key])
        risk={}
        for scope,segment in [('full',tr),('prefix',tr[:100]),('control',active)]:
            risk[scope]={'force_peak_n':max(x for r in segment for x in r['diagnostics']['substep_ground_normal_forces']),
                         'energy_peak_j':max(x for r in segment for x in r['diagnostics']['substep_kinetic_energies']),
                         'minimum_contact_distance_m':min(0.,*(x for r in segment for x in r['diagnostics']['substep_minimum_contact_distances'])),
                         'native_endpoint_speed_peak_rad_s':max(abs(v) for r in segment for v in r['observation_after']['joint_velocity']),
                         'guarded_substeps':sum(r['diagnostics']['guarded_substeps'] for r in segment)}
            if scope!='prefix':
                ref=ae[scope+'_risk']
                for k,rk in [('force_peak_n','ground_force_peak_n'),('energy_peak_j','kinetic_energy_peak_j'),('minimum_contact_distance_m','minimum_contact_distance_m'),('native_endpoint_speed_peak_rad_s','native_joint_speed_peak_rad_s'),('guarded_substeps','guarded_substeps')]: near(risk[scope][k],ref[rk])
        primary.append({'seed':seed,'kind':kind,'tracking_rmse_rad':tracking,**effort,'saturated_control_steps':sum(abs(r['requested_torque'][0])==.5 for r in active),'risk':risk})
    for kind in ('prediction',*controls):
        tr=rows[f'seed{seed}_{kind}']; active=tr[100:]; horizonrows=[]
        for h in (1,5,15,50):
            expected=len(active)-h+1
            assert expected==ar['evaluations'][kind]['free_rollouts'][(1,5,15,50).index(h)]['valid_physical_windows']
            models={k:(initial if k.startswith('frozen') else theta,'trapezoid' in k) for k in controls}
            models['velocity_persistence']=(None,False)
            horizonmetrics={}
            for name,(model,trapezoid) in models.items():
                qs=[]; vs=[]; pathqs=[]; pathvs=[]
                for start in range(expected):
                    win=active[start:start+h]
                    assert all(r['diagnostics']['executed_substeps']==10 and not r['diagnostics']['terminated'] for r in win)
                    assert all(a['observation_after']==b['observation_before'] for a,b in zip(win,win[1:]))
                    q=win[0]['observation_before']['joint_position'][0]; v=win[0]['observation_before']['joint_velocity'][0]
                    for r in win:
                        if model is None:q+=.02*v
                        else:q,v=predict(model,qref,q,v,r['requested_torque'][0],trapezoid)
                        tq=r['observation_after']['joint_position'][0]; tv=r['observation_after']['joint_velocity'][0]
                        pathqs.append(q-tq); pathvs.append(v-tv)
                    qs.append(q-tq);vs.append(v-tv)
                values={'terminal_position_rmse_rad':rmse(qs),'terminal_velocity_rmse_rad_s':rmse(vs),'path_position_rmse_rad':rmse(pathqs),'path_velocity_rmse_rad_s':rmse(pathvs)}
                ref=ar['evaluations'][kind]['free_rollouts'][(1,5,15,50).index(h)]['predictors'][name]
                for key,val in values.items():near(val,ref[key])
                horizonmetrics[name]=values
            horizonrows.append({'h':h,'windows':expected,'metrics':horizonmetrics})
        rollouts[(seed,kind)]=horizonrows
print('AUDIT',json.dumps({k:audited[k] for k in ('checks','failed','maximum_recomputation_difference','execution')},ensure_ascii=False))
print('GATE',json.dumps(audited['development_adoption_gate'],ensure_ascii=False))
print('HISTORICAL',json.dumps({'exact':audited['historical_anchor']['exact_replay_verified'],'pairs':len(audited['historical_anchor']['pairs'])}))
print('PRIMARY',json.dumps(primary,ensure_ascii=False))
for kind in controls:
    group=[p for p in primary if p['kind']==kind]
    mean={k:sum(r[k] for r in group)/3 for k in ('tracking_rmse_rad','actual_absolute_nm_s','actual_squared_nm2_s','saturated_control_steps')}
    mean['risk']={scope:{k:sum(r['risk'][scope][k] for r in group)/3 for k in group[0]['risk'][scope]} for scope in ('full','prefix','control')}
    print('MEAN',kind,json.dumps(mean,ensure_ascii=False))
for kind in ('prediction',*controls):
    print('ROLLOUT_MEANS',kind)
    for hi,h in enumerate((1,5,15,50)):
        values={name:{key:sum(rollouts[(seed,kind)][hi]['metrics'][name][key] for seed in (0,1,2))/3 for key in ('terminal_position_rmse_rad','terminal_velocity_rmse_rad_s','path_position_rmse_rad','path_velocity_rmse_rad_s')} for name in (*controls,'velocity_persistence')}
        print(h,json.dumps(values,ensure_ascii=False))
print('FACTORIAL',json.dumps([{'seed':r['seed'],**r['tracking_factorial_effects']} for r in audited['archive']['seeds']],ensure_ascii=False))
assert all(hashlib.sha256((base/k).read_bytes()).hexdigest()==v for k,v in hash_before.items())
print('INDEPENDENT_RECHECK',json.dumps({'numeric_comparisons':len(differences),'maximum_difference':max(differences),'input_hashes':hash_before,'audit_sha256':hashlib.sha256(audpath.read_bytes()).hexdigest(),'wall_seconds':time.perf_counter()-wall,'cpu_seconds':time.process_time()-cpu,'new_physics':0,'fitting':0}))

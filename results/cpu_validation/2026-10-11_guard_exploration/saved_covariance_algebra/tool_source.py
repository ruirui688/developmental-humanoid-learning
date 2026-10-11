"""Development-only algebra on saved RLS covariance; no fits or predictions."""
import argparse
import hashlib
import json
from pathlib import Path
import time

import numpy as np

ROOT=Path(__file__).resolve().parents[1]
NAMES=('v0','v1','dq0','dq1','startG0','startG1','hingeG0','hingeG1','1')

def digest(b): return hashlib.sha256(b).hexdigest()
def write(p,x): p.write_text(json.dumps(x,indent=2,allow_nan=False)+'\n',encoding='utf-8')

def algebra(snapshot):
    assert snapshot['forgetting_factor']==1. and snapshot['initial_covariance_scale']==100.
    assert snapshot['vector_update_count']==400 and snapshot['scalar_update_count']==800
    theta=np.asarray(snapshot['coefficients'],dtype=float)
    p=np.asarray(snapshot['covariance'],dtype=float)
    assert theta.shape==(2,9) and p.shape==(2,9,9)
    assert np.isfinite(theta).all() and np.isfinite(p).all()
    assert np.array_equal(p[0],p[1]),'both heads must have the same original inputs'
    # lambda=1: P_n^-1 = P_0^-1 + sum x_t x_t^T. Labels do not enter P.
    g=np.linalg.solve(p[0],np.eye(9))-.01*np.eye(9)
    g=(g+g.T)/2
    diag=np.diag(g)
    scale=max(1.,np.linalg.norm(g,ord=2))
    assert np.min(np.linalg.eigvalsh(g))>=-1.e-10*scale
    assert np.min(diag)>=-1.e-10*scale
    rms=np.sqrt(np.maximum(diag,0.)/400.)
    active=rms>1.e-12
    normal=g[np.ix_(active,active)]/(400.*np.outer(rms[active],rms[active]))
    normal=(normal+normal.T)/2
    eigen=np.linalg.eigvalsh(normal)
    spectrum=np.sqrt(np.maximum(eigen,0.))
    tol=max(normal.shape)*np.finfo(float).eps*max(1.,float(np.max(spectrum)))
    full=bool(np.min(spectrum)>tol)
    # For a fixed G branch only; no guard derivative or changing contact model.
    bq=theta[:,2:4];bv=theta[:,:2]
    a=np.block([[np.eye(2)+.02*bq,.02*bv],[bq,bv]])
    modes=np.linalg.eigvals(a)
    return {'feature_rms':dict(zip(NAMES,rms.tolist())),
      'uncentered_scaled_feature_correlation':normal.tolist(),
      'included_features':[n for n,ok in zip(NAMES,active) if ok],
      'scaled_gram_singular_values':spectrum[::-1].tolist(),
      'scaled_gram_condition_number':float(np.max(spectrum)/np.min(spectrum)) if full else None,
      'full_numerical_rank_under_machine_tolerance':full,'machine_rank_tolerance':float(tol),
      'velocity_uncentered_correlation':float(normal[0,1]),
      'dq_uncentered_correlation':float(normal[2,3]),
      'saved_covariance_diagonal':np.diag(p[0]).tolist(),
      'velocity_coefficients':bv.tolist(),'displacement_coefficients':bq.tolist(),
      'fixed_guard_branch_state_modes':[{'real':float(z.real),'imag':float(z.imag),'abs':float(abs(z))} for z in modes],
      'fixed_guard_branch_spectral_radius':float(max(abs(modes))),
      'actual_prediction_calls':0,'actual_model_updates':0,
      'linear_solve_calls':1,'eigenvalue_decompositions':3,'spectral_norm_calls':1}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--audit',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(exist_ok=False,parents=True)
    wall,cpu=time.perf_counter(),time.process_time();record={'status':'started'}
    own=Path(__file__).read_bytes();(args.output/'tool_source.py').write_bytes(own)
    cache={}
    def read(p):
        key=str(p.resolve());assert key not in cache
        cache[key]=p.read_bytes();return cache[key]
    try:
        manifest=json.loads(read(args.input/'manifest.json'))
        raw={n:read(args.input/n) for n in ('metadata.json','seed_results.json')}
        for n,b in raw.items():assert digest(b)==manifest[n]
        audit_blob=read(args.audit);audit=json.loads(audit_blob)
        assert audit['failed']==0 and audit['final_gates']['data_consistency_verified']
        assert audit['audit_script_sha256']=='962a928b5d643ed2a3d4da20da2940a9a4e17932818c859beb204f11bf59ffa3'
        for n,b in raw.items():assert digest(b)==audit['archive']['input_hashes'][n]
        meta=json.loads(raw['metadata.json']);seeds=json.loads(raw['seed_results.json'])
        assert meta['source_commit']=='5ea8df42b09588845760daf0dc1f270aef2a87f1'
        result=[]
        for seed in seeds:
            for group in ('sparse','continuation'):
                cal=seed['calibrations'][group]
                assert cal['completed'] and cal['committed_vector_updates']==400
                result.append({'seed':seed['seed'],'group':group,**algebra(cal['frozen_model'])})
        record={'status':'completed','source_commit':meta['source_commit'],
          'scope':'Algebra derived from six saved development covariance/theta snapshots only.',
          'results':result,'scientific_gates_recomputed':False,'new_physical_calls':0,
          'new_model_updates':0,'new_predictions':0,'prior_audit_reexecutions':0,'git_queries':0,
          'linear_solve_calls':6,'eigenvalue_decompositions':18,'spectral_norm_calls':6,
          'claim_boundary':'No rank threshold for adoption, no causal diagnosis or new holdout. '+
            'Correlations are uncentered RMS normalization. State modes hold guard input fixed; '+
            'they are not full plant stability or safety evidence.'}
        code=0
    except BaseException as exc:
        record.update(status='failed',error={'type':type(exc).__name__,'message':str(exc)});code=1
    finally:
        record.update(input_hashes={p:digest(b) for p,b in cache.items()},tool_sha256=digest(own),
          wall_seconds=time.perf_counter()-wall,cpu_seconds=time.process_time()-cpu)
        write(args.output/'result.json',record)
    print(json.dumps({k:v for k,v in record.items() if k not in ('results','input_hashes')},indent=2))
    if code==0:
        for r in record['results']:
            print(r['seed'],r['group'],'v corr',r['velocity_uncentered_correlation'],
                  'condition',r['scaled_gram_condition_number'],'branch rho',r['fixed_guard_branch_spectral_radius'])
    return code

if __name__=='__main__':raise SystemExit(main())

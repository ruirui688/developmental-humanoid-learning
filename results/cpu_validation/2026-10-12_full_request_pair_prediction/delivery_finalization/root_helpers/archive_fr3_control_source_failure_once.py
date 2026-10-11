"""Preserve the first B invocation's zero-physics clean-source rejection."""
from pathlib import Path
import hashlib
import json

root=Path(__file__).resolve().parents[1]
source=root/'external/fr3_control_first'
dest=root/'results/cpu_validation/2026-10-12_full_request_pair_prediction/control_source_failure'
assert not dest.exists()
run=json.loads((source/'raw/run.json').read_bytes())
assert run['failure']['phase']=='source_validation'
assert run['failure']['message']=='clean_exact_FR_learning_HEAD_required'
assert all(run['cost'][key]==0 for key in ('control_call_attempts','control_call_returns',
 'confirmed_physics_substeps','environment_constructor_attempts','RLS_scalar_update_commits','MPC_decision_attempts'))
dest.mkdir()
pins={}
for path in sorted(source.rglob('*')):
 if path.is_file():
  name=path.relative_to(source).as_posix();data=path.read_bytes();target=dest/name
  target.parent.mkdir(parents=True,exist_ok=True)
  with target.open('xb') as stream:stream.write(data)
  pins[name]={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
own=Path(__file__).read_bytes()
(dest/'archive_source_failure_once.py').write_bytes(own)
manifest={'first_B_invocation_failed':True,'phase':'source_validation',
 'failure':'clean_exact_FR_learning_HEAD_required','cause':'new A archive untracked before its checkpoint commit',
 'physical_control_has_not_started':True,'first_physical_control_attempt_pending':True,
 'automatic_retry':False,'code_protocol_threshold_or_seed_changed':False,'payloads':pins,
 'continuous_goal_stays_active':True}
(dest/'preservation_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'first_source_rejection_preserved':True,'payloads':len(pins),'new_physics_or_model_or_fit':0}))

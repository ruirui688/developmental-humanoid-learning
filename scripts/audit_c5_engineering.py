"""Independent standard-library audit of the fixed four-trial C5 engineering check.

This script does not import the collector, simulator, body model or controller.
Engineering consistency is distinct from learning or adaptation evidence.
"""
from collections import Counter
import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import time
import zipfile

KINDS = ('base_identity', 'wrapper_identity', 'gain_half', 'armature_double')
FIELDS = {'joint_position':8, 'joint_velocity':8, 'actuator_torque':8,
          'previous_command':8, 'imu_gyro':3, 'imu_acceleration':3}
RUNTIME = {'src/developmental_physics/c5_engineering.py',
           'src/developmental_physics/perturbed_environment.py',
           'src/developmental_physics/environment.py',
           'src/developmental_physics/__init__.py',
           'src/developmental_physics/assets/ground_body.xml',
           'docs/C5_ENGINEERING_PROTOCOL.md', 'docs/C5_ENGINEERING_BINDING.json',
           'scripts/audit_c5_engineering.py'}
TOL = 1e-12
RANGES = [[math.radians(a), math.radians(b)] for a,b in
          [(-100,100),(0,135),(-100,100),(0,135),(-90,90),(0,135),(-90,90),(0,135)]]
PLAN = {'pose':'supine','development_seed':0,'reset_seed':3757552657,'trials':list(KINDS),
    'fresh_environment_per_trial':True,'prefix_steps':100,'active_steps':20,
    'physics_substeps_per_call':10,'physics_dt_seconds':.002,'maximum_calls':480,
    'maximum_substeps':4800,'parameter_updates':0,'selected_native_joints':[0,1],
    'active_blocks':'(+.25,+.25)*5 / zero*5 / (-.25,-.25)*5 / zero*5',
    'event_boundary':100,'gain_half':[.5,.5,1.,1.,1.,1.,1.,1.],
    'armature_double_native_values':[.02,.02],
    'study_q_offset_limit_rad':.12,'study_velocity_limit_rad_s':1.}


def sha(data):
    return hashlib.sha256(data).hexdigest()


class Checks:
    def __init__(self):
        self.count = self.failed = 0
        self.maximum_difference = 0.
        self.violations = []

    def check(self, condition, label):
        self.count += 1
        if not condition:
            self.failed += 1
            if len(self.violations) < 100:
                self.violations.append(label)

    def compare(self, actual, expected, label):
        if type(expected) in (int, float) and type(actual) in (int, float):
            difference = abs(actual-expected)
            if math.isfinite(difference):
                self.maximum_difference = max(self.maximum_difference, difference)
            self.check(math.isfinite(actual) and math.isfinite(expected) and difference <= TOL, label)
        elif isinstance(expected, dict):
            self.check(isinstance(actual, dict) and set(actual) == set(expected), label+'.keys')
            if isinstance(actual, dict):
                for key in expected:
                    self.compare(actual.get(key), expected[key], label+'.'+key)
        elif isinstance(expected, list):
            self.check(isinstance(actual, list) and len(actual) == len(expected), label+'.shape')
            if isinstance(actual, list):
                for i, value in enumerate(expected):
                    self.compare(actual[i] if i<len(actual) else None, value, label+':'+str(i))
        else:
            self.check(type(actual) is type(expected) and actual == expected, label)


def finite_vector(values, width):
    if not isinstance(values, list) or len(values) != width or not all(
        type(x) in (int, float) and math.isfinite(x) for x in values):
        raise ValueError('finite native vector required')
    return values


def command(index):
    if type(index) is not int or not 0 <= index < 120:
        raise ValueError('fixed engineering endpoint index required')
    slot = index-100
    amplitude = 0. if slot < 0 else (.25 if slot < 5 else (-.25 if 10 <= slot < 15 else 0.))
    return [amplitude, amplitude]+[0.]*6


def expected_guard(angles, accepted, gains, ranges):
    angles, accepted, gains = (finite_vector(x,8) for x in (angles,accepted,gains))
    if not isinstance(ranges,list) or len(ranges) != 8:
        raise ValueError('eight public native ranges required')
    scaled = [u*g for u,g in zip(accepted,gains)]
    blocked = [(q<=limits[0]+.03 and u<0.) or (q>=limits[1]-.03 and u>0.)
               for q,u,limits in zip(angles,scaled,ranges)]
    return scaled, blocked, [0. if b else u for u,b in zip(scaled,blocked)]


def audit_mass_event(event, dofs, checks):
    before, after = event['before_live'], event['after_live']
    for key in ('qpos','qvel','ctrl','last_command','time','step_id','physics_steps'):
        checks.compare(after[key],before[key],event['kind']+'.event.persistent.'+key)
    armature = list(before['armature'])
    selected = dofs[:2] if event['kind']=='armature_double' else []
    for index in selected:
        armature[index] = .02
    checks.compare(after['armature'],armature,event['kind']+'.armature')
    left, right = event['mass_matrix_before'], event['mass_matrix_after']
    checks.compare(left['qpos'],before['qpos'],'mass.before.q')
    checks.compare(right['qpos'],before['qpos'],'mass.after.q')
    n = len(armature)
    maximum = 0.
    diagonal = []
    for i in range(n):
        a, b = finite_vector(left['matrix'][i],n),finite_vector(right['matrix'][i],n)
        diagonal.append(b[i]-a[i])
        for j in range(n):
            delta = b[j]-a[j]
            expected = .01 if i==j and i in selected else 0.
            maximum = max(maximum,abs(delta-expected))
            checks.compare(delta,expected,'same_q_mass_delta:'+str(i)+':'+str(j))
    report = event['mass_matrix_change']
    checks.compare(report['diagonal_delta'],diagonal,'mass.diagonal')
    checks.compare(report['maximum_absolute_error_from_expected_delta'],maximum,'mass.maximum_error')
    checks.compare(report['selected_native_dof_indices'],selected,'mass.selected')
    checks.compare(report['physics_substeps_added'],0,'mass.no_integrated_step')
    checks.compare(report['expected_selected_diagonal_delta'],.01 if selected else 0.,'mass.expected_delta')
    checks.compare(report['tolerance'],TOL,'mass.tolerance')
    checks.compare(report['diagnostic_only'],True,'mass.diagnostic_only')
    checks.compare(before['step_id'],100,'event.prefix_calls')
    checks.compare(before['physics_steps'],1000,'event.prefix_substeps')
    checks.compare(before['time'],2.,'event.prefix_time')
    if event['kind']=='gain_half':
        checks.check(before['plant_fingerprint']!=after['plant_fingerprint'],'gain.plant_changed')
        checks.compare(after['base_fingerprint'],before['base_fingerprint'],'gain.base_unchanged')
    if event['kind']=='armature_double':
        checks.check(before['plant_fingerprint']!=after['plant_fingerprint'],'armature.plant_changed')
        checks.check(before['base_fingerprint']!=after['base_fingerprint'],'armature.base_changed')
    if event['kind'] in ('base_identity','wrapper_identity'):
        checks.compare(after['plant_fingerprint'],before['plant_fingerprint'],'identity.plant_unchanged')


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def verify_sources(path, metadata, checks, git_root):
    hashes = metadata['source_sha256']
    checks.check(RUNTIME <= set(hashes),'complete_required_source_list')
    with zipfile.ZipFile(path/'source_snapshot.zip') as snapshot:
        checks.compare(sorted(snapshot.namelist()),sorted(hashes),'zip.inventory')
        sources = {name:snapshot.read(name) for name in hashes}
    binding_record = metadata['source_binding']
    commit = binding_record['source_commit']
    checks.check(bool(re.fullmatch('[0-9a-f]{40}',commit)),'source.commit')
    checks.compare(binding_record['source_dirty'],False,'source.clean')
    checks.compare(binding_record['source_status'],'','source.status')
    binding_path = 'docs/C5_ENGINEERING_BINDING.json'
    checks.compare(binding_record['binding_path'],binding_path,'binding.path')
    binding = json.loads(sources[binding_path])
    checks.compare(binding_record['binding'],binding,'binding.record')
    checks.compare(binding_record['binding_sha256'],sha(sources[binding_path]),'binding.sha')
    checks.compare(binding['draft'],False,'binding.frozen')
    checks.compare(binding['schema_version'],1,'binding.schema')
    checks.compare(binding['plan'],PLAN,'binding.plan')
    checks.compare(binding['protocol_path'],'docs/C5_ENGINEERING_PROTOCOL.md','protocol.path')
    checks.compare(binding['protocol_sha256'],hashes[binding['protocol_path']],'protocol.sha')
    checks.compare(set(binding['source_sha256'])|{binding_path},set(hashes),'binding.source_inventory')
    checks.check(binding_path not in binding['source_sha256'],'binding.no_self_hash')
    for name, data in sources.items():
        checks.compare(sha(data),hashes[name],'source.sha:'+name)
        checks.check(not Path(name).is_absolute() and '..' not in Path(name).parts,'safe_source_path:'+name)
        if name != binding_path:
            checks.compare(binding['source_sha256'][name],hashes[name],'binding.source.sha:'+name)
        if git_root is not None:
            blob = subprocess.check_output(['git','show',commit+':'+name],cwd=git_root)
            checks.check(blob==data,'git_blob:'+name)
    checks.compare(hashes['scripts/audit_c5_engineering.py'],sha(Path(__file__).read_bytes()),'executed_auditor')
    return {'source_commit':commit,'source_sha256':hashes}


def audit(path, *, git_root=None, synthetic_fixture=False):
    wall, cpu = time.perf_counter(),time.process_time()
    path = Path(path)
    checks = Checks()
    reconstructed = None
    try:
        metadata = read_json(path/'metadata_final.json')
        checks.compare(metadata['synthetic'],synthetic_fixture,'fixture_scope')
        if not synthetic_fixture:
            checks.compare(metadata['draft'],False,'collector_frozen')
            checks.compare(metadata['source_dirty'],False,'collector_clean')
        else:
            checks.check(type(metadata['draft']) is bool,'fixture_draft_flag')
            checks.compare(metadata['source_dirty'],None,'fixture_no_git_claim')
        checks.compare(metadata['trial_order'],list(KINDS),'trial_order')
        checks.compare(metadata['fixed_plan'],PLAN,'fixed_plan')
        for name,value in {'seed':0,'reset_seed':3757552657,'pose':'supine','prefix_steps':100,
                           'active_steps':20,'maximum_control_calls':480,'maximum_physics_substeps':4800,
                           'model_parameter_updates':0,'policy_updates':0,'teacher_calls':0}.items():
            checks.compare(metadata[name],value,'fixed.'+name)
        manifest = read_json(path/'manifest.json')
        checks.compare(sorted(p.name for p in path.iterdir() if p.is_file() and p.name!='manifest.json'),
                       sorted(manifest),'manifest.inventory')
        for name,expected in manifest.items():
            checks.compare(sha((path/name).read_bytes()),expected,'manifest.sha:'+name)
        provenance = None if synthetic_fixture else verify_sources(path,metadata,checks,git_root)
        outcomes = read_json(path/'trial_outcomes.json')
        checks.compare([o['kind'] for o in outcomes],list(KINDS),'outcome_order')
        by_kind = {o['kind']:o for o in outcomes}
        traces = {k:[] for k in KINDS}
        with gzip.open(path/'trace.jsonl.gz','rt',encoding='utf-8') as stream:
            for line in stream:
                row = json.loads(line)
                traces[row['kind']].append(row)
        totals = Counter()
        effort = {}
        fatal_seen = False
        for kind in KINDS:
            outcome = by_kind[kind]
            for key in ('control_calls_attempted','control_steps','known_physics_substeps_lower_bound',
                        'unknown_original_step_attempts','returned_endpoints'):
                checks.check(type(outcome[key]) is int and outcome[key]>=0,'nonnegative_budget:'+kind+'.'+key)
                totals[key] += outcome[key]
            checks.check(outcome['status'] in ('completed','terminated','exception','blocked'),'known_status:'+kind)
            if outcome['status']=='blocked':
                checks.check(fatal_seen,'blocked_after_fatal:'+kind)
                checks.compare(len(traces[kind]),0,'blocked_no_trace:'+kind)
                for key in ('control_calls_attempted','control_steps','known_physics_substeps_lower_bound',
                            'unknown_original_step_attempts','returned_endpoints'):
                    checks.compare(outcome[key],0,'blocked_zero_budget:'+kind+'.'+key)
                continue
            fatal_seen |= outcome['status']=='exception'
            if 'initial_native_mapping' not in outcome:
                checks.check(outcome['status']=='exception','missing_mapping_requires_exception:'+kind)
                checks.check(not traces[kind],'setup_exception_no_trace:'+kind)
                checks.check(outcome.get('partial_instrumentation',[])==[],'setup_exception_no_instrumentation:'+kind)
                checks.compare(outcome.get('independently_observed_kernel_returned_substeps'),0,'setup_no_observed_return:'+kind)
                checks.compare(outcome.get('independently_observed_kernel_attempts'),0,'setup_no_observed_attempt:'+kind)
                final=outcome.get('final_live_state') or {}
                for field,budget in (('physics_steps','known_physics_substeps_lower_bound'),('step_id','control_steps')):
                    if type(final.get(field)) is int:
                        checks.compare(outcome[budget],final[field],'setup_paid_counter:'+kind+'.'+field)
                checks.compare(outcome['unknown_original_step_attempts'],0,'setup_no_unknown_kernel:'+kind)
                continue
            mapping = outcome['initial_native_mapping']
            checks.compare(mapping['action_limits_nm'],[.5]*8,'public_permission:'+kind)
            checks.compare(mapping['motor_ctrlrange_nm'],[[-.5,.5]]*8,'asset.motor_ctrlrange:'+kind)
            # MuJoCo byte flags can serialize as integer 0/1 or boolean leaves.
            for field,expected in (('motor_ctrl_limited',True),('motor_force_limited',False)):
                flags=mapping[field]
                checks.check(isinstance(flags,list) and len(flags)==8 and all(
                    type(x) in (bool,int) and x in (0,1) and bool(x)==expected for x in flags),
                    'asset.'+field+':'+kind)
            checks.compare(mapping['unit_gain_gear_bias_verified'],True,'unit_motor:'+kind)
            checks.compare(mapping['joint_ids'],list(range(1,9)),'asset.native_joint_ids:'+kind)
            checks.compare(mapping['qpos_indices'],list(range(7,15)),'asset.native_qpos:'+kind)
            checks.compare(mapping['dof_indices'],list(range(6,14)),'asset.native_dof:'+kind)
            checks.compare(mapping['public_joint_ranges'],RANGES,'asset.public_ranges:'+kind)
            checks.compare([mapping['initial_armature'][i] for i in mapping['dof_indices']],[.01]*8,'asset.armature:'+kind)
            rows = traces[kind]
            checks.check(0<=outcome['returned_endpoints']<=outcome['control_calls_attempted']<=120,'call_budget_order:'+kind)
            checks.check(len(rows)<=outcome['returned_endpoints'],'persisted_endpoints_lower_bound:'+kind)
            checks.compare(outcome['control_steps'],outcome['final_live_state'].get('step_id'),'live_control_counter:'+kind)
            all_records = []
            for index,row in enumerate(rows):
                checks.compare(row['step_index'],index,'trace.index:'+kind)
                checks.compare(row['phase'],'prefix' if index<100 else 'active','trace.phase:'+kind)
                if index<len(rows)-1:
                    checks.check(row['study_abort'] is None and not row['environment_terminated'],'no_endpoint_after_stop:'+kind)
                expected_request = command(index)
                checks.compare(row['requested_torque'],expected_request,'request:'+kind+':'+str(index))
                for label in ('observation_before','observation_after'):
                    observation = row[label]
                    checks.compare(set(observation),set(FIELDS),'native.keys:'+kind)
                    for name,width in FIELDS.items():
                        finite_vector(observation[name],width)
                after = row['observation_after']
                if index:
                    for key in ('joint_position','joint_velocity','previous_command'):
                        checks.compare(row['observation_before'][key],rows[index-1]['observation_after'][key],'native.continuity:'+kind+'.'+key)
                checks.compare(after['joint_position'],[row['qpos'][i] for i in mapping['qpos_indices']],'native.q:'+kind)
                checks.compare(after['joint_velocity'],[row['qvel'][i] for i in mapping['dof_indices']],'native.v:'+kind)
                checks.compare(after['previous_command'],expected_request,'native.accepted_request:'+kind)
                if index>=100:
                    triggers = []
                    reference = outcome['reference_q_rad']
                    for axis in (0,1):
                        if abs(after['joint_position'][axis]-reference[axis])>=.12:
                            triggers.append((axis,'absolute_q_minus_qref_rad'))
                        if abs(after['joint_velocity'][axis])>=1.:
                            triggers.append((axis,'absolute_velocity_rad_s'))
                    study = row['study_abort']
                    actual = [] if study is None else [(t['joint_index'],t['signal']) for t in study['triggers']]
                    checks.compare(actual,triggers,'study_triggers:'+kind)
                else:
                    checks.compare(row['study_abort'],None,'no_prefix_study_stop:'+kind)
                records = row['actual_substep_history']
                checks.compare(len(records),row['diagnostics']['executed_substeps'],'instrument_count:'+kind)
                checks.compare(row['diagnostics']['accepted_torque'],expected_request,'diagnostics.accepted:'+kind)
                if records:
                    checks.compare(records[0]['before_angles_rad'],row['observation_before']['joint_position'],'first_substep_native_q:'+kind)
                for sub,record in enumerate(records):
                    gains = [.5,.5]+[1.]*6 if kind=='gain_half' and index>=100 else [1.]*8
                    checks.compare(record['accepted_request'],expected_request,'accepted:'+kind)
                    checks.compare(record['hidden_channel_gains'],gains,'gain_schedule:'+kind)
                    scaled,blocked,control = expected_guard(record['before_angles_rad'],expected_request,gains,mapping['public_joint_ranges'])
                    checks.compare(record['scaled_request_nm'],scaled,'scaled:'+kind)
                    checks.compare(record['independently_expected_guard'],blocked,'guard_flags:'+kind)
                    checks.compare(record['before_ctrl_nm'],control,'actual_guard_ctrl:'+kind)
                    checks.compare(record['after_actuator_force_nm'],control,'actual_unit_force:'+kind)
                    checks.compare(row['diagnostics']['applied_torque_history'][sub],control,'base_history:'+kind)
                    checks.compare(record['original_mj_step_returned'],True,'returned_kernel:'+kind)
                    checks.compare(record['original_mj_step_attempted'],True,'attempted_kernel:'+kind)
                    checks.compare(record['force_after_available'],True,'available_force:'+kind)
                all_records.extend(records)
            partial = outcome.get('partial_instrumentation',[])
            failed_step = (outcome.get('exception') or {}).get('step_index')
            if partial and rows and rows[-1]['step_index']==failed_step:
                checks.compare(partial,rows[-1]['actual_substep_history'],'exception_trace_overlap:'+kind)
            else:
                all_records.extend(partial)
            for record in partial:
                checks.check(type(record['original_mj_step_attempted']) is bool,'partial.attempt_bool:'+kind)
                checks.check(type(record['original_mj_step_returned']) is bool,'partial.return_bool:'+kind)
                checks.check(not record['original_mj_step_returned'] or record['original_mj_step_attempted'],'partial.return_requires_attempt:'+kind)
                checks.check(not record['force_after_available'] or record['original_mj_step_returned'],'partial.force_requires_return:'+kind)
                if type(failed_step) is int and 0<=failed_step<120:
                    checks.compare(record['accepted_request'],command(failed_step),'partial.request:'+kind)
                if record['force_after_available']:
                    finite_vector(record['after_actuator_force_nm'],8)
            kernel_returned = sum(r['original_mj_step_returned'] for r in all_records)
            attempts = sum(r['original_mj_step_attempted'] for r in all_records)
            checks.compare(outcome['independently_observed_kernel_returned_substeps'],kernel_returned,'kernel_budget:'+kind)
            checks.compare(outcome['independently_observed_kernel_attempts'],attempts,'kernel_attempts:'+kind)
            final_counter=outcome['final_live_state'].get('physics_steps')
            if type(final_counter) is int:
                checks.compare(outcome['known_physics_substeps_lower_bound'],max(kernel_returned,final_counter),'paid_lower_bound:'+kind)
            else:
                checks.check(outcome['status']=='exception','unknown_counter_requires_exception:'+kind)
                checks.check(outcome['known_physics_substeps_lower_bound']>=kernel_returned,'known_return_lower_bound:'+kind)
            checks.compare(outcome['unknown_original_step_attempts'],attempts-kernel_returned,'unknown_steps:'+kind)
            actual = [r for r in all_records if r['original_mj_step_returned'] and r['force_after_available']]
            requested_effort = [{'absolute_nm_s':sum(abs(r['accepted_request'][j]) for r in all_records if r['original_mj_step_returned'])*.002,
                                 'squared_nm2_s':sum(r['accepted_request'][j]**2 for r in all_records if r['original_mj_step_returned'])*.002} for j in range(8)]
            actual_effort = [{'absolute_nm_s':sum(abs(r['after_actuator_force_nm'][j]) for r in actual)*.002,
                              'squared_nm2_s':sum(r['after_actuator_force_nm'][j]**2 for r in actual)*.002} for j in range(8)]
            checks.compare(outcome['known_requested_effort_by_joint'],requested_effort,'requested_effort:'+kind)
            checks.compare(outcome['known_actual_force_effort_by_joint'],actual_effort,'actual_effort:'+kind)
            checks.compare(outcome['known_actual_force_substeps'],len(actual),'known_force_count:'+kind)
            effort[kind] = {'requested':requested_effort,'actual':actual_effort}
            if outcome['status']=='completed':
                checks.compare([outcome[x] for x in ('control_calls_attempted','control_steps','returned_endpoints')],[120]*3,'complete_calls:'+kind)
                checks.compare(kernel_returned,1200,'complete_substeps:'+kind)
                checks.compare(attempts,1200,'complete_attempts:'+kind)
                checks.compare(len(actual),1200,'complete_force_count:'+kind)
                checks.compare(outcome['unknown_original_step_attempts'],0,'complete_no_unknown:'+kind)
                checks.compare(len(rows),120,'complete_rows:'+kind)
                checks.check(all(r['study_abort'] is None and not r['environment_terminated'] for r in rows),'complete_no_stop:'+kind)
            if outcome['status']=='terminated':
                checks.check(bool(rows) and (rows[-1]['study_abort'] is not None or rows[-1]['environment_terminated']),'terminated_endpoint:'+kind)
            if len(rows)>100:
                checks.compare(outcome['reference_q_rad'],rows[99]['observation_after']['joint_position'][:2],'paid_prefix_reference:'+kind)
        totals['model_parameter_updates'] = 0
        checks.compare(metadata['actual_budget'],dict(totals),'total_budget')
        checks.compare(metadata['outcome_counts'],dict(Counter(o['status'] for o in outcomes)),'outcome_counts')
        events = read_json(path/'parameter_events.json')
        if all(o['status']=='completed' for o in outcomes):
            checks.compare([e['kind'] for e in events],list(KINDS),'complete_event_inventory')
        for event in events:
            checks.compare(event['step_boundary'],100,'event_boundary')
            if event['status'] in ('applied','not_applicable'):
                audit_mass_event(event,by_kind[event['kind']]['initial_native_mapping']['dof_indices'],checks)
        left,right = traces['base_identity'],traces['wrapper_identity']
        identity_failures_before = checks.failed
        for a,b in zip(left,right):
            for key in ('observation_before','observation_after','qpos','qvel','actual_substep_history'):
                checks.compare(a[key],b[key],'identity.'+key)
            checks.compare(a['diagnostics']['applied_torque_history'],b['diagnostics']['applied_torque_history'],'identity.actual_history')
        identity_complete = len(left)==len(right)==120
        identity_match = checks.failed==identity_failures_before
        checks.compare(metadata['identity_check']['common_native_state_history_match'],identity_match,'identity.report_match')
        checks.compare(metadata['identity_check']['validated_identity'],identity_complete and identity_match,'identity.report')
        complete = all(o['status']=='completed' for o in outcomes)
        checks.compare(metadata['all_four_complete'],complete,'complete_matrix')
        if complete:
            checks.compare(metadata['fatal'],None,'complete_no_fatal')
            checks.compare(metadata['artifact_failures'],[],'complete_no_storage_failure')
            checks.check(not (path/'storage_failure_record.json').exists(),'complete_no_late_storage_failure')
        reconstructed = {'budget':dict(totals),'outcome_counts':dict(Counter(o['status'] for o in outcomes)),
                         'all_four_complete':complete,'identity_rows_complete':identity_complete,'identity_match':identity_match,'effort':effort,'provenance':provenance}
    except (OSError,ValueError,TypeError,KeyError,IndexError,zipfile.BadZipFile,subprocess.CalledProcessError) as exc:
        checks.check(False,'audit_incomplete:'+type(exc).__name__+':'+str(exc))
    passed = reconstructed is not None and reconstructed['all_four_complete'] and reconstructed['identity_rows_complete'] and reconstructed['identity_match'] and checks.failed==0
    return {'checks':checks.count,'failed':checks.failed,'violations':checks.violations,
        'maximum_recomputation_difference':checks.maximum_difference,'archive':reconstructed,
        'audit_script_sha256':sha(Path(__file__).read_bytes()),
        'engineering_pass':bool(passed and not synthetic_fixture and git_root is not None),
        'learning_or_adaptation_validated':False,'synthetic_fixture':synthetic_fixture,
        'execution':{'wall_seconds':time.perf_counter()-wall,'cpu_seconds':time.process_time()-cpu,
                     'physical_calls':0,'model_updates':0,'source_git_verification_enabled':git_root is not None}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    archive = args.archive.resolve()
    if output.is_relative_to(archive) or output.exists():
        parser.error('Use a new output outside the immutable raw archive')
    root = next(p for p in Path(__file__).resolve().parents if (p/'pyproject.toml').is_file())
    result = audit(archive,git_root=root)
    with output.open('x',encoding='utf-8',newline='\n') as stream:
        json.dump(result,stream,indent=2,allow_nan=False)
    print(json.dumps({'checks':result['checks'],'failed':result['failed'],'engineering_pass':result['engineering_pass']},indent=2))
    return not result['engineering_pass']


if __name__=='__main__':
    raise SystemExit(main())

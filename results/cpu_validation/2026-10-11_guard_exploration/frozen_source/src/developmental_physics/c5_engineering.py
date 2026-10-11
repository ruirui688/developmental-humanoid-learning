"""Frozen engineering runner; real collection requires clean source/protocol binding.

Only the pure synthetic backend is callable while DRAFT is true. No project,
MuJoCo or NumPy import occurs here. Prescribed commands use no hidden labels.
"""
from contextlib import contextmanager
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
import platform
import re
import subprocess
import sys
import time
import zipfile

DRAFT = False
FROZEN_BINDING_PATH = 'docs/C5_ENGINEERING_BINDING.json'
FROZEN_PROTOCOL_PATH = 'docs/C5_ENGINEERING_PROTOCOL.md'
FROZEN_RUNNER_PATH = 'src/developmental_physics/c5_engineering.py'
REQUIRED_SOURCE_PATHS = (
    FROZEN_RUNNER_PATH, 'src/developmental_physics/perturbed_environment.py',
    'src/developmental_physics/environment.py', 'src/developmental_physics/__init__.py',
    'src/developmental_physics/assets/ground_body.xml', FROZEN_PROTOCOL_PATH,
    'scripts/audit_c5_engineering.py')
SEED, RESET_SEED, PREFIX, ACTIVE, SUBSTEPS, DT = 0, 3757552657, 100, 20, 10, .002
KINDS = ('base_identity', 'wrapper_identity', 'gain_half', 'armature_double')
OBS_FIELDS = {'joint_position': 8, 'joint_velocity': 8, 'actuator_torque': 8,
              'previous_command': 8, 'imu_gyro': 3, 'imu_acceleration': 3}
JOINTS = ('left_shoulder', 'left_elbow', 'right_shoulder', 'right_elbow',
          'left_hip', 'left_knee', 'right_hip', 'right_knee')
PLAN = {'pose':'supine','development_seed':SEED,'reset_seed':RESET_SEED,'trials':list(KINDS),
    'fresh_environment_per_trial':True,'prefix_steps':PREFIX,'active_steps':ACTIVE,
    'physics_substeps_per_call':SUBSTEPS,'physics_dt_seconds':DT,'maximum_calls':480,
    'maximum_substeps':4800,'parameter_updates':0,'selected_native_joints':[0,1],
    'active_blocks':'(+.25,+.25)*5 / zero*5 / (-.25,-.25)*5 / zero*5',
    'event_boundary':100,'gain_half':[.5,.5,1.,1.,1.,1.,1.,1.],
    'armature_double_native_values':[.02,.02],
    'study_q_offset_limit_rad':.12,'study_velocity_limit_rad_s':1.}


def plain(value):
    if hasattr(value, 'tolist'):
        return plain(value.tolist())
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [plain(v) for v in value]
    if value is None or type(value) in (str, bool, int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else {'invalid_numeric': repr(value)}
    return str(value)


def finite_vector(value, length, label):
    value = plain(value)
    if not isinstance(value, list) or len(value) != length or not all(type(x) in (int, float) and math.isfinite(x) for x in value):
        raise ValueError('finite native '+label+' length '+str(length)+' required')
    return value


def native_observation(value):
    if set(value) != set(OBS_FIELDS):
        raise ValueError('native observation keys must match; hidden fields forbidden')
    return {k: finite_vector(value[k], n, k) for k, n in OBS_FIELDS.items()}


def command(index):
    if index < PREFIX:
        return [0.]*8
    slot = index-PREFIX
    u = .25 if slot < 5 else -.25 if 10 <= slot < 15 else 0.
    return [u, u, 0., 0., 0., 0., 0., 0.]


def error_record(exc):
    return {'type': type(exc).__name__, 'message': str(exc)}


def write_json(path, value):
    with Path(path).open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(plain(value), stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')


def live_snapshot(env, *, best_effort=False):
    getters = {'qpos': lambda: plain(env.data.qpos), 'qvel': lambda: plain(env.data.qvel),
        'ctrl': lambda: plain(env.data.ctrl), 'time': lambda: float(env.data.time),
        'last_command': lambda: plain(env.last_command), 'step_id': lambda: int(env.step_id),
        'physics_steps': lambda: int(env.physics_steps), 'armature': lambda: plain(env.model.dof_armature),
        'actuator_force': lambda: finite_vector(env.data.actuator_force,8,'live actuator force'),
        'sensordata': lambda: plain(env.data.sensordata),
        'plant_fingerprint': env.parameter_fingerprint,
        'base_fingerprint': getattr(env, 'base_model_fingerprint', env.parameter_fingerprint)}
    result, errors = {}, {}
    for key, getter in getters.items():
        try:
            result[key] = getter()
        except BaseException as exc:
            if not best_effort:
                raise
            errors[key] = error_record(exc)
    if errors:
        result['capture_errors'] = errors
    return result


def study_stop(obs, reference, step):
    if step < PREFIX:
        return None
    triggers=[]
    for joint in (0, 1):
        q, v = obs['joint_position'][joint], obs['joint_velocity'][joint]
        if abs(q-reference[joint]) >= .12:
            triggers.append({'joint_index': joint, 'signal': 'absolute_q_minus_qref_rad', 'value': q-reference[joint]})
        if abs(v) >= 1.:
            triggers.append({'joint_index': joint, 'signal': 'absolute_velocity_rad_s', 'value': v})
    return None if not triggers else {'type': 'StudyAbort', 'step_index': step,
        'active_step_index': step-PREFIX, 'triggers': triggers, 'reference_q_rad': reference,
        'thresholds': {'absolute_q_minus_qref_rad': .12, 'absolute_velocity_rad_s': 1.}}


def asset_audit(env):
    joints = [int(x) for x in env._joint_ids]
    qpos = [int(x) for x in env._joint_qpos]
    dofs = [int(x) for x in env._joint_dof]
    if (len(joints)!=8 or len(set(joints))!=8 or len(qpos)!=8 or len(set(qpos))!=8
            or len(dofs)!=8 or len(set(dofs))!=8 or any(d<0 or d>=env.model.nv for d in dofs)
            or any(q<0 or q>=len(env.data.qpos) for q in qpos)):
        raise ValueError('native mapping must contain eight unique joints')
    if env.config.physics_dt != DT or env.config.control_substeps != SUBSTEPS or env.model.opt.timestep != DT:
        raise ValueError('fixed .002 seconds and ten substeps required')
    lookup = [int(env.model.jnt_dofadr[j]) for j in joints]
    qlookup = [int(env.model.jnt_qposadr[j]) for j in joints]
    named = [int(env.model.joint(name).id) for name in JOINTS]
    if lookup != dofs or qlookup != qpos or named != joints:
        raise ValueError('native model lookup mapping mismatch')
    for i in range(8):
        gain, gear, bias = (plain(getattr(env.model, key)[i]) for key in ('actuator_gainprm','actuator_gear','actuator_biasprm'))
        if gain[0] != 1. or any(x != 0. for x in gain[1:]) or gear[0] != 1. or any(x != 0. for x in gear[1:]) or any(x != 0. for x in bias):
            raise ValueError('unchanged unit gain/gear and zero bias required')
        if int(env.model.actuator_trnid[i][0]) != joints[i]:
            raise ValueError('native actuator/joint transmission mismatch')
        if any(int(getattr(env.model,key)[i]) != 0 for key in ('actuator_dyntype','actuator_gaintype','actuator_biastype','actuator_trntype')):
            raise ValueError('ordinary stateless fixed-gain joint motor required')
        if (plain(env.model.actuator_ctrlrange[i])!=[-.5,.5] or not bool(env.model.actuator_ctrllimited[i])
                or bool(env.model.actuator_forcelimited[i])):
            raise ValueError('fixed public .5 N m ctrl limits and no additional force limiter required')
    actions=finite_vector(env.action_limits,8,'action limits')
    if actions != [.5]*8:
        raise ValueError('public action permissions must remain .5 N m')
    initial_armature = plain(env.model.dof_armature)
    if any(initial_armature[d] != .01 for d in dofs):
        raise ValueError('fresh asset native armature .01 required')
    return {'joint_ids': joints, 'qpos_indices': qpos, 'dof_indices': dofs,
        'unit_gain_gear_bias_verified': True, 'initial_armature': initial_armature,
        'public_joint_ranges': [plain(env.model.jnt_range[j]) for j in joints],
        'action_limits_nm':actions,'motor_ctrlrange_nm':plain(env.model.actuator_ctrlrange),
        'motor_ctrl_limited':plain(env.model.actuator_ctrllimited),
        'motor_force_limited':plain(env.model.actuator_forcelimited)}


class SubstepMeter:
    """Scoped read-only mj_step interception; never inserts a step or forward."""
    def __init__(self, module, env, audit):
        self.module, self.env, self.audit = module, env, audit
        self.records=[]
        self.accepted=[0.]*8
        self.gains=[1.]*8
        self.original_returned=0
        self.original_attempts=0

    def hook(self, model, data):
        if model is not self.env.model or data is not self.env.data:
            raise RuntimeError('instrumentation rejects unrelated model/data')
        record={'original_mj_step_attempted': False, 'original_mj_step_returned': False,
            'force_after_available': False, 'accepted_request': self.accepted.copy(),
            'hidden_channel_gains': self.gains.copy(), 'capture_scope': 'before/after original mj_step; no added forward'}
        try:
            angles=finite_vector([data.qpos[i] for i in self.audit['qpos_indices']],8,'substep before angle')
            ctrl=finite_vector(data.ctrl,8,'substep before ctrl')
            scaled=[u*g for u,g in zip(self.accepted,self.gains)]
            guard=[(q <= limits[0]+.03 and u < 0.) or (q >= limits[1]-.03 and u > 0.)
                   for q,u,limits in zip(angles,scaled,self.audit['public_joint_ranges'])]
            expected=[0. if blocked else u for u,blocked in zip(scaled,guard)]
            record.update(before_angles_rad=angles, before_ctrl_nm=ctrl, scaled_request_nm=scaled,
                          independently_expected_guard=guard, independently_expected_ctrl_nm=expected,
                          guard_actual_match=all(abs(a-b)<=1e-12 for a,b in zip(ctrl,expected)))
            if not record['guard_actual_match']:
                raise RuntimeError('actual pre-mj_step ctrl differs from declared scale/guard')
            record['original_mj_step_attempted']=True
            self.original_attempts+=1
            self.original(model,data)
            record['original_mj_step_returned']=True
            self.original_returned+=1  # Facts retained even if post-force read then fails.
            force=finite_vector(data.actuator_force,8,'after mj_step actuator force')
            record.update(after_actuator_force_nm=force, force_after_available=True,
                          unit_motor_force_match=all(abs(a-b)<=1e-12 for a,b in zip(ctrl,force)))
            if not record['unit_motor_force_match']:
                raise RuntimeError('actual unit-motor force differs from pre-step ctrl')
        except BaseException as exc:
            record['exception']=error_record(exc)
            raise
        finally:
            self.records.append(record)

    @contextmanager
    def installed(self):
        self.original=self.module.mj_step
        self.module.mj_step=self.hook
        try:
            yield self
        finally:
            self.module.mj_step=self.original


def boundary_event(kind, env, mapping, mass_matrix):
    before=live_snapshot(env)
    record={'kind':kind, 'step_boundary': PREFIX, 'before_live':before, 'environment_event':None}
    try:
        record['mass_matrix_before']=mass_matrix(env)
        if kind == 'wrapper_identity':
            record['environment_event']=env.set_channel_gains([1.]*8)
        elif kind == 'gain_half':
            record['environment_event']=env.set_channel_gains([.5,.5]+[1.]*6)
        elif kind == 'armature_double':
            record['environment_event']=env.change_armature((0,1),(.02,.02))
        after=live_snapshot(env)
        for key in ('qpos','qvel','ctrl','last_command','time','step_id','physics_steps'):
            if before[key] != after[key]:
                raise RuntimeError('parameter boundary changed persistent live '+key)
        expected=before['armature'].copy()
        if kind == 'armature_double':
            for dof in mapping['dof_indices'][:2]: expected[dof]=.02
        if after['armature'] != expected:
            raise RuntimeError('armature event changed undeclared dofs')
        if kind == 'gain_half' and before['plant_fingerprint']==after['plant_fingerprint']:
            raise RuntimeError('gain event missing from complete plant fingerprint')
        if kind == 'gain_half' and before['base_fingerprint']!=after['base_fingerprint']:
            raise RuntimeError('gain event changed base physical fingerprint')
        record['mass_matrix_after']=mass_matrix(env)
        left,right=record['mass_matrix_before'],record['mass_matrix_after']
        if left['qpos']!=right['qpos'] or left['qpos']!=before['qpos']:
            raise RuntimeError('mass diagnostics must evaluate the identical live q')
        size=len(before['armature'])
        if len(left['matrix'])!=size or len(right['matrix'])!=size:
            raise ValueError('full generalized mass matrix required')
        selected=mapping['dof_indices'][:2] if kind=='armature_double' else []
        maximum=0.;deltas=[]
        for i in range(size):
            a=finite_vector(left['matrix'][i],size,'mass matrix before row')
            b=finite_vector(right['matrix'][i],size,'mass matrix after row')
            for j in range(size):
                expected=.01 if i==j and i in selected else 0.
                maximum=max(maximum,abs((b[j]-a[j])-expected))
            deltas.append(b[i]-a[i])
        record['mass_matrix_change']={'diagonal_delta':deltas,
            'selected_native_dof_indices':selected,'expected_selected_diagonal_delta':.01 if selected else 0.,
            'maximum_absolute_error_from_expected_delta':maximum,'tolerance':1e-12,
            'diagnostic_only':True,'physics_substeps_added':0}
        if maximum>1e-12:
            raise RuntimeError('same-q mass matrix change differs from declared armature diagonal delta')
        record['status']='applied' if kind != 'base_identity' else 'not_applicable'
    except BaseException as exc:
        record['status']='failed';record['error']=error_record(exc)
        record['environment_event']=getattr(exc,'parameter_event_record',record['environment_event'])
        exc.engineering_event_record=record
        raise
    finally:
        record['after_live']=live_snapshot(env,best_effort=True)
    return record


def identity_check(rows):
    left,right=rows.get('base_identity',[]),rows.get('wrapper_identity',[])
    maximum=0.; compared=0
    fields=('observation_before','observation_after','qpos','qvel','actual_substep_history')
    exact=True
    def compare(a,b):
        nonlocal maximum,compared
        if type(a) in (int,float) and type(b) in (int,float):
            compared+=1;maximum=max(maximum,abs(a-b));return abs(a-b)<=1e-12
        if isinstance(a,list) and isinstance(b,list):
            results=[compare(x,y) for x,y in zip(a,b)]
            return len(a)==len(b) and all(results)
        if isinstance(a,dict) and isinstance(b,dict):
            results=[compare(a[k],b[k]) for k in a.keys() & b.keys()]
            return set(a)==set(b) and all(results)
        return a==b
    matches=True
    for a,b in zip(left,right):
        selected_a={k:a[k] for k in fields};selected_b={k:b[k] for k in fields}
        exact=exact and json.dumps(selected_a,sort_keys=True,separators=(',',':'))==json.dumps(selected_b,sort_keys=True,separators=(',',':'))
        matches=compare(selected_a,selected_b) and matches
    return {'complete_120_returned_rows_each':len(left)==len(right)==120,
        'common_rows':min(len(left),len(right)), 'numeric_leaf_comparisons':compared,
        'maximum_absolute_difference':maximum,'serialized_native_state_history_exact':exact,
        'numeric_tolerance':1e-12,'common_native_state_history_match':matches,
        'validated_identity':len(left)==len(right)==120 and matches}


def load_frozen_binding(project_root, *, runner_path=None):
    """Only real entry calls Git; synthetic fixtures may stub this read-only interface."""
    root=Path(project_root).resolve()
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
    status=subprocess.check_output(['git','status','--porcelain','--untracked-files=all'],cwd=root,text=True)
    if not re.fullmatch('[0-9a-f]{40}',commit) or status!='':
        raise ValueError('clean current Git HEAD required for real engineering collection')
    binding_path=root/FROZEN_BINDING_PATH
    data=binding_path.read_bytes()
    if data!=subprocess.check_output(['git','show','HEAD:'+FROZEN_BINDING_PATH],cwd=root):
        raise ValueError('tracked binding bytes must match current HEAD blob')
    binding=json.loads(data)
    if binding.get('draft') is not False or binding.get('schema_version')!=1 or binding.get('plan')!=PLAN:
        raise ValueError('root-frozen binding and unchanged four-trial plan required')
    sources={}
    if not set(REQUIRED_SOURCE_PATHS).issubset(binding.get('source_sha256',{})):
        raise ValueError('frozen source list must include all minimal runtime/protocol sources')
    for name,expected in binding['source_sha256'].items():
        candidate=(root/name).resolve()
        if (Path(name).is_absolute() or not candidate.is_relative_to(root) or name==FROZEN_BINDING_PATH
                or candidate.relative_to(root).as_posix()!=name):
            raise ValueError('safe tracked source list excluding binding self-hash required')
        value=candidate.read_bytes()
        if hashlib.sha256(value).hexdigest()!=expected or value!=subprocess.check_output(['git','show','HEAD:'+name],cwd=root):
            raise ValueError('tracked source bytes/hash must match HEAD: '+name)
        sources[name]=value
    runner_name=(Path(runner_path).resolve() if runner_path is not None else Path(__file__).resolve()).relative_to(root).as_posix()
    if runner_name!=FROZEN_RUNNER_PATH or runner_name not in sources:
        raise ValueError('actual executed runner must be in frozen tracked source list')
    protocol=binding['protocol_path']
    if protocol!=FROZEN_PROTOCOL_PATH or protocol not in sources or hashlib.sha256(sources[protocol]).hexdigest()!=binding['protocol_sha256']:
        raise ValueError('tracked protocol path/hash must be frozen')
    sources[FROZEN_BINDING_PATH]=data
    return {'source_commit':commit,'source_status':status,'source_dirty':False,
            'binding_path':FROZEN_BINDING_PATH,'binding_sha256':hashlib.sha256(data).hexdigest(),
            'binding':binding},sources


def run_engineering(output, backend, *, synthetic=False, project_root=None):
    """Fixed engineering plan; validate frozen binding before any real factory call."""
    if synthetic:
        if getattr(backend,'synthetic',None) is not True:
            raise ValueError('explicit pure synthetic backend required')
        source_record=None;frozen_sources=None
    else:
        if DRAFT:
            raise RuntimeError('DRAFT: real physical execution is forbidden until root freezes source/protocol')
        if getattr(backend,'synthetic',None) is not False:
            raise ValueError('synthetic backend cannot bypass real freeze')
        source_record,frozen_sources=load_frozen_binding(project_root or Path.cwd())
    output=Path(output)
    output.mkdir(parents=True,exist_ok=False)
    wall,cpu=time.perf_counter(),time.process_time()
    metadata={'draft':DRAFT,'synthetic':synthetic,'physical_validation':False,
        'engineering_physics_planned':not synthetic,'engineering_physics_executed':False,
        'algorithm_learning_validated':False,
        'source_binding':source_record,'source_dirty':None if synthetic else False,'fixed_plan':PLAN,
        'seed':SEED,'reset_seed':RESET_SEED,'pose':'supine','trial_order':list(KINDS),
        'prefix_steps':PREFIX,'active_steps':ACTIVE,'maximum_control_calls':480,'maximum_physics_substeps':4800,
        'model_parameter_updates':0,'policy_updates':0,'teacher_calls':0,
        'backend_versions':plain(backend.versions),'python':sys.version,'platform':platform.platform(),
        'created_at_utc':datetime.now(timezone.utc).isoformat(),
        'instrumentation':'Scoped original mj_step only; no inserted forward/step. Failed/unreturned kernel attempts have unknown extra integration; returned kernel facts independently count paid lower bound.',
        'source_sha256':{}}
    sources={Path(__file__).name:Path(__file__).read_bytes()}
    protocol=Path(__file__).with_name('ENGINEERING_PROTOCOL_DRAFT.md')
    if protocol.exists(): sources[protocol.name]=protocol.read_bytes()
    for name,data in getattr(backend,'source_bytes',{}).items(): sources[name]=data
    if not synthetic:
        for name,data in getattr(backend,'source_bytes',{}).items():
            if frozen_sources.get(name)!=data:
                raise ValueError('backend source absent from exact tracked binding')
        sources=frozen_sources
    with zipfile.ZipFile(output/'source_snapshot.zip','x',compression=zipfile.ZIP_DEFLATED) as archive:
        for name,data in sources.items():
            archive.writestr(name,data);metadata['source_sha256'][name]=hashlib.sha256(data).hexdigest()
    write_json(output/'metadata_initial.json',metadata)
    outcomes=[{'kind':k,'status':'planned','control_calls_attempted':0,'control_steps':0,
               'known_physics_substeps_lower_bound':0,'unknown_original_step_attempts':0,'returned_endpoints':0}
              for k in KINDS]
    rows={};events=[];fatal=None
    artifact_failures=[]
    def persist(name,value):
        try:
            write_json(output/name,value)
            return True
        except BaseException as exc:
            error={'artifact':name,'error':error_record(exc)}
            artifact_failures.append(error)
            print(json.dumps({'artifact_write_failure':error,'paid_outcomes':plain(outcomes)},ensure_ascii=False))
            return False
    trace=gzip.open(output/'trace.jsonl.gz','xt',encoding='utf-8')
    try:
        for outcome in outcomes:
            kind=outcome['kind'];rows[kind]=[]
            if fatal is not None:
                outcome.update(status='blocked',blocked_by=deepcopy(fatal))
                persist(kind+'_outcome.json',outcome)
                continue
            env=meter=None; current_step=None; requested=None;phase='setup'
            before_counter=(0,0); pre_returned=pre_attempts=0; before_obs=None; reference=None;record_start=0
            try:
                env=backend.fresh(kind)
                mapping=asset_audit(env)
                initial=native_observation(env.reset(seed=RESET_SEED,pose='supine'))
                if env.physics_steps != 0 or env.step_id != 0:
                    raise RuntimeError('fresh reset unexpectedly added paid steps')
                outcome['initial_native_mapping']=mapping;outcome['fresh_parameters']=live_snapshot(env)
                meter=SubstepMeter(backend.module,env,mapping)
                observation=initial
                with meter.installed():
                    for index in range(PREFIX+ACTIVE):
                        current_step=index;phase='prefix' if index<PREFIX else 'active'
                        if index==PREFIX:
                            phase='event';requested=None;record_start=len(meter.records)
                            reference=observation['joint_position'][:2]
                            event=boundary_event(kind,env,mapping,backend.mass_matrix);events.append(plain(event))
                            observation=native_observation(env.observation())
                            phase='active'
                        requested=command(index)
                        before_obs=observation
                        meter.accepted=[max(-limit,min(limit,u)) for u,limit in zip(requested,mapping['action_limits_nm'])]
                        meter.gains=[.5,.5]+[1.]*6 if kind=='gain_half' and index>=PREFIX else [1.]*8
                        record_start=len(meter.records);pre_returned=meter.original_returned;pre_attempts=meter.original_attempts
                        before_counter=(int(env.step_id),int(env.physics_steps))
                        outcome['control_calls_attempted']+=1
                        try:
                            result=env.step(requested)
                        finally:
                            env_delta=int(env.physics_steps)-before_counter[1]
                            returned_delta=meter.original_returned-pre_returned
                            outcome['control_steps']+=int(env.step_id)-before_counter[0]
                            outcome['known_physics_substeps_lower_bound']+=max(env_delta,returned_delta)
                            outcome['unknown_original_step_attempts']+=(meter.original_attempts-pre_attempts)-returned_delta
                        observation=native_observation(result.observation)
                        outcome['returned_endpoints']+=1
                        instrument=deepcopy(meter.records[record_start:])
                        stop=study_stop(observation,reference,index)
                        raw={'kind':kind,'step_index':index,'phase':phase,'requested_torque':requested,
                            'observation_before':before_obs,'observation_after':observation,
                            'qpos':plain(env.data.qpos),'qvel':plain(env.data.qvel),
                            'diagnostics':plain(result.diagnostics),'actual_substep_history':instrument,
                            'study_abort':stop,'environment_terminated':bool(result.terminated)}
                        row=json.dumps(raw,ensure_ascii=False,allow_nan=False)+'\n'
                        trace.write(row);trace.flush();rows[kind].append(raw)
                        outcome['reference_q_rad']=reference
                        if stop is not None or result.terminated:
                            outcome.update(status='terminated',study_abort=stop,
                                environment_terminated=bool(result.terminated),stop_step_index=index)
                            break
                    else:
                        outcome['status']='completed'
            except BaseException as exc:
                fatal={'kind':kind,'phase':phase,'step_index':current_step,'error':error_record(exc)}
                event=getattr(exc,'engineering_event_record',None)
                if event is not None: events.append(plain(event))
                outcome.update(status='exception',exception=deepcopy(fatal),
                    failed_request=requested,observation_before=before_obs,
                    failure_live_state=None if env is None else live_snapshot(env,best_effort=True),
                    partial_instrumentation=[] if meter is None else plain(meter.records[record_start:]),
                    actual_history_is_lower_bound=True,parameter_event=plain(event))
                print(json.dumps({'fatal_paid_outcome':plain(outcome)},ensure_ascii=False))
            finally:
                if env is not None:
                    outcome['final_live_state']=live_snapshot(env,best_effort=True)
                    # Setup/reset failure cannot erase paid work even before the meter was installed.
                    final=outcome['final_live_state']
                    if type(final.get('physics_steps')) is int:
                        outcome['known_physics_substeps_lower_bound']=max(outcome['known_physics_substeps_lower_bound'],final['physics_steps'])
                    if type(final.get('step_id')) is int:
                        outcome['control_steps']=max(outcome['control_steps'],final['step_id'])
                known=[] if meter is None else [r for r in meter.records if r['original_mj_step_returned']]
                actual=[r for r in known if r['force_after_available']]
                outcome['independently_observed_kernel_returned_substeps']=0 if meter is None else meter.original_returned
                outcome['independently_observed_kernel_attempts']=0 if meter is None else meter.original_attempts
                outcome['known_actual_force_substeps']=len(actual)
                outcome['actual_force_effort_is_lower_bound']=len(actual)!=outcome['known_physics_substeps_lower_bound'] or outcome['unknown_original_step_attempts']>0
                outcome['known_requested_effort_by_joint']=[{
                    'absolute_nm_s':sum(abs(r['accepted_request'][j]) for r in known)*DT,
                    'squared_nm2_s':sum(r['accepted_request'][j]**2 for r in known)*DT} for j in range(8)]
                outcome['known_actual_force_effort_by_joint']=[{
                    'absolute_nm_s':sum(abs(r['after_actuator_force_nm'][j]) for r in actual)*DT,
                    'squared_nm2_s':sum(r['after_actuator_force_nm'][j]**2 for r in actual)*DT} for j in range(8)]
                outcome['actual_budget_is_lower_bound']=outcome['unknown_original_step_attempts']>0 or outcome['status']=='exception'
                if outcome['status']=='completed':
                    if not (outcome['control_calls_attempted']==outcome['control_steps']==outcome['returned_endpoints']==120
                            and outcome['known_physics_substeps_lower_bound']==1200 and outcome['unknown_original_step_attempts']==0):
                        outcome['status']='exception';fatal={'kind':kind,'error':{'type':'IncompleteBudget','message':'claimed completion budget mismatch'}}
                if not persist(kind+'_outcome.json',outcome):
                    fatal={'kind':kind,'phase':'outcome_storage','error':deepcopy(artifact_failures[-1])}
                    outcome.update(status='exception',storage_failure=deepcopy(fatal),actual_budget_is_lower_bound=True)
    finally:
        try:
            trace.close()
        except BaseException as exc:
            fatal={'phase':'trace_close','error':error_record(exc)}
            artifact_failures.append({'artifact':'trace.jsonl.gz','error':error_record(exc)})
            print(json.dumps({'trace_close_failure':fatal,'paid_outcomes':plain(outcomes)},ensure_ascii=False))
    totals={key:sum(o[key] for o in outcomes) for key in ('control_calls_attempted','control_steps','known_physics_substeps_lower_bound','unknown_original_step_attempts','returned_endpoints')}
    totals['model_parameter_updates']=0
    metadata.update(actual_budget=totals,outcome_counts=dict(Counter(o['status'] for o in outcomes)),
        engineering_physics_executed=(not synthetic and (totals['known_physics_substeps_lower_bound']>0
            or totals['unknown_original_step_attempts']>0)),
        fatal=fatal,identity_check=identity_check(rows),all_four_complete=all(o['status']=='completed' for o in outcomes),
        actual_budget_is_lower_bound=any(o.get('actual_budget_is_lower_bound',False) for o in outcomes),
        wall_seconds=time.perf_counter()-wall,cpu_seconds=time.process_time()-cpu,
        artifact_failures=artifact_failures)
    persist('parameter_events.json',events)
    persist('trial_outcomes.json',outcomes)
    if artifact_failures:
        metadata['all_four_complete']=False
        metadata['fatal']=metadata['fatal'] or {'phase':'artifact_storage','error':deepcopy(artifact_failures[-1])}
    persist('metadata_final.json',metadata)
    try:
        manifest={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in output.iterdir() if p.is_file()}
        persist('manifest.json',manifest)
    except BaseException as exc:
        artifact_failures.append({'artifact':'manifest.json','error':error_record(exc)})
    if artifact_failures:
        metadata['all_four_complete']=False
        metadata['fatal']=metadata['fatal'] or {'phase':'artifact_storage','error':deepcopy(artifact_failures[-1])}
        print(json.dumps({'final_paid_metadata':plain(metadata)},ensure_ascii=False))
        persist('storage_failure_record.json',metadata)
    return metadata


class RealBackend:
    """Lazy optional dependencies; construction itself imports no physics backend."""
    synthetic=False

    def __init__(self, project_root):
        self.project_root=Path(project_root).resolve()
        self._loaded=False

    def _load(self):
        if self._loaded:
            return
        import mujoco
        import numpy as np
        import developmental_physics.environment as environment
        import developmental_physics.perturbed_environment as perturbed
        from developmental_physics.perturbed_environment import PerturbedGroundBodyEnv
        for module,name in ((environment,'environment.py'),(perturbed,'perturbed_environment.py')):
            expected=self.project_root/'src'/'developmental_physics'/name
            if Path(module.__file__).resolve()!=expected.resolve():
                raise RuntimeError('imported runtime module must be the frozen project source: '+name)
        # Same original module API used by GroundBodyEnv.step, not a parallel integrator.
        self.module=environment.mujoco
        if self.module is not mujoco:
            raise RuntimeError('unexpected MuJoCo module identity')
        self.np=np;self.environment=environment;self.wrapper_class=PerturbedGroundBodyEnv
        self._loaded=True

    @property
    def versions(self):
        self._load()
        return {'mujoco':self.module.__version__,'numpy':self.np.__version__,'device':'cpu'}

    @property
    def source_bytes(self):
        return {name:(self.project_root/name).read_bytes() for name in REQUIRED_SOURCE_PATHS}

    def fresh(self, kind):
        self._load()
        if kind not in KINDS:
            raise ValueError('undeclared trial kind')
        cls=self.environment.GroundBodyEnv if kind=='base_identity' else self.wrapper_class
        return cls(self.environment.ExplorationConfig())

    def mass_matrix(self, env):
        """Forward on scratch data at exactly live q; never touch or integrate live data."""
        self._load()
        scratch=self.module.MjData(env.model)
        scratch.qpos[:]=env.data.qpos
        scratch.qvel[:]=env.data.qvel
        scratch.ctrl[:]=env.data.ctrl
        if len(scratch.act): scratch.act[:]=env.data.act
        self.module.mj_forward(env.model,scratch)
        matrix=self.np.empty((env.model.nv,env.model.nv))
        # This project CPU environment uses MuJoCo 3.15's (model, data, dst) API.
        # No fallback/retry is attempted; an incompatible API must fail visibly.
        self.module.mj_fullM(env.model,scratch,matrix)
        return {'qpos':plain(scratch.qpos),'matrix':plain(matrix),
            'scope':'scratch MjData: one nonintegrating forward and mj_fullM; no live mutation',
            'physics_substeps_added':0,'diagnostic_only':True}


def main(argv=None):
    import argparse
    parser=argparse.ArgumentParser(description='Frozen C5 CPU engineering check; zero parameter updates')
    parser.add_argument('--output',required=True)
    parser.add_argument('--project-root',default=str(Path.cwd()))
    args=parser.parse_args(argv)
    # run_engineering checks DRAFT/binding before accessing lazy versions/factory.
    record=run_engineering(args.output,RealBackend(args.project_root),project_root=args.project_root)
    print(json.dumps({'actual_budget':record['actual_budget'],'fatal':record['fatal'],
        'all_four_complete':record['all_four_complete'],'identity_check':record['identity_check']},ensure_ascii=False))
    return 0 if (record['fatal'] is None and record['all_four_complete']
        and record['identity_check']['validated_identity']) else 1


if __name__=='__main__':
    raise SystemExit(main())

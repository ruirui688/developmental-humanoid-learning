import gzip
import json
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip('mujoco')
from developmental_physics import feedback_validate as runner


def test_pd_matches_feedback_formula_and_shared_cap():
    command, raw = runner.pd_request(.1,.03,.06,4.,.2)
    assert raw == pytest.approx(-.166)
    assert command == raw
    assert runner.pd_request(.1,0.,.06,64.,0.) == pytest.approx((-.5,-2.56))


@pytest.mark.parametrize('args',[(True,0.,0.,4.,.2),(0.,float('nan'),0.,4.,.2),
                               (0.,0.,0.,-1.,.2),(0.,0.,0.,4.,True)])
def test_pd_rejects_invalid_native_inputs_or_gains(args):
    with pytest.raises(ValueError):
        runner.pd_request(*args)


def test_grid_counts_every_prefix_and_preserves_same_start(tmp_path):
    output = tmp_path/'grid'
    protocol = Path(__file__).resolve().parents[1]/'docs/LOCAL_BODY_LEARNING_V2_PROTOCOL.md'
    meta = runner.run_feedback(output,[0],[(4.,.2),(16.,.2)],protocol_path=protocol)
    assert meta['complete'] and meta['all_trials_successful']
    assert meta['control_steps'] == meta['control_calls_attempted'] == 600
    assert meta['physics_steps'] == 6000
    episodes = json.loads((output/'episodes.json').read_text())
    assert all(e['metric_control_step_count']==200 for e in episodes)
    assert all(e['phase_budgets']['prefix']['control_steps']==100 for e in episodes)
    with gzip.open(output/'trace.jsonl.gz','rt',encoding='utf-8') as stream:
        rows = [json.loads(line) for line in stream]
    prefixes = [[r['observation_after'] for r in rows if r['candidate']==c and r['phase']=='prefix'] for c in (0,1)]
    assert prefixes[0] == prefixes[1]
    assert episodes[0]['prefix_end_q_rad'] == episodes[1]['prefix_end_q_rad']
    for r in rows:
        assert abs(r['requested_torque'][0]) <= .5
        assert r['requested_torque'][1:] == [0.]*7
        if r['phase']=='control':
            q,v = (r['observation_before'][k][0] for k in ('joint_position','joint_velocity'))
            assert r['requested_torque'][0] == runner.pd_request(q,v,r['target_q_rad'],r['kp'],r['kd'])[0]
    with pytest.raises(FileExistsError):
        runner.run_feedback(output,[0],[(4.,.2)],protocol_path=protocol)


def test_partial_fault_keeps_attempted_call_and_physics_cost(tmp_path,monkeypatch):
    original = runner.mujoco.mj_step
    count = 0
    def fail(model,data):
        nonlocal count
        count += 1
        if count == 13:
            raise RuntimeError('injected substep fault')
        original(model,data)
    monkeypatch.setattr(runner.mujoco,'mj_step',fail)
    output = tmp_path/'partial'
    protocol = Path(__file__).resolve().parents[1]/'docs/LOCAL_BODY_LEARNING_V2_PROTOCOL.md'
    meta = runner.run_feedback(output,[0],[(4.,.2)],protocol_path=protocol)
    e = json.loads((output/'episodes.json').read_text())[0]
    assert e['status']=='exception' and not e['complete']
    assert meta['control_calls_attempted']==2
    assert meta['physics_steps']==12
    assert e['metric_control_step_count']==0 and e['tracking_rmse_rad'] is None


def test_interrupt_keeps_remaining_candidates_blocked(tmp_path,monkeypatch):
    original = runner.GroundBodyEnv.step
    count = 0
    def interrupt(env,request):
        nonlocal count
        count += 1
        if count==2:
            raise KeyboardInterrupt()
        return original(env,request)
    monkeypatch.setattr(runner.GroundBodyEnv,'step',interrupt)
    output = tmp_path/'interrupt'
    protocol = Path(__file__).resolve().parents[1]/'docs/LOCAL_BODY_LEARNING_V2_PROTOCOL.md'
    with pytest.raises(KeyboardInterrupt):
        runner.run_feedback(output,[0],[(4.,.2),(16.,.2)],protocol_path=protocol)
    episodes = json.loads((output/'episodes.json').read_text())
    assert episodes[0]['control_calls_attempted']==2
    assert episodes[1]['status']=='blocked' and episodes[1]['control_calls_attempted']==0


def test_non_os_trace_failure_is_fatal_even_if_exception_row_is_saved(tmp_path,monkeypatch):
    original_open = runner.gzip.open
    class FailingStream:
        def __init__(self,stream):
            self.stream = stream
            self.calls = 0
        def __enter__(self):
            self.stream.__enter__()
            return self
        def __exit__(self,*args):
            return self.stream.__exit__(*args)
        def write(self,value):
            self.calls += 1
            if self.calls==1:
                raise RuntimeError('injected trace serialization/stream failure')
            return self.stream.write(value)
    def broken_open(*args,**kwargs):
        return FailingStream(original_open(*args,**kwargs))
    monkeypatch.setattr(runner.gzip,'open',broken_open)
    output = tmp_path/'trace_error'
    protocol = Path(__file__).resolve().parents[1]/'docs/LOCAL_BODY_LEARNING_V2_PROTOCOL.md'
    with pytest.raises(RuntimeError,match='trace serialization'):
        runner.run_feedback(output,[0],[(4.,.2),(16.,.2)],protocol_path=protocol)
    episodes = json.loads((output/'episodes.json').read_text())
    assert episodes[0]['control_calls_attempted']==episodes[0]['control_steps']==1
    assert episodes[0]['physics_steps']==10 and episodes[0]['status']=='exception'
    assert episodes[1]['status']=='blocked' and episodes[1]['control_calls_attempted']==0
    with original_open(output/'trace.jsonl.gz','rt',encoding='utf-8') as stream:
        exception_rows = [json.loads(line) for line in stream]
    assert len(exception_rows)==1
    assert exception_rows[0]['collector_exception']['type']=='RuntimeError'


def test_partial_control_stop_charges_only_executed_substep_effort(tmp_path,monkeypatch):
    original = runner.GroundBodyEnv._stop_reason
    def stop(env):
        if env.physics_steps>=1001:
            return 'injected one-substep control stop'
        return original(env)
    monkeypatch.setattr(runner.GroundBodyEnv,'_stop_reason',stop)
    output = tmp_path/'partial_control'
    protocol = Path(__file__).resolve().parents[1]/'docs/CLASSICAL_PD_DEVELOPMENT_PROTOCOL.md'
    meta = runner.run_feedback(output,[0],[(4.,.2)],protocol_path=protocol)
    e = json.loads((output/'episodes.json').read_text())[0]
    assert e['status']=='terminated' and not e['complete']
    assert meta['physics_steps']==1001 and meta['control_calls_attempted']==101
    with gzip.open(output/'trace.jsonl.gz','rt',encoding='utf-8') as stream:
        last = [json.loads(line) for line in stream][-1]
    assert last['diagnostics']['executed_substeps']==1
    assert e['requested_squared_effort_nm2s']==pytest.approx(last['requested_torque'][0]**2*.002)

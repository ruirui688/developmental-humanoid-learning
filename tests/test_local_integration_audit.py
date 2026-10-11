"""Pure arithmetic audit fixtures: no simulator, archives or experiment fitting."""
import importlib.util
import copy
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest
import zipfile

import pytest

SCRIPT = Path(__file__).resolve().parents[1]/"scripts/audit_local_integration.py"
spec = importlib.util.spec_from_file_location("integration_audit_core", SCRIPT)
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)


class CoreChecks(unittest.TestCase):
    def test_integration_keeps_same_one_step_endpoint_velocity(self):
        endpoint = core.predict(core.INITIAL, .1, .2, .1, .5, "endpoint_euler")
        trapezoid = core.predict(core.INITIAL, .1, .2, .1, .5, "trapezoid")
        self.assertEqual(endpoint[1], trapezoid[1])
        self.assertAlmostEqual(endpoint[0], .2022)
        self.assertAlmostEqual(trapezoid[0], .2021)

    def test_rollout_integrates_predictions_without_true_future_states(self):
        endpoint = core.free_rollout(core.INITIAL, .1, .2, .1, [.5, .5], "endpoint_euler")
        trapezoid = core.free_rollout(core.INITIAL, .1, .2, .1, [.5, .5], "trapezoid")
        self.assertAlmostEqual(endpoint[-1][0], .2046)
        self.assertAlmostEqual(trapezoid[-1][0], .2044)
        self.assertAlmostEqual(endpoint[-1][1], .12)
        self.assertEqual(endpoint[-1][1], trapezoid[-1][1])

    def test_persistence_ignores_the_recorded_requests(self):
        path = core.free_rollout(None, .1, .2, .1, [.5, -.5])
        self.assertEqual(path[-1][1], .1)
        self.assertAlmostEqual(path[-1][0], .204)

    def test_one_record_rls_matches_hand_computed_gain(self):
        covariance = [[100. if i == j else 0. for j in range(5)] for i in range(5)]
        features = [0., 0., .5, .25, 1.]
        theta, matrix = core.replay_rls(core.INITIAL, covariance, features, .1)
        denominator = 132.25
        self.assertAlmostEqual(theta[2], .02+50/denominator*.09)
        self.assertAlmostEqual(theta[3], 25/denominator*.09)
        self.assertAlmostEqual(theta[4], 100/denominator*.09)
        self.assertAlmostEqual(matrix[2][4], -50/denominator*100)
        self.assertEqual(matrix[2][4], matrix[4][2])
        self.assertEqual(covariance[2][4], 0.)
        self.assertEqual(core.INITIAL, [1., 0., .02, 0., 0.])

    def test_mpc_has_same_frozen_candidate_and_prediction_budget(self):
        for rule in core.INTEGRATIONS:
            result = core.replay_mpc(core.INITIAL, 0., 0., 0., .04, 0., [-1., 1.], rule)
            self.assertEqual(result["mathematical_prediction_calls"], 135)
            self.assertEqual(result["feasible_candidates"], 9)
            self.assertEqual(len(result["predicted_q"]), 15)
            self.assertIn(result["torque"], [-.5+i*.125 for i in range(9)])

    def test_no_feasible_candidate_returns_declared_zero_fallback(self):
        result = core.replay_mpc(core.INITIAL, 0., 0., 2., .04, 0., [-1., 1.], "endpoint_euler")
        self.assertTrue(result["fallback"])
        self.assertEqual(result["torque"], 0.)
        self.assertEqual(result["mathematical_prediction_calls"], 9)

    def test_unknown_integration_and_coefficient_dimension_are_rejected(self):
        with self.assertRaises(ValueError):
            core.predict(core.INITIAL, 0., 0., 0., .5, "unknown")
        with self.assertRaises(ValueError):
            core.predict(core.INITIAL[:-1], 0., 0., 0., .5, "endpoint_euler")

    def test_factorial_contrasts_keep_both_main_effects_and_interaction(self):
        matrix = {("nominal", "endpoint_euler"): 4., ("nominal", "trapezoid"): 3.,
                  ("learned", "endpoint_euler"): 2., ("learned", "trapezoid"): 1.5}
        effects = core.factorial_effects(matrix)
        self.assertEqual(effects["learned_minus_nominal"], {"endpoint_euler": -2., "trapezoid": -1.5})
        self.assertEqual(effects["trapezoid_minus_endpoint"], {"nominal": -1., "learned": -.5})
        self.assertEqual(effects["difference_of_differences"], .5)


if __name__ == "__main__":
    unittest.main()


def native(q=0., v=0.):
    return {"joint_position": [q]+[0.]*7, "joint_velocity": [v]+[0.]*7,
            "imu_gyro": [0.]*3, "imu_acceleration": [0.]*3,
            "actuator_torque": [0.]*8, "previous_command": [0.]*8}


def transition(index):
    return {"step_index": index, "phase": "control", "requested_torque": [0.]*8,
            "observation_before": native(), "observation_after": native(),
            "diagnostics": {"executed_substeps": 10, "terminated": False, "time": (index+1)*.02}}


@pytest.mark.parametrize("steps,horizon,expected", [(200,1,200),(200,5,196),(200,15,186),(200,50,151),
                                                    (100,1,100),(100,5,96),(100,15,86),(100,50,51),
                                                    (300,1,300),(300,5,296),(300,15,286),(300,50,251)])
def test_horizon_denominators_use_all_overlapping_legal_windows(steps,horizon,expected):
    indexed = {i:transition(i) for i in range(100,100+steps)}
    result = core.window_denominators(indexed,steps,horizon)
    assert result["expected_windows_from_planned_active_duration"] == expected
    assert result["valid_physical_windows"] == expected
    assert result["excluded_windows"] == 0


@pytest.mark.parametrize("fault,reason", [("missing","missing_control_row"),("partial","partial_physics_interval"),
    ("phase","crossed_phase_boundary"),("native","native_state_discontinuity"),
    ("time","time_discontinuity"),("terminal","continued_after_termination")])
def test_windows_do_not_cross_faults_or_replace_missing_states(fault,reason):
    indexed = {100:transition(100),101:transition(101)}
    if fault == "missing":
        del indexed[101]
    elif fault == "partial":
        indexed[101]["diagnostics"]["executed_substeps"] = 3
    elif fault == "phase":
        indexed[101]["phase"] = "prediction"
    elif fault == "native":
        indexed[101]["observation_before"] = native(.1)
    elif fault == "time":
        indexed[101]["diagnostics"]["time"] += .1
    else:
        indexed[100]["diagnostics"]["terminated"] = True
    assert core.valid_window(indexed,100,2)[1] == reason


def gate_fixture(euler=(1.,1.,1.),trapezoid=(.9,.9,.9),effort=1.):
    return [{"seed":seed,"evaluations":{
        "learned_euler_mpc":{"eligible":True,"actual_effort_complete":True,"tracking_rmse_rad":euler[seed],
            "control_effort":{"actual_absolute_nm_s":1.,"actual_squared_nm2_s":1.}},
        "learned_trapezoid_mpc":{"eligible":True,"actual_effort_complete":True,"tracking_rmse_rad":trapezoid[seed],
            "control_effort":{"actual_absolute_nm_s":effort,"actual_squared_nm2_s":effort}}}}
        for seed in (0,1,2)]


def test_adoption_uses_mean_raw_rmse_not_mean_per_seed_percentages():
    result = core.adoption_gate(gate_fixture(euler=(1.,10.,1.),trapezoid=(.9,9.9,.9)))
    assert result["evaluated"]
    assert result["tracking_mean_improvement"] == pytest.approx(.025)
    assert not result["passed"]


def test_any_seed_worse_by_tiny_real_amount_fails_no_approximate_tie():
    result = core.adoption_gate(gate_fixture(trapezoid=(1.+1e-14,.8,.8)))
    assert result["tracking_mean_improvement"] > .05
    assert not result["passed"]


def test_both_actual_efforts_must_obey_five_percent_bound():
    assert core.adoption_gate(gate_fixture(effort=1.05))["passed"]
    rows = gate_fixture()
    rows[0]["evaluations"]["learned_trapezoid_mpc"]["control_effort"]["actual_squared_nm2_s"] = 1.151
    result = core.adoption_gate(rows)
    assert result["actual_effort_gates"]["actual_absolute_nm_s"]["passed"]
    assert not result["actual_effort_gates"]["actual_squared_nm2_s"]["passed"]
    assert not result["passed"]


@pytest.mark.parametrize("fault",["missing_seed","duplicate_seed","incomplete","missing_effort","invalid_effort"])
def test_missing_or_invalid_pairs_never_pass_adoption(fault):
    rows = gate_fixture()
    if fault == "missing_seed":
        rows.pop()
    elif fault == "duplicate_seed":
        rows[2]["seed"] = 0
    elif fault == "incomplete":
        rows[1]["evaluations"]["learned_trapezoid_mpc"]["eligible"] = False
    elif fault == "missing_effort":
        rows[1]["evaluations"]["learned_trapezoid_mpc"]["actual_effort_complete"] = False
    else:
        rows[1]["evaluations"]["learned_trapezoid_mpc"]["control_effort"]["actual_absolute_nm_s"] = -1.
    assert not core.adoption_gate(rows)["passed"]


def test_zero_effort_reference_is_not_divided_or_hidden():
    rows = gate_fixture()
    for row in rows:
        for group in row["evaluations"].values():
            group["control_effort"] = {"actual_absolute_nm_s":0.,"actual_squared_nm2_s":0.}
    assert core.adoption_gate(rows)["passed"]
    rows[0]["evaluations"]["learned_trapezoid_mpc"]["control_effort"]["actual_absolute_nm_s"] = .1
    result = core.adoption_gate(rows)
    assert result["actual_effort_gates"]["actual_absolute_nm_s"]["relative_increase"] is None
    assert not result["passed"]


def test_output_guard_protects_archive_reference_and_existing_report(tmp_path):
    archive, reference = tmp_path/"archive", tmp_path/"reference"
    for target in (archive/"report.json",reference/"report.json"):
        with pytest.raises(ValueError,match="outside"):
            core.validate_output_path(target,[archive,reference])
    output = tmp_path/"report.json"
    output.write_text("preserve",encoding="utf-8")
    with pytest.raises(ValueError,match="overwrite"):
        core.validate_output_path(output,[archive,reference])
    assert output.read_text() == "preserve"


def test_cli_rejects_holdout_before_trace_or_output_access(tmp_path):
    archive = tmp_path/"holdout"
    archive.mkdir()
    (archive/"metadata.json").write_text(json.dumps({"split":"holdout","seeds":[20,21,22],"pose":"supine","joint_index":0}),encoding="utf-8")
    output = tmp_path/"report.json"
    process = subprocess.run([sys.executable,str(SCRIPT),str(archive),"--output",str(output)],capture_output=True,text=True)
    assert process.returncode == 2
    assert "development" in process.stderr
    assert not output.exists()


def partial_archive(path):
    """Synthetic interrupted plan with one legal three-substep prefix stop."""
    path.mkdir()
    plans = core.planned_matrix()
    phases = ("prefix","calibration","prediction","control")
    episodes = [{**p,"status":"blocked","reason":{"type":"ArchiveAborted"},"collector_exception":None,
        "control_calls_attempted":0,"control_steps":0,"physics_steps":0,
        "phase_budgets":{phase:{"control_calls_attempted":0,"control_steps":0,"physics_steps":0} for phase in phases}}
        for p in plans]
    episodes[0].update(status="terminated",reason="injected_partial_prefix_stop",control_calls_attempted=1,control_steps=1,
                       physics_steps=3,unreturned_physics_steps=0,risk_telemetry_complete=True,
                       environment_fingerprint_before="fixed",environment_fingerprint_after="fixed")
    episodes[0]["phase_budgets"]["prefix"] = {"control_calls_attempted":1,"control_steps":1,"physics_steps":3}
    observation = native()
    diagnostics = {"executed_substeps":3,"step_id":1,"physics_steps":3,"time":.006,"terminated":True,
        "reason":"injected_partial_prefix_stop","requested_torque":[0.]*8,"accepted_torque":[0.]*8,
        "applied_torque":[0.]*8,"applied_torque_history":[[0.]*8 for _ in range(3)],"guarded_substeps":0,
        "substep_ground_normal_forces":[0.]*3,"substep_kinetic_energies":[0.]*3,
        "substep_minimum_contact_distances":[0.]*3,"peak_substep_ground_normal_force":0.,"ground_normal_impulse_ns":0.,
        "peak_substep_kinetic_energy":0.,"minimum_substep_contact_distance":0.}
    row = {"trial_id":"seed0_calibration","seed":0,"kind":"calibration","model_scope":"shared","integration":None,
        "step_index":0,"phase":"prefix","target_q":None,"requested_torque":[0.]*8,
        "observation_before":observation,"observation_after":observation,"diagnostics":diagnostics,
        "predicted_next_qv":{},"model_update":None,"planner_decision":None,
        "qpos":[0.,0.,.5,1.,0.,0.,0.]+[0.]*8,"qvel":[0.]*14}
    effort = {"requested_absolute_nm_s":0.,"requested_squared_nm2_s":0.,"actual_absolute_nm_s":0.,"actual_squared_nm2_s":0.}
    evaluations = {kind:{"completed":False,"status":"blocked","reason":{"type":"DependencyBlocked"}} for kind in core.KINDS}
    evaluations["calibration"] = {"completed":False,"tracking_rmse_rad":None,"velocity_prediction_rmse":{"frozen":None,"learned":None},
        "position_prediction_rmse":{"frozen":None,"learned":None},"metric_control_step_count":0,"saturated_control_steps":0,
        "control_effort":effort,"missing_control_effort_substeps":0,"actual_effort_complete":True,"actual_effort_is_lower_bound":False,
        "actual_control_effort_substeps":0,"mathematical_prediction_calls":0,"planner_fallbacks":0,"planner_decision_count":0,
        "planner_attempt_count":0,"failed_planner_attempts":0,"mathematical_prediction_calls_complete":True,
        "mathematical_prediction_calls_is_lower_bound":False,"controller_seconds_total":0.}
    results = [{"seed":0,"reference_q":None,"initial_model":None,"learned_model":None,"calibration_updates":0,
                "calibration_completed":False,"evaluations":evaluations}]
    sources = {name:(core.ROOT/name).read_bytes() for name in core.REQUIRED_SOURCES}
    metadata = {"split":"development","seeds":[0,1,2],"pose":"supine","joint_index":0,
        "source_commit":"1"*40,"source_status":"","source_dirty":False,
        "source_sha256":{name:hashlib.sha256(blob).hexdigest() for name,blob in sources.items()},
        "protocol":{"path":core.PROTOCOL,"sha256":hashlib.sha256(sources[core.PROTOCOL]).hexdigest()},
        "environment_config":core.ENVIRONMENT,"variant":"hinge","integrations":list(core.INTEGRATIONS),
        "calibration_block_amplitudes_nm":core.CALIBRATION_AMPLITUDES,"gpu":None,"prefix_steps":100,"calibration_steps":300,
        "prediction_steps":100,"control_steps_per_trial":200,"teacher_calls":0,"external_demonstration_samples":0,
        "policy_parameter_updates":0,"planned_episodes":plans,"planned_episode_count":18,"maximum_control_steps":5400,
        "control_calls_attempted":1,"control_steps":1,"physics_steps":3,"model_updates":0,"completed_trials":0,
        "terminated_trials":1,"exception_trials":0,"blocked_trials":17,"unprocessed_trials":0,
        "failed_trials":1,"skipped_trials":17,"all_trials_successful":False,"complete":False,"archive_status":"interrupted"}
    for name,value in (("metadata.json",metadata),("episodes.json",episodes),("seed_results.json",results)):
        (path/name).write_text(json.dumps(value),encoding="utf-8")
    with gzip.open(path/"trace.jsonl.gz","wt",encoding="utf-8") as stream:
        stream.write(json.dumps(row)+"\n")
    with zipfile.ZipFile(path/"source_snapshot.zip","w") as source:
        for name,blob in sources.items():
            source.writestr(name,blob)
    (path/"manifest.json").write_text(json.dumps({p.name:core.file_hash(p) for p in path.iterdir()}),encoding="utf-8")
    return path


def test_legal_partial_stop_keeps_actual_budget_and_fails_only_adoption(tmp_path):
    path = partial_archive(tmp_path/"partial")
    report = core.audit(path,git_root=None)
    assert report["failed"] == 0,report["violations"]
    assert report["archive"]["budget"] == {"control_calls_attempted":1,"control_steps":1,"physics_steps":3,"model_updates":0}
    assert not report["development_adoption_gate"]["passed"]
    assert not report["development_adoption_gate"]["validated_pass"]


def test_manifest_tampering_is_rejected_without_physics_or_fitting(tmp_path):
    path = partial_archive(tmp_path/"partial")
    with (path/"episodes.json").open("a",encoding="utf-8") as stream:
        stream.write(" ")
    report = core.audit(path,git_root=None)
    assert report["failed"] > 0
    assert any(v["check"] == "manifest_hash" for v in report["violations"])
    assert not report["development_adoption_gate"]["validated_pass"]


def test_full_terminal_interval_is_allowed_only_as_window_final_endpoint():
    indexed = {100:transition(100),101:transition(101),102:transition(102)}
    indexed[101]["diagnostics"]["terminated"] = True
    assert core.valid_window(indexed,100,2)[1] is None
    assert core.valid_window(indexed,100,3)[1] == "continued_after_termination"
    assert core.valid_window(indexed,101,2)[1] == "continued_after_termination"
    denominator = core.window_denominators(indexed,3,2)
    assert denominator["valid_physical_windows"] == 1
    assert denominator["valid_windows_ending_in_termination"] == 1


def test_partial_terminal_interval_is_excluded_even_when_it_ends_window():
    indexed = {100:transition(100),101:transition(101)}
    indexed[101]["diagnostics"].update(terminated=True,executed_substeps=3)
    assert core.valid_window(indexed,100,2)[1] == "partial_physics_interval"
    denominator = core.window_denominators(indexed,2,2)
    assert denominator["valid_physical_windows"] == 0
    assert denominator["valid_windows_ending_in_termination"] == 0


@pytest.mark.parametrize("measured",[0,10])
def test_post_return_failure_recovers_paid_requests_without_claiming_missing_actual_history(measured):
    effort = {"requested_absolute_nm_s":0.,"requested_squared_nm2_s":0.,"actual_absolute_nm_s":0.,"actual_squared_nm2_s":0.}
    recorded = {"requested_absolute_nm_s":.01,"requested_squared_nm2_s":.005,
                "actual_absolute_nm_s":.006 if measured else 0.,"actual_squared_nm2_s":.0018 if measured else 0.}
    ev = {"control_effort":recorded,"actual_control_effort_substeps":measured,
          "missing_control_effort_substeps":10-measured,"actual_effort_complete":measured==10,
          "actual_effort_is_lower_bound":measured<10}
    exceptions = [{"phase":"control","requested_torque":[.5]+[0.]*7,"unreturned_physics_steps":0}]
    checks = core.Checks()
    result = core.reconcile_effort(ev,effort,10,0,exceptions,checks,"postreturn")
    assert checks.failed == 0,checks.violations
    assert result["requested_effort_reconstruction_complete"]
    assert result["independent_effort"]["requested_absolute_nm_s"] == .01
    assert result["independent_effort"]["requested_squared_nm2_s"] == .005
    assert result["independent_effort"]["actual_absolute_nm_s"] == 0.
    assert not result["actual_effort_reconstruction_complete"]
    assert result["unreconstructed_actual_effort_substeps"] == 10


def test_unverifiable_request_cost_remains_unknown_instead_of_zero_cost_success():
    effort = {"requested_absolute_nm_s":0.,"requested_squared_nm2_s":0.,"actual_absolute_nm_s":0.,"actual_squared_nm2_s":0.}
    ev = {"control_effort":{"requested_absolute_nm_s":.01,"requested_squared_nm2_s":.005,
                             "actual_absolute_nm_s":0.,"actual_squared_nm2_s":0.},
          "actual_control_effort_substeps":0,"missing_control_effort_substeps":10,
          "actual_effort_complete":False,"actual_effort_is_lower_bound":True}
    result = core.reconcile_effort(ev,effort,10,0,[],core.Checks(),"unrecoverable")
    assert not result["requested_effort_reconstruction_complete"]
    assert not result["actual_effort_reconstruction_complete"]


@pytest.mark.parametrize("kind,phase,cap",[("calibration","prefix",100),("calibration","calibration",300),
    ("prediction","prediction",100),("learned_euler_mpc","control",200),
    ("prediction","calibration",0)])
def test_failed_trial_cannot_exceed_frozen_phase_budget(kind,phase,cap):
    plan = next(p for p in core.planned_matrix() if p["seed"]==0 and p["kind"]==kind)
    budget = {name:{"control_calls_attempted":0,"control_steps":0,"physics_steps":0}
              for name in ("prefix","calibration","prediction","control")}
    budget[phase] = {"control_calls_attempted":cap+1,"control_steps":cap+1,"physics_steps":10*(cap+1)}
    ep = {**plan,"status":"exception","phase_budgets":budget,
          "control_calls_attempted":cap+1,"control_steps":cap+1,"physics_steps":10*(cap+1)}
    checks = core.Checks()
    core.verify_budget_bounds(ep,checks,"overbudget")
    assert any(v["check"] == "frozen_phase_budget_cap" for v in checks.violations)


def test_failed_trial_cannot_exceed_declared_trial_total():
    plan = core.planned_matrix()[0]
    ep = {**plan,"status":"exception","phase_budgets":{
        "prefix":{"control_calls_attempted":100,"control_steps":100,"physics_steps":1000},
        "calibration":{"control_calls_attempted":300,"control_steps":300,"physics_steps":3000},
        "prediction":{"control_calls_attempted":0,"control_steps":0,"physics_steps":0},
        "control":{"control_calls_attempted":0,"control_steps":0,"physics_steps":0}},
        "control_calls_attempted":401,"control_steps":401,"physics_steps":4010}
    checks = core.Checks()
    core.verify_budget_bounds(ep,checks,"overbudget")
    assert any(v["check"] == "frozen_trial_budget_cap" for v in checks.violations)

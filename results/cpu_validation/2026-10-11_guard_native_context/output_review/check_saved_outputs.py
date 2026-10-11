"""One limited saved-output contract check; no scientific formula recomputation."""
from pathlib import Path
import hashlib
import itertools
import json
import time

ROOT = Path(__file__).parent
EXPECTED_HASHES = {
    "manifest.json": "4363934feadb964839ebfaeb902342262aeac70b428e10e3ce3bb17262875565",
    "run.json": "fc90269c3a72dfd6d7eb144b8907f57b6f38b1e171e55fb7b29c3c1b99e98540",
    "description.json": "26c90bbb0cf2c8197f3b5ecd5722a87a645c288810cb0ff895e4224c56a63413",
}
SEEDS = (0, 1, 2)
KINDS = ("cold11", "learned_sparse11", "PDselected", "zero")
PREDICTORS = ("cold11", "learned_sparse11")
CHANNELS = ("q", "v")
SEGMENTS = ("A", "B")
SCORES = ("body6", "gyro", "acc_delta")
checks = 0
failures = []
observed = {}


def check(condition, label, actual=None):
    global checks
    checks += 1
    if not condition:
        failures.append({"label": label, "actual": actual})


def same(actual, expected, label):
    check(actual == expected, label, {"actual": actual, "expected": expected} if actual != expected else None)


def nn(value, label):
    check(type(value) is int and value >= 0, label, value)


def false_science(value, label):
    same(value.get("evaluated"), False, label+":evaluated")
    same(value.get("passed"), False, label+":passed")


def check_counts(counts, label):
    keys = ("saved_active_records", "returned_endpoint_n", "complete_interval_n", "partial_interval_n",
            "exception_record_n", "unreturned_saved_record_n")
    for key in keys:
        nn(counts[key], label+":"+key)
    same(counts["complete_interval_n"]+counts["partial_interval_n"], counts["returned_endpoint_n"], label+":complete_plus_partial")
    same(counts["returned_endpoint_n"]+counts["unreturned_saved_record_n"], counts["saved_active_records"], label+":returned_plus_unreturned")
    check(counts["exception_record_n"] <= counts["saved_active_records"], label+":exception_subset")
    for score in SCORES:
        nn(counts["score_valid_n"][score], label+":score_valid:"+score)
        nn(counts["score_missing_n"][score], label+":score_missing:"+score)
        same(counts["score_valid_n"][score]+counts["score_missing_n"][score], counts["saved_active_records"], label+":score_denominator:"+score)
        same(sum(counts["score_missing_reasons"][score].values()), counts["score_missing_n"][score], label+":score_missing_reasons:"+score)
    denominators = counts["diagnostic_denominators"]
    denominator_keys = [(d["predictor"], d["axis"], d["error_channel"]) for d in denominators]
    same(set(denominator_keys), set(itertools.product(PREDICTORS, (0, 1), CHANNELS)), label+":diagnostic_keys")
    same(len(denominator_keys), 8, label+":diagnostic_no_duplicates")
    for d in denominators:
        nn(d["valid_error_n"], label+":valid_error")
        check(d["valid_error_n"] <= counts["complete_interval_n"], label+":error_subset_complete")
        for score in SCORES:
            paired = d["score_error_pair_n"][score]
            nn(paired, label+":paired")
            check(paired <= d["valid_error_n"] and paired <= counts["score_valid_n"][score], label+":pair_subsets")


started = time.perf_counter()
values, records = {}, []
for name in ("manifest.json", "run.json", "description.json"):
    blob = (ROOT/(name+".original")).read_bytes()
    digest = hashlib.sha256(blob).hexdigest()
    records.append({"path": str(ROOT/(name+".original")), "bytes": len(blob), "sha256": digest})
    same(digest, EXPECTED_HASHES[name], "snapshot_hash:"+name)
    values[name] = json.loads(blob)
read_hash_parse_wall = time.perf_counter()-started
m, r, d = (values[name] for name in ("manifest.json", "run.json", "description.json"))
for name in ("run.json", "description.json"):
    record = next(item for item in records if item["path"].endswith(name+".original"))
    same(m["files"][name]["bytes"], record["bytes"], "manifest_bytes:"+name)
    same(m["files"][name]["sha256"], record["sha256"], "manifest_sha:"+name)
same(m["output_integrity_reads"]["opens"], len(m["files"]), "manifest_integrity_opens")
same(m["output_integrity_reads"]["hash_operations"], len(m["files"]), "manifest_integrity_hash_ops")
same(m["output_integrity_reads"]["bytes"], sum(item["bytes"] for item in m["files"].values()), "manifest_integrity_saved_byte_sum")
same(m["source_cache_records"], r["source_records"], "source_cache_records_preserved")
same(m["status"], "completed", "manifest_status")
same(r["status"], "completed", "run_status")
for label, value in (("manifest", m), ("run", r), ("description", d)):
    false_science(value["scientific_adoption"], label+":science")
same(r["f_provenance"]["source_commit"], "734ab7dab53563327b7dc072378551d2045b68ac", "f_clean_commit")
same(r["f_provenance"]["source_sha256"], "15ffc878f918a7927b09c5ede14b6ac5b57b09bab43b4ff4342ac11a20cdff96", "f_source_sha")
same(r["f_provenance"]["source_dirty"], False, "f_source_clean")
same(r["f_provenance"]["binding_sha256"], "33fecbca2c02a8b38b29be521c1beeca9d1aede3cf260a233bcf0c7be5906140", "f_binding_saved_sha")
same(r["f_provenance"]["protocol"]["sha256"], "eecf6cdf71699d18a076229765d7246c265a9fb0ddc95b60ce875d15795caaf3", "f_protocol_saved_sha")
same(r["e_source_commit"], "dda82b1854d80483d0b16e0532bc414906e6a402", "e_commit_preserved")
for key in ("physical_queries", "model_predict_calls", "rls_updates", "policy_updates", "gain_updates", "gate_updates", "C_D_raw_reads"):
    same(r["descriptive_fee"][key], 0, "zero_new_work:"+key)
same(d["descriptive_fee"], r["descriptive_fee"], "description_run_fees_identical")
check("excludes" in r["timing_scope"], "main_timing_scope_explicit")
check("excludes final manifest" in m["final_record_timing"]["scope"], "final_timing_scope_explicit")

events = d["events"]
expected_trials = {(seed, kind) for seed in SEEDS for kind in KINDS}
same(len(events), 12, "event_count")
same({(e["seed"], e["kind"]) for e in events}, expected_trials, "event_cartesian_keys")
event_map = {}
for e in events:
    label = e["trial_id"]
    same(label, f"seed{e['seed']}_{e['kind']}", label+":trial_identity")
    event_map[label] = e
    check_counts(e["all_counts"], label+":all")
    learned = e["kind"] == "learned_sparse11"
    n = 104 if learned else 200
    same(e["all_counts"]["saved_active_records"], n, label+":saved_n")
    same(e["all_counts"]["complete_interval_n"], n, label+":all_complete")
    same(e["all_counts"]["partial_interval_n"], 0, label+":no_partial")
    same(e["all_counts"]["exception_record_n"], 0, label+":no_exception")
    same(e["source_status"], "terminated" if learned else "completed", label+":status")
    same(e["source_stop"], learned, label+":source_stop")
    same(e["declared_source_stop_flags_present"], learned, label+":stop_flag")
    same(e["stop_flags_in_exception"], False, label+":not_combined_exception")
    same(e["source_returned_unwritten_steps"], 0, label+":no_unwritten_return")
    same(e["source_returned_steps"], 100+n, label+":returned_prefix_plus_active")
    same(e["source_written_returned_steps"], 100+n, label+":written_prefix_plus_active")
    same(e["source_unreturned_physics_steps"], 0, label+":no_unreturned_physics")
    same(e["partial_interval_records"], [], label+":partial_records_empty")
    same(e["source_phase_budgets"]["prefix"], {"control_calls_attempted": 100, "control_steps": 100, "physics_steps": 1000}, label+":prefix_budget")
    same(e["source_phase_budgets"]["control"], {"control_calls_attempted": n, "control_steps": n, "physics_steps": 10*n}, label+":control_budget")
    if learned:
        same(e["terminal_returned_id"], f"{label}:203", label+":terminal_id")
        check_counts(e["tail20_counts"], label+":tail20")
        check_counts(e["earlier_counts"], label+":earlier")
        same(e["tail20_counts"]["returned_endpoint_n"], min(20, n), label+":tail_length")
        same(e["earlier_counts"]["returned_endpoint_n"], max(n-20, 0), label+":earlier_length")
        for key in ("saved_active_records", "returned_endpoint_n", "complete_interval_n", "partial_interval_n"):
            same(e["tail20_counts"][key]+e["earlier_counts"][key], e["all_counts"][key], label+":window_sum:"+key)
        check(e["stop_reason"] is not None, label+":stop_reason_present")
    else:
        same(e["tail20_counts"], None, label+":no_tail")
        same(e["earlier_counts"], None, label+":no_earlier")
        same(e["terminal_returned_id"], None, label+":no_terminal_stop")

groups = d["groups"]
expected_group_keys = set()
for seed, kind, axis, predictor, channel, segment in itertools.product(SEEDS, KINDS, (0, 1), PREDICTORS, CHANNELS, SEGMENTS):
    windows = ("all", "tail20", "earlier") if kind == "learned_sparse11" else ("all",)
    for window in windows:
        expected_group_keys.add((seed, kind, axis, predictor, channel, segment, window))
group_key = lambda g: (g["seed"], g["kind"], g["axis"], g["predictor"], g["error_channel"], g["target_segment"], g["window"])
same(len(groups), 288, "group_count")
same({group_key(g) for g in groups}, expected_group_keys, "conditional_cartesian_group_keys")
same(len({group_key(g) for g in groups}), len(groups), "group_unique_keys")
empty_groups = 0
stat_count = 0
for g in groups:
    label = repr(group_key(g))
    same(g["trial_id"], f"seed{g['seed']}_{g['kind']}", label+":trial_identity")
    counts = g["counts"]
    check_counts(counts, label)
    learned = g["kind"] == "learned_sparse11"
    if not learned:
        expected_n = 100
    else:
        expected_n = {("all", "A"): 100, ("all", "B"): 4, ("tail20", "A"): 16,
                      ("tail20", "B"): 4, ("earlier", "A"): 84, ("earlier", "B"): 0}[(g["window"], g["target_segment"])]
    same(counts["saved_active_records"], expected_n, label+":fixed_segment_window_n")
    same(counts["complete_interval_n"], expected_n, label+":complete_n")
    same(counts["partial_interval_n"], 0, label+":partial_zero")
    same(g["valid_error_n"]+g["complete_error_missing_n"], counts["complete_interval_n"], label+":error_denominator")
    if g["window"] == "all":
        same(g["planned_active_n"], 100, label+":planned_all")
        same(g["unobserved_planned_endpoint_n"], 100-expected_n, label+":unobserved")
    if expected_n == 0:
        empty_groups += 1
        check(bool(g["empty_window_reason"]), label+":empty_reason")
    else:
        same(g["empty_window_reason"], None, label+":nonempty_reason")
    selected_denom = next(item for item in counts["diagnostic_denominators"] if
        (item["predictor"], item["axis"], item["error_channel"]) == (g["predictor"], g["axis"], g["error_channel"]))
    same(selected_denom["valid_error_n"], g["valid_error_n"], label+":selected_error_denominator")
    same({s["score"] for s in g["statistics"]}, set(SCORES), label+":score_keys")
    same(len(g["statistics"]), 3, label+":score_no_duplicates")
    for s in g["statistics"]:
        stat_count += 1
        slabel = label+":"+s["score"]
        same(s["valid_error_n"], g["valid_error_n"], slabel+":valid_error")
        same(s["paired_n"]+s["score_missing_with_valid_error_n"], s["valid_error_n"], slabel+":paired_plus_missing")
        same(s["paired_n"], selected_denom["score_error_pair_n"][s["score"]], slabel+":paired_denominator")
        for key in ("score_description", "signed_error_description", "absolute_error_description", "pearson_signed", "pearson_absolute"):
            same(s[key]["n"], s["paired_n"], slabel+":"+key+":n")
        bins = s["fixed_bins"]
        same([(b["lower_inclusive"], b["upper_exclusive"]) for b in bins], [(0.0, 0.5), (0.5, 1.0), (1.0, None)], slabel+":fixed_bin_edges")
        same(sum(b["n"] for b in bins), s["paired_n"], slabel+":bin_n_sum")
        for b in bins:
            nn(b["n"], slabel+":bin_n")
            if s["paired_n"]:
                expected_fraction = b["n"]/s["paired_n"]
                same(b["fraction_of_valid_score_error_pairs"], expected_fraction, slabel+":bin_pair_fraction")
            else:
                same(b["fraction_of_valid_score_error_pairs"], None, slabel+":empty_pair_fraction")
            if b["n"] == 0:
                for key in ("signed_error_mean", "mean_absolute_error", "max_absolute_error"):
                    same(b[key], None, slabel+":empty_bin:"+key)
        if s["paired_n"] == 0:
            for key in ("pearson_signed", "pearson_absolute"):
                same(s[key]["r"], None, slabel+":empty_pearson_null")
                check(bool(s[key]["reason"]), slabel+":empty_pearson_reason")
            for key in ("score_description", "signed_error_description", "absolute_error_description"):
                for field in ("min", "max", "mean"):
                    same(s[key][field], None, slabel+":empty_description:"+key+":"+field)

quality = d["independent_input_quality_counts"]
same(len(quality), 24, "input_quality_count")
same({(q["seed"], q["kind"], q["target_segment"]) for q in quality}, set(itertools.product(SEEDS, KINDS, SEGMENTS)), "quality_cartesian_keys")
quality_saved_sum = 0
for q in quality:
    label = q["trial_id"]+":"+q["target_segment"]
    same(q["trial_id"], f"seed{q['seed']}_{q['kind']}", label+":quality_identity")
    expected_n = 4 if q["kind"] == "learned_sparse11" and q["target_segment"] == "B" else 100
    same(q["saved_active_records"], expected_n, label+":quality_saved_n")
    quality_saved_sum += q["saved_active_records"]
    nn(q["rows_with_any_quality_flag"], label+":quality_rows")
    check(q["rows_with_any_quality_flag"] <= q["saved_active_records"], label+":quality_subset")
    for flag, n in q["independent_flag_counts"].items():
        nn(n, label+":flag:"+flag)
        check(n <= q["saved_active_records"], label+":flag_subset")
    if not q["independent_flag_counts"]:
        same(q["rows_with_any_quality_flag"], 0, label+":no_flags_no_flagged_rows")
    check("independently" in q["count_semantics"], label+":independent_semantics")
same(quality_saved_sum, r["descriptive_fee"]["input_quality_rows_classified"], "quality_fee_row_sum")
same(quality_saved_sum, r["descriptive_fee"]["active_derived_records"], "active_fee_row_sum")
same(set(d["exception_notifications"]), set(event_map), "exception_notification_trial_keys")
same(sum(len(v) for v in d["exception_notifications"].values()), 0, "no_exception_notifications")

gates = r["original_e_gates"]
same(set(gates), {"control_hypothesis", "pd_reference", "matrix_complete", "c4_scientific_validation"}, "preserved_four_e_gates")
same(gates["matrix_complete"], False, "e_matrix_still_false")
for name, baseline, threshold in (("control_hypothesis", "cold11", 0.2), ("pd_reference", "PDselected", 0.05)):
    gate = gates[name]
    false_science(gate, "e_gate:"+name)
    same(gate["validated_pass"], False, "e_gate:"+name+":validated")
    same(gate["scientific_validation"], False, "e_gate:"+name+":scientific")
    same(gate["candidate"], "learned_sparse11", "e_gate:"+name+":candidate")
    same(gate["baseline"], baseline, "e_gate:"+name+":baseline")
    same(gate["joint_improvement_min"], threshold, "e_gate:"+name+":threshold")
    same(len(gate["rows"]), 3, "e_gate:"+name+":rows")
    same({row["seed"] for row in gate["rows"]}, set(SEEDS), "e_gate:"+name+":seeds")
    same(len(gate["axes"]), 2, "e_gate:"+name+":axes")
    same(set(gate["efforts"]), {"actual_absolute_nm_s", "actual_squared_nm2_s"}, "e_gate:"+name+":efforts")
    same(gate["complete_control_only"], True, "e_gate:"+name+":complete_only")
    for row in gate["rows"]:
        same(row["eligible"], False, "e_gate:"+name+":ineligible")
        same(len(row["baseline_axis_tracking"]), 2, "e_gate:"+name+":baseline_axis")
        same(len(row["candidate_axis_tracking"]), 2, "e_gate:"+name+":candidate_axis")
    for key in ("baseline_raw_mean_joint_rmse", "candidate_raw_mean_joint_rmse", "joint_mean_improvement", "worst_seed_joint_improvement"):
        same(gate[key], None, "e_gate:"+name+":not_ranked:"+key)
false_science(gates["c4_scientific_validation"], "e_c4_gate")
check("20-percent" in gates["c4_scientific_validation"]["reason"], "e_old_prediction_reason_retained")
budget = r["original_e_physics_budget"]
same(budget["control_calls_attempted"], 3312, "e_paid_control_attempts")
same(budget["control_steps"], 3312, "e_paid_control_steps")
same(budget["physics_steps"], 33120, "e_paid_substeps")
for key in ("model_updates", "policy_parameter_updates", "gain_updates", "gate_updates"):
    same(budget[key], 0, "e_update_budget:"+key)
same(sum(e["source_phase_budgets"][phase]["control_steps"] for e in events for phase in ("prefix", "control")), budget["control_steps"], "event_control_budget_sum")
same(sum(e["source_phase_budgets"][phase]["physics_steps"] for e in events for phase in ("prefix", "control")), budget["physics_steps"], "event_substep_budget_sum")

observed.update(group_count=len(groups), score_statistic_blocks=stat_count, event_count=len(events), input_quality_count=len(quality), empty_groups=empty_groups,
    saved_active_records=quality_saved_sum, partial_records=sum(e["all_counts"]["partial_interval_n"] for e in events), source_stop_events=sum(e["source_stop"] for e in events))
result = {"schema_version": 1, "kind": "first_limited_saved_output_contract_check", "checks": checks, "failures": failures, "failure_count": len(failures),
    "observed_saved_counts": observed, "input_records": records,
    "read_accounting": {"this_check_opens": 3, "this_check_bytes": sum(x["bytes"] for x in records), "prior_ingest_opens": 3, "prior_ingest_bytes": 3186453,
        "total_allowed_input_opens": 6, "total_allowed_input_bytes": sum(x["bytes"] for x in records)+3186453,
        "this_read_hash_parse_wall_seconds": read_hash_parse_wall, "prior_read_hash_parse_wall_seconds": 0.022004200145602226,
        "first_contract_check_wall_seconds": time.perf_counter()-started,
        "timing_scope": "current check includes snapshot reads/hash/parse and algebra/structure checks; excludes result serialization/write, stdout and human review"},
    "actual_content_hash_verified": ["run.json", "description.json"],
    "derived_content_hash_verified": False,
    "limitations": ["Only manifest/run/description F saved outputs read", "derived metadata byte count used only in manifest sum; derived bytes were not read or verified", "F provenance is checked against saved expected identity, not a new Git/source read", "Original E gate structure/known failure state checked; no E raw byte reread or metric recalculation", "No Pearson/norm/mean recomputation or diagnostic execution"],
    "new_physics": 0, "new_model_calls": 0, "new_scientific_statistical_computations": 0, "pearson_or_norm_recomputations": 0,
    "derived_trace_e_c_d_reads": 0, "scientific_adoption": {"evaluated": False, "passed": False}}
(ROOT/"FIRST_OUTPUT_CONTRACT_CHECK.json").write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
print(json.dumps(result, ensure_ascii=False))
raise SystemExit(bool(failures))

"""First-only CFD1 saved-contract delivery, with no model or score recomputation."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile


def identity(blob):
    return {"bytes": len(blob), "sha256": hashlib.sha256(blob).hexdigest()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repo, origin, output = args.repo.resolve(), args.input.resolve(), args.output.resolve()
    if output.exists():
        parser.error("first new output required")
    output.mkdir(parents=True)
    raw = output/"raw"
    raw.mkdir()
    payload = {}
    for path in sorted(origin.iterdir()):
        if not path.is_file():
            raise ValueError("unexpected non-file payload")
        blob = path.read_bytes()
        (raw/path.name).write_bytes(blob)
        payload[path.name] = identity(blob)
    run = json.loads((raw/"run.json").read_bytes())
    metrics = json.loads((raw/"metrics.json").read_bytes())
    models = json.loads((raw/"models.json").read_bytes())
    cold = json.loads((raw/"cold_transcribed.json").read_bytes())
    source = run["source"]["commit"]
    checks = []

    def seal():
        (output/"delivery_checks.json").write_text(json.dumps({"status": "passed" if checks and all(c["passed"] for c in checks) else "failed",
            "checks": checks, "fit_model_physics_RMSE_gate_recomputations": 0, "raw_prediction_decodes": 0,
            "scope": "saved fields, byte identity and source archive only"}, indent=2)+"\n", encoding="utf-8")

    def check(name, condition):
        checks.append({"name": name, "passed": bool(condition)})
        seal()

    complete = run["status"] == "completed"
    check("CFD1_clean_first_source_identity", run["experiment_id"] == "CFD1" and len(source) == 40 and run["source"]["clean_committed_bytes_verified"] is True)
    check("saved_metrics_exact_match", run["metrics"] == metrics)
    check("complete_or_preserved_first_failure", (complete and run["first_failure"] is None) or
          (run["status"] == "failed" and run["first_failure"] is not None))
    slots = run["complete_prediction_population"]
    check("all_2073_planned_slots_retained", len(slots) == 2073 and len({
        (s["seed"], s["model"], s["horizon"], s["origin_active_index"]) for s in slots}) == 2073)
    check("complete_population_or_failure", not complete or all(s["available"] and s["status"] == "completed" for s in slots))
    cost = run["cost"]
    check("full_saved_prediction_cost_or_failure", not complete or (cost["pair_prediction_returns"] == 67950 and
        cost["scalar_velocity_head_returns"] == 135900 and cost["seen_saved_scoring_scalar_label_uses"] == 8292 and
        cost["new_axis_RMSE_vector_computations"] == 42))
    check("full_saved_fit_cost_or_failure", not complete or (cost["OLS_returns"] == 3 and
        cost["fold_training_rows"] == 11994 and cost["fold_Y_scalar_uses"] == 23988 and cost["fitted_B_scalar_outputs"] == 24))
    check("three_rank4_excluded_trial_fits_or_failure", not complete or (len(run["fits"]) == 3 and all(
        fit["available"] and fit["rank"] == 4 and fit["observed_rows"] == 3998 and
        fit["seed"] not in fit["training_seeds"] and set(fit["training_seeds"]) == {8101, 8102, 8103}-{fit["seed"]}
        for fit in run["fits"])))
    check("no_new_physics_RLS_or_old_mathematics", all(run[k] == 0 for k in (
        "new_physics_control_calls", "new_physics_substeps", "RLS_updates", "new_physical_training_labels",
        "cold_model_prediction_calls", "cold_RMSE_recomputations", "old_gate_recomputations")))
    check("crossfit_seen_only_science_closed", run["seen_evaluation_development_only"] is True and run["heldout_validation"] is False and
        run["own_fold_evaluation_trial_fit_label_uses"] == 0 and run["global_cross_fold_evaluation_labels_are_training_labels_in_other_maps"] is True and
        all(run[k] is False for k in ("scientific_adoption", "old_free_root_C4_validation", "c4_scientific_validation",
            "c4_contact_scientific_validation", "c5_scientific_dependency_released", "control_candidate_opened")))
    check("unchanged_formal_physics_RLS_ledger", (run["prior_physics_control_calls"], run["prior_physics_substeps"],
        run["historical_RLS_scalar_updates"]) == (544345, 2824018, 125652))
    check("saved_model_fingerprint_binding", not complete or all(models[str(seed)]["CFDlearn"]["parameter_fingerprint"] ==
        run["model_fingerprints"][str(seed)]["CFDlearn"] for seed in (8101, 8102, 8103)))
    closure = ("scripts/develop_causal_difference_prediction.py", "docs/CAUSAL_DIFFERENCE_PREDICTION_PROTOCOL.md",
        "src/developmental_physics/causal_incremental_pair_model.py", "src/developmental_physics/instrumental_action_model.py",
        "src/developmental_physics/__init__.py")
    with zipfile.ZipFile(raw/"source.zip") as archive:
        check("exact_pure_source_closure", len(archive.namelist()) == 5 and set(archive.namelist()) == set(closure))
        for name in archive.namelist():
            committed = subprocess.run(["git", "show", source+":"+name], cwd=repo, capture_output=True, check=True).stdout
            check("source_archive_identity:"+name, archive.read(name) == committed)
    old_source = json.loads((repo/"results/cpu_validation/2026-10-12_causal_incremental_prediction/raw/run.json").read_bytes())
    for seed in (8101, 8102, 8103):
        old_scores = next(s for s in old_source["seed_results"] if s["seed"] == seed)["prediction_scores"]["horizons"]
        check("same_population_cold_transcription:"+str(seed), all(cold[str(seed)]["horizons"][str(h)][key] ==
            old_scores[str(h)]["models"]["CFcold"][key] for h in (1, 2, 5, 10, 20, 50, 150)
            for key in ("q_rmse_axis_rad", "v_rmse_axis_rad_s")))
    (output/"delivery_script.py").write_bytes(Path(__file__).read_bytes())
    (output/"delivery_manifest.json").write_text(json.dumps({"source_commit": source, "payload": payload,
        "delivery_script": identity(Path(__file__).read_bytes()), "checks": len(checks),
        "fit_model_physics_RMSE_gate_recomputations": 0, "raw_prediction_decodes": 0,
        "unmeasured_IO_internal_work": "unknown_not_zero"}, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"delivery": str(output), "checks": len(checks), "failed": [c for c in checks if not c["passed"]]}))
    return int(any(not c["passed"] for c in checks))


if __name__ == "__main__":
    raise SystemExit(main())

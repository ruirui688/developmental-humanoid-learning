"""One CF1 payload delivery and saved-contract check, without model mathematics."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import zipfile


def identity(blob):
    return {"bytes": len(blob), "sha256": hashlib.sha256(blob).hexdigest()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    args = parser.parse_args()
    repo, origin, output = args.repo.resolve(), args.input.resolve(), args.output.resolve()
    if output.exists():
        parser.error("first new output required")
    output.mkdir(parents=True)
    raw = output / "raw"
    raw.mkdir()
    payload = {}
    for path in sorted(origin.iterdir()):
        if not path.is_file():
            raise ValueError("unexpected non-file payload")
        blob = path.read_bytes()
        (raw / path.name).write_bytes(blob)
        payload[path.name] = identity(blob)
    run = json.loads((raw / "run.json").read_bytes())
    metrics = json.loads((raw / "metrics.json").read_bytes())
    models = json.loads((raw / "models.json").read_bytes())
    old = json.loads((raw / "old_scores_transcribed.json").read_bytes())
    checks = []
    checkpath = output / "delivery_checks.json"

    def seal():
        checkpath.write_text(json.dumps({"status": "passed" if checks and all(c["passed"] for c in checks) else "failed",
            "checks": checks, "model_calls": 0, "fit_calls": 0, "physics_calls": 0,
            "RMSE_or_gate_recomputations": 0, "raw_prediction_decodes": 0,
            "scope": "saved fields, byte identity and source archive only"}, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")

    def check(name, condition):
        checks.append({"name": name, "passed": bool(condition)})
        seal()

    check("CF1_identity_and_clean_first_source", run["experiment_id"] == "CF1" and
        run["source"]["commit"] == args.source_commit and run["source"]["clean_committed_bytes_verified"] is True)
    check("saved_metrics_exact_match", run["metrics"] == metrics)
    check("complete_or_preserved_first_failure", (run["status"] == "completed" and run["first_failure"] is None) or
          (run["status"] == "failed" and run["first_failure"] is not None))
    slots = run["complete_prediction_population"]
    check("all_4146_planned_slots_retained", len(slots) == 4146 and len({
        (s["seed"], s["model"], s["horizon"], s["origin_active_index"]) for s in slots}) == 4146)
    check("both_models_full_saved_population_or_failure", run["status"] != "completed" or
        all(s["available"] and s["status"] == "completed" for s in slots))
    cost = run["cost"]
    check("complete_saved_cost_or_failure", run["status"] != "completed" or
        (cost["pair_prediction_returns"] == 135900 and cost["scalar_velocity_head_returns"] == 271800 and
         cost["saved_native_selection_returns"] == 9000 and cost["new_axis_RMSE_vector_computations"] == 84))
    check("no_new_physics_fit_RLS_or_old_mathematics", all(run[k] == 0 for k in (
        "new_physics_control_calls", "new_physics_substeps", "fit_calls", "OLS_calls", "RLS_updates",
        "new_training_scalar_labels", "evaluation_fit_label_uses", "old_model_prediction_calls", "old_fit_RMSE_gate_recomputations")))
    check("seen_only_and_all_science_flags_closed", run["seen_evaluation_development_only"] is True and
        run["heldout_validation"] is False and all(run[k] is False for k in (
        "scientific_adoption", "old_free_root_C4_validation", "c4_scientific_validation",
        "c4_contact_scientific_validation", "c5_scientific_dependency_released", "control_candidate_opened")))
    check("unchanged_formal_physics_and_RLS_ledger", (run["prior_physics_control_calls"],
        run["prior_physics_substeps"], run["historical_RLS_scalar_updates"]) == (544345, 2824018, 125652))
    check("complete_saved_model_fingerprint_binding", run["status"] != "completed" or all(
        models[str(seed)][name]["parameter_fingerprint"] == run["model_fingerprints"][str(seed)][name]
        for seed in (8101, 8102, 8103) for name in ("CFcold", "CFlearn")))
    check("saved_prediction_stream_population", run["status"] != "completed" or run["streams"]["predictions"]["records"] == 4146)
    with zipfile.ZipFile(raw / "source.zip") as archive:
        names = archive.namelist()
        closure = ["scripts/develop_causal_incremental_prediction.py", "docs/CAUSAL_INCREMENTAL_PREDICTION_PROTOCOL.md",
            "src/developmental_physics/causal_incremental_pair_model.py", "src/developmental_physics/instrumental_action_model.py",
            "src/developmental_physics/__init__.py"]
        check("exact_pure_source_closure", len(names) == 5 and set(names) == set(closure))
        for name in names:
            committed = subprocess.run(["git", "show", args.source_commit+":"+name], cwd=repo,
                capture_output=True, check=True).stdout
            check("source_archive_identity:"+name, archive.read(name) == committed)
    old_source = json.loads((repo / "results/cpu_validation/2026-10-12_near_reference_identification/raw/run.json").read_bytes())
    check("old_metrics_transcribed_without_recompute", old["old_metrics_transcribed_not_recomputed"] == old_source["metrics"])
    for seed in (8101, 8102, 8103):
        saved = next(s for s in old_source["seed_results"] if s["seed"] == seed)["prediction_scores"]
        check("old_score_transcription:"+str(seed), old[str(seed)] == saved)
    (output / "delivery_manifest.json").write_text(json.dumps({"source_commit": args.source_commit,
        "input_directory": str(origin), "payload": payload, "delivery_script": identity(Path(__file__).read_bytes()),
        "old_transcribed_structure": list(old) if isinstance(old, dict) else "list",
        "old_source_experiment": old_source["experiment_id"], "new_physics": 0,
        "fit_model_RMSE_gate_recomputations": 0, "unmeasured_IO_internal_work": "unknown_not_zero"}, indent=2)+"\n", encoding="utf-8")
    shutil.copyfile(__file__, output / "delivery_script.py")
    seal()
    print(json.dumps({"delivery": str(output), "checks": len(checks), "failed": [c for c in checks if not c["passed"]]}))
    return int(any(not c["passed"] for c in checks))


if __name__ == "__main__":
    raise SystemExit(main())

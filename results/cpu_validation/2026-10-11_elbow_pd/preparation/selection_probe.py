"""Four synthetic C3-selector checks; no trajectories, simulator or fitting."""
import importlib.util
import json
from pathlib import Path
import time

ROOT=Path(__file__).resolve().parents[2]
SPEC=importlib.util.spec_from_file_location("readonly_c3_selector",ROOT/"scripts/audit_feedback_development.py")
BASE=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BASE)


def fake_trials(metric=.05,effort=.5):
    return [{"trial_id":f"synthetic_seed{seed}_candidate{candidate}",
             "seed":seed,"candidate":candidate,"eligible":True,
             "tracking_rmse_rad":metric,"requested_squared_effort_nm2s":effort}
            for candidate in range(9) for seed in (0,1,2)]


started=time.perf_counter()
cpu_started=time.process_time()
# Eligibility here is synthetic input; a real adapter must independently
# recompute all study/env/partial/schema conditions from original native rows.
rows=fake_trials()
for row in rows:
    if row["candidate"] == 8:
        row["tracking_rmse_rad"] = .001
        if row["seed"] == 1:
            row["eligible"] = False
    if row["candidate"] == 7:
        row["tracking_rmse_rad"] = .02
assert BASE.select_candidates(rows)["selected"]["candidate"] == 7

rows=fake_trials()
for row in rows:
    if row["candidate"] in (1,2,3):
        row["requested_squared_effort_nm2s"] = .3
assert BASE.select_candidates(rows)["selected"]["candidate"] == 1

rows=fake_trials()
for row in rows:
    if row["candidate"] == 1:
        row["tracking_rmse_rad"] = .05-2e-15
        row["requested_squared_effort_nm2s"] = 10.
assert BASE.select_candidates(rows)["selected"]["candidate"] == 1

rows=fake_trials()
for row in rows:
    row["eligible"] = False
selection=BASE.select_candidates(rows)
assert selection["selected"] is None and not selection["selection_success"]

print(json.dumps({"synthetic_cases":4,"passed":4,"physical_steps":0,
                  "rls_updates":0,"heldout_reads":0,"wall_seconds":time.perf_counter()-started,
                  "cpu_seconds":time.process_time()-cpu_started,
                  "boundary":"Selector tests only; no new collector/auditor or scientific gate result"},indent=2))

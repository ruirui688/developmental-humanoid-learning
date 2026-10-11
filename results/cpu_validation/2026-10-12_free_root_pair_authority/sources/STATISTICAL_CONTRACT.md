# FR2 saved control-authority description

This candidate is a descriptive projection of the new FR2 control archive. It is
prepared after the parent reported completion of FR2; its author has not opened
FR2 raw files, model parameters, or result reports. It is not a scientific gate
or a new control candidate. Its first execution remains parent-owned.

```powershell
python external/fr2_authority_candidate/describe_fr2_authority_once.py --raw <new_FR2_raw> --output <fresh_report.json>
```

The program uses Python standard-library modules only. It requires a fresh output
path, writes one JSON report, preserves a caught failure and the partial matrix,
and never retries. It does not import the project, NumPy, a model, or a simulator.

## Fixed population and input budget

- Seeds: 7901, 7902, 7903; methods: cold, learned, pd, zero. All 12 trial rows remain
  in the report, including missing, stopped, or unattempted trials.
- Active phases: A = indices 0–999, B = 1000–1999, full = 0–1999. Each trial has at
  most 1,000 prefix rows. Prefix data only contributes its row count.
- Inputs: `manifest.json`, `run.json`, `trace.jsonl.gz` from the new FR2 directory,
  one explicit read attempt per file, in that order. Manifest binds run/trace
  bytes and SHA256. The compressed trace is held in memory and decoded in one
  forward pass. No second raw pass or other archive file is permitted.
- Caps: 36,000 trace rows, 1,200 macro decisions, 97,200 candidate records;
  at most 81 candidate records per returned decision. Active indices must be
  unique and in 0–1999. Macro decisions occur only on model-method indices
  divisible by 10. These checks do not replace the parent's formal archive audit.
- File read attempts, successful reads, successful bytes, encountered trace
  rows, macro decisions and candidate records are reported. An I/O exception
  can have unknown partial bytes; failed reads are not counted as zero bytes.

The manifest/run identity must be FR2/control, their status must agree, and all
five scientific flags must remain false. This checks saved metadata; the program
does not recompute a scientific decision. `run.json` is the control summary and
fingerprint file, not `models.json`.

## Statistics and denominators

The saved whole-2,000 `control_origin_domain.q2/v2` summaries are transcribed
directly from `run.json`. No bounds are recovered and no A/B domain summary is
recomputed. A saved axis box is descriptive coverage, not joint, contact, or
dynamic validity.

Every A/B/full block reports planned and observed origins, unknown/unattempted
origins, native endpoint counts, and the saved confirmed-substep count. These are
transcriptions and counts, not an effort or safety score. Missing fields remain
`null`; absent PD requests on fallback rows are counted as missing and never
replaced by zero. Fallback is inapplicable (`null`) for pd/zero. Zero has no saved
PD statistic.

PD and final requested-torque saturation means exact saved `abs(value) == 0.5`
per axis. Counts have a known-origin denominator and expose missing observed
origins. A fraction of the full planned phase is emitted only if the saved whole
trial is complete, the projection has no caught failure, and every planned phase
origin and request pair is known. Known-subset fractions do not authorize ranking
incomplete trials. Missing or failed-projection completeness remains `null`.

For cold/learned nonfallback origins with all three saved pairs available, let
`p` be the saved clipped public PD request, `delta` the saved held residual, and
`u` the saved final request. Report mean/max `abs(u-p)`, mean
`abs((p+delta)-u)`, and direction counts. The common denominator is the count of
known nonfallback origins; missing nonfallback fields and unknown fallback states
are exposed separately. Direction counts distinguish zero residual, nonzero
residual with zero effect, effect with/against residual and PD, nonzero effect at
zero PD, and a nonzero final request opposing nonzero PD. No PD is replayed.

Macro summaries use only saved feasible counts, fallback flags, selected
residuals, candidate `torque` pairs, feasible flags and original rejection reason
strings. Planned decision/candidate denominators remain fixed at 100/8,100 per
phase or 200/16,200 per full trial for each model method. Returned, unknown, and
unreturned/unattempted decisions are explicit. Unique first-request counts enter
the histogram only when all 81 saved candidate first-request pairs are known;
selected residual zero/boundary counts use saved `0`/`abs(value) == 0.125`.
Matching first requests do not establish equality of later requests or whole
candidate paths: public PD is recomputed along each forecast trajectory.

## Interpretation and exclusions

Stopped and incomplete trajectories remain descriptive and cannot be ranked.
Request clipping, feasible counts, fallback, and domain co-occurrence do not
identify a cause of the model contribution result. No correlation supports a
new grid, gain, weight, sensor, feature, or exploration choice by itself.

Forbidden inputs are `models.json`, prediction files, journals, source ZIPs,
FR1 trajectories, and old archives. Forbidden computations include model
restoration/prediction, PD replay, fitting, physics, RMSE, effort, contact metrics,
scientific gates, candidate-path reconstruction, CPU early pruning, and tuning.
All five scientific flags retain their saved values; no C4/C5 dependency is
released. Preparation consists only of source review, one AST parse, hashes and
this contract. There are no candidate executions, new tests, or production edits.

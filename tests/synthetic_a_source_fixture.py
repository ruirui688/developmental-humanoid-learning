"""Artificial A-format archive for binding tests; zero physics and fitting.

Records and auditor verdicts are handwritten fixture assertions, never outcomes
of independent production audits. The fake archive is built only at caller's
temporary repository root and is explicitly marked synthetic everywhere.
"""
from copy import deepcopy
import gzip
import hashlib
import io
import json
from pathlib import Path
import zipfile

try:
    from developmental_physics import guard_pair_source_binding as binding
except ImportError:
    import guard_pair_source_binding as binding


def encode(value):
    return json.dumps(value, sort_keys=True, allow_nan=False).encode("utf-8")


def sha(blob):
    return hashlib.sha256(blob).hexdigest()


def observation(index):
    return {"joint_position": [0., .04] + [0.] * 6, "joint_velocity": [0.] * 8,
        "step_id": index, "physics_steps": index * 10, "time": index * .02}


def guard_snapshot():
    return {"qref_rad": [0., .04], "input_mapping": {"basis": "known_angle_guard",
        "guard_used_by_model": True, "public_guard": {"public_joint_ranges_rad": [[-1.7, 1.7], [0., 2.36]],
            "angle_margin_rad": .03, "request_clip_per_axis_nm": .5,
            "q_clipped": False, "future_actual_input": False}},
        "fixture_parameters": "Handwritten assertion, no diagonal fit performed"}


class ArtificialAArchive:
    """Mutable fixture builder; exposed values allow surgical negative cases."""
    def __init__(self, root):
        self.root = Path(root)
        self.sources = {n: ("synthetic source assertion: " + n).encode() for n in binding.REQUIRED_SOURCE_PATHS}
        self.sources[binding.ASSET_PATH] = b'<mujoco><compiler angle="radian"/><worldbody><body><joint name="left_shoulder" range="-1.7 1.7"/><joint name="left_elbow" range="0 2.36"/></body></worldbody></mujoco>'
        self.current_sources = {n: self.sources[n] for n in binding.CURRENT_SOURCE_PATHS}
        self.runtime = {"environment_config": {"fixture_only": True}, "dependencies": {"fixture": "0"}, "mujoco_version": "fixture-no-mujoco"}
        self.metadata = {"suite": "guard_pair_development", "synthetic": True, "seeds": [0, 1, 2],
            "split": "development", "pose": "supine", "joint_indices": [0, 1], "native_joint_count": 8,
            "prefix_steps": 100, "calibration_steps": 400, "prediction_steps": 100, "control_steps_per_trial": 200,
            "source_status": "", "source_dirty": False, "gpu": None, "source_commit": "synthetic-fixture-no-git",
            "backend": "synthetic, no physics", **deepcopy(self.runtime)}
        self.episodes, self.seeds, self.rows = [], [], []
        self.plant = sha(b"handwritten fixture plant; no environment constructed")
        for seed, reset_seed in binding.RESET_SEEDS.items():
            baseline = {k: {"completed": k != "learned_guard", "status": "terminated" if k == "learned_guard" else "completed",
                "tracking_rmse": {"joint_rmse": .03}, "fixture_only": True} for k in binding.BASELINE_KINDS}
            self.seeds.append({"seed": seed, "reset_seed": reset_seed, "reference_q": [0., .04], "direction": [1, 1],
                "calibration_completed": True, "calibration_vector_updates": 800, "calibration_scalar_updates": 1600,
                "initial_models": {"learned_guard": guard_snapshot()}, "nominal_models": {"nominal_guard": guard_snapshot()},
                "calibration_models": {"learned_guard": guard_snapshot()}, "learned_models": {"learned_guard": guard_snapshot()},
                "evaluations": baseline})
            for kind in binding.KINDS:
                self.episodes.append({"seed": seed, "kind": kind, "trial_id": f"seed{seed}_{kind}",
                    "status": "completed", "completed": True, "environment_fingerprint_before": self.plant,
                    "environment_fingerprint_after": self.plant, "fixture_only": True})
                if kind not in ("calibration", "prediction"):
                    continue
                for index in range(500 if kind == "calibration" else 200):
                    self.rows.append({"trial_id": f"seed{seed}_{kind}", "seed": seed, "kind": kind,
                        "shared_transition_id": f"seed{seed}_{kind}:{index}", "step_index": index,
                        "phase": "prefix" if index < 100 else kind, "study_abort": None,
                        "requested_torque": [0.] * 8 if index < 100 else binding._request(index - 100, [1, 1], kind),
                        "observation_before": observation(index), "observation_after": observation(index + 1),
                        "diagnostics": {"executed_substeps": 10, "terminated": False}, "model_update": None,
                        "fixture_only": "Artificial transition, no physical call or model fit"})
        self.audit = {"schema_version": 1, "immutable_scope": binding.audit_scope(True), "failed": 0, "violations": [],
            "final_gates": {"data_consistency_verified": True, "model_contribution": {"known_angle_guard": {"passed": False}}},
            "execution": {"source_git_verification_enabled": False, "physical_simulation_calls": 0, "model_parameter_updates": 0},
            "archive": {"seeds": [{"seed": s, "evaluations": {"prediction": {"eligible": True}, **deepcopy(self.seeds[s]["evaluations"])}} for s in (0, 1, 2)],
                "budget": {"fixture_declared_prior_cost": "handwritten, no actual A execution", "control_calls_attempted": 0, "control_steps": 0, "physics_steps": 0, "model_updates": 0}}}
        self.duplicate_zip_member = None
        self.qref = [0., .04]
        self.public_joint_ranges = [[-1.7, 1.7], [0., 2.36]]

    def kwargs(self):
        return {"synthetic": True, "current_source_bytes": dict(self.current_sources), "expected_runtime": deepcopy(self.runtime)}

    def write(self):
        self.root.mkdir(parents=True, exist_ok=True)
        archive = self.root / binding.A_ROOT
        raw_dir = archive / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
            for name, blob in sorted(self.sources.items()):
                z.writestr(name, blob)
            if self.duplicate_zip_member is not None:
                z.writestr(self.duplicate_zip_member, self.sources[self.duplicate_zip_member])
        zipper = buffer.getvalue()
        hashes = {n: sha(b) for n, b in self.sources.items()}
        self.metadata.update(source_sha256=hashes, source_snapshot_sha256=sha(zipper),
            protocol={"path": binding.A_PROTOCOL_PATH, "sha256": hashes[binding.A_PROTOCOL_PATH]},
            independent_auditor={"path": binding.A_AUDITOR_PATH, "sha256": hashes[binding.A_AUDITOR_PATH], "pending": True, "required_for_formal": True})
        raw = {"source_snapshot.zip": zipper, "metadata.json": encode(self.metadata), "episodes.json": encode(self.episodes),
            "seed_results.json": encode(self.seeds), "trace.jsonl.gz": gzip.compress(b"\n".join(encode(r) for r in self.rows) + b"\n", mtime=0)}
        raw["manifest.json"] = encode({n: sha(b) for n, b in raw.items()})
        self.audit.update(audit_script_sha256=hashes[binding.A_AUDITOR_PATH],
            audit_dependency_sha256={n: hashes[n] for n in binding.A_AUDITOR_SUPPORT_PATHS})
        self.audit["archive"]["input_hashes"] = {n: sha(b) for n, b in raw.items()}
        audit_bytes = encode(self.audit)
        files = {"raw/" + n: {"kind": "synthetic_raw", "source": "artificial-fixture/" + n, "bytes": len(b), "sha256": sha(b)} for n, b in raw.items()}
        files["first_audit.json"] = {"kind": "synthetic_audit", "source": "artificial-fixture/audit", "bytes": len(audit_bytes), "sha256": sha(audit_bytes)}
        for n, blob in raw.items():
            (raw_dir / n).write_bytes(blob)
        (archive / "first_audit.json").write_bytes(audit_bytes)
        (archive / "manifest.json").write_bytes(encode({"files": files, "synthetic_fixture": True}))
        return self

"""Convenient artificial A builder for the B runner's synthetic tests.

No environment or model is instantiated. No real A path or Git is accessed.
Provided current source bytes are cached caller inputs, not filesystem reads.
"""
from copy import deepcopy

try:
    from developmental_physics import guard_pair_source_binding as binding
except ImportError:
    import guard_pair_source_binding as binding
from synthetic_a_source_fixture import ArtificialAArchive


def build_synthetic_a_archive(tmp_path, current_source_bytes, expected_runtime, mutate=None):
    """Return ArtificialAArchive (.root/.kwargs/.rows/.seeds/.plant available).

    Default fake native qref is [0., .04], v is zero. Public pair ranges come
    from the caller-supplied asset when present. The default synthetic asset
    contains shoulder [-1.7,1.7] and elbow [0,2.36], both in radians.
    mutate(fixture) runs once before writing so all byte bindings are updated.
    """
    fixture = ArtificialAArchive(tmp_path)
    fixture.sources.update(current_source_bytes)
    fixture.current_sources = dict(current_source_bytes)
    fixture.runtime = deepcopy(expected_runtime)
    fixture.metadata.update(deepcopy(expected_runtime))
    ranges = binding._public_ranges(fixture.sources[binding.ASSET_PATH])
    fixture.public_joint_ranges = deepcopy(ranges)
    for sr in fixture.seeds:
        for key in ("initial_models", "nominal_models", "calibration_models", "learned_models"):
            for snapshot in sr[key].values():
                snapshot["input_mapping"]["public_guard"]["public_joint_ranges_rad"] = deepcopy(ranges)
    if mutate is not None:
        mutate(fixture)
    return fixture.write()

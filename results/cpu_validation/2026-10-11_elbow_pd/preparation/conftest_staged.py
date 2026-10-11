import importlib.util
from pathlib import Path
import sys

name = "developmental_physics.elbow_feedback_validate"
if importlib.util.find_spec("mujoco") is not None:
    spec = importlib.util.spec_from_file_location(name,Path(__file__).parent/"elbow_feedback_validate.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)

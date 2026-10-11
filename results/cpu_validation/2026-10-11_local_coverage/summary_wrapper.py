"""One authorized C2-C review execution; never rerun or replace artifacts."""
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


root = Path(__file__).resolve().parent.parent
source = root/'external/c2c_results_review.py'
frozen = root/'external/c2c_review_summary_executed_01.py'
output = root/'external/local_coverage_20261011_development_summary.json'
stdout_path = root/'external/c2c_review_summary_stdout_01.txt'
execution_path = root/'external/c2c_review_summary_execution_01.json'
archive = root/'external/local_coverage_20261011_development'
audit = root/'external/local_coverage_20261011_development_audit.json'
for path in (frozen, output, stdout_path, execution_path):
    if path.exists():
        raise SystemExit('Refusing any repeated execution or artifact overwrite: '+str(path))
blob = source.read_bytes()
if hashlib.sha256(blob).hexdigest() != 'd9b36fe54013d0214658e7e5ca4db70f37ad5bb090d452ca302d0d0a82c31efe':
    raise SystemExit('Frozen source changed before execution.')
with frozen.open('xb') as stream:
    stream.write(blob)
manifest = json.loads((archive/'manifest.json').read_text(encoding='utf-8'))
inputs = {name: digest(archive/name) for name in manifest}
inputs['manifest.json'] = digest(archive/'manifest.json')
audit_hash = digest(audit)
command = [sys.executable, str(frozen), '--archive', str(archive),
           '--audit', str(audit), '--output', str(output)]
wall, cpu = time.perf_counter(), time.process_time()
result = subprocess.run(command, cwd=root, capture_output=True, text=True, encoding='utf-8')
wall_seconds, cpu_seconds = time.perf_counter()-wall, time.process_time()-cpu
with stdout_path.open('x', encoding='utf-8', newline='\n') as stream:
    stream.write(result.stdout)
    if result.stderr:
        stream.write('\nSTDERR:\n'+result.stderr)
wrapper = Path(__file__).read_bytes()
execution = {
    'schema_version': 1, 'created_at_utc': datetime.now(timezone.utc).isoformat(),
    'exact_executed_source_path': str(frozen), 'exact_executed_source_bytes': len(blob),
    'exact_executed_source_sha256': hashlib.sha256(blob).hexdigest(),
    'exact_executed_source_bytes_base64': base64.b64encode(blob).decode('ascii'),
    'wrapper_source_sha256': hashlib.sha256(wrapper).hexdigest(),
    'wrapper_source_bytes_base64': base64.b64encode(wrapper).decode('ascii'),
    'input_hashes': inputs, 'audit_sha256': audit_hash, 'command': command,
    'returncode': result.returncode, 'wall_seconds': wall_seconds,
    'cpu_seconds': cpu_seconds, 'cpu_seconds_scope': 'Wrapper process only; child internal process CPU is retained by its summary.',
    'timing_scope': 'subprocess dispatch through completion, includes child startup/imports/report serialization.',
    'stdout_path': str(stdout_path), 'stdout_sha256': digest(stdout_path),
    'summary_path': str(output), 'summary_sha256': digest(output) if output.exists() else None,
    'summary_executions': 1, 'physical_simulation_calls': 0, 'model_prediction_calls': 0,
    'rls_replay_calls': 0, 'real_parameter_updates': 0, 'new_environment_interactions': 0,
}
with execution_path.open('x', encoding='utf-8', newline='\n') as stream:
    json.dump(execution, stream, ensure_ascii=False, indent=2, allow_nan=False)
    stream.write('\n')
print(json.dumps({'returncode': result.returncode, 'wall_seconds': wall_seconds,
                  'cpu_seconds': cpu_seconds, 'summary_sha256': execution['summary_sha256'],
                  'execution_path': str(execution_path), 'stdout': result.stdout, 'stderr': result.stderr}))
raise SystemExit(result.returncode)

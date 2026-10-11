"""Check local Markdown destinations in a specified current delivery only."""
import argparse
import json
from pathlib import Path
import re
from urllib.parse import unquote

parser = argparse.ArgumentParser()
parser.add_argument('--output', required=True)
parser.add_argument('files', nargs='+')
args = parser.parse_args()
repo = Path(__file__).resolve().parents[1]
out = repo / args.output
assert not out.exists()
checks, failures = [], []
for name in args.files:
    path = repo / name
    text = path.read_text(encoding='utf-8')
    for match in re.finditer(r'\]\(([^\n)]+)\)', text):
        destination = match.group(1).strip().strip('<>')
        if re.match(r'^[A-Za-z][A-Za-z0-9+.-]*:', destination) or destination.startswith('#'):
            continue
        local = unquote(destination.split('#', 1)[0])
        target = path.parent / local
        row = dict(file=name, destination=destination, exists=target.exists())
        checks.append(row)
        if not row['exists']:
            failures.append(row)
record = dict(status='passed' if not failures else 'failed', files=args.files,
              local_links_checked=len(checks), failures=failures,
              model_fit_physics_or_scientific_metric_calls=0)
with out.open('x', encoding='utf-8') as stream:
    json.dump(record, stream, indent=2, ensure_ascii=False)
print(json.dumps(record, ensure_ascii=False))
raise SystemExit(bool(failures))

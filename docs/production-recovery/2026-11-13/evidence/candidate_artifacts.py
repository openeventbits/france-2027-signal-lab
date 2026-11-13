import sys, os, json, hashlib
from pathlib import Path
from unittest.mock import patch
from datetime import date
sys.path.insert(0,os.getcwd())
import build_candidate_reference as r
ev=Path(__file__).resolve().parent
phase=sys.argv[1]
sources=r.load_sources(Path.cwd())
with patch.object(r,'_event_reference_date',return_value=date(2026,11,13)):
    artifacts=r.build_all_active_artifacts(sources,Path.cwd())
dest=ev/('candidate-artifacts-'+phase); dest.mkdir(exist_ok=True)
manifest={}
for path,raw in artifacts.items():
    relative=str(path.relative_to(Path.cwd())).replace('\\','/') if path.is_absolute() else path.as_posix()
    target=dest/relative; target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes(raw)
    manifest[relative]=hashlib.sha256(raw).hexdigest()
(ev/f'candidate-artifacts-{phase}.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
print(len(manifest),'artifacts captured at controlled unchanged date')

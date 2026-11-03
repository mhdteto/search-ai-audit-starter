#!/usr/bin/env python3
"""Verify frozen source hashes and reproduce all 17 original fictional outputs."""
from pathlib import Path
import json,subprocess,sys,tempfile,hashlib,shutil
ROOT=Path(__file__).resolve().parents[1]
DEMO=ROOT/'examples/fictional-workflow'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
for entry in json.loads((DEMO/'source-script-hashes.json').read_text()):
    data=(DEMO/'tools'/entry['name']/entry['path']).read_bytes()
    blob=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
    assert blob==entry['sha'],'Frozen source differs from pinned GitHub blob'
with tempfile.TemporaryDirectory() as temp:
    copy=Path(temp)/'workflow';shutil.copytree(DEMO,copy)
    expected={p.relative_to(copy/'reports').as_posix():sha(p) for p in (copy/'reports').rglob('*') if p.is_file()}
    assert len(expected)==17
    subprocess.run([sys.executable,'run_demo.py'],cwd=copy,check=True)
    actual={p.relative_to(copy/'reports').as_posix():sha(p) for p in (copy/'reports').rglob('*') if p.is_file()}
    assert expected==actual,'Fictional workflow outputs changed'
print('Five pinned tool hashes and 17 deterministic original outputs verified.')

"""Run five pinned tools offline on entirely fictional teaching inputs."""
from pathlib import Path
import subprocess, sys, json

BASE=Path(__file__).resolve().parent
JOBS=[
 ['tools/search-ai-discoverability-checker/check.py','https://example.org/','--fixture','inputs/http-fixture.json','--output-dir','reports/discoverability'],
 ['tools/entity-consistency-auditor/audit.py','--identity','inputs/identity.json','--profiles','inputs/profiles.csv','--as-of','2026-11-01','--output-dir','reports/identity'],
 ['tools/authority-evidence-mapper/map_evidence.py','--claims','inputs/claims.csv','--evidence','inputs/evidence.csv','--as-of','2026-11-01','--output-dir','reports/evidence'],
 ['tools/entity-structured-data-kit/validate.py','inputs/entity-graph.json','--output-dir','reports/structured-data'],
 ['tools/ai-citation-tracker/tracker.py','--answers','inputs/answers.csv','--citations','inputs/citations.csv','--as-of','2026-11-01','--output','reports/citations']
]

def main():
    if sys.version_info < (3,9):
        print('Python 3.9+ required; Python 3.10+ recommended by the upstream tools. No packages or API keys.');return 2
    for args in JOBS:
        print('Running:',args[0],flush=True)
        subprocess.run([sys.executable,*args],cwd=BASE,check=True)
    check_results()
    print('PASS: five offline reports reproduce the documented fictional observations.')
    return 0

def check_results():
    read=lambda name:json.loads((BASE/'reports'/name/'report.json').read_text())
    identity=read('identity')
    assert identity['profile_count']==4
    assert identity['status_counts']=={'approved_alias':2,'manual_review':3,'match':6,'mismatch':2,'missing':3}
    evidence=read('evidence')
    assert len(evidence['claims'])==3
    assert 'conflicting sources' in evidence['claims'][0]['statuses']
    assert evidence['claims'][0]['independent_support_publishers']==1
    assert 'missing evidence' in evidence['claims'][2]['statuses']
    citations=read('citations')
    assert len(citations['groups'])==2
    uk=next(g for g in citations['groups'] if g['market']=='United Kingdom')
    fr=next(g for g in citations['groups'] if g['market']=='France')
    assert (uk['answer_count'],uk['cited_answer_count'],uk['explicit_citation_count'],uk['cited_answer_rate'])==(4,2,3,.5)
    assert (fr['answer_count'],fr['cited_answer_count'],fr['explicit_citation_count'],fr['cited_answer_rate'])==(2,1,1,.5)
    page=read('discoverability')
    assert page['page']['status']==200
    assert page['input_url']=='https://example.org/'

if __name__=='__main__':
    raise SystemExit(main())

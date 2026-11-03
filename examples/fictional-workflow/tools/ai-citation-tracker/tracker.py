#!/usr/bin/env python3
"""Offline explicit-citation observation reports. No network access."""
import argparse
import csv
import datetime
import html
import ipaddress
import io
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

ANSWER_FIELDS = ['answer_id','collected_on','engine','model','interface','language','market','prompt_id','prompt','answer_text']
CITATION_FIELDS = ['answer_id','citation_url']
GROUP_FIELDS = ['engine','model','interface','language','market']
METRICS = ['answer_count','cited_answer_count','explicit_citation_count','cited_answer_rate','citations_per_answer','citations_per_cited_answer']
OUTPUT_NAMES = ['report.json','report.html','answers.csv','groups.csv','citations.csv','hostnames.csv']
CAVEAT = ('Counts describe supplied explicit citation observations only. A citation is a distinct normalized URL within an answer; repeated answers count separately. '
          'No inference of uncited use, factual support, authority, search ranking or population-wide visibility. Hostnames are not registrable domains. '
          'Groups preserve engine, model, interface, language and market. Sampling and prompt composition can change every rate.')


def date_value(value):
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise ValueError('Dates must use YYYY-MM-DD')
    try:
        return datetime.date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError('Invalid calendar date: '+value) from exc


def normalize_url(url):
    """Conservative offline HTTP(S) normalization, preserving path and query."""
    if not url or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in url) or '\\' in url:
        raise ValueError('URL contains whitespace, controls or backslash')
    if any(char in url for char in '<>\"{}|^`'):
        raise ValueError('URL contains characters that must be percent-encoded')
    if re.search(r'%(?![0-9a-fA-F]{2})', url):
        raise ValueError('Malformed URL percent escape')
    try:
        parts = urlsplit(url)
        scheme = parts.scheme.lower()
        if scheme not in ('http','https') or not parts.hostname or parts.username is not None or parts.password is not None:
            raise ValueError('Only absolute HTTP(S) URLs without credentials are accepted')
        host = parts.hostname
        if '%' in host or parts.netloc.endswith(':'):
            raise ValueError('Invalid hostname or port')
        if ':' in host:
            host = '['+ipaddress.IPv6Address(host).compressed+']'
        else:
            host = host.encode('idna').decode('ascii').lower().rstrip('.')
            if len(host) > 253 or not all(re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label) for label in host.split('.')):
                raise ValueError('Invalid hostname')
        port = parts.port
        if port is not None and port < 1:
            raise ValueError('Invalid port')
        netloc = host
        if port is not None and (scheme,port) not in (('http',80),('https',443)):
            netloc += ':'+str(port)
        return urlunsplit((scheme,netloc,parts.path or '/',parts.query,''))
    except (UnicodeError, ValueError) as exc:
        raise ValueError('Invalid citation URL: '+url) from exc


def validate_quoting(text):
    # csv.reader(strict=True) alone permits stray quotes in unquoted fields.
    state = 'start'
    for char in text:
        if state == 'quoted':
            if char == '"': state = 'closed'
        elif state == 'closed':
            if char == '"': state = 'quoted'
            elif char in ',\r\n': state = 'start'
            else: raise ValueError('Characters after closing CSV quote')
        elif char == '"':
            if state != 'start': raise ValueError('Quote inside unquoted CSV field')
            state = 'quoted'
        elif char in ',\r\n': state = 'start'
        else: state = 'bare'
    if state == 'quoted': raise ValueError('Unterminated CSV quote')


def read_rows(path, fields):
    try:
        with Path(path).open('r',encoding='utf-8-sig',newline='') as f:
            text = f.read()
            validate_quoting(text)
            reader = csv.reader(io.StringIO(text, newline=''), strict=True)
            if next(reader,None) != fields:
                raise ValueError(str(path)+': headers must exactly match '+','.join(fields))
            rows = []
            for values in reader:
                if len(values) != len(fields):
                    raise ValueError(str(path)+': wrong number of fields at line '+str(reader.line_num))
                if any('\x00' in value for value in values):
                    raise ValueError(str(path)+': NUL character in input')
                rows.append(dict(zip(fields,values)))
            return rows
    except (csv.Error, UnicodeError) as exc:
        raise ValueError(str(path)+': malformed UTF-8 CSV: '+str(exc)) from exc


def analyze(answers_path, citations_path, as_of):
    today = date_value(as_of)
    rows = read_rows(answers_path, ANSWER_FIELDS)
    if not rows:
        raise ValueError('Answers CSV must contain at least one answer')
    answers = {}
    prompt_texts = {}
    for row in rows:
        for field in ANSWER_FIELDS:
            if not row[field].strip():
                raise ValueError('Empty answer field: '+field)
        for field in ('answer_id','prompt_id'):
            if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}',row[field]):
                raise ValueError('Invalid '+field)
        if row['answer_id'] in answers:
            raise ValueError('Duplicate answer_id: '+row['answer_id'])
        if date_value(row['collected_on']) > today:
            raise ValueError('collected_on is after as-of date')
        if row['interface'] not in ('web','app','api','other'):
            raise ValueError('interface must be web, app, api or other')
        if not re.fullmatch(r'[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})*',row['language']):
            raise ValueError('language must be a short language tag such as en or fr-MA')
        if row['prompt_id'] in prompt_texts and prompt_texts[row['prompt_id']] != row['prompt']:
            raise ValueError('One prompt_id must identify exactly one prompt text')
        prompt_texts[row['prompt_id']] = row['prompt']
        answers[row['answer_id']] = dict(row, citation_urls=[])
    urls = defaultdict(set)
    for row in read_rows(citations_path,CITATION_FIELDS):
        if row['answer_id'] not in answers:
            raise ValueError('Citation references unknown answer_id: '+row['answer_id'])
        urls[row['answer_id']].add(normalize_url(row['citation_url']))
    groups = defaultdict(list)
    for ident,row in answers.items():
        row['citation_urls'] = sorted(urls[ident])
        row['citation_count'] = len(urls[ident])
        row['unique_hostname_count'] = len({urlsplit(u).hostname for u in urls[ident]})
        groups[tuple(row[f] for f in GROUP_FIELDS)].append(row)
    summaries = []
    for key,items in sorted(groups.items()):
        count = len(items)
        cited = sum(bool(a['citation_count']) for a in items)
        citations = sum(a['citation_count'] for a in items)
        host_count = Counter(urlsplit(u).hostname for a in items for u in a['citation_urls'])
        host_answers = Counter(h for a in items for h in {urlsplit(u).hostname for u in a['citation_urls']})
        summaries.append(dict(zip(GROUP_FIELDS,key),answer_count=count,cited_answer_count=cited,explicit_citation_count=citations,
            cited_answer_rate=cited/count,citations_per_answer=citations/count,citations_per_cited_answer=citations/cited if cited else None,
            collected_from=min(a['collected_on'] for a in items),collected_to=max(a['collected_on'] for a in items),
            prompt_ids=sorted({a['prompt_id'] for a in items}),
            top_hostnames=[dict(hostname=h,citation_count=n,answer_count=host_answers[h]) for h,n in sorted(host_count.items(),key=lambda x:(-x[1],x[0]))]))
    return dict(schema_version='1.0',as_of=as_of,method=CAVEAT,
        denominators={'cited_answer_rate':'cited_answer_count / answer_count (fraction 0..1)',
                      'citations_per_answer':'explicit_citation_count / answer_count',
                      'citations_per_cited_answer':'explicit_citation_count / cited_answer_count; null if denominator is zero'},
        groups=summaries,answers=sorted(answers.values(),key=lambda a:a['answer_id']))


def safe_cell(value):
    if value is None:
        return ''
    value = str(value)
    # A spreadsheet may skip BOM and whitespace before treating a cell as a formula.
    index = 0
    while index < len(value) and (value[index].isspace() or value[index] == '\ufeff'):
        index += 1
    if value[index:].startswith(('=','+','-','@')):
        return "'"+value
    return value


def write_csv(path,fields,rows):
    with path.open('w',encoding='utf-8',newline='') as f:
        writer=csv.writer(f,lineterminator='\n',quoting=csv.QUOTE_ALL); writer.writerow(fields)
        for row in rows:
            writer.writerow([safe_cell(row.get(field,'')) for field in fields])


def table(fields,rows):
    esc=lambda x:html.escape(str(x),quote=True)
    return '<div class="scroll"><table><thead><tr>'+''.join('<th scope="col">'+esc(f.replace('_',' '))+'</th>' for f in fields)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+esc(row.get(f,''))+'</td>' for f in fields)+'</tr>' for row in rows)+'</tbody></table></div>'


def render_html(report):
    esc=lambda x:html.escape(str(x),quote=True)
    summary_fields=GROUP_FIELDS+['collected_from','collected_to']+METRICS
    hosts=[dict({f:g[f] for f in GROUP_FIELDS},**h) for g in report['groups'] for h in g['top_hostnames']]
    details=''
    for a in report['answers']:
        details+='<details><summary>'+esc(a['answer_id'])+' · '+str(a['citation_count'])+' citations · '+esc(a['engine'])+' / '+esc(a['market'])+'</summary>'+table(ANSWER_FIELDS+['citation_count','unique_hostname_count'],[a])+'<p>Normalized explicit URLs</p><ul>'+''.join('<li><a rel="noreferrer noopener" href="'+esc(u)+'">'+esc(u)+'</a></li>' for u in a['citation_urls'])+'</ul></details>'
    return '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>AI Citation Tracker · observation report</title><style>
:root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;background:#091525;color:#e4edf7;font:16px/1.6 system-ui,sans-serif}main{max-width:1440px;margin:auto;padding:32px 24px}a{color:#6de4ef}h1{font-size:clamp(2rem,5vw,3.5rem);line-height:1.1}h2{margin-top:40px}p{max-width:95ch}.eyebrow{color:#6de4ef;font-weight:700;letter-spacing:.12em}.scroll{overflow:auto;border:1px solid #314960;border-radius:8px}table{border-collapse:collapse;width:100%;font-size:14px}th,td{padding:12px;text-align:left;vertical-align:top;border-bottom:1px solid #314960;white-space:pre-wrap;overflow-wrap:anywhere;min-width:110px}th{background:#13283d;color:#83ecf5}details{margin:16px 0;background:#102136;padding:16px;border:1px solid #314960;border-radius:8px}summary{cursor:pointer;font-weight:650}li{overflow-wrap:anywhere}.note{padding:20px;border-left:4px solid #6de4ef;background:#13283d}footer{margin-top:40px;color:#b7c9dd}a:focus-visible,summary:focus-visible{outline:3px solid #6de4ef;outline-offset:4px}</style></head><body><main><p class="eyebrow">EXPLICIT OBSERVATIONS / OFFLINE</p><h1>AI Citation Tracker</h1>'''+ '<p>As of '+esc(report['as_of'])+' · '+str(len(report['answers']))+' supplied answers</p><p class="note">'+esc(CAVEAT)+'</p><h2>Group metrics</h2><p>Cited answer rate is a fraction: cited answers ÷ all answers in that group. Citation averages use the denominators shown in their column names. A blank average for cited answers means there were none.</p>'+table(summary_fields,[{k:('' if v is None else round(v,6) if isinstance(v,float) else v) for k,v in g.items()} for g in report['groups']])+'<h2>Hostnames</h2><p>Sorted by citation count within each group. All observed hostnames are retained. One hostname may have multiple distinct URLs in an answer.</p>'+table(GROUP_FIELDS+['hostname','citation_count','answer_count'],hosts)+'<h2>Raw observation details</h2><p>Expand an answer to review supplied metadata, prompt, answer text and normalized citations. Zero-citation answers remain included.</p>'+details+'<h2>Comparing date windows</h2><p>Generate separate reports for separately prepared CSV windows and view them side by side. This tool does not calculate trends. Compare only matching engine/model/interface/language/market groups and identical prompt IDs/text, with similar repeat counts, collection procedures and window lengths. A difference in observations does not establish a change in an engine or in reputation.</p><footer>AI Citation Tracker · Independent research utility · <a href="https://mohammedteto.com/research/">Research</a> · <a href="https://mohammedteto.com/method/">Method</a></footer></main></body></html>\n'


def export(report,output,inputs):
    output=Path(output).absolute()
    # Reject every symlink component, including nonexistent-output ancestors.
    for part in (output,)+tuple(output.parents):
        if part.is_symlink():
            raise ValueError('Output directory must not use symlinks')
    if output.exists() and not output.is_dir():
        raise ValueError('Output must be a directory')
    sources=[Path(p).resolve() for p in inputs]
    targets=[output/name for name in OUTPUT_NAMES]
    for target in targets:
        if target.is_symlink() or (target.exists() and not target.is_file()):
            raise ValueError('Output target must be a regular file: '+str(target))
        if any(target.resolve()==source or (target.exists() and source.exists() and target.samefile(source)) for source in sources):
            raise ValueError('Output would overwrite an input: '+str(target))
    for index,target in enumerate(targets):
        if target.exists() and any(other.exists() and target.samefile(other) for other in targets[index+1:]):
            raise ValueError('Output files must not alias one another')
    # Check the complete plan before creating any output.
    output.mkdir(parents=True,exist_ok=True)
    (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (output/'report.html').write_text(render_html(report),encoding='utf-8')
    write_csv(output/'answers.csv',ANSWER_FIELDS+['citation_count','unique_hostname_count'],report['answers'])
    write_csv(output/'groups.csv',GROUP_FIELDS+['collected_from','collected_to']+METRICS,report['groups'])
    citations=[{'answer_id':a['answer_id'],'citation_url':u,'hostname':urlsplit(u).hostname} for a in report['answers'] for u in a['citation_urls']]
    write_csv(output/'citations.csv',CITATION_FIELDS+['hostname'],citations)
    hosts=[dict({f:g[f] for f in GROUP_FIELDS},**h) for g in report['groups'] for h in g['top_hostnames']]
    write_csv(output/'hostnames.csv',GROUP_FIELDS+['hostname','citation_count','answer_count'],hosts)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--answers',required=True,type=Path)
    parser.add_argument('--citations',required=True,type=Path)
    parser.add_argument('--as-of',required=True,help='Fixed YYYY-MM-DD validation cutoff (inclusive)')
    parser.add_argument('--output',required=True,type=Path,help='Directory for six deterministic report files')
    args=parser.parse_args()
    try:
        report=analyze(args.answers,args.citations,args.as_of)
        export(report,args.output,[args.answers,args.citations])
    except (ValueError,OSError) as exc:
        parser.exit(2,'error: '+str(exc)+'\n')
    print('Wrote 6 reports for '+str(len(report['answers']))+' answers to '+str(args.output))

if __name__=='__main__': main()

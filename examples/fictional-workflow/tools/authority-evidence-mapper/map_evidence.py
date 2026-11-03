#!/usr/bin/env python3
"""Map supplied human evidence declarations without network access. MIT licensed."""
import argparse
import csv
from datetime import date
from html import escape
import json
from pathlib import Path
import re
import sys
import unicodedata
from urllib.parse import urlsplit

CLAIM_FIELDS = ['claim_id', 'entity', 'claim_text']
EVIDENCE_FIELDS = ['evidence_id', 'claim_id', 'source_url', 'publisher', 'published_on', 'accessed_on', 'relationship', 'support_status', 'review_note']
RELATIONSHIPS = {'independent', 'owned', 'affiliated', 'unknown'}
SUPPORT_STATUSES = {'supports', 'partial', 'contradicts', 'unreviewed'}
LIMITATION = ('Relationship and support labels are human declarations, not verified facts. '
              'A URL is not verification. Review age does not establish evidence validity. '
              'This offline report makes no credibility, authority, or ranking judgment.')


def read_csv(path, fields):
    with Path(path).open(encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle, strict=True)
        if reader.fieldnames is None or len(reader.fieldnames) != len(set(reader.fieldnames)) or set(reader.fieldnames) != set(fields):
            raise ValueError(f'{path}: expected exactly these headers: {", ".join(fields)}')
        rows = []
        for number, row in enumerate(reader, 2):
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f'{path}: row {number} has the wrong number of cells')
            rows.append(row)
        return rows


def parse_date(value, label, required=False):
    if not value:
        if required:
            raise ValueError(f'{label}: date is required')
        return None
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise ValueError(f'{label}: use YYYY-MM-DD')
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f'{label}: invalid date {value}') from error


def normalized_publisher(value):
    return ' '.join(unicodedata.normalize('NFKC', value).casefold().split())


def validate_url(value):
    try:
        parsed = urlsplit(value)
        if parsed.scheme.lower() not in {'https', 'http'} or not parsed.hostname or parsed.username is not None or parsed.password is not None or any(ch.isspace() or ord(ch) < 32 for ch in value):
            raise ValueError('invalid')
        parsed.port
    except ValueError as error:
        raise ValueError('source_url must be an absolute HTTP(S) URL without credentials or whitespace') from error


def build_report(claims, evidence, as_of, stale_days=180):
    reference = parse_date(as_of, 'as-of', True)
    if not isinstance(stale_days, int) or stale_days < 0:
        raise ValueError('stale-days must be a nonnegative integer')
    mapped = {}
    for raw in claims:
        row = {key: str(raw.get(key, '')).strip() for key in CLAIM_FIELDS}
        if any(not row[key] for key in CLAIM_FIELDS):
            raise ValueError('Every claim requires claim_id, entity and claim_text')
        if row['claim_id'] in mapped:
            raise ValueError(f'Duplicate claim_id: {row["claim_id"]}')
        mapped[row['claim_id']] = dict(row, evidence=[])
    seen = set()
    for raw in evidence:
        row = {key: str(raw.get(key, '')).strip() for key in EVIDENCE_FIELDS}
        ident = row['evidence_id']
        if not ident or ident in seen:
            raise ValueError(f'Empty or duplicate evidence_id: {ident}')
        seen.add(ident)
        if row['claim_id'] not in mapped:
            raise ValueError(f'Unknown claim_id: {row["claim_id"]}')
        if not normalized_publisher(row['publisher']):
            raise ValueError(f'{ident}: publisher is required')
        if row['relationship'] not in RELATIONSHIPS or row['support_status'] not in SUPPORT_STATUSES:
            raise ValueError(f'{ident}: invalid relationship or support_status')
        validate_url(row['source_url'])
        published = parse_date(row['published_on'], f'{ident} published_on')
        accessed = parse_date(row['accessed_on'], f'{ident} accessed_on')
        if (published and published > reference) or (accessed and accessed > reference):
            raise ValueError(f'{ident}: dates cannot be after as-of')
        if published and accessed and published > accessed:
            raise ValueError(f'{ident}: published_on cannot be after accessed_on')
        age = (reference - accessed).days if accessed else None
        row.update(review_age_days=age, review_age='unknown' if age is None else ('stale' if age > stale_days else 'within threshold'))
        mapped[row['claim_id']]['evidence'].append(row)
    for claim in mapped.values():
        rows = claim['evidence']
        labels = {row['support_status'] for row in rows}
        claim['statuses'] = (['missing evidence'] if not rows else []) + [label for status, label in [('unreviewed','unreviewed'), ('partial','partial'), ('supports','supporting sources'), ('contradicts','conflicting sources')] if status in labels]
        claim['distinct_publishers'] = len({normalized_publisher(row['publisher']) for row in rows})
        claim['independent_support_publishers'] = len({normalized_publisher(row['publisher']) for row in rows if row['relationship'] == 'independent' and row['support_status'] == 'supports'})
    return dict(as_of=as_of, stale_days=stale_days, limitation=LIMITATION, claims=list(mapped.values()))


def csv_safe(value):
    text = '' if value is None else str(value)
    # Guard spreadsheet formulas even behind whitespace/control characters.
    if text.lstrip(' \t\r\n\v\f\ufeff').startswith(('=', '+', '-', '@')) or text.startswith(('\t', '\r', '\n')):
        return "'" + text
    return text


def write_csv(path, fields, rows):
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: csv_safe(row.get(key)) for key in fields})


def html_report(report):
    def h(value):
        return escape('' if value is None else str(value), quote=True)
    sections = []
    for claim in report['claims']:
        evidence_rows = []
        for row in claim['evidence']:
            age = row['review_age'] + (f' ({row["review_age_days"]} days)' if row['review_age_days'] is not None else '')
            cells = [h(row['evidence_id']), f'<a href="{h(row["source_url"])}" rel="noreferrer">{h(row["publisher"])}</a>', h(row['support_status']), h(row['relationship']), h(row['published_on'] or 'Unknown'), h(row['accessed_on'] or 'Unknown'), h(age), h(row['review_note'] or 'No note supplied')]
            evidence_rows.append('<tr>'+''.join('<td>'+cell+'</td>' for cell in cells)+'</tr>')
        table = '<div class="scroll"><table><thead><tr>'+''.join('<th>'+x+'</th>' for x in ['Evidence ID','Source / publisher','Declared support','Declared relationship','Published','Accessed','Review age','Reviewer note'])+'</tr></thead><tbody>'+''.join(evidence_rows)+'</tbody></table></div>' if evidence_rows else '<p>No evidence supplied. This claim has no supporting evidence in this dataset.</p>'
        sections.append(f'<section><h2>{h(claim["claim_id"])} · {h(claim["entity"])}</h2><p>{h(claim["claim_text"])}</p><p class="status">{h(" · ".join(claim["statuses"]))}</p><p>Distinct publishers: {claim["distinct_publishers"]} · Declared independent supporting publishers: {claim["independent_support_publishers"]}</p>{table}</section>')
    return '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Authority Evidence Mapper report</title><style>body{margin:0;background:#081321;color:#eef7fc;font:16px/1.6 system-ui,sans-serif}main{max-width:1200px;margin:auto;padding:32px 20px}h1,h2,a,.status{color:#36d9ee}section,.notice{background:#0d2539;padding:24px;border-radius:12px;margin:24px 0}.scroll{overflow:auto}table{border-collapse:collapse;width:100%;min-width:850px}th,td{text-align:left;vertical-align:top;padding:12px;border-bottom:1px solid #31506a;overflow-wrap:anywhere}th{font-size:14px}a{overflow-wrap:anywhere}h1{line-height:1.2}footer{font-size:14px}</style></head><body><main><h1>Authority Evidence Mapper</h1><p>Offline evidence review inventory</p><p>As of '+h(report['as_of'])+' · Review-age threshold: '+str(report['stale_days'])+' days · Claims: '+str(len(report['claims']))+'</p><div class="notice">'+h(LIMITATION)+' Statuses may coexist: supporting sources never hide conflicting sources. Publisher counts use normalized labels supplied in the input.</div>'+''.join(sections)+'<footer>Generated locally. No URLs were fetched. Code MIT · Documentation CC BY 4.0.</footer></main></body></html>\n'


def write_reports(report, output_dir):
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    (target/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    summaries = [dict(claim, statuses='; '.join(claim['statuses'])) for claim in report['claims']]
    write_csv(target/'claims.csv', CLAIM_FIELDS+['statuses','distinct_publishers','independent_support_publishers'], summaries)
    write_csv(target/'evidence.csv', EVIDENCE_FIELDS+['review_age_days','review_age'], [row for claim in report['claims'] for row in claim['evidence']])
    (target/'report.html').write_text(html_report(report), encoding='utf-8')


def guard_output_paths(claims_path, evidence_path, output_dir):
    """Reject resolved aliases and existing hard links before writing any report."""
    inputs = [Path(claims_path).resolve(), Path(evidence_path).resolve()]
    for name in ('claims.csv', 'evidence.csv', 'report.json', 'report.html'):
        target = (Path(output_dir) / name).resolve()
        for source in inputs:
            if target == source or (target.exists() and source.exists() and target.samefile(source)):
                raise ValueError(f'Output collision: {name} resolves to input file {source}; choose a different --output-dir')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--claims', required=True)
    parser.add_argument('--evidence', required=True)
    parser.add_argument('--as-of', required=True, help='YYYY-MM-DD reference date')
    parser.add_argument('--stale-days', type=int, default=180)
    parser.add_argument('--output-dir', default='reports')
    args = parser.parse_args(argv)
    try:
        guard_output_paths(args.claims, args.evidence, args.output_dir)
        report = build_report(read_csv(args.claims, CLAIM_FIELDS), read_csv(args.evidence, EVIDENCE_FIELDS), args.as_of, args.stale_days)
        write_reports(report, args.output_dir)
    except (ValueError, OSError, csv.Error) as error:
        parser.exit(2, f'Error: {error}\n')
    print(f'Wrote {len(report["claims"])} claims to {args.output_dir} (JSON, CSV and HTML). No network access performed.')
    return 0

if __name__ == '__main__':
    sys.exit(main())

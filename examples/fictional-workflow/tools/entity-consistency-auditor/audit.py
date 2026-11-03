#!/usr/bin/env python3
"""Compare supplied identity observations offline, without verifying truth."""
import argparse
from collections import Counter
import csv
from datetime import date
import html
import json
from pathlib import Path
import re
import sys
import unicodedata
from urllib.parse import urlsplit

FIELDS = ('name', 'role', 'organization', 'description')
HEADERS = ('source_url', 'observed_at', 'language', 'market') + FIELDS
NOTICE = 'Consistency with the supplied record only. No truth verification, entity resolution, or Google ranking prediction.'


def normalize(value):
    return ' '.join(unicodedata.normalize('NFKC', value).split()).casefold()


def parse_date(value, label):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise ValueError(f'{label}: use a valid YYYY-MM-DD date')
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValueError(f'{label}: use a valid YYYY-MM-DD date') from None


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'duplicate JSON key: {key}')
        result[key] = value
    return result


def read_identity(path):
    with path.open(encoding='utf-8-sig') as stream:
        record = json.load(stream, object_pairs_hook=unique_object)
    if not isinstance(record, dict):
        raise ValueError('identity must be a JSON object')
    if set(record) - {'entity_id', 'entity_type', 'aliases', *FIELDS}:
        raise ValueError('identity has unsupported fields')
    for key in ('entity_id', 'entity_type', 'name'):
        if not isinstance(record.get(key), str) or not record[key].strip():
            raise ValueError(f'identity requires a nonempty string: {key}')
    if record['entity_type'] not in ('person', 'organization'):
        raise ValueError('entity_type must be person or organization')
    for field in FIELDS:
        if field in record and (not isinstance(record[field], str) or not record[field].strip()):
            raise ValueError(f'identity {field} must be a nonempty string; omit unspecified fields')
    aliases = record.get('aliases', {})
    if not isinstance(aliases, dict):
        raise ValueError('aliases must be an object')
    for field, values in aliases.items():
        if field not in FIELDS or field not in record:
            raise ValueError('alias field must have a canonical value')
        if not isinstance(values, list) or any(not isinstance(v, str) or not v.strip() for v in values):
            raise ValueError(f'aliases for {field} must be an array of nonempty strings')
    return record


def validate_url(value, label):
    if not value or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError(f'{label}: source_url must be an absolute http/https URL without whitespace')
    try:
        parsed = urlsplit(value)
        valid = parsed.scheme.lower() in ('http', 'https') and parsed.hostname and parsed.username is None and parsed.password is None
        parsed.port
    except ValueError:
        valid = False
    if not valid:
        raise ValueError(f'{label}: source_url must be an absolute http/https URL without credentials')


def read_profiles(path, as_of):
    rows, seen = [], set()
    with path.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.reader(stream, strict=True)
        headers = next(reader, [])
        if len(headers) != len(HEADERS) or set(headers) != set(HEADERS):
            raise ValueError('profiles headers must contain exactly: ' + ','.join(HEADERS))
        for number, values in enumerate(reader, 2):
            if len(values) != len(headers):
                raise ValueError(f'row {number}: incorrect number of CSV fields')
            row = dict(zip(headers, values))
            validate_url(row['source_url'], f'row {number}')
            observed = parse_date(row['observed_at'], f'row {number} observed_at')
            if observed > as_of:
                raise ValueError(f'row {number}: observed_at is in the future relative to as-of')
            key = (row['source_url'], row['observed_at'], normalize(row['language']), normalize(row['market']))
            if key in seen:
                raise ValueError(f'row {number}: duplicate source/date/language/market observation')
            seen.add(key)
            rows.append(row)
    if not rows:
        raise ValueError('profiles must contain at least one observation')
    return rows


def evaluate(identity, profiles, as_of):
    results = []
    for row in profiles:
        for field in FIELDS:
            if field not in identity:
                continue
            observed, canonical = row[field], identity[field]
            if not observed.strip():
                status = 'missing'
            elif field == 'description':
                status = 'manual_review'
            elif normalize(observed) == normalize(canonical):
                status = 'match'
            elif normalize(observed) in {normalize(v) for v in identity.get('aliases', {}).get(field, [])}:
                status = 'approved_alias'
            else:
                status = 'mismatch'
            results.append({**{key: row[key] for key in HEADERS[:4]}, 'field': field, 'canonical': canonical, 'observed': observed, 'status': status})
    return {'schema_version': 1, 'as_of': as_of.isoformat(), 'notice': NOTICE, 'identity': identity, 'profile_count': len(profiles), 'status_counts': dict(sorted(Counter(r['status'] for r in results).items())), 'results': results}


def csv_safe(value):
    value = str(value)
    probe = value.lstrip()
    while probe.startswith('\ufeff'):
        probe = probe[1:].lstrip()
    if probe.startswith(('=', '+', '-', '@')) or value.startswith(('\t', '\r', '\n')):
        return "'" + value
    return value


def write_reports(report, directory):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    columns = ['source_url', 'observed_at', 'language', 'market', 'field', 'canonical', 'observed', 'status']
    with (directory / 'report.csv').open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, lineterminator='\n', quoting=csv.QUOTE_ALL)
        writer.writeheader()
        writer.writerows({key: csv_safe(row[key]) for key in columns} for row in report['results'])
    esc = html.escape
    rows = []
    for row in report['results']:
        cells = []
        for key in columns:
            value = esc(row[key], quote=True)
            if key == 'source_url':
                value = f'<a href="{value}" rel="noopener noreferrer">{value}</a>'
            cells.append(f'<td>{value}</td>')
        rows.append('<tr>' + ''.join(cells) + '</tr>')
    counts = ''.join(f'<li><strong>{esc(key.replace("_", " "))}</strong>: {value}</li>' for key, value in report['status_counts'].items())
    content = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Entity consistency report</title>
<style>:root{{color-scheme:dark}}*{{box-sizing:border-box}}body{{margin:0;background:#081321;color:#eff7fc;font:16px/1.6 system-ui,sans-serif}}main{{max-width:1400px;margin:auto;padding:clamp(20px,4vw,64px)}}h1{{font-size:clamp(30px,5vw,52px);line-height:1.1}}h2{{font-size:24px}}a{{color:#36d9ee;overflow-wrap:anywhere}}.eyebrow{{color:#36d9ee;letter-spacing:.12em;text-transform:uppercase}}.notice{{border-left:4px solid #36d9ee;padding:20px;background:#0d2539}}.table{{overflow-x:auto}}table{{border-collapse:collapse;width:100%;font-size:14px}}th,td{{padding:12px;text-align:left;vertical-align:top;border-bottom:1px solid #34516a;min-width:120px;overflow-wrap:anywhere;max-width:300px}}th{{color:#36d9ee}}ul{{display:flex;flex-wrap:wrap;gap:12px 32px;padding:0;list-style:none}}footer{{margin-top:40px;color:#b6cadb}}code{{overflow-wrap:anywhere}}</style></head>
<body><main><p class="eyebrow">Offline supplied-data audit</p><h1>Entity consistency report</h1><p>{esc(report['identity']['name'])} · <code>{esc(report['identity']['entity_id'])}</code> · {esc(report['identity']['entity_type'])}</p><p>As of {esc(report['as_of'])} · {report['profile_count']} supplied observations</p><p class="notice">{esc(NOTICE)} Description fields always require human review. Missing data is never agreement.</p><h2>Field outcomes</h2><ul>{counts}</ul><p>Counts describe field comparisons, not an authority score. Language and market are supplied context, not inferred identity variants.</p><div class="table" role="region" aria-label="Field comparison results" tabindex="0"><table><thead><tr>{''.join('<th scope="col">' + esc(c.replace('_', ' ')) + '</th>' for c in columns)}</tr></thead><tbody>{''.join(rows)}</tbody></table></div><footer>Entity Consistency Auditor · Local report · Preserve source context and review differences before editing profiles.</footer></main></body></html>'''
    (directory / 'report.html').write_text(content, encoding='utf-8')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--identity', type=Path, required=True)
    parser.add_argument('--profiles', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--as-of', help='YYYY-MM-DD; default is the local current date')
    args = parser.parse_args(argv)
    try:
        as_of = parse_date(args.as_of, 'as-of') if args.as_of is not None else date.today()
        identity = read_identity(args.identity)
        profiles = read_profiles(args.profiles, as_of)
        report = evaluate(identity, profiles, as_of)
        targets = [(args.output_dir / f'report.{extension}').resolve() for extension in ('json', 'csv', 'html')]
        inputs = [args.identity.resolve(), args.profiles.resolve()]
        for target in targets:
            for source in inputs:
                if target == source or (target.exists() and target.samefile(source)):
                    raise ValueError('output paths must not overwrite input files')
        write_reports(report, args.output_dir)
    except (ValueError, OSError, UnicodeError, csv.Error) as error:
        print(f'Error: {error}', file=sys.stderr)
        return 2
    print(f'Wrote report.json, report.csv and report.html to {args.output_dir}')
    return 0


if __name__ == '__main__':
    sys.exit(main())

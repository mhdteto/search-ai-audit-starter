#!/usr/bin/env python3
"""Offline educational subset lint. Not a schema.org or search eligibility validator."""
import argparse
import html
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

RECOMMENDED = {
    'Person': ('@id', 'name', 'url'),
    'Organization': ('@id', 'name', 'url'),
    'ProfilePage': ('@id', 'url', 'mainEntity'),
    'Article': ('@id', 'headline', 'url', 'author', 'publisher', 'datePublished'),
}
URL_FIELDS = {'url', 'sameAs', 'image', 'mainEntityOfPage', 'contentUrl', 'logo'}
RELATIONS = {'author': {'Person', 'Organization'}, 'publisher': {'Person', 'Organization'}, 'worksFor': {'Organization'}}
NOTICE = 'Educational subset structural lint only. No full schema.org validation, factual verification, Google eligibility, ranking or AI citation assessment.'

class DuplicateKey(ValueError):
    pass

def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateKey('Duplicate JSON key: ' + key)
        result[key] = value
    return result

def http_url(value):
    if not isinstance(value, str) or re.search(r'[\s\x00-\x1f\x7f\\]', value):
        return False
    try:
        parsed = urlsplit(value)
        return (parsed.scheme in ('https', 'http') and bool(parsed.hostname)
                and parsed.username is None and parsed.password is None
                and parsed.port != 0)
    except (ValueError, TypeError):
        return False

def valid_id(value):
    return http_url(value) or (isinstance(value, str) and bool(re.fullmatch(r'#[A-Za-z0-9_.~-]+', value)))

def type_names(value):
    values = value if isinstance(value, list) else [value]
    if not values or any(not isinstance(t, str) or not re.fullmatch(r'(https://schema\.org/)?[A-Za-z][A-Za-z0-9]*', t) for t in values):
        return None
    return {t.rsplit('/', 1)[-1] for t in values}

def lint(data):
    issues = []
    def add(level, code, path, message):
        issues.append({'level': level, 'code': code, 'path': path, 'message': message})
    if not isinstance(data, dict):
        add('error', 'root', '$', 'Subset input must be a JSON object.')
        return issues
    if data.get('@context') != 'https://schema.org':
        add('error', 'context', '$.@context', 'Subset supports exactly "https://schema.org"; other JSON-LD contexts are outside scope.')
    nodes = data.get('@graph', [data])
    if not isinstance(nodes, list) or not nodes:
        add('error', 'graph', '$.@graph', '@graph must be a nonempty list in this subset.')
        return issues
    ids = {}
    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            add('error', 'node', '$.@graph[' + str(index) + ']', 'Graph entries must be objects.')
            continue
        ident = node.get('@id')
        if isinstance(ident, str):
            if ident in ids:
                add('error', 'duplicate-id', '$.@graph[' + str(index) + '].@id', 'Repeated graph definition: ' + ident)
            ids[ident] = node
    # Local means an exact declared ID, a #fragment, or a fragment sharing a
    # document base with a declared ID. Other absolute IDs are external.
    bases = {ident.split('#', 1)[0] for ident in ids if not ident.startswith('#')}
    def walk(value, path):
        if isinstance(value, list):
            for i, item in enumerate(value): walk(item, path + '[' + str(i) + ']')
            return
        if not isinstance(value, dict): return
        if '@context' in value and value['@context'] != 'https://schema.org':
            if path != '$': add('error', 'context', path + '.@context', 'Nested context changes are outside this subset.')
        if '@id' in value and not valid_id(value['@id']):
            add('error', 'id-format', path + '.@id', 'Subset IDs must be HTTP(S) URLs or simple #fragments.')
        names = None
        if '@type' in value:
            names = type_names(value['@type'])
            if names is None:
                add('error', 'type-format', path + '.@type', '@type must be a type name, schema.org HTTPS type URL, or nonempty list of those strings.')
            else:
                for name in sorted(names):
                    if name not in RECOMMENDED:
                        add('warning', 'unsupported-type', path + '.@type', name + ' is not modeled by this kit; no vocabulary membership check was made.')
                    for field in RECOMMENDED.get(name, ()):
                        if field not in value or value[field] in (None, '', []):
                            add('warning', 'recommended-field', path + '.' + field, name + ': kit recommendation missing; not a schema.org legal requirement.')
        elif set(value) != {'@id'} and path != '$':
            add('warning', 'untyped-object', path, 'Object has no @type; semantics not checked.')
        if set(value) == {'@id'} and valid_id(value['@id']):
            ref = value['@id']
            local = ref.startswith('#') or ('#' in ref and ref.split('#', 1)[0] in bases)
            if local and ref not in ids:
                add('error', 'dangling-reference', path + '.@id', 'Unresolved local graph reference: ' + ref)
        for key, item in value.items():
            prop_path = path + '.' + key
            if key in URL_FIELDS:
                for v in item if isinstance(item, list) else [item]:
                    if isinstance(v, dict):
                        if '@id' not in v and not ('contentUrl' in v or 'url' in v):
                            add('warning', 'url-object', prop_path, 'URL-bearing object cannot be checked without @id, url or contentUrl.')
                    elif not http_url(v):
                        add('error', 'url', prop_path, 'Expected an absolute HTTP(S) URL without credentials, whitespace or controls; got ' + repr(v))
            expected = RELATIONS.get(key)
            if key == 'mainEntity' and names and 'ProfilePage' in names:
                expected = {'Person', 'Organization'}
            if expected:
                for target in item if isinstance(item, list) else [item]:
                    actual = None
                    if isinstance(target, dict):
                        ref = target.get('@id')
                        resolved = ids.get(ref) if isinstance(ref, str) else None
                        resolved = resolved if resolved is not None else target
                        actual = type_names(resolved.get('@type')) if '@type' in resolved else None
                    if actual is not None and not (actual & expected):
                        add('warning', 'relationship-type', prop_path, 'Kit model expects ' + '/'.join(sorted(expected)) + '; resolved target has ' + '/'.join(sorted(actual)) + '. Broader schema.org ranges or subclasses are not inferred.')
                    elif not isinstance(target, dict):
                        add('warning', 'relationship-shape', prop_path, 'Kit examples use a typed object or @id reference; this value is outside that relationship model.')
            if not key.startswith('@') or key == '@graph': walk(item, prop_path)
    walk(data, '$')
    if '@graph' not in data and '@type' not in data:
        add('warning', 'untyped-object', '$', 'No @type supplied; semantics not checked.')
    return issues

def inspect_file(path):
    try:
        data = json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=unique_pairs,
                          parse_constant=lambda v: (_ for _ in ()).throw(ValueError('Non-JSON number: ' + v)))
        issues = lint(data)
    except DuplicateKey as exc:
        issues = [{'level': 'error', 'code': 'duplicate-key', 'path': '$', 'message': str(exc)}]
    except (ValueError, UnicodeError, RecursionError) as exc:
        issues = [{'level': 'error', 'code': 'json-syntax', 'path': '$', 'message': str(exc)}]
    except OSError as exc:
        issues = [{'level': 'error', 'code': 'input-read', 'path': '$', 'message': str(exc)}]
    return {'file': path.as_posix(), 'issues': issues}

def render(report):
    esc = lambda v: html.escape(str(v), quote=True)
    rows = []
    for entry in report['files']:
        for issue in entry['issues']:
            rows.append('<tr>' + ''.join('<td>' + esc(v) + '</td>' for v in [entry['file'], issue['level'], issue['code'], issue['path'], issue['message']]) + '</tr>')
    files = ''.join('<li>' + esc(e['file']) + ': ' + str(len(e['issues'])) + ' issue(s)</li>' for e in report['files'])
    return '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Structured data subset lint report</title><style>body{font:16px system-ui;background:#081b30;color:#edf7ff;margin:0;padding:clamp(1rem,4vw,3rem)}main{max-width:1200px;margin:auto}h1{color:#67e8f9}table{border-collapse:collapse;width:100%;background:#102a43}td,th{text-align:left;padding:12px;border:1px solid #36546b;overflow-wrap:anywhere}section{overflow:auto}p{line-height:1.6}.notice{border-left:4px solid #67e8f9;padding:1rem}</style><main><h1>Structured data subset lint</h1><p class="notice">''' + esc(NOTICE) + '</p><p>Errors: ' + str(report['summary']['errors']) + ' · Warnings: ' + str(report['summary']['warnings']) + '</p><ul>' + files + '</ul><section><table><thead><tr><th>File</th><th>Level</th><th>Code</th><th>Path</th><th>Finding</th></tr></thead><tbody>' + ''.join(rows) + '</tbody></table></section></main></html>\n'

def same_file(a, b):
    return a.resolve() == b.resolve() or (a.exists() and b.exists() and a.samefile(b))

def main(argv=None):
    parser = argparse.ArgumentParser(description=NOTICE)
    parser.add_argument('files', nargs='*', type=Path)
    parser.add_argument('--all', metavar='DIRECTORY', type=Path, help='Read all immediate *.json files in a directory')
    parser.add_argument('--output-dir', type=Path, default=Path('reports'))
    args = parser.parse_args(argv)
    files = args.files + (sorted(args.all.glob('*.json')) if args.all else [])
    if not files: parser.error('Supply input JSON files or --all DIRECTORY with *.json files.')
    targets = [args.output_dir / 'report.json', args.output_dir / 'report.html']
    try:
        for target in targets:
            if any(same_file(source, target) for source in files):
                raise ValueError('Input/output collision: ' + str(target))
        if same_file(targets[0], targets[1]):
            raise ValueError('Output/output collision')
        report = {'tool': 'entity-structured-data-kit', 'version': '1.0.0', 'scope': NOTICE, 'files': [inspect_file(p) for p in files]}
        issues = [i for entry in report['files'] for i in entry['issues']]
        report['summary'] = {level + 's': sum(i['level'] == level for i in issues) for level in ('error', 'warning')}
        args.output_dir.mkdir(parents=True, exist_ok=True)
        targets[0].write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        targets[1].write_text(render(report), encoding='utf-8')
    except (OSError, ValueError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print('Errors: {errors}; warnings: {warnings}'.format(**report['summary']))
    return 1 if report['summary']['errors'] else 0

if __name__ == '__main__':
    sys.exit(main())

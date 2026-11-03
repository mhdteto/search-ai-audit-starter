#!/usr/bin/env python3
"""Bounded public-page observations. MIT licensed; no third-party dependencies."""
import argparse
from datetime import datetime, timezone
import html
from html.parser import HTMLParser
import http.client
import ipaddress
import json
from pathlib import Path
import re
import queue
import threading
import socket
import ssl
import sys
import time
from urllib.parse import urljoin, urlsplit, urlunsplit

MAX_BODY = 1024 * 1024
MAX_REDIRECTS = 3
TIMEOUT = 5
MAX_LINKS = 20


def validate_url(url):
    if not isinstance(url, str) or not url or re.search(r'[\x00-\x20\x7f\\]', url):
        raise ValueError('URL contains whitespace, controls or backslashes')
    try:
        p = urlsplit(url)
        port = p.port
        host = p.hostname
    except ValueError as exc:
        raise ValueError('Malformed URL or port') from exc
    if p.scheme not in ('http', 'https') or not host or p.username is not None or p.password is not None:
        raise ValueError('Use an absolute HTTP(S) URL without credentials')
    if p.netloc.endswith(':'):
        raise ValueError('Empty URL port')
    expected = 443 if p.scheme == 'https' else 80
    if port is not None and port != expected:
        raise ValueError('Only the default scheme port is supported (HTTP 80 / HTTPS 443)')
    host = host.rstrip('.').lower()
    if host == 'localhost' or host.endswith('.localhost') or '%' in host:
        raise ValueError('Local hosts and zone identifiers are forbidden')
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        try:
            host = host.encode('idna').decode('ascii')
        except UnicodeError as exc:
            raise ValueError('Invalid hostname') from exc
        if len(host) > 253 or any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label) for label in host.split('.')):
            raise ValueError('Invalid hostname')
    else:
        if not public_ip(ip):
            raise ValueError('Destination IP is not globally routable')
    netloc = '[' + host + ']' if ':' in host else host
    return urlunsplit((p.scheme, netloc, p.path or '/', p.query, ''))


def public_ip(value):
    ip = ipaddress.ip_address(value)
    return ip.is_global and not (ip.is_multicast or ip.is_reserved or ip.is_loopback or ip.is_link_local or ip.is_unspecified) and not getattr(ip, 'ipv4_mapped', None)


def resolve_public(host, port, resolver=None):
    resolver = resolver or socket.getaddrinfo
    results = queue.Queue(maxsize=1)
    def lookup():
        try:
            results.put((True, resolver(host, port, type=socket.SOCK_STREAM)))
        except Exception as exc:
            results.put((False, exc))
    # A daemon worker prevents a stuck system resolver from holding the CLI open.
    threading.Thread(target=lookup, daemon=True).start()
    try:
        success, result = results.get(timeout=TIMEOUT)
    except queue.Empty as exc:
        raise ValueError('DNS resolution timed out') from exc
    if not success:
        raise ValueError('DNS resolution failed: ' + str(result))
    answers = result
    addresses = [item[4][0] for item in answers]
    if not addresses or any(not public_ip(address) for address in addresses):
        raise ValueError('DNS must return only globally routable addresses')
    return addresses[0]


class PinnedHTTPConnection(http.client.HTTPConnection):
    def __init__(self, host, port, address, timeout):
        super().__init__(host, port, timeout=timeout)
        self.address = address
        self.deadline = time.monotonic() + timeout

    def remaining(self):
        seconds = self.deadline - time.monotonic()
        if seconds <= 0:
            raise TimeoutError('Request deadline exceeded')
        return seconds

    def connect(self):
        # Numeric validated address: never resolve the hostname again at connect time.
        self.sock = socket.create_connection((self.address, self.port), self.remaining())
        self._pinned_socket = self.sock
        self.sock.settimeout(self.remaining())


class PinnedHTTPSConnection(PinnedHTTPConnection):
    def connect(self):
        raw = socket.create_connection((self.address, self.port), self.remaining())
        self.sock = raw
        self._pinned_socket = raw
        try:
            raw.settimeout(self.remaining())
            self.sock = ssl.create_default_context().wrap_socket(raw, server_hostname=self.host)
            self._pinned_socket = self.sock
            self.sock.settimeout(self.remaining())
        except BaseException:
            raw.close()
            raise


def live_transport(url):
    url = validate_url(url)
    p = urlsplit(url)
    port = 443 if p.scheme == 'https' else 80
    address = resolve_public(p.hostname, port)
    cls = PinnedHTTPSConnection if p.scheme == 'https' else PinnedHTTPConnection
    connection = cls(p.hostname, port, address, TIMEOUT)
    def expire():
        pinned = getattr(connection, '_pinned_socket', connection.sock)
        if pinned is not None:
            try:
                pinned.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            connection.close()
    # Absolute budget after resolution, in addition to socket operation timeouts.
    watchdog = threading.Timer(TIMEOUT, expire)
    watchdog.daemon = True
    watchdog.start()
    try:
        target = p.path + ('?' + p.query if p.query else '')
        connection.request('GET', target, headers={'User-Agent':'SearchAIDiscoverabilityChecker/1.0', 'Accept-Encoding':'identity', 'Accept':'text/html,application/xml,text/plain;q=0.9,*/*;q=0.1'})
        response = connection.getresponse()
        # Preserve repeated headers rather than silently dropping directives.
        headers = {}
        for name, value in response.getheaders():
            key = name.lower()
            headers[key] = headers[key] + ', ' + value if key in headers else value
        check_headers(headers)
        body = response.read(MAX_BODY + 1)
        if len(body) > MAX_BODY:
            raise ValueError('Response exceeds 1 MiB body limit')
        return {'status':response.status, 'headers':headers, 'body':body.decode('utf-8',errors='replace')}
    finally:
        watchdog.cancel()
        connection.close()


def check_headers(headers):
    if headers.get('content-encoding','identity').strip().lower() not in ('', 'identity'):
        raise ValueError('Encoded response rejected; only identity encoding supported')
    length = headers.get('content-length')
    if length is not None:
        try:
            if int(length) < 0 or int(length) > MAX_BODY:
                raise ValueError('Response Content-Length outside body limit')
        except (ValueError, TypeError) as exc:
            raise ValueError('Invalid or excessive Content-Length') from exc


def fetch(url, transport):
    chain = []
    for step in range(MAX_REDIRECTS + 1):
        url = validate_url(url)
        response = transport(url)
        headers = {str(k).lower(): str(v) for k,v in response.get('headers',{}).items()}
        check_headers(headers)
        body = response.get('body','')
        if not isinstance(body,str) or len(body.encode('utf-8')) > MAX_BODY:
            raise ValueError('Invalid or excessive response body')
        status = response['status']
        if type(status) is not int or not 100 <= status <= 599:
            raise ValueError('Response status must be an integer from 100 to 599')
        chain.append({'url':url,'status':status})
        if status in (301,302,303,307,308) and 'location' in headers:
            if step == MAX_REDIRECTS:
                raise ValueError('Redirect limit exceeded')
            location = headers['location']
            if re.search(r'[\x00-\x20\x7f\\]', location):
                raise ValueError('Unsafe redirect location')
            url = validate_url(urljoin(url, location))
            continue
        return {'url':url,'status':status,'headers':headers,'body':body,'redirect_chain':chain}
    raise ValueError('Redirect limit exceeded')


class PageParser(HTMLParser):
    def __init__(self, base):
        super().__init__(convert_charrefs=True)
        self.base = base
        self.result = {'meta_robots':[], 'canonicals':[], 'internal_links':[], 'json_ld_blocks':0, 'json_ld_invalid_blocks':0, 'json_ld_types':[]}
        self.in_json = False
        self.json_parts = []
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'meta' and (a.get('name') or '').lower() in ('robots','googlebot','bingbot'):
            name = (a.get('name') or '').lower()
            self.result['meta_robots'].append((name + ': ' if name != 'robots' else '') + (a.get('content') or ''))
        if tag == 'link' and 'canonical' in (a.get('rel') or '').lower().split():
            raw = a.get('href') or ''
            value = urljoin(self.base,raw)
            try:
                validate_url(value)
                valid = bool(raw)
            except ValueError:
                valid = False
            self.result['canonicals'].append({'declared':raw,'resolved':value,'valid_http_url':valid})
        if tag == 'a' and a.get('href') and len(self.result['internal_links']) < MAX_LINKS:
            try:
                target=validate_url(urljoin(self.base,a['href']))
            except ValueError:
                return
            if urlsplit(target).netloc == urlsplit(self.base).netloc and target not in self.result['internal_links']:
                self.result['internal_links'].append(target)
        if tag == 'script' and (a.get('type') or '').lower() == 'application/ld+json':
            self.in_json = True
            self.json_parts = []
    def handle_data(self,data):
        if self.in_json:
            self.json_parts.append(data)
    def handle_endtag(self,tag):
        if tag == 'script' and self.in_json:
            self.in_json = False
            self.result['json_ld_blocks'] += 1
            try:
                data = json.loads(''.join(self.json_parts))
                def visit(value, depth=0):
                    if depth > 40:
                        return
                    if isinstance(value,dict):
                        types = value.get('@type',[])
                        types = [types] if isinstance(types,str) else types
                        if isinstance(types,list):
                            self.result['json_ld_types'].extend(t for t in types if isinstance(t,str))
                        for child in value.values(): visit(child,depth+1)
                    elif isinstance(value,list):
                        for child in value: visit(child,depth+1)
                visit(data)
            except (ValueError,RecursionError):
                self.result['json_ld_invalid_blocks'] += 1


def parse_page(body,url):
    parser = PageParser(url)
    parser.feed(body)
    parser.result['json_ld_types'] = sorted(set(parser.result['json_ld_types']))
    return parser.result


def parse_robots(body):
    groups, directives, sitemaps = [], [], []
    current = None
    seen_rules = False
    for raw in body.splitlines():
        line = raw.split('#',1)[0].strip()
        if ':' not in line:
            continue
        key,value = (part.strip() for part in line.split(':',1))
        key = key.lower()
        directives.append({'directive':key,'value':value})
        if key == 'sitemap':
            sitemaps.append(value)
        elif key == 'user-agent':
            if current is None or seen_rules:
                current = {'user_agents':[], 'rules':[]}
                groups.append(current)
                seen_rules = False
            current['user_agents'].append(value)
        elif current is not None:
            current['rules'].append({'directive':key,'value':value})
            seen_rules = True
    return {'groups':groups,'directives':directives,'sitemaps':sitemaps,'interpretation':'Manual review required; no engine-specific allow/deny decision is calculated.'}


def without_body(response):
    result = {k:v for k,v in response.items() if k not in ('body','headers')}
    allowed = {'content-type','x-robots-tag','link','location','content-encoding','content-length'}
    result['headers'] = {key:value for key,value in response.get('headers',{}).items() if key in allowed}
    return result


def analyze(url,transport,collected_at):
    url = validate_url(url)
    report = {'schema_version':1,'mode':'observational','input_url':url,'collected_at':collected_at,
              'limits':{'resources':3,'http_requests':12,'redirects_per_resource':MAX_REDIRECTS,'body_bytes_per_response':MAX_BODY,'dns_wait_seconds':TIMEOUT,'request_budget_seconds':TIMEOUT,'internal_link_sample':MAX_LINKS},
              'scope':'One page, its origin robots.txt, and at most one same-origin sitemap candidate. Redirects bounded to three per resource.',
              'interpretation':'HTTP success, directives and markup do not establish indexing, ranking, AI retrieval or citations.'}
    page = fetch(url,transport)
    report['page'] = without_body(page)
    content_type = page['headers'].get('content-type','').split(';',1)[0].strip().lower()
    if 200 <= page['status'] < 300 and content_type in ('text/html','application/xhtml+xml'):
        report['page'].update(parse_page(page['body'],page['url']))
        report['page']['analysis'] = 'HTML observations only'
        report['page']['base_element_handling'] = 'Links resolve against final page URL; HTML base elements are not applied.'
    else:
        report['page']['analysis'] = 'skipped: response is not successful HTML'
    p = urlsplit(page['url'])
    origin = p.scheme + '://' + p.netloc
    candidates = []
    try:
        robots = fetch(origin + '/robots.txt',transport)
        report['robots'] = without_body(robots)
        status = robots['status']
        availability = 'available' if 200 <= status < 300 else ('missing (404); no robots file observed' if status == 404 else 'forbidden (403); policy unknown' if status == 403 else 'unavailable; policy unknown')
        report['robots']['availability'] = availability
        if 200 <= status < 300:
            report['robots'].update(parse_robots(robots['body']))
            candidates = report['robots']['sitemaps']
    except (ValueError,OSError,http.client.HTTPException) as exc:
        report['robots'] = {'availability':'request failed; policy unknown','error':str(exc)}
    report['sitemap'] = {'status':'not requested','note':'No valid same-origin declaration; /sitemap.xml is the bounded fallback.'}
    candidate = origin + '/sitemap.xml'
    for item in candidates:
        try:
            safe = validate_url(item)
            if urlsplit(safe).netloc == p.netloc and urlsplit(safe).scheme == p.scheme:
                candidate = safe
                break
        except ValueError:
            continue
    try:
        sitemap = fetch(candidate,transport)
        report['sitemap'] = without_body(sitemap)
        report['sitemap']['note'] = 'Response observed only; XML validity, listed URLs and sitemap index children are not evaluated.'
    except (ValueError,OSError,http.client.HTTPException) as exc:
        report['sitemap'] = {'status':'request failed','error':str(exc)}
    return report


def fixture_transport(path):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(data,dict):
        raise ValueError('Fixture root must be an object')
    stamp = data['collected_at']
    if not isinstance(stamp,str):
        raise ValueError('Fixture collected_at must be a string')
    resources = data['responses']
    if not isinstance(resources,dict):
        raise ValueError('Fixture responses must be an object')
    for url, response in resources.items():
        if validate_url(url) != url or not isinstance(response,dict):
            raise ValueError('Fixture records require normalized URLs and response objects')
        if type(response.get('status')) is not int or not 100 <= response['status'] <= 599:
            raise ValueError('Fixture status must be an integer from 100 to 599')
        if not isinstance(response.get('headers'),dict) or not all(isinstance(k,str) and isinstance(v,str) for k,v in response['headers'].items()):
            raise ValueError('Fixture headers must map strings to strings')
        if not isinstance(response.get('body'),str):
            raise ValueError('Fixture body must be a string')
    def transport(url):
        if url not in resources:
            raise ValueError('Offline fixture has no response for ' + url)
        return resources[url]
    return transport,stamp


def review_findings(report):
    findings = []
    page = report.get('page',{})
    status = page.get('status')
    if isinstance(status,int) and not 200 <= status < 300:
        findings.append('Page returned HTTP ' + str(status) + '. Review availability and response intent before markup changes.')
    directives = page.get('meta_robots',[]) + [page.get('headers',{}).get('x-robots-tag','')]
    if any(re.search(r'\b(noindex|none)\b', item, re.I) for item in directives):
        findings.append('A noindex or none token is present. Review the intended audience and provider-specific semantics; do not remove it automatically.')
    canonicals = page.get('canonicals',[])
    if page.get('analysis') == 'HTML observations only' and not canonicals:
        findings.append('No canonical link was observed. Review whether a canonical is appropriate for this page.')
    if len(canonicals) > 1:
        findings.append('Multiple canonical links were observed. Review the intended preferred URL.')
    if any(not item.get('valid_http_url') for item in canonicals):
        findings.append('A canonical href is empty or fails the HTTP(S) syntax/public-literal check. Review its value; target availability was not checked.')
    robots = report.get('robots',{})
    if robots.get('availability') != 'available':
        findings.append('Robots availability: ' + robots.get('availability','unknown') + '. Review the resource and provider policy; no allow/deny conclusion is calculated.')
    sitemap = report.get('sitemap',{})
    if not isinstance(sitemap.get('status'),int) or not 200 <= sitemap['status'] < 300:
        findings.append('The sitemap candidate was not successfully fetched. Review its declaration, URL and response.')
    if page.get('json_ld_invalid_blocks',0):
        findings.append('At least one JSON-LD block could not be parsed. Review the source JSON; schema semantics were not validated.')
    if not findings:
        findings.append('No additional review flags from these limited observations. This is not evidence of indexing, ranking, AI retrieval or citations.')
    return findings


def render_html(report):
    escape = lambda value: html.escape(str(value), quote=True)
    page = report.get('page',{})
    robots = report.get('robots',{})
    sitemap = report.get('sitemap',{})
    directives = page.get('meta_robots',[]) + ([page.get('headers',{}).get('x-robots-tag')] if page.get('headers',{}).get('x-robots-tag') else [])
    summary = [
        ('Collection',report.get('collected_at','unknown')),
        ('Transport',report.get('transport','unknown')),
        ('Page HTTP status',page.get('status','unknown')),
        ('Final page URL',page.get('url',report.get('input_url','unknown'))),
        ('HTML analysis',page.get('analysis','unknown')),
        ('Canonical links observed',len(page.get('canonicals',[])) if 'canonicals' in page else 'not analyzed'),
        ('Robots directives (meta and header)',' | '.join(directives) or 'none observed / not analyzed'),
        ('robots.txt',robots.get('availability','unknown')),
        ('Sitemap candidate response',sitemap.get('status','unknown')),
        ('JSON-LD blocks',page.get('json_ld_blocks','not analyzed')),
        ('Internal links sampled',len(page.get('internal_links',[])) if 'internal_links' in page else 'not analyzed')]
    rows = ''.join('<dt>'+escape(key)+'</dt><dd>'+escape(value)+'</dd>' for key,value in summary)
    findings = ''.join('<li>'+escape(value)+'</li>' for value in review_findings(report))
    evidence = escape(json.dumps(report,indent=2,ensure_ascii=False))
    return '<!doctype html>\n<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Search &amp; AI discoverability observations</title><style>body{background:#071a2e;color:#e3f2fa;font:16px/1.6 system-ui,sans-serif;margin:0}main{max-width:1080px;margin:auto;padding:40px 24px}h1,h2{color:#60e5ef;line-height:1.15}p{max-width:72ch}pre,dl,ul{background:#102b42;border:1px solid #24526c;border-radius:12px;padding:24px}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px}dt{color:#60e5ef;font-weight:600}dd{margin:0 0 16px;overflow-wrap:anywhere}ul{padding-left:44px}li{margin:12px 0}small{color:#b2cddd}summary{cursor:pointer;color:#60e5ef;padding:12px 0}</style></head><body><main><small>SEARCH · EVIDENCE · INTERPRETATION</small><h1>Search &amp; AI discoverability observations</h1><p>This bounded technical snapshot does not establish indexing, rankings or AI citations. Review the observed directives and the limits before making changes.</p><h2>Observed snapshot</h2><dl>' + rows + '</dl><h2>Manual review</h2><ul>' + findings + '</ul><details><summary>Full JSON evidence and request limits</summary><pre>' + evidence + '</pre></details><p>Generated by Search AI Discoverability Checker. Fictional fixture reports are labeled in the evidence.</p></main></body></html>\n'


def output_paths(directory,fixture=None):
    directory = Path(directory)
    targets = [directory/'report.json', directory/'report.html']
    if fixture is not None:
        source = Path(fixture)
        for target in targets:
            if target.resolve() == source.resolve() or (target.exists() and source.exists() and target.samefile(source)):
                raise ValueError('Output collides with fixture input')
    if targets[0].resolve() == targets[1].resolve() or (all(p.exists() for p in targets) and targets[0].samefile(targets[1])):
        raise ValueError('Output paths collide')
    if any(p.is_symlink() for p in targets):
        raise ValueError('Output symlinks are forbidden')
    return targets


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('url')
    parser.add_argument('--output-dir',default='reports')
    parser.add_argument('--fixture',help='Synthetic offline JSON transport; makes no network calls')
    args = parser.parse_args(argv)
    try:
        url = validate_url(args.url)
        targets = output_paths(args.output_dir,args.fixture)
        if args.fixture:
            transport,stamp = fixture_transport(args.fixture)
        else:
            transport,stamp = live_transport,datetime.now(timezone.utc).isoformat()
        report = analyze(url,transport,stamp)
        report['transport'] = 'synthetic offline fixture' if args.fixture else 'live public HTTP(S)'
        serialized = json.dumps(report,indent=2,ensure_ascii=False) + '\n'
        rendered = render_html(report)
        Path(args.output_dir).mkdir(parents=True,exist_ok=True)
        for target,content in zip(targets,(serialized,rendered)):
            with target.open('w',encoding='utf-8',newline='\n') as stream:
                stream.write(content)
        print('Wrote ' + str(targets[0]) + ' and ' + str(targets[1]))
        return 0
    except (ValueError,OSError,KeyError,TypeError,http.client.HTTPException) as exc:
        print('Check failed: ' + str(exc),file=sys.stderr)
        return 2

if __name__ == '__main__':
    sys.exit(main())

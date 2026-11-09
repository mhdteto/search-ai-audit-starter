# Triage a Lighthouse robots.txt failure under a strict CSP

If Lighthouse reports a CSP violation while fetching robots.txt, record two separate observations: what the audit could fetch and what the server returned to a direct HTTP request.

## 1. Capture the page policy and the direct response

Set these variables to the public page and final origin you are authorized to inspect. Use the page's final origin if it redirects to another host.

```bash
page='https://example.org/'
origin='https://example.org'
curl -sS --max-time 10 -D - -o /dev/null "$page"
curl -sS --max-time 10 -i "$origin/robots.txt"
```

The first command shows response headers. If the site sets CSP in an HTML meta element, inspect the document separately. The second command shows the HTTP status, headers and body for robots.txt. These commands do not follow redirects. If the robots response redirects, record the status and Location, then inspect the permitted destination separately.

## 2. Preserve the evidence from both checks

| Evidence | Record |
| --- | --- |
| Lighthouse | Version, browser version, page URL, date and exact robots.txt audit explanation. |
| Direct HTTP | Requested URL, status, redirects, content type and robots.txt body. |
| CSP | The policy on the tested document and where it was declared. |

For example, if the audit reports a CSP violation and direct HTTP returns 200 with robots directives, record both outcomes. Review the rules for the crawler in scope. A 200 response alone does not establish rule validity, crawler access, indexing or ranking. Keep the production CSP intact while investigating the audit.

## 3. Save a repeatable observation

From the Starter root, run the bounded live check against an authorized page:

```bash
python3 audit.py live "$page" --output-dir reports/live
```

Save the resulting JSON report alongside the Lighthouse output and record the conditions. [Starter live workflow](../README.md#3-observe-one-real-public-page-separately) · [French quick-start](QUICKSTART.fr.md)

This procedure was checked on a local fixture. A direct GET returned the same robots.txt body with HTTP 200 when the HTML document used either `connect-src 'none'` or `connect-src 'self'`. Lighthouse behavior is documented by the upstream reporter. [Lighthouse issue #17292](https://github.com/GoogleChrome/lighthouse/issues/17292)

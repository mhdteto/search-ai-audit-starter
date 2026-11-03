# Entirely fictional authority workflow

Alex Rowan, Cedar Notes, publishers, claims, source reviews, page responses, AI engines and answers are invented teaching inputs. Reserved example domains are placeholders. No client outcome or real AI measurement is included. Reports are actual output of the five pinned Python programs.

## Reproduce

Download this repository’s Code → Download ZIP, extract it, then open a terminal in examples/fictional-workflow/. Python 3.10+ is recommended by the upstream projects; this exact bundle is also exercised on Python 3.9.6. Standard library only. No packages, account, API key or network calls are needed.

```sh
python3 run_demo.py
```

The runner replaces files within reports/ and asserts the documented observations. Keep your own data elsewhere. It never edits the inputs. Read each script's --help and repository documentation before adapting it.

- inputs/: seven entirely fictional input files.
- tools/: five unmodified, pinned source scripts with their license notices.
- versions.json: exact public GitHub source commits.
- reports/: deterministic original CLI outputs. The website copies add only a noindex meta directive to HTML for hosting.

## Read the outcome

Identity: four profiles produce six matches, two approved aliases, two mismatches, three missing fields and three descriptions requiring manual review. These are field counts, not a score.

Evidence: three claims. The chair claim has support and a contradiction. Duplicate publisher labels normalize to one independent-support publisher. The offices claim has no evidence. All support/relationship labels are invented human declarations; the program verifies none of them.

Structured data: zero errors/warnings in a narrow educational subset; not proof of truth, complete schema.org validity or Google eligibility. The fictional visible-copy brief is: Alex Rowan is Research Director at Cedar Notes; Cedar Notes publishes educational reading-journal notes; Alex authored the named reading-journal article. The disputed forum and office claims must not be added to the markup.

Citations: six fabricated answers, five raw citation rows. English / United Kingdom: 2 cited answers out of 4, three normalized explicit citations across answers. French / France: 1 out of 2, one citation. Both fractions equal 50% in this tiny invented dataset. No benchmark, causal comparison or international visibility conclusion follows.

Technical fixture: synthetic page HTTP 200, canonical, one JSON-LD block, robots and sitemap observations; no indexing or retrieval conclusion.

## Rights and attribution

Created by Mohammed Teto, https://mohammedteto.com. Original synthetic inputs, this walkthrough and generated examples: CC BY 4.0. Source code and original project documentation retain their included upstream licenses; every bundled tool is by Mohammed Teto and its versioned repository is listed in versions.json. This runner is MIT licensed: permission is granted to use, copy, modify, distribute, sublicense and sell it with this notice; provided as is, without warranty or liability.

## Verify the frozen teaching snapshot

The tools/ copies are deliberately frozen at versions.json commits. They are not installed packages or live copies of their repositories. source-script-hashes.json records the original Git blob hashes. New functionality belongs in the source tool repository.

From this repository’s root:

```sh
python3 tools/verify_connected_demo.py
```

[Tool library](../../README.md) · [Measurement protocol](../../docs/measurement-protocol.md)

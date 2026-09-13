# Review package Slice 3 — validation record

Implementation baseline: `standards-atlas-current-202609132150.zip`.
Baseline SHA-256: `d8e63211dbad7ca66af14f3e5301b06485a56f8858387d3ce3d400396ee0c2e6`.

## Scope and authority

The human-only `review-workbench` service adds paginated source-bound presentation, safe
literal evidence rendering, typed predicate editors, atomic human review batches,
Development/Holdout coverage, persisted bookmarks and a separate Holdout assessment/exposure
ledger. It reuses the source, selection, proposal and decision contracts from Slices 1/2.
No model is started and no qualification/acceptance/release policy is changed. Model/MCP
interfaces cannot record human decisions through this service. Reviewer identity is declared
local provenance, not cryptographic authentication.

## Executed regression checks

| Check | Result |
| --- | --- |
| Architecture and unit regression | 2,660 passed, 9 skipped; 242 warnings. |
| Integration, contract and property directories | 172 passed, 4 skipped. |
| Initial Chromium DOM/interaction suite through an ASGI bridge | 5 passed; desktop and narrow-screen layout checked. |
| Live loopback Uvicorn/httpx smoke test | Passed: HTML, JavaScript module responses, same-origin/CSRF guards and an explicit saved decision. |
| Changed Python files: AST, imports, line lengths and `compileall` | Passed. |
| JavaScript module syntax: `node --experimental-default-type=module --check` | Passed for all three modules. |

Test groups overlap and must not be added as independent counts. The broad regression ran
before the final UI identity-change guard and its sixth browser test. Final overlay and browser
results below cover those final additions and formatting cleanup. Browser tests are opt-in
and account for five skips in the recorded broad run (six after the final added browser test).

## Covered behavior

Synthetic tests exercise fixed/replayable materialized queue order, paging/filter bounds,
source completeness and structural indices, exact quoted evidence with overlaps and Unicode,
server-side Holdout response filtering, explicit assessment and repeat-safe exposure logging,
no implicit disclosure of later model proposals, reviewer-specific resume, typed false/null/
empty decisions, explicit human attestation, exact proposal confirmation, atomic rejection of
invalid batches, stale/forged/foreign view rejection, preserved human revisions, and complete
compatibility with the existing suite importer. CLI tests show that review startup needs no
LLM configuration/manifests and refuses network bind addresses.

Security tests cover same-origin including ports, hostile Host/Origin and fetch-site headers,
CSRF and JSON requirements, invalid/oversized payloads, registry paths/symlinks, source and
journal fingerprints, process-bound view receipts and absence of publication/model endpoints.
A rendered HTML/script-shaped model rationale remains literal text, never an executed node.

## Browser validation modes

The installed Chromium has an administrator URL blocklist that prevents navigation even to
loopback (`ERR_BLOCKED_BY_ADMINISTRATOR`). That restriction was not changed. To exercise the
actual DOM and application code, tests load the checked-in assets locally and bridge `fetch`
to Starlette's ASGI test client. The bridge bundles the three modules only inside the test
fixture and does not change shipped assets, server security or production network behavior.
The live Uvicorn/httpx test separately exercises actual loopback HTTP transport.

This combination is **not** a successful direct Chromium-to-server network test. On an
unrestricted local test host, the default browser mode uses the live loopback server:

```bash
STANDARDS_ATLAS_BROWSER_TESTS=1 \
  uv run --extra chat --with playwright pytest -q \
  tests/unit/application/semantic_qualification/test_review_workbench_browser.py
```

Install a compatible Playwright Chromium first, or set `STANDARDS_ATLAS_CHROMIUM` to an
installed executable. `STANDARDS_ATLAS_BROWSER_BRIDGE=1` explicitly selects the isolated
ASGI bridge mode. `STANDARDS_ATLAS_REVIEW_SCREENSHOT` optionally writes a synthetic UI screenshot.

## Limits

Ruff and Hypothesis are unavailable in this environment. Dependency installation was attempted
but DNS/network access failed. The AST/import/line-length checks are not a substitute for Ruff;
no Ruff pass is claimed. Other conditional skips concern the optional MCP SDK/private fixtures.
No live Codex interaction, production standard annotation or productive qualification run was
performed. All newly stored test decisions and model identities are synthetic.

The local workbench journal is not embedded in the existing suite publication in this slice;
retain the whole review-package directory as its exposure audit record. A real Holdout-use
declaration is still required. End-to-end workflow/archival integration remains in Slice 4.

## Final changed-file overlay verification

The changed-file ZIP was applied to a freshly extracted copy of the uploaded baseline.
Tests ran from that independent checkout, with `PYTHONPATH=src` resolving to the overlay:

| Final check | Result |
| --- | --- |
| Targeted overlay regression: architecture, schemas, Slices 1/2/3, existing web adapter and chat CLI | 235 passed, 1 skipped; 161 warnings. |
| Final Chromium DOM/interaction suite through the explicit ASGI bridge | 6 passed; 8 warnings. |
| ZIP contents | 31 new/changed project-relative files; no removals, private Corpus data, decisions, caches or logs. |
| Overlay/source byte comparison and unchanged-baseline verification | Passed. |
| Staged whitespace check and ZIP integrity | Passed. |

The sixth browser test verifies that editing the reviewer/package setup cannot silently save
or reveal under the previously opened identity. The final JavaScript modules also passed
Node syntax checks. Only this validation record and a wording correction in the user guide
were updated after those final overlay tests; application and test code were unchanged.

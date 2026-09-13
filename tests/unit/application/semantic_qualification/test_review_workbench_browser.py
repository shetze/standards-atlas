"""Opt-in real-browser tests against a live loopback server and synthetic review sources.

STANDARDS_ATLAS_BROWSER_TESTS=1 runs these tests. Chromium can be selected with
STANDARDS_ATLAS_CHROMIUM; otherwise Playwright's installed browser is used.
"""

import os
import re
import socket
import threading
import time
from pathlib import Path

import pytest
from test_review_package import make_review
from test_review_workbench import model_proposal

from standards_atlas.adapters.web.review_security import ReviewWorkbenchHttpConfig
from standards_atlas.adapters.web.review_workbench import create_review_workbench_app
from standards_atlas.application.review_workbench import ReviewWorkbenchService
from standards_atlas.application.semantic_qualification.review_package.model import (
    EvidenceQuote,
    SemanticPredicate,
)
from standards_atlas.application.semantic_qualification.review_package.service import (
    load_review,
    record_proposal,
)

pytestmark = pytest.mark.skipif(
    os.environ.get("STANDARDS_ATLAS_BROWSER_TESTS") != "1",
    reason="opt-in real Chromium tests",
)


@pytest.fixture
def browser_review(tmp_path):
    playwright = pytest.importorskip("playwright.sync_api")
    uvicorn = pytest.importorskip("uvicorn")
    root, _, _, _ = make_review(tmp_path)
    package, state = load_review(root)
    dev = next(c.example_id for c in package.cases if c.split == "development")
    holdout = next(c.example_id for c in package.cases if c.split == "holdout")
    source = next(s for s in package.population if s.example_id == dev)
    record_proposal(
        root,
        expected_revision=state.revision,
        example_id=dev,
        attribute="role_semantics_present",
        predicate=SemanticPredicate(equals=True),
        producer="Synthetic browser fixture",
        producer_kind="model",
        model="test-only-model",
        rationale='<img src=x onerror="window.__atlasPwned=true"> <script>bad()</script>',
        provenance="synthetic-test-only",
        evidence=(EvidenceQuote(quote=source.text),),
    )
    held_source = next(s for s in package.population if s.example_id == holdout)
    model_proposal(root, holdout, text=held_source.text)
    bridge_mode = os.environ.get("STANDARDS_ATLAS_BROWSER_BRIDGE") == "1"
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    app = create_review_workbench_app(
        ReviewWorkbenchService(root.parent), ReviewWorkbenchHttpConfig(port=port)
    )
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.02)
    assert server.started
    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(
            executable_path=os.environ.get("STANDARDS_ATLAS_CHROMIUM") or None,
            headless=True,
            args=["--no-sandbox"],
        )
        page = browser.new_page(viewport={"width": 1600, "height": 1100})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        if bridge_mode:
            # Isolated DOM execution when browser network navigation is administratively
            # disabled. The ASGI bridge does not relax browser/HTTP security in production.
            from starlette.testclient import TestClient

            client = TestClient(app, base_url=f"http://127.0.0.1:{port}")
            assets = (
                Path(__file__).resolve().parents[4]
                / "src/standards_atlas/resources/web/review_workbench"
            )

            def bridge(_source, path, options):
                response = client.request(
                    options.get("method", "GET"),
                    path,
                    headers=options.get("headers", {}),
                    content=options.get("body"),
                )
                return {"status": response.status_code, "body": response.json()}

            page.expose_binding("__atlasBridge", bridge)
            storage = {}

            def mount():
                html = (assets / "index.html").read_text()
                html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.S)
                html = re.sub(r"<link[^>]*>", "", html)
                page.set_content(html)
                page.add_style_tag(content=(assets / "app.css").read_text())
                page.evaluate(
                    """data => {
                    window.__atlasStorage = data;
                    Object.defineProperty(window, 'localStorage', {configurable:true, value:{
                        getItem: key => window.__atlasStorage[key] || null,
                        setItem: (key, value) => {window.__atlasStorage[key] = value;}
                    }});
                    window.fetch = async (path, options={}) => {
                        const r = await window.__atlasBridge(path, options);
                        return {status:r.status, ok:r.status>=200 && r.status<300,
                                json:async()=>r.body};
                    };
                }""",
                    storage,
                )
                scripts = []
                for name in ("format.js", "editors.js", "app.js"):
                    text = (assets / name).read_text()
                    text = re.sub(r"^import .*?;\n", "", text, flags=re.M)
                    scripts.append(re.sub(r"\bexport (?=(?:const|function))", "", text))
                page.evaluate("(async()=>{\n" + "\n".join(scripts) + "\n})()")

            def reload_dom():
                storage.update(page.evaluate("window.__atlasStorage"))
                mount()

            page._atlas_reload_dom = reload_dom
            mount()
        else:
            page.goto(f"http://127.0.0.1:{port}")
        page.locator("#packageSelect option[value=review]").wait_for(state="attached")
        page.fill("#reviewer", "Synthetic human reviewer")
        page.select_option("#packageSelect", "review")
        page.click("#openPackage")
        page.locator("#caseContent").wait_for(state="visible")
        page.wait_for_function("document.body.dataset.busy === 'false'")
        yield page, root, dev, holdout
        assert not errors, errors
        browser.close()
    server.should_exit = True
    thread.join(timeout=10)
    sock.close()
    assert not thread.is_alive()


def wait_idle(page):
    page.wait_for_function("document.body.dataset.busy === 'false'")


def choose_correction(page, attribute, *, scalar=None, empty=False):
    card = page.locator(f'.attribute-card[data-attribute="{attribute}"]')
    card.locator(".decision-fields > label select").select_option("corrected")
    if scalar is not None:
        card.locator(".value-editor select").select_option(label=scalar)
    if empty:
        card.locator(".value-editor input[type=checkbox]").last.check()
    card.locator(".decision-fields > label textarea").fill("Synthetic independently checked value.")
    return card


def test_browser_renders_full_source_evidence_and_never_executes_proposals(browser_review):
    page, root, dev, holdout = browser_review
    source = next(s for s in load_review(root)[0].population if s.example_id == dev)
    assert page.locator("#sourceText").text_content() == source.text
    assert page.locator("#sourceText mark").count() > 0
    assert page.locator(".proposal img, .proposal script").count() == 0
    assert page.evaluate("window.__atlasPwned") is None
    page.uncheck("#showEvidence")
    assert page.locator("#sourceText mark").count() == 0
    assert not load_review(root)[1].decisions
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    # Screenshot is diagnostic evidence, not a shipped fixture or production review.
    screenshot = os.environ.get("STANDARDS_ATLAS_REVIEW_SCREENSHOT")
    if screenshot:
        page.check("#showEvidence")
        page.screenshot(path=screenshot, full_page=True)
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


def test_browser_bulk_stages_only_visible_proposals_then_requires_explicit_attestation(
    browser_review,
):
    page, root, dev, _ = browser_review
    page.click("#selectSuggested")
    assert not load_review(root)[1].decisions
    page.click("#save")
    wait_idle(page)
    assert "ausdrücklich bestätigen" in page.locator("#error").inner_text()
    assert not load_review(root)[1].decisions
    page.check("#attested")
    page.click("#save")
    wait_idle(page)
    assert "gespeichert" in page.locator("#notice").inner_text()
    decisions = load_review(root)[1].decisions
    assert decisions and all(d.example_id == dev for d in decisions)
    assert not (root / "development.yaml").exists()


def test_browser_typed_false_null_and_empty_are_not_unreviewed(browser_review):
    page, root, _, _ = browser_review
    choose_correction(page, "role_semantics_present", scalar="Nein (false)")
    choose_correction(page, "primary_function", scalar="Keine primäre Zuordnung (null)")
    card = choose_correction(page, "process_functions")
    card.locator(".value-editor .choices input").evaluate_all(
        "nodes => nodes.forEach(n => n.checked = false)"
    )
    page.check("#attested")
    page.click("#save")
    wait_idle(page)
    assert "leere Liste ausdrücklich" in page.locator("#error").inner_text()
    assert not load_review(root)[1].decisions
    card.locator(".value-editor input[type=checkbox]").last.check()
    page.click("#save")
    wait_idle(page)
    assert page.locator("#error").is_hidden()
    values = {d.attribute: d.predicate.model_dump() for d in load_review(root)[1].decisions}
    assert values == {
        "role_semantics_present": {"equals": False},
        "primary_function": {"equals": None},
        "process_functions": {"equals": []},
    }


def test_browser_holdout_reveal_and_resume_do_not_confirm_any_annotation(browser_review):
    page, root, _, holdout = browser_review
    page.locator(f'button[data-example-id="{holdout}"]').click()
    wait_idle(page)
    assert page.locator("#blindPanel").is_visible()
    assert page.locator("#sourceText mark").count() == 0
    assert "SENTINEL-MODEL-RATIONALE" not in page.locator("#attributes").inner_text()
    page.fill("#assessment", "My source-based first impression: role statement requires scrutiny.")
    page.click("#reveal")
    wait_idle(page)
    assert "SENTINEL-MODEL-RATIONALE" in page.locator("#attributes").inner_text()
    assert page.locator("#sourceText mark").count() > 0
    assert not load_review(root)[1].decisions
    if hasattr(page, "_atlas_reload_dom"):
        page._atlas_reload_dom()
    else:
        page.reload()
    page.click("#openPackage")
    wait_idle(page)
    current = page.locator(f'button[data-example-id="{holdout}"]').get_attribute("aria-current")
    assert current == "true"
    assert page.locator("#blindPanel").is_hidden()
    assert not load_review(root)[1].decisions


def test_browser_stale_save_preserves_inputs_and_never_retries_as_new_approval(browser_review):
    page, root, dev, _ = browser_review
    card = choose_correction(page, "role_semantics_present", scalar="Nein (false)")
    model_proposal(root, dev)
    page.check("#attested")
    page.click("#save")
    wait_idle(page)
    assert "stale review revision" in page.locator("#error").inner_text()
    assert card.locator(".decision-fields > label select").input_value() == "corrected"
    assert not load_review(root)[1].decisions
    page.once("dialog", lambda dialog: dialog.accept())
    page.click("#reloadCase")
    wait_idle(page)
    card = page.locator('.attribute-card[data-attribute="role_semantics_present"]')
    assert card.locator(".decision-fields > label select").input_value() == ""
    assert not load_review(root)[1].decisions


def test_browser_changed_reviewer_cannot_silently_approve_under_old_identity(browser_review):
    page, root, dev, _ = browser_review
    choose_correction(page, "role_semantics_present", scalar="Nein (false)")
    page.fill("#reviewer", "Changed human identity")
    page.check("#attested")
    page.click("#save")
    wait_idle(page)
    assert "Reviewer oder Paket wurde geändert" in page.locator("#error").inner_text()
    assert not load_review(root)[1].decisions

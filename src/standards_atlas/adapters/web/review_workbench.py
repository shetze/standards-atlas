"""Paginated, loopback-only HTML human review adapter; no inference or publication routes."""

from __future__ import annotations

import secrets
from pathlib import Path

from pydantic import ValidationError

from standards_atlas.application.review_workbench import ReviewWorkbenchService
from standards_atlas.application.review_workbench.model import (
    BookmarkSubmission,
    DecisionSubmission,
    RevealSubmission,
)

from .review_security import ReviewSecurityMiddleware, ReviewWorkbenchHttpConfig, ViewReceipts


def create_review_workbench_app(
    service: ReviewWorkbenchService,
    config: ReviewWorkbenchHttpConfig | None = None,
):
    try:
        from starlette.applications import Starlette
        from starlette.concurrency import run_in_threadpool
        from starlette.responses import FileResponse, JSONResponse
        from starlette.routing import Mount, Route
        from starlette.staticfiles import StaticFiles
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "Review workbench dependencies are missing; install the 'chat' extra"
        ) from exc
    config = config or ReviewWorkbenchHttpConfig()
    assets = Path(__file__).resolve().parents[2] / "resources" / "web" / "review_workbench"
    csrf = secrets.token_urlsafe(32)
    receipts = ViewReceipts()

    async def index(_request):
        return FileResponse(assets / "index.html")

    async def bootstrap(_request):
        return JSONResponse(
            {
                "service": "review-workbench",
                "api_version": "1.0",
                "csrf_token": csrf,
                "reviewer_identity": "self-declared",
            }
        )

    async def packages(_request):
        return JSONResponse(await run_in_threadpool(service.list_packages))

    async def package(request):
        return JSONResponse(
            await run_in_threadpool(
                service.get_package,
                request.path_params["handle"],
                reviewer=request.query_params.get("reviewer", ""),
            )
        )

    async def cases(request):
        q = request.query_params
        return JSONResponse(
            await run_in_threadpool(
                service.list_cases,
                request.path_params["handle"],
                split=q.get("split", "all"),
                status=q.get("status", "all"),
                query=q.get("q", ""),
                document_key=q.get("document_key", ""),
                attribute=q.get("attribute", ""),
                limit=int(q.get("limit", "10")),
                offset=int(q.get("offset", "0")),
                anchor=q.get("anchor", ""),
            )
        )

    async def case(request):
        value = await run_in_threadpool(
            service.get_case,
            request.path_params["handle"],
            request.query_params.get("example_id", ""),
            reviewer=request.query_params.get("reviewer", ""),
        )
        value["view_token"] = receipts.sign(value.pop("view"))
        return JSONResponse(value)

    async def decisions(request):
        submission = DecisionSubmission.model_validate(await request.json())
        view = receipts.verify(submission.view_token)
        return JSONResponse(
            await run_in_threadpool(
                service.decide,
                request.path_params["handle"],
                view=view,
                decisions=submission.decisions,
            )
        )

    async def reveal(request):
        submission = RevealSubmission.model_validate(await request.json())
        await run_in_threadpool(
            service.reveal,
            request.path_params["handle"],
            view=receipts.verify(submission.view_token),
            assessment=submission.assessment,
        )
        return JSONResponse({"revealed": True, "semantic_decisions_added": 0})

    async def bookmark(request):
        submission = BookmarkSubmission.model_validate(await request.json())
        await run_in_threadpool(
            service.bookmark,
            request.path_params["handle"],
            **submission.model_dump(),
        )
        return JSONResponse({"saved": True})

    async def error(_request, exc):
        if isinstance(exc, ValidationError):
            # Error contexts may contain exception objects and are not JSON serializable.
            return JSONResponse(
                {
                    "error": "Invalid review request",
                    "details": exc.errors(include_context=False, include_input=False),
                },
                status_code=422,
            )
        if isinstance(exc, (KeyError, FileNotFoundError)):
            status, detail = 404, "Review artifact or selected case is unavailable"
        elif isinstance(exc, OSError):
            status = 503
            detail = (
                "Local review storage failed; reload and verify the saved revision before retrying"
            )
        else:
            detail = str(exc)
            status = 409 if any(word in detail for word in ("stale", "writer is active")) else 400
        return JSONResponse({"error": detail}, status_code=status)

    base = "/api/packages/{handle:str}"
    app = Starlette(
        debug=False,
        routes=[
            Route("/", index, methods=["GET"]),
            Route("/api/bootstrap", bootstrap, methods=["GET"]),
            Route("/api/packages", packages, methods=["GET"]),
            Route(base, package, methods=["GET"]),
            Route(base + "/cases", cases, methods=["GET"]),
            Route(base + "/case", case, methods=["GET"]),
            Route(base + "/decisions", decisions, methods=["POST"]),
            Route(base + "/reveal", reveal, methods=["POST"]),
            Route(base + "/bookmark", bookmark, methods=["POST"]),
            Mount("/assets", StaticFiles(directory=assets), name="assets"),
        ],
        exception_handlers={ValueError: error, KeyError: error, OSError: error},
    )
    app.add_middleware(ReviewSecurityMiddleware, config=config, csrf_token=csrf)
    return app


def run_review_workbench_server(app, config: ReviewWorkbenchHttpConfig) -> None:
    try:
        import uvicorn
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "Review workbench dependencies are missing; install the 'chat' extra"
        ) from exc
    # One foreground worker; ignore proxy headers for this loopback-only human interface.
    uvicorn.run(app, host=config.host, port=config.port, workers=1, proxy_headers=False)

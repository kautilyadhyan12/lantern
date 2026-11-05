"""Web app: ask a question, watch the investigation, read the cited report."""

import asyncio
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from starlette.middleware.base import RequestResponseEndpoint

from lantern.assessment import CREDIBILITY, LIKELIHOOD, RELIABILITY
from lantern.config import AppSettings
from lantern.models import Claim, Investigation, Source, now
from lantern.report import to_markdown
from lantern.runtime import continue_investigation, missing_keys, run_investigation
from lantern.store import Store

HERE = Path(__file__).parent
Runner = Callable[[Investigation, AppSettings, Store], Coroutine[Any, Any, Investigation]]
CSP = (
    "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
    "frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
)


class NewInvestigation(BaseModel):
    brief: str = Field(min_length=1, max_length=600)
    depth: Literal["quick", "deep"] = "deep"


def segments(text: str, claims: list[Claim]) -> list[tuple[str, str | None]]:
    """Split saved text into plain parts and highlighted claim quotes (no overlaps)."""
    parts: list[tuple[str, str | None]] = []
    cursor = 0
    for claim in sorted(claims, key=lambda item: item.start):
        if claim.start < cursor:
            continue
        parts += [(text[cursor : claim.start], None), (text[claim.start : claim.end], claim.ref)]
        cursor = claim.end
    parts.append((text[cursor:], None))
    return [part for part in parts if part[0]]


def create_app(  # noqa: PLR0915  # routes share one store and settings via closure
    settings: AppSettings | None = None,
    runner: Runner = run_investigation,
    continuer: Runner = continue_investigation,
) -> FastAPI:
    config = settings or AppSettings()
    store = Store(config.data_dir)
    tasks: set[asyncio.Task[Investigation]] = set()
    for stale in store.all():
        if stale.status in {"queued", "running"}:
            stale.status = "failed"
            stale.error = "The server restarted during this investigation. Please start it again."
            store.save(stale)

    app = FastAPI(title="Lantern", docs_url=None, redoc_url=None, openapi_url=None)
    templates = Jinja2Templates(directory=HERE / "templates")
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")

    @app.middleware("http")
    async def security_headers(request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = CSP
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    def load(investigation_id: str) -> Investigation:
        investigation = store.load(investigation_id)
        if investigation is None:
            raise HTTPException(404, "No investigation with this id.")
        return investigation

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> Response:
        left = max(0, config.daily_run_limit - store.started_today())
        context = {"items": store.all()[:50], "missing": missing_keys(config), "left": left}
        return templates.TemplateResponse(request, "index.html", context)

    def blocked() -> JSONResponse | None:
        """Why no investigation may start now (missing keys, daily limit), or None."""
        if missing := missing_keys(config):
            return JSONResponse({"error": f"Missing keys: {', '.join(missing)}."}, 503)
        if store.started_today() >= config.daily_run_limit:
            message = f"Today's limit of {config.daily_run_limit} investigations is used up."
            return JSONResponse({"error": f"{message} Try again tomorrow."}, 429)
        return None

    def launch(investigation: Investigation, work: Runner) -> None:
        task = asyncio.create_task(work(investigation, config, store))
        tasks.add(task)
        task.add_done_callback(tasks.discard)

    @app.post("/api/investigations")
    async def start(body: NewInvestigation) -> JSONResponse:
        if refusal := blocked():
            return refusal
        investigation = Investigation(id=store.new_id(), brief=body.brief.strip(), depth=body.depth)
        store.save(investigation)
        launch(investigation, runner)
        return JSONResponse({"id": investigation.id}, 201)

    @app.post("/api/investigations/{investigation_id}/continue")
    async def resume(investigation_id: str) -> JSONResponse:
        investigation = load(investigation_id)
        if investigation.status in {"queued", "running"}:
            return JSONResponse({"error": "This investigation is already running."}, 409)
        if investigation.status == "refused" or not investigation.questions:
            message = "Only an investigation that has started researching can be continued."
            return JSONResponse({"error": message}, 409)
        if refusal := blocked():
            return refusal
        investigation.status = "queued"
        investigation.continued_at.append(now())
        store.save(investigation)
        launch(investigation, continuer)
        return JSONResponse({"id": investigation.id}, 202)

    @app.get("/api/investigations/{investigation_id}")
    async def progress(investigation_id: str) -> dict[str, Any]:
        item = load(investigation_id)
        return {
            "status": item.status,
            "error": item.error,
            "steps": [step.message for step in item.steps[-60:]],
            "counts": {
                "questions": len(item.questions),
                "sources": len(item.sources),
                "claims": len(item.claims),
            },
        }

    @app.get("/investigations/{investigation_id}", response_class=HTMLResponse)
    async def page(request: Request, investigation_id: str) -> Response:
        item = load(investigation_id)
        report = item.report
        context = {
            "inv": item,
            "claims": {claim.ref: claim for claim in item.claims},
            "sources": {source.ref: source for source in item.sources},
            "sections": {s.question_ref: s for s in report.sections} if report else {},
            "ranges": dict(LIKELIHOOD),
            "reliability": RELIABILITY,
            "credibility": CREDIBILITY,
        }
        return templates.TemplateResponse(request, "investigation.html", context)

    @app.get("/investigations/{investigation_id}/sources/{ref}", response_class=HTMLResponse)
    async def saved_copy(request: Request, investigation_id: str, ref: str) -> Response:
        item = load(investigation_id)
        source: Source | None = item.source(ref)
        text = store.text(source.text_sha256) if source else None
        if source is None or text is None:
            raise HTTPException(404, "This saved copy does not exist.")
        claims = [claim for claim in item.claims if claim.source_ref == ref]
        context = {
            "inv": item,
            "source": source,
            "parts": segments(text, claims),
            "reliability": RELIABILITY,
        }
        return templates.TemplateResponse(request, "source.html", context)

    @app.get("/investigations/{investigation_id}/report.md")
    async def markdown(investigation_id: str) -> PlainTextResponse:
        item = load(investigation_id)
        headers = {"Content-Disposition": f'attachment; filename="lantern-{item.id}.md"'}
        return PlainTextResponse(to_markdown(item), headers=headers, media_type="text/markdown")

    @app.get("/investigations/{investigation_id}/investigation.json")
    async def as_json(investigation_id: str) -> Response:
        item = load(investigation_id)
        headers = {"Content-Disposition": f'attachment; filename="lantern-{item.id}.json"'}
        body = item.model_dump_json(indent=2)
        return Response(body, media_type="application/json", headers=headers)

    return app

"""Canonical web application, also available with python -m second_brain.web."""
from __future__ import annotations

import os

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse

from second_brain import __version__
from second_brain.console import render_console
from second_brain.hybrid import RetrievalBoundaryError
from second_brain.routes_legacy import router as legacy_router
from second_brain.routes_operational import router as operational_router
from second_brain.routes_refinement import router as refinement_router
from second_brain.web_contracts import QueryRequest
from second_brain.workbench import query_bundle, readiness

app = FastAPI(title="SZL Second Brain", version=__version__, docs_url=None, redoc_url=None,
              description="Public handles-only retrieval, Python console and review-required frontier memory.")
app.include_router(legacy_router)
app.include_router(operational_router)
app.include_router(refinement_router)


@app.exception_handler(RequestValidationError)
async def invalid_request(request: Request, exc: RequestValidationError) -> JSONResponse:
    # Return locations/types only; don't reflect arbitrary malformed request data.
    errors = [{"loc": e["loc"], "type": e["type"]} for e in exc.errors()]
    body_error = any(e["loc"] and e["loc"][0] == "body" for e in errors)
    return JSONResponse({"state": "UNAVAILABLE", "error": "Invalid request", "details": errors},
                        status_code=400 if body_error else 422)


@app.exception_handler(RetrievalBoundaryError)
async def retrieval_boundary(request: Request, exc: RetrievalBoundaryError) -> JSONResponse:
    return JSONResponse({"state": "BLOCKED", "ready": False, "handles": [],
                         "reason": type(exc).__name__}, status_code=422)


@app.get("/readyz")
def readyz() -> JSONResponse:
    payload = readiness()
    return JSONResponse(payload, status_code=200 if payload["ready"] else 503,
                        headers={"Cache-Control": "no-store"})


@app.get("/api/v1/query")
def query_get(q: str = Query("", max_length=2000), k: int = Query(6, ge=1, le=12)) -> JSONResponse:
    return _query_response(q.strip(), k)


@app.post("/api/v1/query")
def query_post(body: QueryRequest) -> JSONResponse:
    return _query_response(body.query, body.k)


def _query_response(q: str, k: int) -> JSONResponse:
    bundle = query_bundle(q, k)
    return JSONResponse(bundle, status_code=503 if bundle["retrieve"]["state"] == "UNAVAILABLE" else 200,
                        headers={"Cache-Control": "no-store"})


@app.get("/", response_class=HTMLResponse)
def console(q: str = Query("", max_length=2000), k: int = Query(6, ge=1, le=12)) -> HTMLResponse:
    status = readiness()
    bundle, error = None, None
    try:
        if q.strip():
            bundle = query_bundle(q.strip(), k)
    except RetrievalBoundaryError as exc:
        error = type(exc).__name__
    return HTMLResponse(render_console(q, k, status, bundle, error),
                        status_code=422 if error else 200,
                        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
                                 "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'self'"})


def main() -> None:
    import uvicorn
    uvicorn.run("second_brain.web:app", host=os.environ.get("HOST", "127.0.0.1"),
                port=int(os.environ.get("PORT", os.environ.get("SECOND_BRAIN_PORT", "8101"))))


if __name__ == "__main__":
    main()

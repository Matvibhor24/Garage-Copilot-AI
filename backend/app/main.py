"""FastAPI entry point: one stateless service for REST, the customer link and the voice gateway."""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import config, gateway, routes_auth, routes_customer, routes_owner, routes_photos, routes_tasks
from app.services import core

app = FastAPI(title="GarageCopilot")
if config.CORS_ORIGINS:
    app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])
app.include_router(routes_customer.router)
app.include_router(routes_owner.router)
app.include_router(routes_auth.router)
app.include_router(gateway.router)
app.include_router(routes_photos.router)
app.include_router(routes_tasks.router)


@app.exception_handler(core.Forbidden)
def forbidden(request: Request, exc: core.Forbidden):
    return JSONResponse({"detail": str(exc)}, status_code=403)


@app.exception_handler(core.NotFound)
def not_found(request: Request, exc: core.NotFound):
    return JSONResponse({"detail": str(exc)}, status_code=404)


@app.exception_handler(core.Invalid)
def invalid(request: Request, exc: core.Invalid):
    return JSONResponse({"detail": str(exc)}, status_code=409)


@app.get("/health")
def health():
    return {"ok": True}

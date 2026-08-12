from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.core.config import ensure_storage_dirs, settings
from app.utils.responses import error

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
)

# Explicit origins so credentialed requests are valid (a wildcard origin
# combined with credentials is rejected by browsers). ``all_cors_origins``
# adds the deployed frontend origin (FRONTEND_ORIGIN) to the local dev origins
# when it is configured, so production never needs a wildcard.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.all_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # Browsers hide every response header from cross-origin JS unless it is
    # named here. The dataset export is fetched over XHR so the UI can show a
    # loading state, and it reads the download filename from this header; the
    # frontend falls back to a generated name, but exposing it keeps the served
    # filename authoritative. Response *bodies* are unaffected.
    expose_headers=["Content-Disposition"],
)


@app.exception_handler(RequestValidationError)
def _on_validation_error(request: Request, exc: RequestValidationError):
    """Return request-validation failures in the app's standard envelope.

    FastAPI's default handler returns a bare ``{"detail": [...]}`` at HTTP 422,
    which is inconsistent with every other endpoint's
    ``{"success", "message", "error"}`` shape. We keep the 422 status and the
    original error list (under ``error.detail``) so clients that already read
    ``detail`` still work, while new clients can rely on the envelope. Successful
    responses are unchanged.
    """
    return error(
        "Request validation failed.",
        422,
        {"detail": jsonable_encoder(exc.errors())},
    )


@app.on_event("startup")
def _startup() -> None:
    ensure_storage_dirs()


app.include_router(router)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.core.config import ensure_storage_dirs, settings

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
)

# Explicit origins so credentialed requests are valid (a wildcard origin
# combined with credentials is rejected by browsers).
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    ensure_storage_dirs()


app.include_router(router)

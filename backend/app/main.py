from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.api.routes import tests as tests_router
from app.api.routes import analysis as analysis_router
from app.api.routes import narrative as narrative_router
from app.api.routes import uploads as uploads_router
from app.api.routes import pdf as pdf_router

app = FastAPI(
    title="Incremental Tool API",
    version="0.1.0",
    docs_url="/api/docs" if settings.environment != "production" else None,
    redoc_url=None,
)

_cors_origins = ["http://localhost:3000"]
if settings.cors_origins:
    _cors_origins += [o.strip() for o in settings.cors_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tests_router.router)
app.include_router(analysis_router.router)
app.include_router(narrative_router.router)
app.include_router(uploads_router.router)
app.include_router(pdf_router.router)


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.routes.auth import router as auth_router
from app.routes.chats import router as chats_router
from app.routes.interests import router as interests_router
from app.routes.matches import router as matches_router
from app.routes.photos import router as photos_router
from app.routes.profile import router as profile_router
from app.routes.shortlists import router as shortlists_router


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    debug=settings.debug,
)

if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.get("/", tags=["System"])
async def root() -> dict[str, str]:
    return {"message": f"{settings.app_name} is running"}


@app.get(f"{settings.api_v1_prefix}/health", tags=["System"])
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(auth_router, prefix=settings.api_v1_prefix)
app.include_router(photos_router, prefix=settings.api_v1_prefix)
app.include_router(profile_router, prefix=settings.api_v1_prefix)
app.include_router(shortlists_router, prefix=settings.api_v1_prefix)
app.include_router(interests_router, prefix=settings.api_v1_prefix)
app.include_router(matches_router, prefix=settings.api_v1_prefix)
app.include_router(chats_router, prefix=settings.api_v1_prefix)

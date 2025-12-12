from fastapi import FastAPI
from routers.moderation import router as moderation_router
from routers.notification import router as notification_router

app = FastAPI(
    title="Content Moderation API",
    version="1.0.0",
    description="Runs full PII, Toxicity, NSFW pipeline and writes results to DB."
)

# Include moderation routes
app.include_router(moderation_router)
app.include_router(notification_router)
@app.get("/")
def root():
    return {"status": "running", "message": "Content Moderation API"}

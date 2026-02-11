from fastapi import FastAPI
from user_service.api.router import router

app = FastAPI(title="SmartCourse User Service")
app.include_router(router)

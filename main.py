# Basic FastAPI app

from fastapi import FastAPI
from routers import users, courses

app = FastAPI()


@app.get("/")
def read_root():
    return {"message": "Hello, Smart-Course Server here!"}


# Include routers for users and courses
app.include_router(users.router)

from fastapi import FastAPI

app = FastAPI(
    title="ForgoteLabeling API",
    version="1.0.0"
)


@app.get("/")
def root():
    return {
        "message": "ForgoteLabeling API is running."
    }
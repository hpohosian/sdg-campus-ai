from fastapi import FastAPI

app = FastAPI()

@app.get("/message")
def read_root():
    return {"message": "Hello World"}

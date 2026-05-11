from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from chatbot.routers.session_router import router as session_router
from chatbot.routers.message_router import router as message_router

app = FastAPI()

origins = [
    "http://127.0.0.1",  # Moodle address
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # allow these domains
    allow_credentials=True,
    allow_methods=["*"],    # GET, POST, PUT, DELETE...
    allow_headers=["*"],    # any headers
)

app.include_router(session_router)
app.include_router(message_router)

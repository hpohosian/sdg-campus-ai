import time
import hmac
import hashlib

from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from settings import Settings

class HMACAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        timestamp = request.headers.get("X-Timestamp")
        signature = request.headers.get("X-Signature")
        body = await request.body()
        settings = Settings()
        
        expected = hmac.new(
            settings.MOODLE_SECRET.encode(),
            f"{timestamp}{body.decode()}".encode(),
            hashlib.sha256
        ).hexdigest()
        
        if not hmac.compare_digest(signature, expected):
            raise HTTPException(status_code=401, detail="Invalid signature")
        
        # Replay attack: reject timestamps older than 5 minutes
        if abs(time.time() - int(timestamp)) > 300:
            raise HTTPException(status_code=401, detail="Request expired")
        
        return await call_next(request)

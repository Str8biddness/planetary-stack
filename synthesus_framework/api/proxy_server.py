"""Lightweight CORS proxy — forwards dashboard requests to the production server on :5000"""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import httpx, asyncio

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

BACKEND = "http://127.0.0.1:5000"

@app.api_route("/{path:path}", methods=["GET","POST","PUT","DELETE","OPTIONS"])
async def proxy(request: Request, path: str):
    async with httpx.AsyncClient(timeout=30) as client:
        body = await request.body()
        headers = {k: v for k, v in request.headers.items() if k.lower() not in ("host", "content-length")}
        resp = await client.request(
            method=request.method,
            url=f"{BACKEND}/{path}",
            content=body,
            headers=headers,
            params=request.query_params,
        )
        return JSONResponse(content=resp.json(), status_code=resp.status_code)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)

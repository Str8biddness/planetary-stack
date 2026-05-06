# api/parameter_cloud_app.py
# Minimal FastAPI app that serves the Parameter Cloud router only.

from fastapi import FastAPI

from api.parameter_cloud import router as parameter_cloud_router

app = FastAPI(title="Synthesus Parameter Cloud")
app.include_router(parameter_cloud_router)

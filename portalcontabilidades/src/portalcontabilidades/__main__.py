"""Run the installed application with python -m portalcontabilidades."""
import uvicorn


if __name__ == "__main__":
    uvicorn.run("portalcontabilidades.app:app", host="0.0.0.0", port=8000, reload=True)

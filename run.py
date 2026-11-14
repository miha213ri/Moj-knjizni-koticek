"""Local development runner. NeoServ uses passenger_wsgi.py instead."""
import uvicorn

if __name__ == "__main__":
    uvicorn.run("app.main:application", host="127.0.0.1", port=8000, reload=False)

# arXiv-Discovery-API

To use it:

1. setup an virtual environment: `python -m venv venv`
2. download required libraries (fastapi, uvicorn, pydantic): `pip install -r requirements.txt`
3. 

curl.exe -X POST "http://127.0.0.1:8000/discover" `
  -H "Content-Type: application/json" `
  -d '{"topic":"machine learning"}'
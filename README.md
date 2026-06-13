# arXiv-Discovery-API

To use it:

1. setup an virtual environment: `python -m venv venv`
2. download required libraries (fastapi, uvicorn, pydantic): `pip install -r requirements.txt`
3. go to the http://localhost:8000/docs
4. click "try it now" to change the search topic and the start date

Note: 
- this will find all papers relevant to some topic (the search topic) that were published past some date (the start date)
- a lot of papers get published, so even setting the start date to 3 days ago can get you the maximum number of papers (i set it as 500)
- u can change maximum papers if u want idk whatever

Here is a command if u don't want yo use the docs:

```Powershell
curl.exe -X POST "http://127.0.0.1:8000/discover" `
  -H "Content-Type: application/json" `
  -d '{"topic":"machine learning"}'
```

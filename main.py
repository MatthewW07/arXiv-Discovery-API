from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Tuple
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import re
from datetime import datetime, date

# Default Parameters
MAX_PAPERS = 500
MAX_QUOTE_LEN = 150
PAGE_LIMIT = 2000

# Precompiled regex patterns
WHITESPACE_RE = re.compile(r'[\r\n\t]+')
MULTISPACE_RE = re.compile(r'\s+')
SENTENCE_SPLIT_RE = re.compile(r'\.\s+(?=[A-Z])')
RESULTS_RE = re.compile(
    r'\b(we show|we prove|we demonstrate|our results|results show|'
    r'we found|we observed|we discovered|we established)\b',
    re.IGNORECASE,
)
FUTURE_WORK_RE = re.compile(
    r'\b(open problem|future work|conjecture|however|limitation|'
    r'we plan|future research|remains open|question remains)\b',
    re.IGNORECASE
)

app = FastAPI(
    title="Research Discovery API", 
    description="API to discover new papers for a given topic from arXiv"
)

class TopicInput(BaseModel):
    topic: str
    start_date: date | None = None
    end_date: date | None = None
    max_papers: int | None = None

class PaperResult(BaseModel):
    title: str
    key_result: str
    future_work: str
    authors: List[str]
    published_date: str
    updated_date: str
    url: str
    pdf: str

class DiscoveryOutput(BaseModel):
    topic: str
    paper_count: int
    results: List[PaperResult]

# Cleaning the text
def clean_text(text: str) -> str:
    if not text:
        return ""
    text = WHITESPACE_RE.sub(' ', text)
    text = MULTISPACE_RE.sub(' ', text)
    return text.strip()

# Split text into sentences
def split_into_sentences(text: str) -> List[str]:
    if not text:
        return []
    sentences = SENTENCE_SPLIT_RE.split(text)
    return [s.strip() for s in sentences if s.strip()]

def _truncate(text: str, max_len: int) -> str:
    return text[:max_len] + ("..." if len(text) > max_len else "")

# Extract all the highlights (key results and future work)
def extract_highlights(abstract: str, max_len: int = MAX_QUOTE_LEN) -> Tuple[str, str]:
    if not abstract:
        return "", ""
    
    sentences = split_into_sentences(abstract)
    key_result = None
    future_work = None

    for sentence in sentences:
        if key_result is None and RESULTS_RE.search(sentence):
            key_result = _truncate(sentence, max_len)
        if future_work is None and FUTURE_WORK_RE.search(sentence):
            future_work = _truncate(sentence, max_len)
        if key_result is not None and future_work is not None:
            break

    # Fall back if not found
    if key_result is None:
        if sentences:
            key_result = _truncate(sentences[0], max_len)
        else:
            key_result = _truncate(abstract, max_len)

    return key_result, future_work   
    

# Get data from arXiv
async def get_discovery_data(
    topic: str, 
    start_date: date | None,
    end_date: date | None,
    max_papers: int
) -> DiscoveryOutput:

    start = 0
    batch_size = min(max_papers, PAGE_LIMIT)
    papers: List[PaperResult] = []

    while len(papers) < max_papers:
        
        # Build desired url
        base_url = "http://export.arxiv.org/api/query"
        params = {
            "search_query": f"all:{topic}",
            "start": start,
            "max_results": batch_size,
            "sortBy": "submittedDate",
            "sortOrder": "descending"
        }

        # Properly encode parameters to handle special characters
        query_string = urllib.parse.urlencode(params)
        arxiv_url = f"{base_url}?{query_string}"

        # Fetch data
        try:
            req = urllib.request.Request(
                arxiv_url,
                headers={"User-Agent": "ResearchDiscoveryAPI/1.0"}
            )
            with urllib.request.urlopen(req, timeout=50) as response:
                data = response.read()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to fetch from arXiv: {str(e)}")
    
        # Parse XML data
        try:
            root = ET.fromstring(data)
        except ET.ParseError as e:
            raise HTTPException(status_code=500, detail=f"Failed to parse arXiv response: {str(e)}")
    
        # Define Atom namespace
        ns = {'atom': 'http://www.w3.org/2005/Atom'}

        # Find entries
        entries = root.findall('atom:entry', ns)
        if not entries:
            break

        searching = True

        for entry in entries:
            # Extract Title
            title_element = entry.find('atom:title', ns)
            title = clean_text(title_element.text) if title_element is not None else "No title available"

            # Extract Abstract
            abstract_element = entry.find('atom:summary', ns)
            abstract = clean_text(abstract_element.text) if abstract_element is not None else "No abstract available"

            # Extract Authors
            author_elements = entry.findall('atom:author', ns)
            authors = []
            for author_element in author_elements:
                name_element = author_element.find('atom:name', ns)
                if name_element is not None and name_element.text:
                    authors.append(clean_text(name_element.text))

            # Extract Published Date
            published_element = entry.find('atom:published', ns)
            if published_element is None or not published_element.text:
                continue
            published_date = datetime.fromisoformat(published_element.text.replace("Z", "+00:00")).date()

            # Extract Updated Date
            updated_element = entry.find('atom:updated', ns)
            updated_date = clean_text(updated_element.text)[:10] if updated_element is not None else ""

            # Extract arXiv Url
            url_element = entry.find('atom:id', ns)
            url = clean_text(url_element.text) if url_element is not None else ""
            pdf = url.replace("abs", "pdf", 1)

            if end_date is not None and published_date > end_date:
                continue

            if start_date is not None and published_date < start_date:
                searching = False
                break

            key_result, future_work = extract_highlights(abstract)

            papers.append(
                PaperResult(
                    title=title,
                    key_result=key_result,
                    future_work=future_work,
                    authors=authors,
                    published_date=str(published_date)[:10],
                    updated_date=updated_date,
                    url=url,
                    pdf=pdf
                )
            )

            if len(papers) >= max_papers:
                searching = False
                break
        
        if not searching:
            break

        start += batch_size

    return DiscoveryOutput(
        topic=topic,
        paper_count=len(papers),
        results=papers
    )

@app.get("/")
async def root():
    return {"status": "ok"}
    
@app.post("/discover", response_model=DiscoveryOutput)
async def discover_research(input: TopicInput) -> DiscoveryOutput:
    # Get inputs
    topic = input.topic.strip()
    start_date = input.start_date
    end_date = input.end_date
    max_papers = input.max_papers if input.max_papers is not None else MAX_PAPERS

    # Check necessary inputs
    if not topic:
        raise HTTPException(status_code=400, detail="Topic cannot be empty")
    
    try:
        return await get_discovery_data(topic, start_date, end_date, max_papers) 
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"Error processing topic: {str(e)}")
    
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="localhost", port=8000)
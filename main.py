from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import re
from datetime import datetime, date

MAX_QUOTE_LEN = 150

app = FastAPI(
    title="Research Discovery API", 
    description="API to discover new papers for a given topic from arXiv"
)

class TopicInput(BaseModel):
    topic: str
    start_date: date | None = None
    max_papers: int | None = None

class PaperResult(BaseModel):
    title: str
    key_result: str
    future_work: str
    authors: List[str]
    published_date: str
    updated_date: str
    url: str

class DiscoveryOutput(BaseModel):
    topic: str
    paper_count: int
    results: List[PaperResult]

# Cleaning the text
def clean_text(text: str) -> str:
    if not text:
        return ""
    # Replace newlines/tabs with spaces
    text = re.sub(r'[\r\n\t]+', ' ', text)
    # Contract multiple spaces
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

# Split text into sentences
def split_into_sentences(text: str) -> List[str]:
    if not text:
        return []
    # Split by period followed by space and capital letter
    sentences = re.split(r'\.\s+(?=[A-Z])', text)
    # Clean up each sentence
    sentences = [s.strip() for s in sentences if s.strip()]
    return sentences

# Extract sentences sounding like key results
def extract_key_results(abstract: str, max_len=MAX_QUOTE_LEN) -> str:
    if not abstract:
        return "No abstract available"
    sentences = split_into_sentences(abstract)

    results_phrases = [
        r'\bwe show\b', 
        r'\bwe prove\b', 
        r'\bwe demonstrate\b', 
        r'\bour results\b', 
        r'\bresults show\b', 
        r'\bwe found\b', 
        r'\bwe observed\b', 
        r'\bwe discovered\b', 
        r'\bwe established\b'
    ]

    # Look for key phrases
    for sentence in sentences:
        for phrase in results_phrases:
            if re.search(phrase, sentence, re.IGNORECASE):
                return sentence[:max_len] + ("..." if len(sentence) > max_len else "")
            
    # Fallback to first sentence
    if sentences:
        return sentences[0][:max_len] + ("..." if len(sentences[0]) > max_len else "")
    return abstract[:max_len] + ("..." if len(abstract) > max_len else "")            
    
# Extract sentences sounding like open problems or future work
def extract_future_work(abstract: str, max_len=MAX_QUOTE_LEN) -> str:
    if not abstract:
        return ""
    sentences = split_into_sentences(abstract)

    open_phrases = [
        r'\bopen problem\b',
        r'\bfuture work\b',
        r'\bconjecture\b',
        r'\bhowever\b',
        r'\blimitation\b',
        r'\bwe plan\b',
        r'\bfuture research\b',
        r'\bremains open\b',
        r'\bquestion remains\b'
    ]

    # Search for open problem phrases
    for sentence in sentences:
        for phrase in open_phrases:
            if re.search(phrase, sentence, re.IGNORECASE):
                return sentence[:max_len] + ("..." if len(sentence) > max_len else "")
        
    # No fallback
    return ""

def get_discovery_data(topic: str, start_date: date, max_papers: int) -> DiscoveryOutput:
    start = 0
    batch_size = 50
    papers = []

    while len(papers) < max_papers:
        # Url creation
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
            with urllib.request.urlopen(req, timeout=20) as response:
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
            return DiscoveryOutput(
                topic=topic, 
                paper_count=0,
                results=[]
            )

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

            if published_date < start_date:
                searching = False
                break

            papers.append(
                PaperResult(
                    title=title,
                    # abstract=abstract,
                    key_result=extract_key_results(abstract),
                    future_work=extract_future_work(abstract),
                    authors=authors,
                    published_date=str(published_date)[:10],
                    updated_date=updated_date,
                    url=url
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
    topic = input.topic.strip()
    start_date = input.start_date
    max_papers = input.max_papers
    if not topic:
        raise HTTPException(status_code=400, detail="Topic cannot be empty")
    
    try:
        data = get_discovery_data(topic, start_date, max_papers) 
        return data
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"Error processing topic: {str(e)}")
    
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="localhost", port=8000)
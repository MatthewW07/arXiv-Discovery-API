from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import re

app = FastAPI(title="Research Discovery API (arXiv-powered)", description="API to discover new papers from arXiv for a given topic.")

class TopicInput(BaseModel):
    topic: str

class DiscoveryOutput(BaseModel):
    new_papers: List[str]
    key_results: List[str]
    open_problems: List[str]

def clean_text(text: str) -> str:
    """Clean up text: replace newlines, extra spaces."""
    if not text:
        return ""
    # Replace newlines and tabs with space
    text = re.sub(r'[\r\n\t]+', ' ', text)
    # Replace multiple spaces with single space
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def split_into_sentences(text: str) -> List[str]:
    """Simple sentence splitter (not perfect but works for abstracts)."""
    if not text:
        return []
    # Split by period followed by space or end of string
    sentences = re.split(r'\.\s+', text)
    # Clean up each sentence
    sentences = [s.strip() for s in sentences if s.strip()]
    return sentences

def extract_key_result(abstract: str) -> str:
    """Try to extract a sentence that sounds like a key result."""
    if not abstract:
        return "No abstract available"
    sentences = split_into_sentences(abstract)
    # Look for result-oriented phrases
    result_phrases = [
        r'\bwe show\b', r'\bwe prove\b', r'\bwe demonstrate\b', 
        r'\bour results\b', r'\bresults show\b', r'\bwe found\b', 
        r'\bwe observed\b', r'\bwe discovered\b', r'\bwe established\b'
    ]
    for sentence in sentences:
        for phrase in result_phrases:
            if re.search(phrase, sentence, re.IGNORECASE):
                return sentence[:200] + ("..." if len(sentence) > 200 else "")
    # Fallback: first sentence
    if sentences:
        return sentences[0][:200] + ("..." if len(sentences[0]) > 200 else "")
    return abstract[:200] + ("..." if len(abstract) > 200 else "")

def extract_open_problem(abstract: str) -> str:
    """Try to extract a sentence that sounds like an open problem or future work."""
    if not abstract:
        return ""
    sentences = split_into_sentences(abstract)
    # Look for open problem/future work phrases
    open_phrases = [
        r'\bopen problem\b', r'\bfuture work\b', r'\bconjecture\b', 
        r'\bhowever\b', r'\blimitation\b', r'\bwe plan\b', 
        r'\bfuture research\b', r'\bremains open\b', r'\bquestion remains\b'
    ]
    for sentence in sentences:
        for phrase in open_phrases:
            if re.search(phrase, sentence, re.IGNORECASE):
                return sentence[:200] + ("..." if len(sentence) > 200 else "")
    # If nothing found, return empty string
    return ""

def get_discovery_data(topic: str) -> DiscoveryOutput:
    """Fetch recent papers from arXiv for the given topic."""
    # URL encode the topic
    encoded_topic = urllib.parse.quote(topic)
    # arXiv API query: search by all fields, sort by submitted date descending, max 5 results
    url = f"http://export.arxiv.org/api/query?search_query=all:{encoded_topic}&start=0&max_results=5&sortBy=submittedDate&sortOrder=descending"
    
    try:
        with urllib.request.urlopen(url) as response:
            data = response.read()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch from arXiv: {str(e)}")
    
    # Parse the XML
    try:
        root = ET.fromstring(data)
    except ET.ParseError as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse arXiv response: {str(e)}")
    
    # Define the Atom namespace
    ns = {'atom': 'http://www.w3.org/2005/Atom'}
    
    # Find all entries (papers)
    entries = root.findall('atom:entry', ns)
    
    new_papers = []
    key_results = []
    open_problems = []
    
    for entry in entries:
        # Extract title
        title_elem = entry.find('atom:title', ns)
        title = clean_text(title_elem.text) if title_elem is not None else "No title"
        
        # Extract summary (abstract)
        summary_elem = entry.find('atom:summary', ns)
        summary = clean_text(summary_elem.text) if summary_elem is not None else ""
        
        new_papers.append(title)
        key_results.append(extract_key_result(summary))
        open_problems.append(extract_open_problem(summary))
    
    # If no papers found, return empty lists
    if not new_papers:
        return DiscoveryOutput(new_papers=[], key_results=[], open_problems=[])
    
    return DiscoveryOutput(
        new_papers=new_papers,
        key_results=key_results,
        open_problems=open_problems
    )

@app.post("/discover", response_model=DiscoveryOutput)
async def discover_research(input: TopicInput):
    """Discover new papers, key results, and open problems for a given topic from arXiv."""
    topic = input.topic.strip()
    if not topic:
        raise HTTPException(status_code=400, detail="Topic cannot be empty")
    try:
        data = get_discovery_data(topic)
        return data
    except Exception as e:
        # Re-raise HTTPException as is, otherwise wrap
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"Error processing topic: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="localhost", port=8000)
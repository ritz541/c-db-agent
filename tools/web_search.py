"""
Web Search Tool — Search for jobs and fetch job descriptions
Uses TinyFish API for web search and content extraction.
"""

import os
import re
import requests
import structlog
from tools.base import BaseTool

logger = structlog.get_logger()


def _is_url(text: str) -> bool:
    """Check if text looks like a URL."""
    return bool(re.match(r'^https?://', text.strip()))


class WebSearchTool(BaseTool):
    """Search the web for jobs and fetch their descriptions."""

    def get_name(self) -> str:
        return "web_search"

    def get_description(self) -> str:
        return (
            "Search the web for job postings and fetch their descriptions. "
            "If you provide a URL, it extracts the content automatically. "
            "Use search for finding jobs, then fetch to get job descriptions for application drafts."
        )

    def get_parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query or URL to fetch (e.g., 'software engineer remote' or 'https://company.com/jobs/123')"
                },
                "action": {
                    "type": "string",
                    "enum": ["search", "fetch", "auto"],
                    "description": "Action: 'auto' detects URL vs search, 'search' for finding, 'fetch' for extracting"
                },
                "url": {
                    "type": "string",
                    "description": "URL to fetch (only used when action='fetch')"
                }
            },
            "required": ["query"]
        }

    def execute(self, db_conn, query: str, action: str = "auto", url: str = None) -> dict:
        """Search for jobs or fetch a job description from a URL."""
        try:
            api_key = os.getenv("TINYFISH_API_KEY")
            if not api_key:
                return {"success": False, "error": "TINYFISH_API_KEY not configured in .env"}

            # Auto-detect: if query is a URL or action is fetch
            if action == "auto":
                target_url = url or (_is_url(query) and query)
                if target_url:
                    logger.info("web_search.auto_fetch", url=target_url)
                    return self._fetch_url(target_url, api_key)
                else:
                    logger.info("web_search.auto_search", query=query)
                    return self._search_jobs(query, api_key)

            if action == "fetch":
                target_url = url or query
                return self._fetch_url(target_url, api_key)
            else:
                return self._search_jobs(query, api_key)

        except Exception as e:
            logger.error("web_search.failed", error=str(e))
            return {"success": False, "error": str(e)}

    def _search_jobs(self, query: str, api_key: str) -> dict:
        """Search for jobs using TinyFish Search API."""
        try:
            logger.info("web_search.searching", query=query)
            response = requests.get(
                "https://api.search.tinyfish.ai",
                headers={"X-API-Key": api_key},
                params={
                    "query": query,
                    "format": "json",
                    "purpose": "Finding job postings for job application"
                },
                timeout=30
            )
            response.raise_for_status()
            data = response.json()

            # Extract job-relevant results
            results = []
            for item in data.get("results", []):
                results.append({
                    "title": item.get("title"),
                    "url": item.get("url"),
                    "snippet": item.get("snippet"),
                    "source": item.get("source")
                })

            logger.info("web_search.search_results", count=len(results))
            return {
                "success": True,
                "query": query,
                "results": results,
                "count": len(results),
                "message": f"Found {len(results)} results for '{query}'"
            }

        except requests.HTTPError as e:
            logger.error("web_search.search_http_error", error=str(e))
            return {"success": False, "error": f"Search API error: {e}"}

    def _fetch_url(self, url: str, api_key: str) -> dict:
        """Fetch and extract content from a URL using TinyFish Fetch API."""
        try:
            logger.info("web_search.fetching", url=url)
            response = requests.post(
                "https://api.fetch.tinyfish.ai",
                headers={"X-API-Key": api_key, "Content-Type": "application/json"},
                json={
                    "urls": [url],
                    "format": "markdown",
                    "purpose": "Extracting job description for application draft"
                },
                timeout=30
            )
            response.raise_for_status()
            data = response.json()

            # TinyFish returns {"results": [...]} with array of results
            results = data.get("results", [])
            if results and len(results) > 0:
                result_data = results[0]
            else:
                result_data = data

            content = result_data.get("text", "")
            title = result_data.get("title", "") or result_data.get("description", "")

            logger.info("web_search.fetch_success", url=url, content_len=len(content))
            return {
                "success": True,
                "url": url,
                "title": title,
                "content": content,
                "message": f"Fetched content from {url}"
            }

        except requests.HTTPError as e:
            logger.error("web_search.fetch_http_error", url=url, error=str(e))
            return {"success": False, "error": f"Fetch API error: {e}"}


web_search_tool = WebSearchTool()
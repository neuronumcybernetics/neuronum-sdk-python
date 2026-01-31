"""
Search Content MCP Server
Built-in tool that queries the sitemap FTS5 table to answer
content and information questions from indexed pages.
"""

from mcp.server.fastmcp import FastMCP
import sqlite3
import os
import re

# -----------------------------------------------------------------------------
# Database Setup
# -----------------------------------------------------------------------------

# The agent_memory.db is in the server root (one level up from tools/)
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "agent_memory.db")

# Stopwords to exclude from FTS5 queries
FTS5_STOPWORDS = {"or", "and", "not", "near", "the", "a", "an", "is", "it",
                  "to", "in", "for", "of", "on", "at", "by", "with", "from",
                  "as", "be", "was", "are", "were", "been", "being", "have",
                  "has", "had", "do", "does", "did", "will", "would", "could",
                  "should", "may", "might", "can", "this", "that", "these",
                  "those", "i", "me", "my", "we", "our", "you", "your", "what",
                  "how", "where", "when", "who", "which", "about", "tell",
                  "show", "give", "please", "help"}

# -----------------------------------------------------------------------------
# MCP Server
# -----------------------------------------------------------------------------

mcp = FastMCP("search-content")


@mcp.tool()
def search_content(query: str, operator: str = None) -> dict:
    """Search indexed content for information. Use this tool when the user asks
    questions about the website, documentation, services, products, pricing,
    features, legal information, or any general information question.

    Args:
        query: The search query to find relevant content

    Returns:
        Matching content and best page to serve
    """
    # Extract tokens and filter stopwords
    tokens = re.findall(r"\b\w+\b", query.lower())
    keywords = [t for t in tokens if t not in FTS5_STOPWORDS]

    if not keywords:
        return {
            "success": True,
            "content": "No information found for that query.",
            "page": "index.html",
            "sources": []
        }

    keywords = keywords[:10]
    quoted_keywords = [f'"{keyword}"' for keyword in keywords]
    search_expr = " OR ".join(quoted_keywords)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT file_name, file_content, bm25(sitemap) as score
            FROM sitemap
            WHERE sitemap MATCH ?
            ORDER BY score
            LIMIT 5
        """, (search_expr,))

        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return {
                "success": True,
                "content": "No information found for that query.",
                "page": "index.html",
                "sources": []
            }

        # Best matching page for serving
        best_page = rows[0][0]

        # Combine content from all matching pages
        content_parts = []
        sources = []
        for file_name, file_content, score in rows:
            content_parts.append(f"[{file_name}]: {file_content}")
            sources.append(file_name)

        combined_content = "\n\n".join(content_parts)

        return {
            "success": True,
            "content": combined_content,
            "page": best_page,
            "sources": sources
        }

    except Exception as e:
        conn.close()
        return {
            "success": False,
            "error": str(e),
            "content": "Content search temporarily unavailable.",
            "page": "index.html",
            "sources": []
        }


# -----------------------------------------------------------------------------
# Run Server
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()

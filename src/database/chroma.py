"""
ChromaDB Client

Handles vector embeddings for semantic search (RAG).
Stores embeddings of markets, articles, and Reddit posts for similarity search.

Uses sentence-transformers for local embeddings (no API key needed).
"""

import os
import logging

import chromadb
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


class ChromaClient:
    """Client for ChromaDB vector database."""
    
    def __init__(self):
        """Initialize ChromaDB client.

        Connects to the Docker ChromaDB server via HTTP.
        Host and port configurable via CHROMA_HOST and CHROMA_PORT env vars.
        """
        self.host = os.getenv("CHROMA_HOST", "127.0.0.1")
        self.port = int(os.getenv("CHROMA_PORT", "8001"))
        self.client = None

        # Collection names
        self.MARKETS_COLLECTION = "markets"
        self.ARTICLES_COLLECTION = "articles"
        self.REDDIT_COLLECTION = "reddit"

    def connect(self):
        """Connect to ChromaDB Docker container via HTTP."""
        if self.client is None:
            self.client = chromadb.HttpClient(
                host=self.host, port=self.port,
            )
            self.client.heartbeat()
            logger.info(f"Connected to ChromaDB at {self.host}:{self.port}")
    
    def __enter__(self):
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        pass  # ChromaDB handles cleanup automatically
    
    def get_or_create_collection(self, name: str):
        """Get or create a collection."""
        self.connect()
        return self.client.get_or_create_collection(
            name=name,
            metadata={"hnsw:space": "cosine"}  # Use cosine similarity
        )
    
    def add_markets(self, markets: list[dict]) -> int:
        """
        Add markets to the vector store.
        
        Args:
            markets: List of market dicts with id and question
            
        Returns:
            Number of markets added
        """
        collection = self.get_or_create_collection(self.MARKETS_COLLECTION)
        
        ids = []
        documents = []
        metadatas = []
        
        for market in markets:
            market_id = str(market.get("id"))
            question = market.get("question", "")
            
            if not question:
                continue
            
            ids.append(market_id)
            documents.append(question)
            metadatas.append({
                "type": "market",
                "volume_24h": float(market.get("volume_24h", 0) or 0),
                "source": "polymarket",
            })
        
        if ids:
            # Upsert to handle duplicates
            collection.upsert(
                ids=ids,
                documents=documents,
                metadatas=metadatas,
            )
        
        logger.info(f"Added {len(ids)} markets to ChromaDB")
        return len(ids)
    
    def add_articles(self, articles: list[dict]) -> int:
        """
        Add articles to the vector store.
        
        Args:
            articles: List of article dicts
            
        Returns:
            Number of articles added
        """
        collection = self.get_or_create_collection(self.ARTICLES_COLLECTION)
        
        ids = []
        documents = []
        metadatas = []
        
        for article in articles:
            article_id = str(article.get("external_id") or article.get("id"))
            title = article.get("title", "")
            content = article.get("content") or article.get("summary") or ""
            
            # Combine title and content for embedding
            text = f"{title}. {content}"[:2000]  # Limit length
            
            if not text.strip():
                continue
            
            ids.append(article_id)
            documents.append(text)
            metadatas.append({
                "type": "article",
                "source": article.get("source", "unknown"),
                "title": title[:200],
                "url": article.get("url", ""),
            })
        
        if ids:
            collection.upsert(
                ids=ids,
                documents=documents,
                metadatas=metadatas,
            )
        
        logger.info(f"Added {len(ids)} articles to ChromaDB")
        return len(ids)
    
    def add_reddit_posts(self, posts: list[dict]) -> int:
        """
        Add Reddit posts to the vector store.
        
        Args:
            posts: List of post dicts from MongoDB
            
        Returns:
            Number of posts added
        """
        collection = self.get_or_create_collection(self.REDDIT_COLLECTION)
        
        ids = []
        documents = []
        metadatas = []
        
        for post in posts:
            post_id = str(post.get("post_id") or post.get("_id"))
            title = post.get("title", "")
            selftext = post.get("selftext", "")
            
            # Combine title and body
            text = f"{title}. {selftext}"[:2000]
            
            if not text.strip():
                continue
            
            ids.append(post_id)
            documents.append(text)
            metadatas.append({
                "type": "reddit",
                "subreddit": post.get("subreddit", ""),
                "score": post.get("score", 0),
                "title": title[:200],
            })
        
        if ids:
            collection.upsert(
                ids=ids,
                documents=documents,
                metadatas=metadatas,
            )
        
        logger.info(f"Added {len(ids)} Reddit posts to ChromaDB")
        return len(ids)
    
    def search(
        self,
        query: str,
        collection_name: str = None,
        n_results: int = 10,
        where: dict = None,
    ) -> list[dict]:
        """
        Search for similar documents.
        
        Args:
            query: Search query
            collection_name: Collection to search (None = search all)
            n_results: Number of results
            where: Filter conditions
            
        Returns:
            List of results with id, document, metadata, distance
        """
        self.connect()
        
        results = []
        
        collections = [collection_name] if collection_name else [
            self.MARKETS_COLLECTION,
            self.ARTICLES_COLLECTION,
            self.REDDIT_COLLECTION,
        ]
        
        for coll_name in collections:
            try:
                collection = self.client.get_collection(coll_name)
                
                query_result = collection.query(
                    query_texts=[query],
                    n_results=n_results,
                    where=where,
                )
                
                # Format results
                for i, doc_id in enumerate(query_result["ids"][0]):
                    results.append({
                        "id": doc_id,
                        "document": query_result["documents"][0][i],
                        "metadata": query_result["metadatas"][0][i],
                        "distance": query_result["distances"][0][i] if query_result.get("distances") else None,
                        "collection": coll_name,
                    })
                    
            except Exception as e:
                logger.debug(f"Collection {coll_name} not found or empty: {e}")
        
        # Sort by distance (lower = more similar)
        results.sort(key=lambda x: x.get("distance") or float("inf"))
        
        return results[:n_results]
    
    def search_markets(self, query: str, n_results: int = 5) -> list[dict]:
        """Search for similar markets."""
        return self.search(query, self.MARKETS_COLLECTION, n_results)
    
    def search_articles(self, query: str, n_results: int = 5) -> list[dict]:
        """Search for similar articles."""
        return self.search(query, self.ARTICLES_COLLECTION, n_results)
    
    def search_reddit(self, query: str, n_results: int = 5) -> list[dict]:
        """Search for similar Reddit posts."""
        return self.search(query, self.REDDIT_COLLECTION, n_results)
    
    def search_all(self, query: str, n_results: int = 10) -> list[dict]:
        """Search across all collections."""
        return self.search(query, None, n_results)
    
    def get_stats(self) -> dict:
        """Get collection statistics."""
        self.connect()
        
        stats = {}
        
        for coll_name in [self.MARKETS_COLLECTION, self.ARTICLES_COLLECTION, self.REDDIT_COLLECTION]:
            try:
                collection = self.client.get_collection(coll_name)
                stats[coll_name] = collection.count()
            except Exception:
                stats[coll_name] = 0
        
        return stats


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    with ChromaClient() as chroma:
        stats = chroma.get_stats()
        print(f"ChromaDB stats: {stats}")

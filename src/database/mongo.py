"""
MongoDB Client

Handles connection and operations for MongoDB.
Used for storing Reddit posts (nested document structure).
"""

import os
import logging
from datetime import datetime
from typing import Optional

from pymongo import MongoClient, DESCENDING
from pymongo.errors import DuplicateKeyError
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


class MongoDBClient:
    """Client for MongoDB operations."""
    
    def __init__(self):
        """Initialize MongoDB connection."""
        self.host = os.getenv("MONGO_HOST", "127.0.0.1")
        self.port = int(os.getenv("MONGO_PORT", 27017))
        self.user = os.getenv("MONGO_USER", "pmi")
        self.password = os.getenv("MONGO_PASSWORD")
        self.database = os.getenv("MONGO_DATABASE", "prediction_market_intel")
        if not self.password:
            raise ValueError(
                "MONGO_PASSWORD not set. Copy .env.example to .env and fill in credentials."
            )
        
        self.uri = f"mongodb://{self.user}:{self.password}@{self.host}:{self.port}/?authSource=admin"
        self.client = None
        self.db = None
    
    def connect(self):
        """Establish connection to MongoDB."""
        if self.client is None:
            self.client = MongoClient(self.uri)
            self.db = self.client[self.database]
            self.client.server_info()
            logger.info(f"Connected to MongoDB at {self.host}:{self.port}")
    
    def close(self):
        """Close MongoDB connection."""
        if self.client:
            self.client.close()
            self.client = None
            self.db = None
    
    def __enter__(self):
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
    
    def init_collections(self):
        """Initialize collections with indexes."""
        self.connect()
        
        # Reddit posts collection
        posts = self.db["reddit_posts"]
        posts.create_index("post_id", unique=True)
        posts.create_index("subreddit")
        posts.create_index("created_utc")
        posts.create_index("score")
        posts.create_index([("title", "text"), ("selftext", "text")])
        
        logger.info("MongoDB collections initialized")
    
    def insert_post(self, post: dict) -> bool:
        """
        Insert a Reddit post.
        
        Args:
            post: Post document
            
        Returns:
            True if inserted, False if duplicate
        """
        self.connect()
        
        try:
            # Add metadata
            post["_inserted_at"] = datetime.utcnow()
            
            self.db["reddit_posts"].insert_one(post)
            return True
            
        except DuplicateKeyError:
            return False
    
    def insert_posts(self, posts: list[dict]) -> int:
        """
        Insert multiple posts, skipping duplicates.
        
        Args:
            posts: List of post documents
            
        Returns:
            Number of posts inserted
        """
        self.connect()
        
        inserted = 0
        for post in posts:
            if self.insert_post(post):
                inserted += 1
        
        return inserted
    
    def get_posts(
        self,
        subreddit: str = None,
        limit: int = 100,
        min_score: int = None,
    ) -> list[dict]:
        """
        Retrieve posts with optional filters.
        
        Args:
            subreddit: Filter by subreddit
            limit: Maximum posts to return
            min_score: Minimum score filter
            
        Returns:
            List of post documents
        """
        self.connect()
        
        query = {}
        if subreddit:
            query["subreddit"] = subreddit
        if min_score is not None:
            query["score"] = {"$gte": min_score}
        
        cursor = self.db["reddit_posts"].find(query).sort("score", DESCENDING).limit(limit)
        
        return list(cursor)
    
    def search_posts(self, text: str, limit: int = 50) -> list[dict]:
        """
        Full-text search on posts.
        
        Args:
            text: Search query
            limit: Maximum results
            
        Returns:
            List of matching posts
        """
        self.connect()
        
        cursor = self.db["reddit_posts"].find(
            {"$text": {"$search": text}},
            {"score": {"$meta": "textScore"}}
        ).sort([("score", {"$meta": "textScore"})]).limit(limit)
        
        return list(cursor)
    
    def get_subreddit_stats(self) -> list[dict]:
        """Get post counts by subreddit."""
        self.connect()
        
        pipeline = [
            {"$group": {"_id": "$subreddit", "count": {"$sum": 1}, "avg_score": {"$avg": "$score"}}},
            {"$sort": {"count": -1}}
        ]
        
        return list(self.db["reddit_posts"].aggregate(pipeline))
    
    def count_posts(self) -> int:
        """Get total post count."""
        self.connect()
        return self.db["reddit_posts"].count_documents({})


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    with MongoDBClient() as mongo:
        mongo.init_collections()
        print(f"Total posts: {mongo.count_posts()}")

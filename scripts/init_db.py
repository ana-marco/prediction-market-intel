#!/usr/bin/env python3
"""
Initialize all databases for the Prediction Market Intelligence Agent.

Run this after `docker-compose up -d` to set up schemas and collections.

Usage:
    python scripts/init_db.py
"""

import sys
import time
import logging
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def wait_for_postgres(max_retries: int = 30, delay: float = 2.0) -> bool:
    """Wait for PostgreSQL to be ready."""
    from database.postgres import PostgresClient
    
    logger.info("Waiting for PostgreSQL...")
    
    for i in range(max_retries):
        try:
            db = PostgresClient()
            with db.get_cursor() as cursor:
                cursor.execute("SELECT 1")
            logger.info("PostgreSQL is ready!")
            return True
        except Exception as e:
            logger.debug(f"Attempt {i+1}/{max_retries}: {e}")
            time.sleep(delay)
    
    logger.error("PostgreSQL failed to become ready")
    return False


def init_postgres() -> bool:
    """Initialize PostgreSQL schema."""
    from database.postgres import PostgresClient
    
    try:
        db = PostgresClient()
        db.init_schema()
        logger.info("PostgreSQL schema initialized")
        return True
    except Exception as e:
        logger.error(f"Failed to initialize PostgreSQL: {e}")
        return False


def init_mongodb() -> bool:
    """Initialize MongoDB collections and indexes."""
    try:
        import pymongo
        from dotenv import load_dotenv
        import os
        
        load_dotenv()
        
        # Use connection string format (more reliable on Windows)
        user = os.getenv("MONGO_USER", "pmi")
        password = os.getenv("MONGO_PASSWORD", "pmi_dev_password")
        client = pymongo.MongoClient(
            f"mongodb://{user}:{password}@127.0.0.1:27017/?authSource=admin"
        )
        
        db = client["prediction_market_intel"]
        
        # Create collections with indexes
        # Reddit posts
        posts = db["reddit_posts"]
        posts.create_index("post_id", unique=True)
        posts.create_index("subreddit")
        posts.create_index("created_utc")
        posts.create_index([("title", "text"), ("selftext", "text")])
        
        logger.info("MongoDB collections initialized")
        return True
        
    except Exception as e:
        logger.error(f"Failed to initialize MongoDB: {e}")
        return False


def init_neo4j() -> bool:
    """Initialize Neo4j constraints and indexes."""
    try:
        from neo4j import GraphDatabase
        from dotenv import load_dotenv
        import os
        
        load_dotenv()
        
        driver = GraphDatabase.driver(
            "bolt://127.0.0.1:7687",  # Use IP, not localhost (IPv6 issues on Windows)
            auth=(
                os.getenv("NEO4J_USER", "neo4j"),
                os.getenv("NEO4J_PASSWORD", "pmi_dev_password")
            )
        )
        
        with driver.session() as session:
            # Create constraints (these also create indexes)
            constraints = [
                "CREATE CONSTRAINT market_id IF NOT EXISTS FOR (m:Market) REQUIRE m.id IS UNIQUE",
                "CREATE CONSTRAINT topic_name IF NOT EXISTS FOR (t:Topic) REQUIRE t.name IS UNIQUE",
                "CREATE CONSTRAINT article_id IF NOT EXISTS FOR (a:Article) REQUIRE a.id IS UNIQUE",
                "CREATE CONSTRAINT indicator_id IF NOT EXISTS FOR (i:Indicator) REQUIRE i.series_id IS UNIQUE",
            ]
            
            for constraint in constraints:
                try:
                    session.run(constraint)
                except Exception as e:
                    # Constraint might already exist
                    logger.debug(f"Constraint note: {e}")
        
        driver.close()
        logger.info("Neo4j constraints initialized")
        return True
        
    except Exception as e:
        logger.error(f"Failed to initialize Neo4j: {e}")
        return False


def init_chromadb() -> bool:
    """Initialize ChromaDB collections."""
    try:
        import chromadb
        
        client = chromadb.HttpClient(host="127.0.0.1", port=8000)  # Use IP, not localhost
        
        # Create collections for different content types
        collections = [
            "news_articles",      # Guardian, gov.uk
            "market_descriptions", # Polymarket
            "reddit_posts",        # Reddit
        ]
        
        for name in collections:
            try:
                client.get_or_create_collection(
                    name=name,
                    metadata={"description": f"Embeddings for {name}"}
                )
                logger.info(f"ChromaDB collection '{name}' ready")
            except Exception as e:
                logger.warning(f"Collection {name}: {e}")
        
        logger.info("ChromaDB collections initialized")
        return True
        
    except Exception as e:
        logger.error(f"Failed to initialize ChromaDB: {e}")
        return False


def main():
    """Initialize all databases."""
    print("\n" + "="*50)
    print("Prediction Market Intelligence Agent")
    print("Database Initialization")
    print("="*50 + "\n")
    
    results = {}
    
    # PostgreSQL (required)
    if wait_for_postgres():
        results["PostgreSQL"] = init_postgres()
    else:
        results["PostgreSQL"] = False
    
    # MongoDB
    results["MongoDB"] = init_mongodb()
    
    # Neo4j
    results["Neo4j"] = init_neo4j()
    
    # ChromaDB
    results["ChromaDB"] = init_chromadb()
    
    # Summary
    print("\n" + "="*50)
    print("Initialization Results")
    print("="*50)
    
    all_ok = True
    for db, success in results.items():
        status = "OK" if success else "FAILED"
        print(f"  [{status}] {db}")
        if not success:
            all_ok = False
    
    print()
    
    if all_ok:
        print("All databases initialized successfully!")
        return 0
    else:
        print("Some databases failed to initialize.")
        print("Make sure Docker containers are running: docker-compose up -d")
        return 1


if __name__ == "__main__":
    sys.exit(main())

import motor.motor_asyncio
from functools import lru_cache
import logging
from app.config import settings

logger = logging.getLogger(__name__)

class Mongo:
    """
    MongoDB connection singleton class using Motor for async operations.
    Implements the singleton pattern to ensure only one database connection is created.
    """
    _instance = None
    _client = None
    _db = None

    def __new__(cls):
        if cls._instance is None:
            logger.info(f"Initializing MongoDB connection to database: {settings.db_name}")
            cls._instance = super(Mongo, cls).__new__(cls)
            try:
                # Create the MongoDB client
                cls._client = motor.motor_asyncio.AsyncIOMotorClient(
                    settings.mongo_uri,
                    serverSelectionTimeoutMS=5000  # 5 second timeout for server selection
                )
                # Get the database instance
                cls._db = cls._client[settings.db_name]
                # Verify the connection is working
                cls._client.admin.command('ping')
                logger.info("MongoDB connection established successfully")
            except Exception as e:
                logger.error(f"Failed to connect to MongoDB: {str(e)}")
                raise
            cls._instance = cls._db
        return cls._instance

    @classmethod
    async def close_connection(cls):
        """
        Close the MongoDB connection when the application shuts down
        """
        if cls._client:
            logger.info("Closing MongoDB connection")
            cls._client.close()
            cls._client = None
            cls._db = None
            cls._instance = None


@lru_cache()
def get_database():
    """
    Get a cached database connection
    """
    return Mongo()


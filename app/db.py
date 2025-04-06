import motor.motor_asyncio

from app.config import AppConfig


class Mongo(object):
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Mongo, cls).__new__(cls)

            config = AppConfig()
            mongo_uri = config.mongo_uri

            client = motor.motor_asyncio.AsyncIOMotorClient(mongo_uri)
            db = client[config.db_name]

            cls._instance = db

        return cls._instance

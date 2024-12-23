# database.py

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

# Load .env if running outside docker (inside docker, env are passed in)
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")  # Example: postgresql://user:pass@host:5432/dbname

# Create the engine
engine = create_engine(DATABASE_URL, future=True)

# Create a configured "SessionLocal" class
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)

# Base class for our models
Base = declarative_base()

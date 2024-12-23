# models.py

from sqlalchemy import Column, Integer, BigInteger
from sqlalchemy.orm import declarative_base
from database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    telegram_user_id = Column(BigInteger, unique=True, index=True)
    # Additional columns as needed

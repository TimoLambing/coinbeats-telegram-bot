# models.py (example)
from sqlalchemy import Column, Integer, BigInteger, String
from database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    telegram_user_id = Column(BigInteger, unique=True, index=True)
    first_start_param = Column(String, nullable=True)  # store any referral code or TappAds param here

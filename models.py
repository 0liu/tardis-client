#!/usr/bin/env python3


from sqlalchemy import Column
from sqlalchemy import DateTime, Integer, Float, String
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import declarative_base


Base = declarative_base()
db_url = "sqlite+aiosqlite:///database.db"
engine = create_async_engine(db_url, echo=False)

sample = {
    "type": "book_snapshot",
    "symbol": "BTC-PERPETUAL",
    "exchange": "deribit",
    "name": "quote_5s",
    "depth": 1,
    "interval": 5000,
    "bids": [{"price": 39760, "amount": 7630}],
    "asks": [{"price": 39760.5, "amount": 49050}],
    "timestamp": "2022-04-28T22:17:45.000Z",
    "localTimestamp": "2022-04-28T22:17:45.105Z",
}


class BookSnapshot(Base):
    """The model class for a book/quote snapshot object."""

    __tablename__ = "booksnapshots"
    dtype = Column(String, primary_key=True, nullable=False)
    symbol = Column(String, primary_key=True, nullable=False)
    exchange = Column(String, primary_key=True, nullable=False)
    name = Column(String, primary_key=True, nullable=False)
    depth = Column(Integer)
    interval = Column(Integer, nullable=False)
    timestamp = Column(DateTime, primary_key=True, nullable=False)
    localTimestamp = Column(DateTime)
    bids_0_price = Column(Float)
    bids_0_amount = Column(Integer)
    bids_1_price = Column(Float)
    bids_1_amount = Column(Integer)
    bids_2_price = Column(Float)
    bids_2_amount = Column(Integer)
    bids_3_price = Column(Float)
    bids_3_amount = Column(Integer)
    bids_4_price = Column(Float)
    bids_4_amount = Column(Integer)
    asks_0_price = Column(Float)
    asks_0_amount = Column(Integer)
    asks_1_price = Column(Float)
    asks_1_amount = Column(Integer)
    asks_2_price = Column(Float)
    asks_2_amount = Column(Integer)
    asks_3_price = Column(Float)
    asks_3_amount = Column(Integer)
    asks_4_price = Column(Float)
    asks_4_amount = Column(Integer)


# helper functions used to initialize the database
def create_schema(engine) -> None:
    Base.metadata.create_all(engine)


def drop_schema(engine) -> None:
    Base.metadata.drop_all(engine)


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

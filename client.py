#!/usr/bin/env python3

"""
A Tardis machine-server normalized websocket client
to download data from a lookback period to now.
"""

import logging
import asyncio
import aiohttp
import json
import urllib.parse
from datetime import datetime, timedelta
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import inspect

import models

GET_HIST_DATA_TIMEOUT = 30 * 60  # 30 minutes

logger = logging.getLogger("tardis_client")
logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
ch.setFormatter(formatter)
logger.addHandler(ch)


def parse_msg(msg_s: str):
    """
    Convert message string to dictionary and flatten it.
    """
    msg: dict = eval(msg_s)
    msg["dtype"] = msg["type"]
    msg.pop("type")
    msg["timestamp"] = datetime.fromisoformat(msg["timestamp"].rstrip("Z"))
    msg["localTimestamp"] = datetime.fromisoformat(msg["localTimestamp"].rstrip("Z"))
    bid_ask = [key for key, val in msg.items() if isinstance(val, list)]
    for key in bid_ask:
        bid_ask_list = msg.pop(key)
        for level, val_dict in enumerate(bid_ask_list):
            for k, v in val_dict.items():
                new_key = f"{key}_{level}_{k}"
                msg[new_key] = v
    return msg


def parse_orm_select_results(results):
    results_list = [
        {
            col.key: getattr(r, col.key)
            for col in inspect(r).mapper.column_attrs
            if getattr(r, col.key) is not None
        }
        for r, in results
    ]
    return results_list


async def get_hist_data(
    exchange="deribit",
    symbols=["BTC-PERPETUAL"],
    data_types=["quote_1m"],
    start="2022-04-26",
    end="2022-04-27",
    include_disconnect=False,
):
    replay_options = {
        "exchange": exchange,
        "symbols": symbols,
        "dataTypes": data_types,
        "from": start,
        "to": end,
        "withDisconnectMessages": include_disconnect,
    }
    options = urllib.parse.quote_plus(json.dumps(replay_options))
    URL = f"ws://localhost:8001/ws-replay-normalized?options={options}"

    data = []
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(URL) as websocket:
            async for msg in websocket:
                d = parse_msg(msg.data)  # convert string to dict
                if d["dtype"] != "disconnect":
                    data.append(d)
    return data


async def stream_live_data(
    exchange="deribit",
    symbols=["BTC-PERPETUAL"],
    data_types=["quote_1s"],
    include_disconnect=False,
):
    stream_options = {
        "exchange": exchange,
        "symbols": symbols,
        "withDisconnectMessages": include_disconnect,
        "dataTypes": data_types,
    }
    options = urllib.parse.quote_plus(json.dumps(stream_options))
    URL = f"ws://localhost:8001/ws-stream-normalized?options={options}"

    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(URL) as websocket:
            async for msg in websocket:
                d = parse_msg(msg.data)
                if d["dtype"] != "disconnect":
                    yield d


async def record_live_data(
    exchange="deribit", symbols=["BTC-PERPETUAL"], data_types=["quote_1m"]
):
    # Get streaming generator
    stream = stream_live_data(exchange=exchange, symbols=symbols, data_types=data_types)

    # Record live data to db
    model_lookup = {"book_snapshot": models.BookSnapshot}
    async_session = sessionmaker(
        models.engine, expire_on_commit=False, class_=AsyncSession
    )
    async with async_session() as session:
        async for entry in stream:
            logger.info(f"Received Live Data: {entry}")
            # Discard 1st live point which is not aligned with interval.
            t = entry["timestamp"]
            if (t.second * 1000 + t.microsecond / 1000) % entry["interval"] != 0:
                continue
            # Insert to database
            model = model_lookup.get(entry["dtype"], None)
            if model is not None:

                row = model(**entry)
                async with session.begin():
                    session.add(row)
                await session.commit()


async def get_data_without_gap_coro(
    exchange: str,
    symbols: list,
    data_types: list,
    lookback: timedelta,
    recording_warmup_seconds: int = 15 * 60,
):
    job_description = f"""
    === Job ===
    exchange: {exchange}
    symbols: {symbols}
    data_types: {data_types}
    lookback: {lookback}
    recording warmup time: {recording_warmup_seconds} seconds

    """
    logger.info(job_description)

    # Create a streaming task in background, and record live data.
    logger.info("Starting live data recording...")
    record_co = record_live_data(
        exchange=exchange, symbols=symbols, data_types=data_types
    )
    record_task = asyncio.create_task(record_co)
    logger.info("Live data recording started.")

    logger.info(
        f"Warm up live data recording for {recording_warmup_seconds} seconds ..."
    )
    await asyncio.sleep(recording_warmup_seconds)

    # Get historical data
    # Latest 15 min historical data unavailable
    hist_end = datetime.utcnow() - timedelta(minutes=14)
    hist_start = hist_end - lookback
    hist_co = get_hist_data(
        exchange=exchange,
        symbols=symbols,
        data_types=data_types,
        start=str(hist_start.date()),
        end=str(hist_end),
    )
    logger.info(f"Downloading historical data ...")
    try:
        hist_data = await asyncio.wait_for(hist_co, timeout=GET_HIST_DATA_TIMEOUT)
        actual_hist_start = hist_data[0]["timestamp"]
        actual_hist_end = hist_data[-1]["timestamp"]
        logger.info(
            f"Downloaded historical data from {actual_hist_start} to {actual_hist_end}."
        )
    except asyncio.TimeoutError:
        logger.error("Time out for getting historical data!")
        hist_data = []
        actual_hist_start, actual_hist_end = None, None

    # Get recorded live data from database
    logger.info("Get recorded live data ...")
    if hist_data:
        query_start = actual_hist_end
    else:
        query_start = datetime.utcnow() - lookback
    async_session = sessionmaker(
        models.engine, expire_on_commit=False, class_=AsyncSession
    )
    async with async_session() as session:
        results = await session.execute(
            select(models.BookSnapshot).where(
                models.BookSnapshot.timestamp >= query_start
            )
        )
        await session.commit()
    recorded_data = parse_orm_select_results(results)
    recorded_start = recorded_data[0]["timestamp"]
    recorded_end = recorded_data[-1]["timestamp"]
    logger.info(f"Get recorded live data from {recorded_start} to {recorded_end}.")

    # Stop streaming and recording
    logger.info("Stop live data recording...")
    record_task.cancel()
    while not record_task.cancelled():
        await asyncio.sleep(0.1)
    logger.info("Live data recording stopped.")

    # Combine historical data and recorded live data
    combined_data = hist_data + recorded_data

    # Cut data to be exactly as the lookback requested,
    # as the API always downloads from 00:00 of a day.
    i = 0
    exact_start = recorded_end - lookback
    for i, entry in enumerate(combined_data):
        if entry["timestamp"] >= exact_start:
            break
    combined_data = combined_data[i:]
    logger.info(
        f"The combined data are from {combined_data[0]['timestamp']} to {combined_data[-1]['timestamp']}."
    )

    return combined_data


def get_data_without_gap(
    exchange: str,
    symbols: list,
    data_types: list,
    lookback: timedelta,
    recording_warmup_seconds: int,
):
    # Initialize database
    asyncio.run(models.init_db())

    # Get data until now
    data = asyncio.run(
        get_data_without_gap_coro(
            exchange=exchange,
            symbols=symbols,
            data_types=data_types,
            lookback=lookback,
            recording_warmup_seconds=recording_warmup_seconds,
        )
    )

    return data


if __name__ == "__main__":
    data = get_data_without_gap(
        exchange="deribit",
        symbols=["BTC-PERPETUAL"],
        data_types=["quote_1m"],
        lookback=timedelta(days=1),
        recording_warmup_seconds=15 * 60,
    )

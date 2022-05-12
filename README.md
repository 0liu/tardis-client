
Tardis Replay Client with Live Streaming
========================================

The problem comes from downloading historical cryptocurrency data (ex. BTCUSD
perpetual quotes on deribit from a week ago to now) from Tardis.dev API. Assume
the local tardis-machine server has been shut down and is being restarted.
After some warm-up period, it's desired to generate minute time series combined
with the recent live data without any gap.


# Design of solution

## Analysis 
We want historical data from a lookback period to now. However, downloading
historical data from Tardis replay API is slow and takes some time. During this
time period, live data keep coming in and they could be lost without recording
them. The idea is recording the live streaming data to a database while
downloading a large block of historical data. When the downloading finishes, we
combine the historical data with the recorded data in the database. In this way
we will obtain a most updated data block, with most of historical data from
Tardis (slow, higher quality) and the latest small portion from recording (fast,
lower quality).

## Design


- Database

  For simple demo purpose, the Python built-in SQLite is used.
    
- Database Tables / Models
  
  Create a table/model for each possible data type: book_snapshot/quote,
  trade_bar, trade, book_change, since they have different data fields and
  structures. Quote data type is a special case of book_snapshot with depth=1.
  
- Concurrent data streming, recording and downloading

  Tardis API Python client is based on Python `Asyncio` module, and all
  functions are co-routines. Therefore the client functions are also designed as
  coroutines listed below:

  - `get_data_without_gap(exchange: str, symbols: list, data_types: list,
    lookback: timedelta, recording_warmup_seconds: int)`
    This is the main entry point to run for this problem. 
  - Coroutine `get_data_without_gap_coro`. Implements the major logic.
  - Coroutine `record_live_data`. Iterate from live data stream generator and insert to databse.
  - Coroutine `stream_live_data`. A live data stream generator from Tardis websocket streaming API.
  - Coroutine `get_hist_data`. Download a block of historical data from Tardis websocket replay API.
    
- Message format

  - The message data from API is string and converted to dictionary in this client module.
  - `type` field is replaced as `dtype` because `type` is a Python keyword.
  - Both `timestamp` and `localTimestamp` strings are converted to Python `datetime` objects.
  - Bids and asks nested lists are flattened for each depth level, like
    `bids_0_price`, `bids_0_amount`, `asks_0_price`, `asks_0_amount`, etc.


# Usage
1. Start Tardis machine server docker
``` python
docker run -p 8000:8000 -p 8001:8001 -e "TM_API_KEY=<KEY>" -d tardisdev/tardis-machine
```

2. Create a Conda environment
``` python
conda create -n tardis -f environment.yml
conda activate tardis
```

3. Run the program

```
python client.py
```

or to inspect the result data in `IPython`:

``` python
from datetime import timedelta
from client import get_data_without_gap

data = get_data_without_gap(
        exchange="deribit",
        symbols=["BTC-PERPETUAL"],
        data_types=["quote_1m"],
        lookback=timedelta(weeks=1),
        recording_warmup_seconds=15 * 60,
)
```



# Future extensions

1. For now the program can only run one download session for a single set of parameters , from starting streaming and
   recording to download the requested data.
   
   To download data without gap at any time, we can run live data streaming and recording in a separate thread and keep it alive as a service, so the local database will keep a copy of recorded data. Whenever we need historical data, we can call this client to download from Tardis API (slow, higher quality) and combine with the recorded data from local database (fast, lower quality) to fill the gap.  

2. There is no interface designed to accept arguments now. Please open
   `client.py` file to modify parameters in the `if __name__ == "__main__"`
   section. In the future an arguments interface can be added to command line
   using `argparse` module or web request.

3. The program only works with quote (book_snapshot) data now. Other types can
   be added later.


# Issues with Tardis machine server normalized API
- API doesn't provide the latest 15 minutes historical data.
      
  To avoid any gap between the downloaded historical data and the recorded live
  data, the live recording task must run for at least 15 minutes at the startup.

- Historical data downloading always starts from 00:00 of the day.

  This is not a big problem, but the API downloads unwanted extra data.
        
- Live streaming with 1 second interval loses data points randomly.

- The replay API for historical data downloading is slow.

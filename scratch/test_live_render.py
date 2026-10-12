import asyncio, sys, os
sys.path.insert(0, ".")
from main import L2EngineRunner
from config import AppConfig

cfg = AppConfig()
runner = L2EngineRunner(config=cfg, record_data=False)

async def test_run():
    print("Testing runner.run_live for 4 seconds...")
    try:
        await runner.run_live(duration_secs=4, show_ui=False)
    except Exception as e:
        print("EXCEPTION in run_live:", type(e), e)
    print("Book valid:", runner.book.is_valid)
    print("Bids len:", len(runner.book.bids))
    print("Asks len:", len(runner.book.asks))
    print("Trades len:", len(runner.trades.trades))
    print("Update count:", runner.book.update_count)

if __name__ == "__main__":
    asyncio.run(test_run())

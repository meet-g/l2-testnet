import asyncio, sys, os
sys.path.insert(0, ".")
from main import L2EngineRunner
from config import AppConfig

cfg = AppConfig()
runner = L2EngineRunner(config=cfg, record_data=False)

async def test_ui():
    print("Testing runner.run_live WITH UI for 5 seconds...")
    try:
        # We simulate what run_live does
        task = asyncio.create_task(runner.run_live(duration_secs=5, show_ui=True))
        await task
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_ui())

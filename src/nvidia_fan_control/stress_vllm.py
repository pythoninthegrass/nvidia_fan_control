"""
Stress test script for local vLLM server.
Makes parallel HTTP requests (up to 10 concurrent) until Ctrl+C.
"""

import asyncio
import aiohttp
import time
import signal
import sys
from dataclasses import dataclass
from typing import Optional

# Configuration
VLLM_URL = "http://localhost:8000/v1/chat/completions"
MAX_CONCURRENT = 50
MODEL = "MiniMax-M2.1-FP8-INT4-AWQ"

# Test prompts to cycle through
PROMPTS = [
    "What is the capital of France?",
    "Explain quantum computing in one sentence.",
    "Write a haiku about programming.",
    "What is 2 + 2?",
    "Name three colors.",
    "What is machine learning?",
    "Tell me a short joke.",
    "What year did World War II end?",
    "Define 'algorithm' briefly.",
    "What is the speed of light?",
]


@dataclass
class Stats:
    total_requests: int = 0
    successful: int = 0
    failed: int = 0
    total_latency: float = 0.0
    min_latency: float = float("inf")
    max_latency: float = 0.0
    total_tokens: int = 0


stats = Stats()
running = True


def signal_handler(sig, frame):
    global running
    print("\n\n🛑 Stopping stress test...")
    running = False


async def make_request(
    session: aiohttp.ClientSession,
    semaphore: asyncio.Semaphore,
    prompt: str,
    request_id: int,
) -> Optional[float]:
    """Make a single request to vLLM."""
    global stats

    async with semaphore:
        if not running:
            return None

        payload = {
            "model": MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 50,
            "temperature": 0.7,
        }

        start_time = time.perf_counter()
        try:
            async with session.post(VLLM_URL, json=payload) as response:
                latency = time.perf_counter() - start_time

                if response.status == 200:
                    data = await response.json()
                    stats.successful += 1
                    stats.total_latency += latency
                    stats.min_latency = min(stats.min_latency, latency)
                    stats.max_latency = max(stats.max_latency, latency)

                    # Extract token count if available
                    usage = data.get("usage", {})
                    tokens = usage.get("total_tokens", 0)
                    stats.total_tokens += tokens

                    print(
                        f"✅ #{request_id:5d} | {latency:6.2f}s | {tokens:4d} tokens | {prompt[:30]}..."
                    )
                else:
                    stats.failed += 1
                    error_text = await response.text()
                    print(f"❌ #{request_id:5d} | Status {response.status}: {error_text[:50]}")

        except aiohttp.ClientError as e:
            stats.failed += 1
            print(f"❌ #{request_id:5d} | Connection error: {e}")
        except Exception as e:
            stats.failed += 1
            print(f"❌ #{request_id:5d} | Error: {e}")

        stats.total_requests += 1
        return None


async def print_stats_periodically():
    """Print statistics every 10 seconds."""
    while running:
        await asyncio.sleep(10)
        if not running:
            break
        print_current_stats()


def print_current_stats():
    """Print current statistics."""
    if stats.successful > 0:
        avg_latency = stats.total_latency / stats.successful
        min_lat = stats.min_latency if stats.min_latency != float("inf") else 0
        print("\n" + "=" * 70)
        print(f"📊 STATS | Total: {stats.total_requests} | "
              f"✅ {stats.successful} | ❌ {stats.failed}")
        print(f"   Latency: avg={avg_latency:.2f}s | min={min_lat:.2f}s | max={stats.max_latency:.2f}s")
        print(f"   Total tokens: {stats.total_tokens} | "
              f"Throughput: {stats.successful / (stats.total_latency / MAX_CONCURRENT):.2f} req/s (approx)")
        print("=" * 70 + "\n")


async def stress_test():
    """Main stress test loop."""
    global running

    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    request_id = 0

    print(f"🚀 Starting vLLM stress test")
    print(f"   URL: {VLLM_URL}")
    print(f"   Model: {MODEL}")
    print(f"   Max concurrent: {MAX_CONCURRENT}")
    print(f"   Press Ctrl+C to stop\n")
    print("=" * 70)

    timeout = aiohttp.ClientTimeout(total=120)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        # Start stats printer
        stats_task = asyncio.create_task(print_stats_periodically())

        tasks = set()

        while running:
            # Keep MAX_CONCURRENT tasks running
            while len(tasks) < MAX_CONCURRENT and running:
                prompt = PROMPTS[request_id % len(PROMPTS)]
                task = asyncio.create_task(
                    make_request(session, semaphore, prompt, request_id)
                )
                tasks.add(task)
                request_id += 1

            if not tasks:
                break

            # Wait for at least one task to complete
            done, tasks = await asyncio.wait(
                tasks, return_when=asyncio.FIRST_COMPLETED
            )

        # Cancel remaining tasks
        for task in tasks:
            task.cancel()

        stats_task.cancel()
        try:
            await stats_task
        except asyncio.CancelledError:
            pass

    # Final stats
    print("\n" + "=" * 70)
    print("📈 FINAL RESULTS")
    print("=" * 70)
    print(f"Total requests:    {stats.total_requests}")
    print(f"Successful:        {stats.successful}")
    print(f"Failed:            {stats.failed}")
    if stats.successful > 0:
        print(f"Average latency:   {stats.total_latency / stats.successful:.2f}s")
        print(f"Min latency:       {stats.min_latency:.2f}s")
        print(f"Max latency:       {stats.max_latency:.2f}s")
        print(f"Total tokens:      {stats.total_tokens}")
    print("=" * 70)


def main():
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        asyncio.run(stress_test())
    except KeyboardInterrupt:
        pass

    print("\n👋 Stress test complete!")
    sys.exit(0)


if __name__ == "__main__":
    main()

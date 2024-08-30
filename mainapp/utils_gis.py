import asyncio
import os
import pickle
from typing import List, Tuple, Dict, Any

import aiohttp
import tenacity


class FailedToGetException(Exception):
    pass


@tenacity.retry(
    wait=tenacity.wait_exponential(multiplier=2, min=2, max=30),
    stop=tenacity.stop_after_attempt(10),
    retry=tenacity.retry_if_exception_type(FailedToGetException),
)
async def fetch_elevation_batch(session: aiohttp.ClientSession, points_batch: List[Tuple[float, float]]) -> List[Dict[str, Any]]:
    url = "https://api.open-elevation.com/api/v1/lookup"
    payload = {
        "locations": [{"latitude": lat, "longitude": lon} for lat, lon in points_batch]
    }
    async with session.post(url, json=payload) as response:
        if response.status == 200:
            data = await response.json()
            return data["results"]
        elif response.status in [429, 502, 503, 504]:
            raise FailedToGetException(f"Retryable error {response.status}")
        else:
            response.raise_for_status()


async def get_elevations_for_points_dict(points: List) -> Dict[Tuple[float, float], float]:
    cache_file = "elevations_cache.pkl"
    if os.path.exists(cache_file):
        with open(cache_file, 'rb') as f:
            cache = pickle.load(f)
    else:
        cache = {}

    ROUND_TO = 3
    hits_misses = {"hits": 0, "misses": 0}
    semaphore = asyncio.Semaphore(3)

    points_to_fetch = []
    for lat, lon in points:
        rounded_point = (round(lat, ROUND_TO), round(lon, ROUND_TO))
        if rounded_point not in cache:
            points_to_fetch.append((lat, lon))
        else:
            hits_misses["hits"] += 1

    async def process_batch(points_batch: List[Tuple[float, float]]):
        async with semaphore:
            async with aiohttp.ClientSession() as session:
                results = await fetch_elevation_batch(session, points_batch)
                for result in results:
                    rounded_point = (
                        round(result["latitude"], ROUND_TO),
                        round(result["longitude"], ROUND_TO),
                    )
                    cache[rounded_point] = result["elevation"]
                    hits_misses["misses"] += 1

    tasks = []
    for i in range(0, len(points_to_fetch), 50):
        batch = points_to_fetch[i:i + 50]
        tasks.append(process_batch(batch))
    await asyncio.gather(*tasks)
    print(f"Cache hits: {hits_misses['hits']}, misses: {hits_misses['misses']}")

    with open(cache_file, 'wb') as f:
        pickle.dump(cache, f)

    return cache

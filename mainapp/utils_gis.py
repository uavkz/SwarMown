import asyncio
import os
import pickle
from typing import cast, List

import aiohttp
import tenacity


class FailedToGetException(Exception):
    pass


@tenacity.retry(
    wait=tenacity.wait_exponential(multiplier=2, min=2, max=30),
    stop=tenacity.stop_after_attempt(10),
    retry=tenacity.retry_if_exception_type(FailedToGetException),
)
async def get_elevation(lng, lat):
    access_token = 'pk.eyJ1Ijoia2luZHlhayIsImEiOiJja2F0cml2eTcwNDZhMnJvOXI4N2Y4MjRjIn0.f7FSJnib2jKKvtJe4ql-Bg'
    url = f'https://api.mapbox.com/v4/mapbox.mapbox-terrain-v2/tilequery/{lng},{lat}.json?layers=contour&limit=50&access_token={access_token}'

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status == 200:
                data = await response.json()
                if 'features' in data and len(data['features']) > 0:
                    elevations = [feature['properties']['ele'] for feature in data['features']]
                    highest_elevation = max(elevations)
                    return highest_elevation
                else:
                    raise Exception('No elevation data')
            else:
                raise FailedToGetException('Failed to get elevation data')
    return None


async def get_elevations_for_points_dict(points: list) -> dict:
    cache_file = "elevations_cache.pkl"
    if os.path.exists(cache_file):
        with open(cache_file, 'rb') as f:
            cache = pickle.load(f)
    else:
        cache = {}

    ROUND_TO = 3
    hits_misses = {"hits": 0, "misses": 0}
    semaphore = asyncio.Semaphore(25)
    async def fetch_with_cache(lng, lat):
        rounded_point = (round(lat, ROUND_TO), round(lng, ROUND_TO))
        if rounded_point in cache:
            hits_misses["hits"] += 1
        else:
            hits_misses["misses"] += 1
            async with semaphore:
                elevation = await get_elevation(lng, lat)
            cache[rounded_point] = elevation
    tasks = [fetch_with_cache(lat, lon) for lat, lon in points]
    await asyncio.gather(*tasks)
    print(f"Cache hits: {hits_misses['hits']}, misses: {hits_misses['misses']}")

    with open(cache_file, 'wb') as f:
        pickle.dump(cache, f)

    return cast(dict, cache)

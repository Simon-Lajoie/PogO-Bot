# utils/api_client.py

import aiohttp
import logging
import asyncio # Required for the retry delay

class RiotAPIClient:
    def __init__(self, api_key: str, region: str):
        self.api_key = api_key
        self.region = region
        self.headers = {"X-Riot-Token": self.api_key}

    async def get_ranked_stats_by_puuid(self, puuid: str, game_type: str) -> list | None:
        """Fetches ranked stats for a PUUID for either LoL or TFT with retry logic."""
        if game_type == "LoL":
            url = f"https://{self.region}.api.riotgames.com/lol/league/v4/entries/by-puuid/{puuid}"
        elif game_type == "TFT":
            url = f"https://{self.region}.api.riotgames.com/tft/league/v1/by-puuid/{puuid}"
        else:
            logging.error(f"Invalid game_type provided: {game_type}")
            return None

        MAX_RETRIES = 3
        for attempt in range(MAX_RETRIES):
            async with aiohttp.ClientSession() as session:
                try:
                    async with session.get(url, headers=self.headers) as response:
                        # Specifically handle rate limit error (429)
                        if response.status == 429:
                            retry_after = int(response.headers.get("Retry-After", "1"))
                            logging.warning(
                                f"Rate limited on attempt {attempt + 1}/{MAX_RETRIES}. "
                                f"Retrying after {retry_after} seconds..."
                            )
                            await asyncio.sleep(retry_after)
                            continue  # Go to the next attempt in the for loop

                        # The original 404 handling is a final state (player is unranked), not an error to retry
                        if response.status == 404:
                            return []

                        # Raise an exception for other bad responses (e.g., 5xx server errors)
                        response.raise_for_status()

                        # If the request was successful, return the JSON data
                        return await response.json()

                except aiohttp.ClientError as e:
                    # Catches other client-side errors like connection issues to be retried
                    logging.warning(
                        f"Request for {puuid} failed on attempt {attempt + 1}/{MAX_RETRIES}: {e}"
                    )
                except Exception as e:
                    # Catch any other unexpected errors, log, and retry
                    logging.warning(
                        f"An unexpected error occurred for {puuid} on attempt {attempt + 1}/{MAX_RETRIES}: {e}"
                    )

            # Wait for a short period before the next retry to avoid hammering the server
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(1)

        # This part is reached only if all retries fail
        logging.error(f"Failed to fetch stats for {puuid} after {MAX_RETRIES} retries.")
        return None
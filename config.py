# config.py

# --- Discord Channel IDs ---
GENERAL_CHANNEL_ID = 1249887657761443841
TFT_LEADERBOARD_CHANNEL_ID = 1249993766300024842
LOL_LEADERBOARD_CHANNEL_ID = 1249993747119472693

# --- API & Task Timings ---
REGION = 'na1'
RANK_FETCH_INTERVAL_SECONDS = 30
LEADERBOARD_UPDATE_INTERVAL_SECONDS = 120
API_BATCH_SIZE = 10

# --- Image Generation Constants ---
FONT_PATH = "assets/fonts/BebasNeue-Regular.ttf"
TFT_BACKGROUND_PATH = "assets/img/leaderboard_tft.png"
LOL_BACKGROUND_PATH = "assets/img/leaderboard_soloq.png"

# --- Game-Specific Constants ---
TFT_QUEUE_TYPE = "RANKED_TFT"
LOL_QUEUE_TYPE = "RANKED_SOLO_5x5"

# --- Load data dictionaries ---
from data import discord_ids, tft_summoner_ids, lol_summoner_ids, ranks, summoner_names_list, emoji_codes
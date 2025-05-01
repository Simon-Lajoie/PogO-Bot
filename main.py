import asyncio
import io
from datetime import datetime, timedelta, timezone
import discord
from discord.ext import commands, tasks
from collections import defaultdict
from datetime import datetime, timedelta
import random

from riotwatcher import LolWatcher, TftWatcher
from PIL import Image, ImageDraw, ImageFont
import logging
import os
from dotenv import load_dotenv
from data import discord_ids, tft_summoner_ids, lol_summoner_ids, ranks, summoner_names_list, emoji_codes

# --- Riot API Setup ---
load_dotenv()
lol_watcher_key = os.environ.get('LOL_WATCHER_KEY')
tft_watcher_key = os.environ.get('TFT_WATCHER_KEY')
tft_watcher = TftWatcher(api_key=tft_watcher_key)
lol_watcher = LolWatcher(api_key=lol_watcher_key)

# --- Logging ---
logging.basicConfig(level=logging.INFO, filename='app.log', filemode='w',
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logging.getLogger("PIL").setLevel(logging.WARNING)
logging.getLogger("discord").setLevel(logging.WARNING)

# --- Constants ---
REGION = 'na1'
GENERAL_CHANNEL_ID = 1249887657761443841
TFT_LEADERBOARD_CHANNEL_ID = 1249993766300024842
LOL_LEADERBOARD_CHANNEL_ID = 1249993747119472693

RANK_FETCH_INTERVAL_SECONDS = 60 # How often to wait between batches of rank fetching
LEADERBOARD_UPDATE_INTERVAL_SECONDS = 360 # 6 minutes for leaderboard image update

API_BATCH_SIZE = 8
API_RETRY_ATTEMPTS = 3 # Number of retries on connection errors
TFT_QUEUE_TYPE = "RANKED_TFT"
LOL_QUEUE_TYPE = "RANKED_SOLO_5x5"

# Image Constants
NORMAL_FONT_SIZE = 25
MEDIUM_FONT_SIZE = 23
SMALL_FONT_SIZE = 21
RANK_IMAGE_SIZE = (55, 55)
POGO_IMAGE_SIZE = (40, 40)
BACKGROUND_SIZE = (1366, 757)
TFT_BACKGROUND_PATH = "img/leaderboard_tft.png"
LOL_BACKGROUND_PATH = "img/leaderboard_soloq.png"
FONT_PATH = "fonts/BebasNeue-Regular.ttf"

# --- Global State ---
leaderboard_status_messages = {"TFT": None, "LoL": None}
previous_leaderboard_rankings = {"TFT": [], "LoL": []}
last_leaderboard_messages = {"TFT": None, "LoL": None}

# In-memory storage for the latest fetched rankings
updated_tft_rankings_list = []
updated_lol_rankings_list = []
# Locks for concurrent access to the ranking lists
updated_tft_rankings_list_lock = asyncio.Lock()
updated_lol_rankings_list_lock = asyncio.Lock()

def get_discord_username(summoner_name):
    name = discord_ids.get(summoner_name)
    if name is None:
        name = summoner_name
    return name


# TFT-SUMMONER-V1 : /tft/summoner/v1/summoners/by-puuid/{encryptedPUUID} :  id
def get_tft_summoner_id(summoner_name):
    return tft_summoner_ids.get(summoner_name)

# SUMMONER-V4 : /lol/summoner/v4/summoners/by-puuid/{encryptedPUUID} :  id
def get_lol_summoner_id(summoner_name):
    return lol_summoner_ids.get(summoner_name)

def calculate_tier_division_value(tier_division_rank):
    return ranks.get(tier_division_rank, 0)


def rank_to_value(tier_division_rank, lp):
    tier_division_value = calculate_tier_division_value(tier_division_rank)
    final_ranked_value = tier_division_value * 100 + lp
    return final_ranked_value

async def get_ranked_stats(summoner_names, get_summoner_id_func, watcher, queue_type, game_name=""):
    from requests.exceptions import HTTPError
    rankings_list = []

    for summoner_name in summoner_names:
        max_attempts = 2
        attempt = 0
        ranked_stats = None
        while attempt < max_attempts:
            try:
                summoner_id = get_summoner_id_func(summoner_name)
                logging.info(f"Making request to Riot API for {game_name} ranked stats of summoner: {summoner_name}")
                print(f"Making request to Riot API for {game_name} ranked stats of summoner: {summoner_name}")
                ranked_stats = watcher.league.by_summoner(region=REGION, encrypted_summoner_id=summoner_id)
                break
            except ConnectionError:
                attempt += 1
                wait_time = 2 ** attempt
                logging.warning(f"ConnectionError occurred, retrying in {wait_time} seconds...")
                await asyncio.sleep(wait_time)
            except HTTPError as e:
                if e.response.status_code == 429:
                    retry_after = int(e.response.headers.get('Retry-After', 0))
                    logging.warning(f"429 Client Error: Too Many Requests, retrying in {retry_after} seconds...")
                    await asyncio.sleep(retry_after)
                    continue
                else:
                    raise e
        else:
            logging.error(f"Failed to get data from Riot API after {max_attempts} attempts")

        ranked_stats = next((stats for stats in ranked_stats if stats["queueType"] == queue_type), None)

        if ranked_stats:
            tier = ranked_stats["tier"]
            rank = ranked_stats["rank"]
            lp = ranked_stats["leaguePoints"]
            tier_division = f"{tier} {rank}"
            ranked_value = rank_to_value(tier_division, lp)
            if tier in ["MASTER", "GRANDMASTER", "CHALLENGER"]:
                rank = ""
                tier_division_lp = f"{tier} {lp}"
            else:
                tier_division_lp = f"{tier} {rank} {lp}"
            print(f"{summoner_name}: {ranked_value}: {tier} {rank} {lp} LP")
        else:
            tier = "UNRANKED"
            lp = 0
            ranked_value = 0
            tier_division_lp = tier
            print(f"{summoner_name}: {tier}")

        rankings_list.append((summoner_name, ranked_value, lp, tier, tier_division_lp))

    rankings_list.sort(key=lambda x: (x[1], x[0]), reverse=True)
    return rankings_list

async def update_rankings_list_task(
    lock: asyncio.Lock,
    rankings_list_to_update: list,
    game_type_name: str
):
    """
    Continuously fetches rankings in batches for a specific game type.
    Determines which API functions/constants to use based on game_type_name.
    """
    logging.info(f"Starting continuous rank fetching task for {game_type_name}...")
    print(f"Starting background rank fetching for {game_type_name}...")

    # Determine the correct functions and constants based on game_type_name ONCE
    if game_type_name == "TFT":
        id_func = get_tft_summoner_id
        watcher_instance = tft_watcher
        q_type = TFT_QUEUE_TYPE
    elif game_type_name == "LoL":
        id_func = get_lol_summoner_id
        watcher_instance = lol_watcher
        q_type = LOL_QUEUE_TYPE
    else:
        logging.error(f"[{game_type_name} Fetcher] Invalid game_type_name provided. Stopping task.")
        print(f"Error: Invalid game type '{game_type_name}' for fetching task.")
        return # Stop the task if the game type is unknown

    # --- Main Loop ---
    while True:
        logging.info(f"[{game_type_name} Fetcher] Starting new full pass...")
        all_summoners = summoner_names_list[:]
        random.shuffle(all_summoners)

        for i in range(0, len(all_summoners), API_BATCH_SIZE):
            batch = all_summoners[i:i + API_BATCH_SIZE]
            logging.info(f"[{game_type_name} Fetcher] Fetching rankings for batch: {batch}")
            print(f"Fetching {game_type_name} batch: {batch}")

            try:
                # Call the generic get_ranked_stats with the correct parameters
                batch_rankings = await get_ranked_stats(
                    summoner_names=batch,
                    get_summoner_id_func=id_func,           # Use determined function
                    watcher=watcher_instance,               # Use determined watcher
                    queue_type=q_type,                      # Use determined queue type
                    game_name=game_type_name
                )
            except Exception as e:
                logging.exception(f"[{game_type_name} Fetcher] Unhandled error calling get_ranked_stats for batch {batch}: {e}")
                print(f"Error fetching {game_type_name} batch: {e}")
                await asyncio.sleep(10)
                continue

            if not batch_rankings:
                logging.warning(f"[{game_type_name} Fetcher] Received no ranking data for batch: {batch}")
                await asyncio.sleep(RANK_FETCH_INTERVAL_SECONDS)
                continue

            # --- Update shared list (logic remains the same) ---
            async with lock:
                new_data_map = {ranking[0]: ranking for ranking in batch_rankings}
                for idx, existing_ranking in enumerate(rankings_list_to_update):
                    summoner_name = existing_ranking[0]
                    if summoner_name in new_data_map:
                        rankings_list_to_update[idx] = new_data_map[summoner_name]
                        del new_data_map[summoner_name]
                rankings_list_to_update.extend(new_data_map.values())
                rankings_list_to_update.sort(key=lambda x: (x[1], x[0]), reverse=True)

            logging.info(f"[{game_type_name} Fetcher] Updated rankings list ({len(rankings_list_to_update)} players).")

            # --- Wait interval ---
            logging.debug(f"[{game_type_name} Fetcher] Waiting {RANK_FETCH_INTERVAL_SECONDS}s until next batch...")
            await asyncio.sleep(RANK_FETCH_INTERVAL_SECONDS)

        logging.info(f"[{game_type_name} Fetcher] Completed full pass. Repeating loop.")

def get_random_message(old_summoner, new_summoner, position, game_type):
    new_summoner = get_discord_username(new_summoner)
    old_summoner = get_discord_username(old_summoner)
    gourish_summoner = get_discord_username("Gourish")
    salsa_king_summoner = get_discord_username("Wallaby")
    messages = [
        f"{new_summoner} just pulled off a spectacular heist {emoji_codes.get('business')}, ousting {old_summoner} from position {position} like a sneaky mastermind {emoji_codes.get('cathiago')}!",
        f"Yeah.. {emoji_codes.get('sadge')} I'm sorry to announce {new_summoner} has dethroned {old_summoner} from position {position}. Don't ask me how. {emoji_codes.get('pepeshrug')}. Surely this is deserved. {emoji_codes.get('scam')}",
        f"{emoji_codes.get('pogo')} {new_summoner} has kicked {old_summoner} from position {position}. Did you really expect me to praise you for that ? Take this instead: {emoji_codes.get('pantsgrab')}",
        f"{emoji_codes.get('pogo')} ALERT! ALERT! {emoji_codes.get('pogo')} {new_summoner} has executed a flawless takedown, banishing {old_summoner} from position {position}. It's time to rally the troops and show our support to {new_summoner} by showering them with a barrage of {emoji_codes.get('pogo')}.",
        f"{emoji_codes.get('pogo')} {new_summoner} has decisively toppled {old_summoner} from position {position}, leaving no doubt of their supremacy. {emoji_codes.get('cathiago')}",
        f"NAHHHH THIS {new_summoner} PLAYER MIGHT JUST THE THE BEST PLAYER IN THE WORLD.{emoji_codes.get('dongerj')} HE LITERALLY JUST TOOK POSITION {position} FROM {old_summoner} JUST LIKE THAT ? {emoji_codes.get('huh')} IT'S WAY TOO FREE. {new_summoner} IS JUST BUILT DIFFERENT! {emoji_codes.get('pepestrong')}",
        f"{new_summoner} --> {position} {emoji_codes.get('pogo')} {old_summoner} --> {emoji_codes.get('deadge')}",
        f"{emoji_codes.get('pogo')} BREAKING NEWS! BREAKING NEWS! {emoji_codes.get('pogo')} A major upset has just occurred. {new_summoner} has just dethroned {old_summoner} from position {position}. It's a shocking turn of events, a stunning upset, a colossal blunder. {emoji_codes.get('aycaramba')}",
        f"{emoji_codes.get('pogo')} Hold on as {new_summoner} shakes things up and steals the glory from {old_summoner} at position {position}. {old_summoner} has just been humiliated, disgraced, destroyed. {emoji_codes.get('huh')} They have been reduced to nothing. {emoji_codes.get('huh')} They are now forgotten. {emoji_codes.get('huh')}",
        f"{emoji_codes.get('pogo')} Ladies and gentlemen, gather 'round! Witness the rise of {new_summoner} as they conquer position {position} and send {old_summoner} packing! {emoji_codes.get('pantsgrab')} It's like watching a legendary underdog story unfold before our eyes. {emoji_codes.get('business')}",
        f"{emoji_codes.get('pogo')} Hey {old_summoner}, guess who just took your spot at position {position}? {emoji_codes.get('scam')} Oh right, it's {new_summoner}! {emoji_codes.get('deadge')} {emoji_codes.get('aycaramba')} Looks like someone could use a lesson or two... Get ready to learn TFT buddy. {emoji_codes.get('pogo')}",
        f"{emoji_codes.get('pogo')} Brace yourselves for the rise of {new_summoner}! They've outshined {old_summoner} at position {position}. {emoji_codes.get('peepoflor')} Meanwhile, {old_summoner} seems to be lost in the shadows of defeat. {emoji_codes.get('sadge')} Better luck next time, {old_summoner}, you'll need it! {emoji_codes.get('pogo')}",
        f"{emoji_codes.get('pogo')} Brace yourselves, ladies and gentlemen, because we have a new champion in town! {emoji_codes.get('pepestrong')} {new_summoner} has just obliterated {old_summoner} from position {position}, leaving no room for doubt. It's a devastating blow, a crushing defeat, a humiliating loss. {emoji_codes.get('deadge')}",
        f"{emoji_codes.get('pogo')} Hold on to your seats, folks, because we have a wild ride ahead of us! {emoji_codes.get('pogo')} {new_summoner} has just pulled off a miraculous feat, snatching position {position} from {old_summoner} in a nail-biting showdown.",
        f"{emoji_codes.get('pogo')} Wow! Wow! Wow! {emoji_codes.get('pogo')} {new_summoner} has just outplayed {old_summoner} from position {position}, showing us all what this game is all about. {emoji_codes.get('yeahboi')} It's a dazzling show, a thrilling game, a spectacular victory. {emoji_codes.get('dongerj')}",
        f"{emoji_codes.get('pogo')} {new_summoner} has just taken position {position} from {old_summoner}. {emoji_codes.get('business')} In a cruel display of humiliation, {new_summoner} has left a message for us: This game is just all luck no skills, unlucky buddy {emoji_codes.get('scam')}",
        f"{emoji_codes.get('pogo')} OOF! {old_summoner} just got destroyed by {new_summoner}, who took position {position} from them. {emoji_codes.get('aycaramba')} Mortdog sends his regards, unlucky buddy {emoji_codes.get('pantsgrab')}",
        f"{emoji_codes.get('huh')} HUH... {old_summoner} just got outplayed by {new_summoner}, who snatched position {position} from them. Maybe you just didn’t hit this game, surely you will hit next game {emoji_codes.get('scam')} 📉",
        f"{emoji_codes.get('pogo')} What a tragedy.. Surely. {emoji_codes.get('pogo')} {old_summoner} just got annihilated by {new_summoner}, who claimed position {position} from them. Who balances this game? {emoji_codes.get('pepeshrug')} Unlucky buddy. Take this L {emoji_codes.get('sadge')}",
        f"{emoji_codes.get('pogo')} {old_summoner} just got humiliated by {new_summoner}, who kicked them from position {position}. RIP BOZO. 🤡 You won’t be missed {emoji_codes.get('deadge')}",
        f"{old_summoner} got yeeted from {position} by {new_summoner}! {emoji_codes.get('pogo')} Take this L. {emoji_codes.get('pantsgrab')}",
        f"{new_summoner} humiliated {old_summoner} for {position}! {emoji_codes.get('absolutecinema')} Get lost, noob. {emoji_codes.get('pogo')}",
        f"{new_summoner} clowning {old_summoner} at {position}! {emoji_codes.get('pogo')} Bald move, bro. {emoji_codes.get('wallabyBald')}",
        f"{new_summoner} rolled {old_summoner} for {position}! {emoji_codes.get('pogo')} You're washed up. {emoji_codes.get('pepestrong')}",
        f"{old_summoner} got scammed by {new_summoner} at {position}! {emoji_codes.get('scam')} Unlucky, buddy. {emoji_codes.get('pogo')}",
        f"{new_summoner} dunked {old_summoner} from {position}! {emoji_codes.get('pogo')} You're irrelevant now. {emoji_codes.get('deadge')}",
        f"{old_summoner} got smoked by {new_summoner} at {position}! {emoji_codes.get('pogo')} What was that? {emoji_codes.get('huh')}",
        f"{new_summoner} toppled {old_summoner} at {position}! {emoji_codes.get('dongerj')} You're done for. {emoji_codes.get('pogo')}",
        f"{old_summoner} got kicked from {position} by {new_summoner}! {emoji_codes.get('pogo')} See ya, bud. {emoji_codes.get('salute')}",
        f"{new_summoner} crushed {old_summoner} at {position}! {emoji_codes.get('pogo')} It's over for you. {emoji_codes.get('joever')}",
        f"{new_summoner} outplayed {old_summoner} at {position}! {emoji_codes.get('icant')} Can't believe you choked. {emoji_codes.get('pogo')}",
        f"{new_summoner} snatched {position} from {old_summoner}! {emoji_codes.get('xdd')} You're irrelevant now. {emoji_codes.get('pogo')}",
        f"{old_summoner} got bodied by {new_summoner} at {position}! {emoji_codes.get('pogo')} What's your excuse? {emoji_codes.get('yamesy')}",
        f"{new_summoner} sent {old_summoner} packing from {position}! {emoji_codes.get('barack')} You're history. {emoji_codes.get('pogo')}",
        f"{old_summoner} got laughed off {position} by {new_summoner}! {emoji_codes.get('hah')} Pathetic showing. {emoji_codes.get('pogo')}",
        f"{new_summoner} slapped {old_summoner} from {position}! {emoji_codes.get('pogo')} Here's your flowers. {emoji_codes.get('peepoflor')}",
        f"{new_summoner} owned {old_summoner} at {position}! {emoji_codes.get('business')} You're a ghost now. {emoji_codes.get('pogo')}",
        f"{old_summoner} got wrecked by {new_summoner} at {position}! {emoji_codes.get('pogo')} Take this L. {emoji_codes.get('sadge')}",
        f"{new_summoner} erased {old_summoner} from {position}! {emoji_codes.get('pogo')} Really, dude? {emoji_codes.get('buffet')}",
        f"{new_summoner} dethroned {old_summoner} at {position}! {emoji_codes.get('pogo')} Smirky victory. {emoji_codes.get('cathiago')}",
        f"{old_summoner} got outplayed by {new_summoner} at {position}! {emoji_codes.get('yeahboi')} You're finished. {emoji_codes.get('pogo')}",
        f"{new_summoner} annihilated {old_summoner} at {position}! {emoji_codes.get('pogo')} Total disaster. {emoji_codes.get('aycaramba')}",
        f"{old_summoner} got clowned by {new_summoner} at {position}! {emoji_codes.get('pogo')} You're irrelevant. {emoji_codes.get('pepeshrug')}",
        f"{new_summoner} crushed {old_summoner} from {position}! {emoji_codes.get('pogo')} RIP, you're gone. {emoji_codes.get('deadge')}"
    ]
    gourish_messages = ["demoted", "banished", "relegated", "exiled", "downgraded", "dismissed", "degraded", "expelled",
                        "ousted", "lowered", "removed", "cast out", "dethroned", "ejected", "displaced", "deposed"]
    #if old_summoner == gourish_summoner:
    #    gourish_random = random.choice(gourish_messages)
    #    return f"{emoji_codes['pogo']} {new_summoner} has just {gourish_random} {old_summoner} to their rightful place… NOOB! GOOGOO IS A NOOB! AGREED!  {emoji_codes['aycaramba']}"
    #if old_summoner == salsa_king_summoner:
    #    return f"{emoji_codes['pogo']} {new_summoner} has overtaken {old_summoner} to achieve rank {position}, telling {old_summoner} that throughout Heaven and Earth, he alone is The Fraudulent One. {emoji_codes['pogo']}"
    #if new_summoner == salsa_king_summoner:
    #    return f"{emoji_codes['pogo']} {new_summoner} has overtaken {old_summoner} to achieve rank {position}, proving once again that throughout Heaven and Earth, he alone is The Honored One. {emoji_codes['pogo']}"
    return f"{game_type} : " + random.choice(messages)


async def clear_channel(channel):
    # Check if the bot has the necessary permissions to delete messages
    if not channel.permissions_for(channel.guild.me).manage_messages:
        print(f"I do not have permission to delete messages in {channel.name}")
        return

    # Get the last 5 messages in the channel
    messages = []
    async for message in channel.history(limit=5):
        messages.append(message)

    # Delete the messages
    for message in messages:
        await message.delete()
        logging.debug(f"Message deleted: {message.content}")

async def update_leaderboard(
    game_type: str,
    previous_rankings: list,
    message: discord.Message,
    updated_rankings_list_lock: asyncio.Lock,
    updated_rankings_list: list,
    leaderboard_channel_id: int,
    background_image_path: str,
    send_alert_message: bool = True # Flag to control rank change alert
):
    """
    Generic function to update a game leaderboard (TFT or LoL).
    """
    global last_leaderboard_messages # Access the dictionary storing last messages

    async with updated_rankings_list_lock:
        general_channel = client.get_channel(GENERAL_CHANNEL_ID)
        leaderboard_channel = client.get_channel(leaderboard_channel_id)

        if not general_channel or not leaderboard_channel:
            logging.error(f"Could not find required channels for {game_type} leaderboard.")
            print(f"Error: Could not find required channels for {game_type} leaderboard.")
            # Potentially edit message to show error and stop?
            # await message.edit(content=f"Error updating {game_type} leaderboard: Channel not found.")
            return # Stop execution if channels aren't found

        # Edit the content of the message object to display "refreshing..."
        logging.info(f"{game_type} Countdown timer: Refreshing {game_type} leaderboard...")
        print(f"Refreshing {game_type} leaderboard...")
        try:
            await message.edit(content=f"Refreshing {game_type} leaderboard...")
        except discord.NotFound:
            logging.warning(f"Message for {game_type} leaderboard update not found. It might have been deleted.")
            # Decide how to handle this - maybe just log and continue, or stop?
            # For now, we'll log and continue, assuming a new message might be needed later.
            pass
        except discord.HTTPException as e:
            logging.error(f"Failed to edit message for {game_type} leaderboard refresh: {e}")
            print(f"Failed to edit message for {game_type} leaderboard refresh: {e}")
            # Continue, but refreshing state won't be shown on the old message.


        logging.info(f"Previous {game_type} rankings: {previous_rankings}")
        print(f"Collecting {game_type} ranked stats...")
        # Compare the top 4 summoners in the previous rankings with the top 4 summoners in the new rankings
        # Ensure we don't go out of bounds if lists are shorter than 4
        comparison_range = min(4, len(updated_rankings_list), len(previous_rankings) if previous_rankings else 0)
        if previous_rankings: # Only compare if there are previous rankings
            for i in range(comparison_range):
                 # Check if player at rank i has changed
                if updated_rankings_list[i][0] != previous_rankings[i][0]:
                    current_player = updated_rankings_list[i][0]
                    rank = updated_rankings_list[i][1] # Assuming index 1 is numerical rank or similar

                    # Skip if the current player is unranked (assuming rank 0 means unranked as in TFT example)
                    # Adjust this condition if 'unranked' is represented differently
                    if rank == 0:
                         continue

                    # Find the previous rank of the current player
                    player_ranks = [idx for idx, p_rank in enumerate(previous_rankings) if p_rank[0] == current_player]

                    if player_ranks:
                        previous_rank_index = player_ranks[0]
                        # Check if the player moved up in the rankings (lower index means higher rank)
                        if i < previous_rank_index:
                            logging.info(f"{game_type} Rankings have changed! {updated_rankings_list[i][0]} has passed {previous_rankings[i][0]}")
                            print(f"{game_type} Rankings have changed! {updated_rankings_list[i][0]} has passed {previous_rankings[i][0]}")
                            # Send alert message if enabled
                            if send_alert_message:
                                try:
                                    await general_channel.send(
                                        get_random_message(previous_rankings[i][0], updated_rankings_list[i][0], i + 1, game_type))
                                    logging.info(f"{game_type} Rankings update message sent to General chat!")
                                    print(f"{game_type} Rankings update message sent to General chat!")
                                except discord.HTTPException as e:
                                     logging.error(f"Failed to send {game_type} rank change alert: {e}")
                                     print(f"Failed to send {game_type} rank change alert: {e}")
                            else:
                                logging.info(f"{game_type} Rankings changed message (alert disabled).")
                                print(f"{game_type} Rankings changed message (alert disabled).")

        # Clear the contents of the previous_rankings list
        previous_rankings.clear()
        # Add the new rankings to the previous_rankings list
        previous_rankings.extend(updated_rankings_list)

        logging.info(f"Newly {game_type} updated rankings: {previous_rankings}")
        print(f"Updating {game_type} leaderboard...")

        # Delete the last leaderboard message for this specific game_type if it exists
        last_message_for_game = last_leaderboard_messages.get(game_type)
        if last_message_for_game:
            try:
                print(f"Deleting last {game_type} message...")
                await last_message_for_game.delete()
                last_leaderboard_messages[game_type] = None # Clear it after successful deletion
            except discord.NotFound:
                print(f"Last {game_type} message already deleted or not found.")
                last_leaderboard_messages[game_type] = None # Clear it as it's gone
            except discord.HTTPException as e:
                logging.error(f"Failed to delete previous {game_type} leaderboard message: {e}")
                print(f"Failed to delete previous {game_type} leaderboard message: {e}")
                # Keep the reference in case deletion works next time? Or clear it? Let's clear it.
                last_leaderboard_messages[game_type] = None


        # --- Image Generation (Identical logic, uses parameters) ---
        NORMAL_FONT_SIZE = 25
        MEDIUM_FONT_SIZE = 23
        SMALL_FONT_SIZE = 21
        RANK_IMAGE_SIZE = (55, 55)
        POGO_IMAGE_SIZE = (40, 40) # Assuming "POGO" was for unranked?
        BACKGROUND_SIZE = (1366, 757) # Assuming size is same for both

        try:
            # Load the background image and resize it
            background_image = Image.open(background_image_path).convert("RGBA")
            background_image = background_image.resize(BACKGROUND_SIZE)

            # Create a new image
            image = Image.new("RGB", BACKGROUND_SIZE, "white").convert("RGBA")
            image.alpha_composite(background_image)

            draw = ImageDraw.Draw(image)

            # Load fonts (consider loading only once outside the loop if performance matters)
            font_bebas_normal = ImageFont.truetype("fonts/BebasNeue-Regular.ttf", NORMAL_FONT_SIZE)
            font_bebas_medium = ImageFont.truetype("fonts/BebasNeue-Regular.ttf", MEDIUM_FONT_SIZE)
            font_bebas_small = ImageFont.truetype("fonts/BebasNeue-Regular.ttf", SMALL_FONT_SIZE)

            # Draw the summoner names, tier images, and tier text
            x_offsets = [70, 513, 956]
            y_offsets = [0, 73, 146, 219, 292, 364, 439] # Offsets relative to top-left of each player slot area

            for i in range(3): # Columns
                for j in range(7): # Rows
                    index = i * 7 + j
                    if index >= len(updated_rankings_list):
                        break
                    summoner = updated_rankings_list[index] # Assumes format [name, rank_value, ?, tier_str, rank_division_str]
                    x_base = x_offsets[i]
                    y_base = y_offsets[j]

                    # Determine font size for name
                    name_font = font_bebas_small if len(summoner[0]) > 12 else font_bebas_normal
                    # Draw summoner name (Adjust coordinates based on your template image)
                    # These coordinates (x+45, y+235) looked specific to the template structure
                    draw.text((x_base + 45, y_base + 235), summoner[0], fill="white", font=name_font)

                    # Draw tier image
                    tier_str = summoner[3].upper() # Ensure consistent casing (e.g., "UNRANKED")
                    try:
                        image_path = f"img/{tier_str}.png"
                        tier_image = Image.open(image_path).convert("RGBA")

                        # Determine image size and position
                        image_size = POGO_IMAGE_SIZE if tier_str == "UNRANKED" else RANK_IMAGE_SIZE
                        tier_image.thumbnail(image_size) # Use thumbnail to resize while preserving aspect ratio

                        tier_image_x = x_base + 165
                        # Adjust y position based on tier - refine this logic if needed
                        if tier_str in ["UNRANKED", "PLATINUM", "DIAMOND", "MASTER", "GRANDMASTER", "CHALLENGER"]:
                            tier_image_y = y_base + 225
                        else: # IRON, BRONZE, SILVER, GOLD, EMERALD?
                            tier_image_y = y_base + 220

                        image.alpha_composite(tier_image, dest=(tier_image_x, tier_image_y))
                    except FileNotFoundError:
                        logging.warning(f"Tier image not found: {image_path}")
                        print(f"Warning: Tier image not found: {image_path}")
                    except Exception as img_err:
                        logging.error(f"Error processing tier image {image_path}: {img_err}")
                        print(f"Error processing tier image {image_path}: {img_err}")


                    # Draw tier & rank text
                    # Determine font size for rank text (GM/Challenger smaller?)
                    rank_font = font_bebas_medium if tier_str in ["GRANDMASTER", "CHALLENGER"] else font_bebas_normal
                    rank_text = f"{summoner[4]}" # Assuming index 4 holds rank/division like "I", "IV", "250 LP"
                    # Adjust coordinates based on template
                    draw.text((x_base + 237, y_base + 235), rank_text, fill="white", font=rank_font)

            # Save the image to a file-like object in memory
            with io.BytesIO() as output:
                image.save(output, format="PNG")
                output.seek(0)
                print(f"Sending updated {game_type} leaderboard...")
                # Send the image and store the message object
                sent_message = await leaderboard_channel.send(
                    file=discord.File(output, filename="leaderboard.png"))
                last_leaderboard_messages[game_type] = sent_message # Store the message object

        except FileNotFoundError:
            logging.error(f"Background image not found: {background_image_path}")
            print(f"Error: Background image not found: {background_image_path}")
            await message.edit(content=f"Error updating {game_type} leaderboard: Image asset missing.")
            return # Stop if background is missing
        except Exception as e:
            logging.exception(f"An error occurred during {game_type} leaderboard image generation or sending: {e}")
            print(f"An error occurred during {game_type} leaderboard image generation or sending: {e}")
            try:
                 await message.edit(content=f"Error updating {game_type} leaderboard. Please check logs.")
            except discord.HTTPException:
                 pass # Ignore if editing fails
            return # Stop if image generation/sending failed


    # Start the countdown timer using the passed function
    logging.info(f"Starting {game_type} countdown timer...")
    print(f"Starting {game_type} countdown timer...")
    # Pass game_type and the specific refreshing message content to the generic timer
    await countdown_timer(360, message, game_type)


async def countdown_timer(time: int, message: discord.Message, game_type: str):
    """Generic countdown timer for leaderboard updates."""
    log_prefix = f"[{game_type} Countdown]"
    logging.info(f"{log_prefix} Starting timer ({time}s) for message {message.id}")
    print(f"Starting {game_type} countdown timer ({time}s)")

    time = max(1, time)

    initial_minutes = (time + 59) // 60  # Round up

    try:
        await message.edit(content=f"Next update in: {initial_minutes} minutes")
    except discord.NotFound:
        logging.warning(f"{log_prefix} Status message {message.id} not found at start. Stopping timer.")
        return
    except discord.HTTPException as e:
        logging.error(f"{log_prefix} Failed to edit status message at start: {e}. Stopping timer.")
        return

    last_displayed_minute = initial_minutes
    notified_10 = False
    notified_5 = False

    while time > 0:
        await asyncio.sleep(1)
        time -= 1

        if time <= 0:
            break

        minutes_remaining = (time + 59) // 60

        try:
            if time == 10 and not notified_10:
                await message.edit(content="Next update in: 10 seconds")
                logging.info(f"{log_prefix} Displayed 10 seconds")
                notified_10 = True

            elif time == 5 and not notified_5:
                await message.edit(content="Next update in: 5 seconds")
                logging.info(f"{log_prefix} Displayed 5 seconds")
                notified_5 = True

            elif minutes_remaining < last_displayed_minute:
                await message.edit(content=f"Next update in: {minutes_remaining} minutes")
                logging.info(f"{log_prefix} Updated to {minutes_remaining} minutes")
                last_displayed_minute = minutes_remaining

        except discord.NotFound:
            logging.warning(f"{log_prefix} Status message {message.id} not found during update. Stopping timer.")
            return
        except discord.HTTPException as e:
            logging.error(f"{log_prefix} Failed to edit status message during update: {e}")
            # Continue loop

    logging.info(f"{log_prefix} Countdown timer finished naturally for message {message.id}")
    print(f"{game_type} Countdown timer finished.")


# ===============================================================
# ANTI-NUKE (Protects from mass deletion of channels and bans)
# ===============================================================
# Define thresholds and timeframes
BAN_THRESHOLD = 2
KICK_THRESHOLD = 2
DELETE_THRESHOLD = 2
TIME_FRAME = timedelta(minutes=5)

# Track actions
action_tracker = defaultdict(list)


async def check_actions(user, action_type, threshold):
    now = datetime.now(timezone.utc)
    # Remove old actions
    action_tracker[action_type] = [action for action in action_tracker[action_type]
                                   if now - action[1] < TIME_FRAME]
    # Add new action
    action_tracker[action_type].append((user, now))

    # Count actions by this user
    user_actions = [action for action in action_tracker[action_type]
                    if action[0] == user]
    if len(user_actions) >= threshold:
        return True
    return False

# =====================
# Discord Bot Setup & Loops
# =====================

intents = discord.Intents.default()
intents.members = True
intents.guilds = True
intents.message_content = True
client = commands.Bot(command_prefix="!", intents=intents) # Use Bot for tasks

# --- Scheduled Task: TFT Leaderboard Update ---
@tasks.loop(seconds=LEADERBOARD_UPDATE_INTERVAL_SECONDS)
async def tft_leaderboard_update_loop():
    logging.info("[TFT Loop] Task triggered.")
    game_type = "TFT"
    status_message = leaderboard_status_messages.get(game_type)
    prev_ranks = previous_leaderboard_rankings.get(game_type) # Get the mutable list

    if status_message is None or prev_ranks is None:
        logging.error(f"[TFT Loop] State not initialized (message or prev_ranks missing). Skipping cycle.")
        return

    await update_leaderboard(
        game_type=game_type,
        previous_rankings=prev_ranks, # Pass the list
        message=status_message,
        updated_rankings_list_lock=updated_tft_rankings_list_lock,
        updated_rankings_list=updated_tft_rankings_list, # Pass the global list
        leaderboard_channel_id=TFT_LEADERBOARD_CHANNEL_ID,
        background_image_path=TFT_BACKGROUND_PATH,
        send_alert_message=True # Enable alerts for TFT
    )
    logging.info("[TFT Loop] Task cycle completed.")

@tft_leaderboard_update_loop.before_loop
async def before_tft_loop():
    logging.info("TFT Loop: Waiting for bot to be ready...")
    await client.wait_until_ready()
    logging.info("TFT Loop: Bot ready, loop starting.")

# --- Scheduled Task: LoL Leaderboard Update ---
@tasks.loop(seconds=LEADERBOARD_UPDATE_INTERVAL_SECONDS)
async def lol_leaderboard_update_loop():
    logging.info("[LoL Loop] Task triggered.")
    game_type = "LoL"
    status_message = leaderboard_status_messages.get(game_type)
    prev_ranks = previous_leaderboard_rankings.get(game_type) # Get the mutable list

    if status_message is None or prev_ranks is None:
        logging.error(f"[LoL Loop] State not initialized (message or prev_ranks missing). Skipping cycle.")
        return

    await update_leaderboard(
        game_type=game_type,
        previous_rankings=prev_ranks, # Pass the list
        message=status_message,
        updated_rankings_list_lock=updated_lol_rankings_list_lock,
        updated_rankings_list=updated_lol_rankings_list, # Pass the global list
        leaderboard_channel_id=LOL_LEADERBOARD_CHANNEL_ID,
        background_image_path=LOL_BACKGROUND_PATH,
        send_alert_message=True # Enable alerts for LoL
    )
    logging.info("[LoL Loop] Task cycle completed.")

@lol_leaderboard_update_loop.before_loop
async def before_lol_loop():
    logging.info("LoL Loop: Waiting for bot to be ready...")
    await client.wait_until_ready()
    logging.info("LoL Loop: Bot ready, loop starting.")

# --- Bot Event: On Ready ---
@client.event
async def on_ready():
    print(f'Logged in as {client.user.name} ({client.user.id})')
    logging.info(f"Bot logged in as {client.user.name}")
    print('------')

    # --- Channel Setup ---
    tft_lb_channel = client.get_channel(TFT_LEADERBOARD_CHANNEL_ID)
    lol_lb_channel = client.get_channel(LOL_LEADERBOARD_CHANNEL_ID)

    # Stop the bot if critical channels are missing
    if not tft_lb_channel:
        logging.error(f"FATAL: TFT Leaderboard Channel (ID: {TFT_LEADERBOARD_CHANNEL_ID}) not found.")
        print(f"Error: TFT Leaderboard Channel (ID: {TFT_LEADERBOARD_CHANNEL_ID}) not found.")
        await client.close()
        return
    if not lol_lb_channel:
        logging.error(f"FATAL: LoL Leaderboard Channel (ID: {LOL_LEADERBOARD_CHANNEL_ID}) not found.")
        print(f"Error: LoL Leaderboard Channel (ID: {LOL_LEADERBOARD_CHANNEL_ID}) not found.")
        await client.close()
        return

    # Clear Channels on Startup
    await clear_channel(tft_lb_channel)
    await clear_channel(lol_lb_channel)
    await asyncio.sleep(1)

    # --- Send Initial Status Messages ---
    try:
        if tft_lb_channel:
            tft_message = await tft_lb_channel.send("Initializing TFT Leaderboard...")
            leaderboard_status_messages["TFT"] = tft_message
            logging.info(f"Sent initial TFT status message (ID: {tft_message.id})")
        if lol_lb_channel:
            lol_message = await lol_lb_channel.send("Initializing LoL Leaderboard...")
            leaderboard_status_messages["LoL"] = lol_message
            logging.info(f"Sent initial LoL status message (ID: {lol_message.id})")
    except discord.Forbidden:
        logging.error("Bot lacks permission to send messages in one or more leaderboard channels.")
        print("Error: Bot cannot send messages in leaderboard channels.")
        # Decide if you want to stop the bot here
    except discord.HTTPException as e:
        logging.error(f"Failed to send initial status messages: {e}")
        print(f"Error sending initial status messages: {e}")


    # --- Start Background Data Fetching Tasks ---
    client.loop.create_task(
        update_rankings_list_task(
            lock=updated_tft_rankings_list_lock,
            rankings_list_to_update=updated_tft_rankings_list,
            game_type_name="TFT"
        ),
        name="TFT Rank Fetcher"
    )
    logging.info("Launched background task: TFT Rank Fetcher")

    client.loop.create_task(
        update_rankings_list_task(
            lock=updated_lol_rankings_list_lock,
            rankings_list_to_update=updated_lol_rankings_list,
            game_type_name="LoL"
        ),
        name="LoL Rank Fetcher"
    )
    logging.info("Launched background task: LoL Rank Fetcher")

    # --- Start Scheduled Leaderboard Update Loops ---
    if not tft_leaderboard_update_loop.is_running():
        tft_leaderboard_update_loop.start()
    logging.info("Started TFT leaderboard update loop.")

    if not lol_leaderboard_update_loop.is_running():
        lol_leaderboard_update_loop.start()
    logging.info("Started LoL leaderboard update loop.")

    print("Bot is ready and tasks are running.")

@client.event
async def on_message(message):
    message_lower = message.content.lower()
    if message.author == client.user:
        return

    if message_lower == 'poggiesxdd':
        await message.delete()
        await message.channel.send("<:POGGIES:926135482360950824>")

    if message_lower == 'pogo':
        await message.delete()
        await message.channel.send(file=discord.File("img/UNRANKED.png"))

    if message_lower == 'tpogo':
        await message.delete()
        await message.channel.send(file=discord.File("img/tpogo.png"))

    if message_lower == 'huhpogo':
        await message.delete()
        await message.channel.send(file=discord.File("img/huhpogo.gif"))

    if message_lower == 'caughtpogo':
        await message.delete()
        await message.channel.send(file=discord.File("img/caughtpogo.png"))

    if message_lower == 'bigcaughtpogo':
        await message.delete()
        await message.channel.send(file=discord.File("img/bigcaughtpogo.png"))

    #if message.author.id == 80373001006096384:
    #    await message.delete()
    #    await message.channel.send(file=discord.File("img/tpogo.png"))

    ''' SPOILERS TEMPLATE '''
    # Check for "arcane" outside of the specific channel
    #if "arcane" in message_lower and message.channel.id != 1304878343329550396:
    #    await message.delete()
    #    target_channel = client.get_channel(1304878343329550396)
    #    if target_channel is not None:
    #        await message.channel.send(file=discord.File("img/tpogo.png"))
    #        await message.channel.send(f"NO ARCANE SPOILERS ALLOWED! DISCUSS HERE: {target_channel.mention}")

    #if message_lower == "xdd123":
    #    target_channel = client.get_channel(1305241451734634506)
    #    target_user = client.get_user(315272936053276672)
    #    await message.delete()
    #    await message.channel.send(file=discord.File("img/tpogo.png"))
    #    await message.channel.send(f"FINAL WARNING {target_user.mention}!! NO POKEMON SCREENSHOTS IN GENERAL CHAT! DISCUSS HERE: {target_channel.mention}")

    #if message_lower == "flameswtf123":
    #    target_user = client.get_user(80373001006096384)
    #    await message.delete()
    #    await message.channel.send(file=discord.File("img/tpogo.png"))
    #    await message.channel.send(f"FINAL WARNING {target_user.mention}!! NO THREATS TOWARDS ME!")

    if message_lower == "is gourish a noob ?":
        target_user = client.get_user(700837976544116808)
        await message.channel.send(file=discord.File("img/tpogo.png"))
        await message.channel.send(f"YES! {target_user.mention} IS A NOOB! AGREED!")


@client.event
async def on_member_ban(guild, user):
    async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.ban):
        if entry.target.id == user.id:
            print(f"{entry.user} banned {user.name}")
            if await check_actions(entry.user, "ban", BAN_THRESHOLD):
                print(f"{entry.user} exceeded ban threshold")
                # Ban the user
                await guild.ban(entry.user, reason="Exceeded ban threshold")
                print(f"{entry.user} banned!")
                # Get the channel
                channel = client.get_channel(GENERAL_CHANNEL_ID)  # general chat
                # Send banned message to the channel
                await channel.send(f"{entry.user.mention} was banned! RIP BOZO! <:PogO:949833186689568768>")


@client.event
async def on_member_remove(member):
    async for entry in member.guild.audit_logs(limit=1, action=discord.AuditLogAction.kick):
        if entry.target.id == member.id:
            print(f"{entry.user} kicked {member.name}")
            if await check_actions(entry.user, "kick", KICK_THRESHOLD):
                print(f"{entry.user} exceeded kick threshold")
                # Ban the user
                await member.guild.ban(entry.user, reason="Exceeded kick threshold")
                print(f"{entry.user} banned!")
                # Get the channel
                channel = client.get_channel(GENERAL_CHANNEL_ID)  # general chat
                # Send banned message to the channel
                await channel.send(f"{entry.user.mention} was banned! RIP BOZO! <:PogO:949833186689568768>")


@client.event
async def on_guild_channel_delete(channel):
    guild = channel.guild
    # print(f"Checking audit logs for channel delete in guild: {guild.name}")
    async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.channel_delete):
        # print(f"Audit log entry found: {entry}")
        if entry.target.id == channel.id:
            # print(f"{entry.user} deleted {channel.name}")
            if await check_actions(entry.user, "delete", DELETE_THRESHOLD):
                print(f"{entry.user} exceeded delete threshold")
                # Ban the user
                await channel.guild.ban(entry.user, reason="Exceeded delete threshold")
                print(f"{entry.user} banned!")
                # Get the channel
                channel = client.get_channel(GENERAL_CHANNEL_ID)  # general chat
                # Send banned message to the channel
                await channel.send(f"{entry.user.mention} was banned! RIP BOZO! <:PogO:949833186689568768>")

#Temporarily to silence user reaction
#@client.event
#async def on_reaction_add(reaction, user):
    #if user.id == 80373001006096384:
    #    await reaction.remove(user)

# --- Run the Bot ---
if __name__ == "__main__":
    bot_token = os.environ.get('DISCORD_TOKEN')
    if not bot_token:
        print("Error: DISCORD_TOKEN not found in .env file.")
    else:
        try:
            client.run(bot_token)
        except discord.LoginFailure:
            logging.error("FATAL: Improper token passed.")
            print("Error: Improper Discord token provided.")
        except Exception as e:
            logging.exception(f"An unexpected error occurred during bot execution: {e}")
            print(f"An unexpected error occurred: {e}")

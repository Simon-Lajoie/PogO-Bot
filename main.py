import asyncio
import io
from collections import deque
from datetime import datetime, timedelta
from time import time
import discord
import random
from riotwatcher import LolWatcher, ApiError, TftWatcher, RateLimiter
from PIL import Image, ImageDraw, ImageFont
from discord.ext import commands
from itertools import combinations
import logging
import os
from dotenv import load_dotenv

intents = discord.Intents.default()
intents.message_content = True
client = commands.Bot(command_prefix="/", intents=intents)
load_dotenv()


class CustomRateLimiter(RateLimiter):
    def __init__(self):
        super().__init__()
        self.short_requests = deque(maxlen=20)
        self.long_requests = deque(maxlen=100)

    def record_response(self, region, endpoint_name, method_name, url, response):
        pass

    def wait_until(self, region, endpoint_name, method_name):
        current_time = time()
        while self.short_requests and current_time - self.short_requests[0] > 1:
            self.short_requests.popleft()
        while self.long_requests and current_time - self.long_requests[0] > 120:
            self.long_requests.popleft()
        if len(self.short_requests) == 20:
            wait_time = 1 - (current_time - self.short_requests[0])
            logging.info(f"Rate limit exceeded for short requests. Waiting for {wait_time} seconds before retrying.")
            return datetime.now() + timedelta(seconds=wait_time)
        if len(self.long_requests) == 100:
            wait_time = 120 - (current_time - self.long_requests[0])
            logging.info(f"Rate limit exceeded for long requests. Waiting for {wait_time} seconds before retrying.")
            return datetime.now() + timedelta(seconds=wait_time)
        self.short_requests.append(current_time)
        self.long_requests.append(current_time)
        return None


lol_watcher_key = os.environ.get('LOL_WATCHER_KEY')
tft_watcher_key = os.environ.get('TFT_WATCHER_KEY')
client_id = os.environ.get('CLIENT_ID')
tft_watcher = TftWatcher(api_key=tft_watcher_key, rate_limiter=CustomRateLimiter())
lol_watcher = LolWatcher(api_key=lol_watcher_key, rate_limiter=CustomRateLimiter())

logging.basicConfig(level=logging.DEBUG, filename='app.log', filemode='w',
                    format='%(name)s - %(levelname)s - %(message)s')
logging.getLogger("PIL").setLevel(logging.WARNING)

# =====================
# Teamfight Tactics
# =====================
region = 'na1'
summoner_names_list_tft = ["Sir Mighty Bacon", "Settupss", "Classiq", "Salsa King", "Sehnbon", "Wyatt1", "Gourish",
                           "Gabyumi", "Best Pigeon NA", "meyst", "Limited", "Z3SIeeper", "BlackDrag", "Flames", "silvah bee",
                           "Tiny Cena", "Aàrón", "5billon", "Nappy", "KingNeptun3", "Mrs Mighty Bacon", "cpt stryder",
                           "Goosecan", "cancerkween", "Azote", "Kovannate3", "ÇatFood", "Skrt Skrt Skaarl",
                           "NonMaisWallah", "Fonty", "Oogli", "Lewis Kane"  # ,"dokudami milk", "Yazeed"
                           ]
summoner_names_list_lol = ["Sir Mighty Bacon", "Settupss", "Classiq", "Salsa King", "Sehnbon", "Wyatt1", "Gourish",
                           "Gabyumi", "Best Pigeon NA", "meyst", "Limited", "Z3SIeeper", "BlackDrag", "Flames", "silvah bee",
                           "Tiny Cena", "Aàrón", "5billon", "Nappy", "KingNeptun3", "Mrs Mighty Bacon", "cpt stryder",
                           "Goosecan", "cancerkween", "Azote", "Kovannate3", "ÇatFood", "Skrt Skrt Skaarl",
                           "NonMaisWallah", "Mnesia", "Fonty", "Oogli","Cowboy Codi"  # ,"dokudami milk", "Yazeed"
                           ]

previous_match_history_ids = []
updated_tft_rankings_list = []
updated_lol_rankings_list = []
loop = client.loop


def calculate_tier_division_value(tier_division_rank):
    ranks = {
        "IRON IV": 1,
        "IRON III": 2,
        "IRON II": 3,
        "IRON I": 4,
        "BRONZE IV": 5,
        "BRONZE III": 6,
        "BRONZE II": 7,
        "BRONZE I": 8,
        "SILVER IV": 9,
        "SILVER III": 10,
        "SILVER II": 11,
        "SILVER I": 12,
        "GOLD IV": 13,
        "GOLD III": 14,
        "GOLD II": 15,
        "GOLD I": 16,
        "PLATINUM IV": 17,
        "PLATINUM III": 18,
        "PLATINUM II": 19,
        "PLATINUM I": 20,
        "DIAMOND IV": 21,
        "DIAMOND III": 22,
        "DIAMOND II": 23,
        "DIAMOND I": 24,
        "MASTER I": 25,
        "GRANDMASTER I": 25,
        "CHALLENGER I": 25
    }
    rank_number = ranks[tier_division_rank]
    return rank_number


def rank_to_value(tier_division_rank, lp):
    tier_division_value = calculate_tier_division_value(tier_division_rank)
    final_ranked_value = tier_division_value * 100 + lp
    return final_ranked_value


async def get_tft_ranked_stats(summoner_names):
    from requests.exceptions import HTTPError
    rankings_list = []
    for summoner_name in summoner_names:
        max_attempts = 2
        attempt = 0
        ranked_stats = None
        while attempt < max_attempts:
            try:
                await asyncio.sleep(1)
                # Gets account information
                logging.info(f"Making request to Riot API for summoner: {summoner_name}")
                summoner = tft_watcher.summoner.by_name(region=region, summoner_name=summoner_name)
                await asyncio.sleep(1)
                # Gets TFT ranked_stats using summoner's ID
                logging.info(f"Making request to Riot API for ranked stats of summoner: {summoner_name}")
                ranked_stats = tft_watcher.league.by_summoner(region=region, encrypted_summoner_id=summoner["id"])
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
            # handle the case where all attempts failed
            logging.error(f"Failed to get data from Riot API after {max_attempts} attempts")

        # Find the object with the "queueType" value of "RANKED_TFT"
        ranked_stats = next((stats for stats in ranked_stats if stats["queueType"] == "RANKED_TFT"), None)

        if ranked_stats:
            tier = ranked_stats["tier"]
            rank = ranked_stats["rank"]
            lp = ranked_stats["leaguePoints"]
            tier_division = tier + " " + rank
            ranked_value = rank_to_value(tier_division, lp)
            if tier == "MASTER" or tier == "GRANDMASTER" or tier == "CHALLENGER":
                rank = ""
                tier_division_lp = tier + " " + str(lp)
            else:
                tier_division_lp = tier + " " + rank + " " + str(lp)
            print(f" {summoner_name} : {ranked_value} : {tier} {rank} {lp} LP ")
        else:
            tier_division = "UNRANKED"
            tier = "UNRANKED"
            lp = 0
            ranked_value = 0
            print(f" {summoner_name} : {tier}")
            tier_division_lp = tier_division
        rankings_list.append((summoner_name, ranked_value, lp, tier, tier_division_lp))

    rankings_list.sort(key=lambda x: x[1], reverse=True)
    return rankings_list


async def update_tft_rankings_list(updated_tft_rankings_list_lock):
    global updated_tft_rankings_list
    while True:
        for i in range(0, len(summoner_names_list_tft), 8):
            batch = summoner_names_list_tft[i:i + 8]
            logging.info(f"Updating TFT rankings for batch: {batch}")
            batch_rankings = await get_tft_ranked_stats(batch)
            async with updated_tft_rankings_list_lock:
                for ranking in batch_rankings:
                    summoner_name = ranking[0]
                    existing_ranking = next((r for r in updated_tft_rankings_list if r[0] == summoner_name), None)
                    if existing_ranking:
                        updated_tft_rankings_list.remove(existing_ranking)
                    updated_tft_rankings_list.append(ranking)
                updated_tft_rankings_list.sort(key=lambda x: x[1], reverse=True)
            logging.info(f"Updated TFT rankings list: {updated_tft_rankings_list}")
            logging.info(f"Waiting 1 minutes until next TFT batch update...")
            await asyncio.sleep(60)


async def update_lol_rankings_list(updated_lol_rankings_list_lock):
    global updated_lol_rankings_list
    while True:
        for i in range(0, len(summoner_names_list_lol), 8):
            batch = summoner_names_list_lol[i:i + 8]
            logging.info(f"Updating LoL rankings for batch: {batch}")
            batch_rankings = await get_lol_ranked_stats(batch)
            async with updated_lol_rankings_list_lock:
                for ranking in batch_rankings:
                    summoner_name = ranking[0]
                    existing_ranking = next((r for r in updated_lol_rankings_list if r[0] == summoner_name), None)
                    if existing_ranking:
                        updated_lol_rankings_list.remove(existing_ranking)
                    updated_lol_rankings_list.append(ranking)
                updated_lol_rankings_list.sort(key=lambda x: x[1], reverse=True)
            logging.info(f"Updated LoL rankings list: {updated_lol_rankings_list}")
            logging.info(f"Waiting 1 minutes until next LoL batch update...")
            await asyncio.sleep(60)


async def get_lol_ranked_stats(summoner_names):
    from requests.exceptions import HTTPError
    rankings_list = []
    for summoner_name in summoner_names:
        max_attempts = 2
        attempt = 0
        ranked_stats = None
        while attempt < max_attempts:
            try:
                await asyncio.sleep(1)
                # Gets account information
                logging.info(f"Making request to Riot API for summoner: {summoner_name}")
                summoner = lol_watcher.summoner.by_name(region=region, summoner_name=summoner_name)
                await asyncio.sleep(1)
                # Gets LoL ranked_stats using summoner's ID
                logging.info(f"Making request to Riot API for ranked stats of summoner: {summoner_name}")
                ranked_stats = lol_watcher.league.by_summoner(region=region, encrypted_summoner_id=summoner["id"])
                break
            except ConnectionError:
                attempt += 1
                wait_time = 2 ** attempt
                logging.warning(f"ConnectionError occurred, retrying in {wait_time} seconds...")
                await asyncio.sleep(wait_time)
            except HTTPError as e:
                if e.response.status_code == 429:
                    retry_after = int(e.response.headers.get('Retry-After', 0))
                    logging.warning(f"429 ClientError: TooManyRequests, retrying in {retry_after} seconds...")
                    await asyncio.sleep(retry_after)
                    continue
                else:
                    raise e
        else:
            # handle the case where all attempts failed
            logging.error(f"Failed to get data from Riot API after {max_attempts} attempts")

        # Find the object with the "queueType" value of "RANKED_SOLO_5x5"
        ranked_stats = next((stats for stats in ranked_stats if stats["queueType"] == "RANKED_SOLO_5x5"), None)

        if ranked_stats:
            tier = ranked_stats["tier"]
            rank = ranked_stats["rank"]
            lp = ranked_stats["leaguePoints"]
            tier_division = tier + " " + rank
            ranked_value = rank_to_value(tier_division, lp)
            if tier == "MASTER" or tier == "GRANDMASTER" or tier == "CHALLENGER":
                rank = ""
                tier_division_lp = tier + " " + str(lp)
            else:
                tier_division_lp = tier + " " + rank + " " + str(lp)
            print(f"{summoner_name}: {ranked_value}: {tier} {rank} {lp} LP")
        else:
            tier_division = "UNRANKED"
            tier = "UNRANKED"
            lp = 0
            ranked_value = 0
            print(f"{summoner_name}: {tier}")
            tier_division_lp = tier_division
        rankings_list.append((summoner_name, ranked_value, lp, tier, tier_division_lp))

    rankings_list.sort(key=lambda x: x[1], reverse=True)
    return rankings_list


def get_discord_username(summoner_name):
    discord_ids = {"Sir Mighty Bacon": "<@149681004880199681>", "Settupss": "<@144611125391130624>",
                   "Classiq": "<@155758849582825472>", "Salsa King": "<@315272936053276672>",
                   "Sehnbon": "<@198960489022095360>", "Wyatt1": "<@86595633288351744>",
                   "Gourish": "<@700837976544116808>", "Gabyumi": "<@241712679150944257>",
                   "Best Pigeon NA": "<@180136748091834368>", "meyst": "<@153778413646118912>",
                   "Limited": "<@715430081975025687>", "Z3SIeeper": "<@130242869708587008>",
                   "BlackDrag": "<@244390872983011328>", "Flames": "<@80373001006096384>",
                   "silvah bee": "<@527593111547805696>", "Tiny Cena": "<@154752158854545408>",
                   "Aàrón": "<@64494156914888704>", "5billon": "<@133779784105721856>",
                   "Nappy": "<@170962579974389762>", "KingNeptun3": "<@275435768661540866>",
                   "Mrs Mighty Bacon": "<@251140411043610625>", "cpt stryder": "<@148338461433135104>",
                   "Yazeed": "<@495380694525280276>", "Kenpachi": "<@263107658762944512>",
                   "Goosecan": "<@221019724505546752>", "cancerkween": "<@999785244045615224>",
                   "azote": "<@80372982337241088>", "Kovannate3": "<@1946154    71226617865>",
                   "ÇatFood": "<@160067484559474688>", "Skrt Skrt Skaarl": "<@272440042251616256>",
                   "NonMaisWallah": "<@520754531525459969>", "Mnesia": "<@402638715849146378>",
                   "Fonty": "<@133458482232819712>", "Oogli": "<@173232033772994560>", "Cowboy Codi": "<@115992535855267844>",
                   "Lewis Kane": "<@913637634767716393"}
    return discord_ids[summoner_name]


def get_random_message(old_summoner, new_summoner, position):
    emoji_codes = {
        "pogo": "<:PogO:949833186689568768>",
        "huh": "<:HUH:972927428638949416>",
        "pantsgrab": "<:pantsgrab:986381093815066674>",
        "deadge": "<:deadge:980719694032015401>",
        "scam": "<:scam:1079216347252265060>",
        "business": "<:business:1074568868309258292>",
        "yeahboi": "<:yeahboi:986385284419702784>",
        "aycaramba": "<:aycaramba:960051307752849448>",
        "dongerj": "<:dongerj:1038990718036889641>",
        "cathiago": "<:CATHIAGO:926136030871060500>",
        "peepoflor": "<:peepoflor:974826396641808414>",
        "pepeshrug": "<:pepeshrug:847289938253053952>",
        "sadge": "<:sadge:1119499660638306416>",
        "pepestrong": "<:PepeStrong:958637692583817226>"
    }
    new_summoner = get_discord_username(new_summoner)
    old_summoner = get_discord_username(old_summoner)
    gourish_summoner = get_discord_username("Gourish")
    messages = [
        f"{new_summoner} just pulled off a spectacular heist {emoji_codes['business']}, ousting {old_summoner} from position {position} like a sneaky mastermind {emoji_codes['cathiago']}!",
        f"Yeah.. {emoji_codes['sadge']} I'm sorry to announce {new_summoner} has dethroned {old_summoner} from position {position}. Don't ask me how. {emoji_codes['pepeshrug']}. Surely this is deserved. {emoji_codes['scam']}",
        f"{emoji_codes['pogo']} {new_summoner} has kicked {old_summoner} from position {position}. Did you really expect me to praise you for that ? Take this instead: {emoji_codes['pantsgrab']}",
        f"Ladies and gentlemen, let's gather 'round and give a thunderous round of applause to {new_summoner} for a breathtaking achievement! {emoji_codes['peepoflor']} With sheer grace and undeniable skill, {new_summoner} has claimed a well-deserved position in the prestigious top 4 of the illustrious PogO TFT Leaderboard. {emoji_codes['business']} Like a shining star ascending the heavens, they gracefully surpassed the formidable {old_summoner} at position {position}, leaving us all in awe of their remarkable talent. It's a triumph that deserves a standing ovation, a testament to the heights one can reach with unwavering dedication and unparalleled expertise. Let the celebration begin for this TFT maestro, a true master of the arena! {emoji_codes['yeahboi']}",
        f"{emoji_codes['pogo']} ALERT! ALERT! {emoji_codes['pogo']} {new_summoner} has executed a flawless takedown, banishing {old_summoner} from position {position}. It's time to rally the troops and show our support to {new_summoner} by showering them with a barrage of {emoji_codes['pogo']}.",
        f"{emoji_codes['pogo']} {new_summoner} has decisively toppled {old_summoner} from position {position}, leaving no doubt of their supremacy. {emoji_codes['cathiago']}",
        f"NAHHHH THIS {new_summoner} PLAYER MIGHT JUST THE THE BEST PLAYER IN THE WORLD.{emoji_codes['dongerj']} HE LITERALLY JUST TOOK POSITION {position} FROM {old_summoner} JUST LIKE THAT ? {emoji_codes['huh']} IT'S WAY TOO FREE. {new_summoner} IS JUST BUILT DIFFERENT! {emoji_codes['pepestrong']}",
        f"{new_summoner} --> {position} {emoji_codes['pogo']} {old_summoner} --> {emoji_codes['deadge']}",
        f"{emoji_codes['pogo']} BREAKING NEWS! BREAKING NEWS! {emoji_codes['pogo']} A major upset has just occurred in the TFT scene. {new_summoner} has just dethroned {old_summoner} from position {position}. It's a shocking turn of events, a stunning upset, a colossal blunder. {emoji_codes['aycaramba']} How did this happen? How did this travesty occur? How did this abomination come to be? {emoji_codes['pepeshrug']} We may never know. All we know is that {old_summoner} has just lost their dignity, their honor, their pride. {emoji_codes['sadge']}",
        f"{emoji_codes['pogo']} Hold on as {new_summoner} shakes things up and steals the glory from {old_summoner} at position {position}. {old_summoner} has just been humiliated, disgraced, destroyed. {emoji_codes['huh']} They have been reduced to nothing. {emoji_codes['huh']} They are now irrelevant. {emoji_codes['huh']} They are now forgotten. {emoji_codes['huh']} They are now dead to us. {emoji_codes['deadge']} All hail our new TFT overlord! {new_summoner}",
        f"{emoji_codes['pogo']} Unbelievable chaos has erupted in the TFT realm! Brace yourselves as {new_summoner} shatters the status quo and snatches the crown from {old_summoner} at position {position}. It's an absolute whirlwind of confusion, a mind-bending plot twist, an inexplicable mishap. The world is left scratching its head, questioning the very fabric of reality. {emoji_codes['pogo']} How did the stars align for this calamity? {emoji_codes['huh']} How did the TFT gods allow such an unfathomable catastrophe? {emoji_codes['aycaramba']} How did this confounding enigma come to pass? {emoji_codes['scam']}",
        f"{emoji_codes['pogo']} Attention, esteemed individuals, assemble and be captivated for a momentous announcement! {emoji_codes['pogo']} We stand in awe as {new_summoner} emerges as the undisputed victor, toppling {old_summoner} from their exalted position {position}. {emoji_codes['dongerj']} The path to this remarkable achievement remains shrouded in mystery, with scant details divulged on the hows and whys. {emoji_codes['pepeshrug']} The precise methods and strategies employed may forever elude our understanding, leaving us in awe of the enigma that surrounds this monumental accomplishment. {emoji_codes['yeahboi']} Such is the nature of this astounding feat, a tale woven with threads of intrigue and bewilderment, forever etched in the annals of TFT history. {emoji_codes['business']}",
        f"Well, well, well... Look who's the new ruler of the TFT kingdom!👑 {new_summoner} has cunningly snatched the crown from {old_summoner} at position {position}. It's a classic case of 'outplayed and outwitted.' {emoji_codes['scam']} Bow down to the new TFT mastermind, for they have left their opponents scratching their heads in utter disbelief. {emoji_codes['pogo']}",
        f"{emoji_codes['pogo']} Ladies and gentlemen, gather 'round! Witness the rise of {new_summoner} as they conquer position {position} and send {old_summoner} packing! {emoji_codes['pantsgrab']} It's like watching a legendary underdog story unfold before our eyes. {emoji_codes['business']} Let's give a standing ovation to {new_summoner} for defying the odds and proving that dreams do come true in the realm of TFT!",
        f"{emoji_codes['pogo']} Hey {old_summoner}, guess who just took your spot at position {position}? {emoji_codes['scam']} Oh right, it's {new_summoner}! {emoji_codes['deadge']} They strategically outplayed you, leaving you in a state of utter confusion and embarrassment. {emoji_codes['aycaramba']} Looks like someone could use a lesson or two... Get ready to learn TFT buddy. {emoji_codes['pogo']}",
        f"{emoji_codes['pogo']} Brace yourselves, TFT enthusiasts, for the rise of {new_summoner}! They've outshined {old_summoner} at position {position} like a radiant sun emerging from the clouds. {emoji_codes['peepoflor']} Meanwhile, {old_summoner} seems to be lost in the shadows of defeat. {emoji_codes['sadge']} Better luck next time, {old_summoner}, you'll need it! {emoji_codes['pogo']}",
        f"{emoji_codes['pogo']} Brace yourselves, ladies and gentlemen, because we have a new champion in town! {emoji_codes['pepestrong']} {new_summoner} has just obliterated {old_summoner} from position {position}, leaving no room for doubt. It's a devastating blow, a crushing defeat, a humiliating loss. {emoji_codes['deadge']} How did this happen? How did this disaster strike? How did this nightmare unfold? {emoji_codes['scam']} We may never know the full story, but we can all witness the aftermath. {emoji_codes['pantsgrab']}",
        f"{emoji_codes['pogo']} Hold on to your seats, folks, because we have a wild ride ahead of us! {emoji_codes['pogo']} {new_summoner} has just pulled off a miraculous feat, snatching position {position} from {old_summoner} in a nail-biting showdown. It's a jaw-dropping spectacle, a mind-blowing display, a heart-stopping performance. {emoji_codes['peepoflor']} How did they do it? How did they pull it off? How did they defy the odds? {emoji_codes['pepestrong']} We may never understand the secrets of their genius, but we can all admire their brilliance. {emoji_codes['yeahboi']}",
        f"{emoji_codes['pogo']} Wow! Wow! Wow! {emoji_codes['pogo']} {new_summoner} has just outplayed {old_summoner} from position {position}, showing us all what TFT is all about. {emoji_codes['yeahboi']} It's a dazzling show, a thrilling game, a spectacular victory. {emoji_codes['dongerj']} How did they do it? How did they win? How did they conquer? {emoji_codes['business']} We may never know the details, but we can all appreciate the results. 📈 {emoji_codes['peepoflor']}",
        f"{emoji_codes['pogo']} {new_summoner} has just taken position {position} from {old_summoner}. {emoji_codes['business']} In a cruel display of humiliation, {new_summoner} has left a message for us: This game is just all luck no skills, unlucky buddy {emoji_codes['scam']}",
        f"{emoji_codes['pogo']} OOF! {old_summoner} just got destroyed by {new_summoner}, who took position {position} from them. {emoji_codes['aycaramba']} Mortdog sends his regards, unlucky buddy {emoji_codes['pantsgrab']}",
        f"{emoji_codes['huh']} HUH... {old_summoner} just got outplayed by {new_summoner}, who snatched position {position} from them. Maybe you just didn’t hit this game, surely you will hit next game {emoji_codes['scam']} 📉",
        f"{emoji_codes['pogo']} What a tragedy.. Surely. {emoji_codes['pogo']} {old_summoner} just got annihilated by {new_summoner}, who claimed position {position} from them. Who balances this game? {emoji_codes['pepeshrug']} Unlucky buddy. Take this L {emoji_codes['sadge']}",
        f"{emoji_codes['pogo']} {old_summoner} just got humiliated by {new_summoner}, who kicked them from position {position}. RIP BOZO. 🤡 You won’t be missed {emoji_codes['deadge']}"
    ]
    gourish_messages = ["demoted", "banished", "relegated", "exiled", "downgraded", "dismissed", "degraded", "expelled",
                        "ousted", "lowered", "removed", "cast out", "dethroned", "ejected", "displaced", "deposed"]
    if old_summoner == gourish_summoner:
        gourish_random = random.choice(gourish_messages)
        return f"{emoji_codes['pogo']} {new_summoner} has just {gourish_random} {old_summoner} to their rightful place… GOURISH LOW! {emoji_codes['aycaramba']}"
    return random.choice(messages)


def balance_algorithm(rankings):
    # extract the values from the rankings
    values = [ranking[1] for ranking in rankings]
    # compute all possible combinations of players
    n = len(values)
    best_team1 = None
    best_team2 = None
    best_diff = float('inf')
    for team1 in combinations(range(n), n // 2):
        team2 = [i for i in range(n) if i not in team1]
        value1 = sum(values[i] for i in team1)
        value2 = sum(values[i] for i in team2)
        diff = abs(value1 - value2)
        if diff < best_diff:
            best_team1 = [rankings[i][0] for i in team1]
            best_team2 = [rankings[i][0] for i in team2]
            best_diff = diff
    return best_team1, best_team2


async def balance(ctx, summoner_names):
    # split the names by comma to get the individual names
    names = summoner_names.split(',')
    # let Discord know that your bot is still processing the request
    await ctx.defer()
    # get a value for each name (replace this with your own code)
    rankings = get_lol_ranked_stats(names)
    # balance the teams
    # assign players to teams using the minimax algorithm
    team1, team2 = balance_algorithm(rankings)
    # send the balanced teams back to the user
    # print(team1)
    # print(team2)
    await ctx.send(f'Team 1: {", ".join(team1)}')
    await ctx.send(f'Team 2: {", ".join(team2)}')


async def update_tft_leaderboard(previous_rankings, message, updated_tft_rankings_list_lock):
    global updated_tft_rankings_list
    async with updated_tft_rankings_list_lock:
        # channel = client.get_channel(1118758206840262686) TESTING SERVER
        general_channel = client.get_channel(846551161388662789)
        tft_leaderboard_channel = client.get_channel(1118278946048454726)

        # Edit the content of the message object to display "refreshing..."
        logging.info("TFT Countdown timer: Refreshing leaderboard...")
        await message.edit(content="Refreshing leaderboard...")

        logging.info(f"Previous TFT rankings: {previous_rankings}")
        print("Collecting TFT ranked stats...")
        # Compare the top 4 summoners in the previous rankings with the top 3 summoners in the new rankings
        for i in range(4):
            if previous_rankings and updated_tft_rankings_list[i][0] != previous_rankings[i][0]:
                current_player = updated_tft_rankings_list[i][0]
                player_ranks = [x for x in range(len(previous_rankings)) if previous_rankings[x][0] == current_player]
                if player_ranks:
                    previous_rank = player_ranks[0]
                    if i < previous_rank:
                        print(updated_tft_rankings_list[i])
                        print(previous_rankings[i])
                        logging.info(
                            f"TFT Rankings have changed! {updated_tft_rankings_list[i][0]} has passed {previous_rankings[i][0]}")
                        # Send alert message when rankings have changed and someone ranked up
                        await general_channel.send(
                            get_random_message(previous_rankings[i][0], updated_tft_rankings_list[i][0], i + 1))
                        logging.info("TFT Rankings update message sent to TFT Leaderboard chat!")

        # Clear the contents of the previous_rankings list
        previous_rankings.clear()
        # Add the new rankings to the previous_rankings list
        previous_rankings.extend(updated_tft_rankings_list)

        logging.info(f"Newly TFT updated rankings: {previous_rankings}")
        print("Updating TFT leaderboard...")
        # Delete the last leaderboard message if it exists
        if hasattr(update_tft_leaderboard, "last_message") and update_tft_leaderboard.last_message:
            try:
                print("Deleting last TFT message...")
                await update_tft_leaderboard.last_message.delete()
            except:
                pass
        # Set up some constants
        NORMAL_FONT_SIZE = 25
        MEDIUM_FONT_SIZE = 23
        SMALL_FONT_SIZE = 21
        RANK_IMAGE_SIZE = (55, 55)
        POGO_IMAGE_SIZE = (40, 40)
        BACKGROUND_IMAGE_PATH = "img/leaderboard_tft.png"
        BACKGROUND_SIZE = (1366, 757)

        # Load the background image and resize it to the desired size
        background_image = Image.open(BACKGROUND_IMAGE_PATH).convert("RGBA")
        background_image = background_image.resize(BACKGROUND_SIZE)

        # Create a new image with the same size as the background image and convert it to RGBA mode
        image = Image.new("RGB", BACKGROUND_SIZE, "white").convert("RGBA")
        image.alpha_composite(background_image)

        draw = ImageDraw.Draw(image)

        # Draw the summoner names, tier images, and tier text
        x_offsets = [70, 513, 956]
        y_offsets = [0, 73, 146, 219, 292, 364, 439]
        for i in range(3):
            for j in range(7):
                index = i * 7 + j
                if index >= len(updated_tft_rankings_list):
                    break
                summoner = updated_tft_rankings_list[index]
                x = x_offsets[i]
                y = y_offsets[j]

                if len(summoner[0]) > 12:
                    # Load the font smaller size for summoner name
                    font = ImageFont.truetype("fonts/BebasNeue-Regular.ttf", SMALL_FONT_SIZE)
                else:
                    # Load the font normal size for summoner name
                    font = ImageFont.truetype("fonts/BebasNeue-Regular.ttf", NORMAL_FONT_SIZE)
                # Draw summoner name
                draw.text((x + 45, y + 235), summoner[0], fill="white", font=font)

                # Draw tier image
                image_path = f"img/{summoner[3]}.png"
                tier_image = Image.open(image_path).convert("RGBA")
                if summoner[3] == "UNRANKED":
                    image_size = POGO_IMAGE_SIZE
                else:
                    image_size = RANK_IMAGE_SIZE
                tier_image.thumbnail(image_size)
                tier_image_x = x + 165
                if summoner[3] == "UNRANKED" or summoner[3] == "PLATINUM" or summoner[3] == "DIAMOND" or summoner[
                    3] == "MASTER" or summoner[3] == "GRANDMASTER" or summoner[3] == "CHALLENGER":
                    tier_image_y = y + 225
                else:
                    tier_image_y = y + 220
                image.alpha_composite(tier_image, dest=(tier_image_x, tier_image_y))

                # Load the font normal size for the tier & rank text
                font = ImageFont.truetype("fonts/BebasNeue-Regular.ttf", NORMAL_FONT_SIZE)
                # Load the font small size for the tier GM+ & rank text
                small_font = ImageFont.truetype("fonts/BebasNeue-Regular.ttf", MEDIUM_FONT_SIZE)
                # Draw tier & rank text
                if summoner[3] == "GRANDMASTER" or summoner[3] == "CHALLENGER":
                    draw.text((x + 237, y + 235), f"{summoner[4]}", fill="white", font=small_font)
                else:
                    draw.text((x + 237, y + 235), f"{summoner[4]}", fill="white", font=font)

        # Save the image to a file-like object in memory
        with io.BytesIO() as output:
            image.save(output, format="PNG")
            output.seek(0)
            print("Sending updated TFT leaderboard...")
            update_tft_leaderboard.last_message = await tft_leaderboard_channel.send(
                file=discord.File(output, filename="leaderboard.png"))

    # Start the countdown timer and pass the message object as a parameter
    logging.info("Starting TFT countdown timer...")
    await countdown_timer_tft(360, message)


async def update_lol_leaderboard(previous_rankings, message, updated_lol_rankings_list_lock):
    global updated_lol_rankings_list
    async with updated_lol_rankings_list_lock:
        # channel = client.get_channel(1118758206840262686) TESTING SERVER
        general_channel = client.get_channel(846551161388662789)
        lol_leaderboard_channel = client.get_channel(1129965287131861043)

        # Edit the content of the message object to display "refreshing..."
        logging.info("LoL Countdown timer: Refreshing LoL leaderboard...")
        await message.edit(content="Refreshing leaderboard...")

        logging.info(f"LoL Previous rankings: {previous_rankings}")
        print("Collecting LoL ranked stats...")
        # Compare the top 4 summoners in the previous rankings with the top 3 summoners in the new rankings
        for i in range(4):
            if previous_rankings and updated_lol_rankings_list[i][0] != previous_rankings[i][0]:
                current_player = updated_lol_rankings_list[i][0]
                player_ranks = [x for x in range(len(previous_rankings)) if previous_rankings[x][0] == current_player]
                if player_ranks:
                    previous_rank = player_ranks[0]
                    if i < previous_rank:
                        print(updated_lol_rankings_list[i])
                        print(previous_rankings[i])
                        logging.info(
                            f"LoL Rankings have changed! {updated_lol_rankings_list[i][0]} has passed {previous_rankings[i][0]}")
                        # Send alert message when rankings have changed and someone ranked up
                        # await general_channel.send(
                        #    get_random_message(previous_rankings[i][0], updated_lol_rankings_list[i][0], i + 1))
                        logging.info("LoL Rankings changed message sent!")

        # Clear the contents of the previous_rankings list
        previous_rankings.clear()
        # Add the new rankings to the previous_rankings list
        previous_rankings.extend(updated_lol_rankings_list)

        logging.info(f"Newly LoL updated rankings: {previous_rankings}")
        print("Updating LoL leaderboard...")
        # Delete the last leaderboard message if it exists
        if hasattr(update_lol_leaderboard, "last_message") and update_lol_leaderboard.last_message:
            try:
                print("Deleting last LoL message...")
                await update_lol_leaderboard.last_message.delete()
            except:
                pass
        # Set up some constants
        NORMAL_FONT_SIZE = 25
        MEDIUM_FONT_SIZE = 23
        SMALL_FONT_SIZE = 21
        RANK_IMAGE_SIZE = (55, 55)
        POGO_IMAGE_SIZE = (40, 40)
        BACKGROUND_IMAGE_PATH = "img/leaderboard_soloq.png"
        BACKGROUND_SIZE = (1366, 757)

        # Load the background image and resize it to the desired size
        background_image = Image.open(BACKGROUND_IMAGE_PATH).convert("RGBA")
        background_image = background_image.resize(BACKGROUND_SIZE)

        # Create a new image with the same size as the background image and convert it to RGBA mode
        image = Image.new("RGB", BACKGROUND_SIZE, "white").convert("RGBA")
        image.alpha_composite(background_image)

        draw = ImageDraw.Draw(image)

        # Draw the summoner names, tier images, and tier text
        x_offsets = [70, 513, 956]
        y_offsets = [0, 73, 146, 219, 292, 364, 439]
        for i in range(3):
            for j in range(7):
                index = i * 7 + j
                if index >= len(updated_lol_rankings_list):
                    break
                summoner = updated_lol_rankings_list[index]
                x = x_offsets[i]
                y = y_offsets[j]

                if len(summoner[0]) > 12:
                    # Load the font smaller size for summoner name
                    font = ImageFont.truetype("fonts/BebasNeue-Regular.ttf", SMALL_FONT_SIZE)
                else:
                    # Load the font normal size for summoner name
                    font = ImageFont.truetype("fonts/BebasNeue-Regular.ttf", NORMAL_FONT_SIZE)
                # Draw summoner name
                draw.text((x + 45, y + 235), summoner[0], fill="white", font=font)

                # Draw tier image
                image_path = f"img/{summoner[3]}.png"
                tier_image = Image.open(image_path).convert("RGBA")
                if summoner[3] == "UNRANKED":
                    image_size = POGO_IMAGE_SIZE
                else:
                    image_size = RANK_IMAGE_SIZE
                tier_image.thumbnail(image_size)
                tier_image_x = x + 165
                if summoner[3] == "UNRANKED" or summoner[3] == "PLATINUM" or summoner[3] == "DIAMOND" or summoner[
                    3] == "MASTER" or summoner[3] == "GRANDMASTER" or summoner[3] == "CHALLENGER":
                    tier_image_y = y + 225
                else:
                    tier_image_y = y + 220
                image.alpha_composite(tier_image, dest=(tier_image_x, tier_image_y))

                # Load the font normal size for the tier & rank text
                font = ImageFont.truetype("fonts/BebasNeue-Regular.ttf", NORMAL_FONT_SIZE)
                # Load the font small size for the tier GM+ & rank text
                small_font = ImageFont.truetype("fonts/BebasNeue-Regular.ttf", MEDIUM_FONT_SIZE)
                # Draw tier & rank text
                if summoner[3] == "GRANDMASTER" or summoner[3] == "CHALLENGER":
                    draw.text((x + 237, y + 235), f"{summoner[4]}", fill="white", font=small_font)
                else:
                    draw.text((x + 237, y + 235), f"{summoner[4]}", fill="white", font=font)

        # Save the image to a file-like object in memory
        with io.BytesIO() as output:
            image.save(output, format="PNG")
            output.seek(0)
            print("Sending updated LoL leaderboard...")
            update_lol_leaderboard.last_message = await lol_leaderboard_channel.send(
                file=discord.File(output, filename="leaderboard.png"))

    # Start the countdown timer and pass the message object as a parameter
    logging.info("Starting LoL countdown timer...")
    await countdown_timer_lol(360, message)


async def get_match_history(previous_match_history_ids):
    match_history_ids = []
    general_channel = client.get_channel(846551161388662789)
    for summoner_name in summoner_names_list_tft:
        # Gets account information
        summoner = tft_watcher.summoner.by_name(region=region, summoner_name=summoner_name)
        # Gets last 3 TFT games ids from match history using summoner's PUUID and find the ranked games
        last_3_games_ids = tft_watcher.match.by_puuid(region=region, puuid=summoner["puuid"], count=3)
        ranked_games = []
        for game in last_3_games_ids:
            match = tft_watcher.match.by_id(region=region, match_id=game)
            if match["info"]["queue_id"] == 1100:
                ranked_games.append(match)
        print(f"Ranked games ID: {ranked_games}")
        # Check if any ids in last_3_games_ids are present in previous_match_history_ids
        common_ids = set(last_3_games_ids).intersection(previous_match_history_ids)
        logging.info(f"{summoner_name} common ids: {common_ids}")
        print(f"{summoner_name} common ids: {common_ids}")
        placements = []
        game_ids = []
        if not common_ids:
            for game in ranked_games:
                # Find the player placements in the every match
                for participant in game["info"]["participants"]:
                    if participant["puuid"] == summoner["puuid"]:
                        placements.append(participant["placement"])
                        game_ids.append(game["metadata"]["match_id"])
                        break
            logging.info(f"{summoner_name} placements: {placements}")
            print(f"{summoner_name} got the following placements: {placements}")
            for i in range(len(placements) - 1):
                if placements[i] == 1 and placements[i + 1] == 1:
                    pogo_emote = "<:PogO:949833186689568768>"
                    await general_channel.send(
                        f"🏆 ATTENTION! {get_discord_username(summoner_name)} got two 1st placements in a row! {pogo_emote} 🏆")
                    # Add game ids to match_history_ids
                    match_history_ids.extend(game_ids[i:i + 2])
                if placements[i] == 8 and placements[i + 1] == 8:
                    aycaramba_emote = "<:aycaramba:960051307752849448>"
                    await general_channel.send(
                        f"📉 ATTENTION! {get_discord_username(summoner_name)} got two 8th placements in a row! {aycaramba_emote} 📉")
                    # Add game ids to match_history_ids
                    match_history_ids.extend(game_ids[i:i + 2])
            else:
                match_history_ids.extend(common_ids)
    return match_history_ids


async def check_match_history_streak():
    global previous_match_history_ids
    logging.info(f"Checking match history...")
    print(f"Checking match history...")
    match_history_ids = await get_match_history(previous_match_history_ids)
    # Save current match history ids
    previous_match_history_ids = match_history_ids
    print(f"previous match history ids: {previous_match_history_ids}")


async def countdown_timer_tft(time, message):
    logging.info(f"Starting TFT countdown timer with time={time} and message={message.content}")

    # Calculate the number of minutes remaining
    minutes = time // 60

    # Edit the content of the message object to display the time remaining
    await message.edit(content=f"Next update in: {minutes} minutes")
    while time > 0:
        await asyncio.sleep(1)
        time -= 1
        # logging.info(f"Countdown timer ticked with time={time} and message={message.content}")
        # Calculate the number of minutes and seconds remaining
        minutes, seconds = divmod(time, 60)
        minutes = minutes + 1
        # Check if the content of the message object has been changed to "refreshing..."
        if message.content == "Refreshing TFT leaderboard...":
            logging.info(f"TFT Countdown timer stopped because message content changed to 'refreshing...'")
            # Break out of the while loop to stop the countdown timer
            break

        # Edit the content of the message object to display the time remaining
        if seconds == 59:
            logging.info(f"TFT Countdown timer updated: {minutes} minutes")
            await message.edit(content=f"Next update in: {minutes} minutes")
        elif minutes == 0 and seconds == 10:
            await message.edit(content=f"Next update in: {seconds:2d} seconds")

    logging.info(f"TFT Countdown timer finished with time={time} and message={message.content}")


async def countdown_timer_lol(time, message):
    logging.info(f"Starting LoL countdown timer with time={time} and message={message.content}")

    # Calculate the number of minutes remaining
    minutes = time // 60

    # Edit the content of the message object to display the time remaining
    await message.edit(content=f"Next update in: {minutes} minutes")
    while time > 0:
        await asyncio.sleep(1)
        time -= 1
        # logging.info(f"Countdown timer ticked with time={time} and message={message.content}")
        # Calculate the number of minutes and seconds remaining
        minutes, seconds = divmod(time, 60)
        minutes = minutes + 1
        # Check if the content of the message object has been changed to "refreshing..."
        if message.content == "Refreshing Soloq leaderboard...":
            logging.info(f"LoL Countdown timer stopped because message content changed to 'refreshing...'")
            # Break out of the while loop to stop the countdown timer
            break

        # Edit the content of the message object to display the time remaining
        if seconds == 59:
            logging.info(f"LoL Countdown timer updated: {minutes} minutes")
            await message.edit(content=f"Next update in: {minutes} minutes")
        elif minutes == 0 and seconds == 10:
            await message.edit(content=f"Next update in: {seconds:2d} seconds")

    logging.info(f"LoL Countdown timer finished with time={time} and message={message.content}")


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


async def update_tasks(updated_tft_rankings_list_lock, updated_lol_rankings_list_lock):
    tft_leaderboard_channel = client.get_channel(1118278946048454726)
    lol_leaderboard_channel = client.get_channel(1129965287131861043)
    leaderboard_update_count = 0
    previous_tft_rankings = []
    previous_lol_rankings = []
    # Send the initial message
    message_tft = await tft_leaderboard_channel.send("Starting TFT leaderboard...")
    message_lol = await lol_leaderboard_channel.send("Starting LoL leaderboard...")
    while True:
        logging.info(f"update_tasks loop with message={message_tft.content}")
        # Call update_tft_leaderboard every 5 minutes and pass the message object as a parameter
        task1 = client.loop.create_task(
            update_tft_leaderboard(previous_tft_rankings, message_tft, updated_tft_rankings_list_lock))
        task2 = client.loop.create_task(
            update_lol_leaderboard(previous_lol_rankings, message_lol, updated_lol_rankings_list_lock))
        leaderboard_update_count += 1

        # Reset the leaderboard_update_count variable after it reaches a certain value
        if leaderboard_update_count >= 1000000:
            leaderboard_update_count = 0

        logging.info(f"Waiting for update_tft_leaderboard task to complete...")
        # Wait for the update_tft_leaderboard and update_lol_leaderboard task to complete
        await asyncio.gather(task1, task2)

        # Call check_match_history_streak every 10 minutes
        # client.loop.create_task(check_match_history_streak())

        # Clear the contents of the app.log file every 10 leaderboard updates
       # if leaderboard_update_count % 10 == 0:
            # Delete the file if it exists
       #     if os.path.exists("app.log"):
       #         os.remove("app.log")

            # Create a new file with the same name
        #    with open("app.log", 'w') as file:
        #        file.write('')


# =====================
# Discord
# =====================
@client.event
async def on_ready():
    logging.debug("on_ready function called")
    await client.tree.sync()
    print("Success: PogO bot is connected to Discord".format(client))
    tft_leaderboard_channel = client.get_channel(1118278946048454726)
    lol_leaderboard_channel = client.get_channel(1129965287131861043)
    await clear_channel(tft_leaderboard_channel)
    await clear_channel(lol_leaderboard_channel)
    print("Success: PogO bot has cleared the TFT leaderboard channel")
    updated_tft_rankings_list_lock = asyncio.Lock()
    updated_lol_rankings_list_lock = asyncio.Lock()
    client.loop.create_task(update_tasks(updated_tft_rankings_list_lock, updated_lol_rankings_list_lock))
    client.loop.create_task(update_tft_rankings_list(updated_tft_rankings_list_lock))
    client.loop.create_task(update_lol_rankings_list(updated_lol_rankings_list_lock))


@client.hybrid_command()
async def balance_teams(ctx, summoner_names):
    await balance(ctx, summoner_names)


@client.event
async def on_message(message):
    if message.author == client.user:
        return

    if message.content == 'PogO':
        await message.delete()
        await message.channel.send(file=discord.File("img/UNRANKED.png"))

    if message.content == 'T PogO':
        await message.delete()
        await message.channel.send(file=discord.File("img/tpogo.png"))
    # if message.content.startswith('test'):
    #    await message.channel.send('test')


client.run(client_id)

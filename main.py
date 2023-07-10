import asyncio
import io
import discord
import random

import requests
from riotwatcher import LolWatcher, ApiError, TftWatcher
from PIL import Image, ImageDraw, ImageFont
from discord.ext import commands
from itertools import combinations
import logging
import os

intents = discord.Intents.default()
intents.message_content = True
client = commands.Bot(command_prefix="/", intents=intents)
lol_watcher_key = os.environ.get('LOL_WATCHER_KEY')
tft_watcher_key = os.environ.get('TFT_WATCHER_KEY')
client_id = os.environ.get('CLIENT_ID')
tft_watcher = TftWatcher(tft_watcher_key)
lol_watcher = LolWatcher(lol_watcher_key)

logging.basicConfig(level=logging.DEBUG, filename='app.log', filemode='w',
                    format='%(name)s - %(levelname)s - %(message)s')
logging.getLogger("PIL").setLevel(logging.WARNING)

# =====================
# Teamfight Tactics
# =====================
region = 'na1'
summoner_names_list = ["Sir Mighty Bacon", "Settupss", "Classiq", "Salsa King", "Sehnbon", "Wyatt1", "Gourish",
                       "Gabyumi", "Mii Chan", "meyst", "Limited", "Z3SIeeper", "BlackDrag", "Flames", "silvah bee",
                       "Tiny Cena", "Aàrón", "5billon", "Nappy", "KingNeptun3", "Mrs Mighty Bacon", "cpt stryder",
                       "Goosecan", "cancerkween", "Azote", "Kovannate3", "ÇatFood", "Tkipp", "Skrt Skrt Skaarl",
                       "NonMaisWallah"  # ,"dokudami milk", "Yazeed"
                       ]


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


async def get_tft_ranked_stats():
    rankings_list = []
    for i, summoner_name in enumerate(summoner_names_list):
        # Gets account information
        logging.info(f"Making request to Riot API for summoner: {summoner_name}")
        summoner = tft_watcher.summoner.by_name(region=region, summoner_name=summoner_name)
        # Gets TFT rankedStats using summoner's ID
        logging.info(f"Making request to Riot API for ranked stats of summoner: {summoner_name}")
        rankedStats = tft_watcher.league.by_summoner(region=region, encrypted_summoner_id=summoner["id"])
        # Find the object with the "queueType" value of "RANKED_TFT"
        rankedStats = next((stats for stats in rankedStats if stats["queueType"] == "RANKED_TFT"), None)

        if rankedStats:
            tier = rankedStats["tier"]
            rank = rankedStats["rank"]
            lp = rankedStats["leaguePoints"]
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

        if (i + 1) % 5 == 0:
            response = requests.get(
                "https://na1.api.riotgames.com/tft/league/v1/entries/by-summoner/cuPjNdhPu6N3dCfsZE5bYkSPGmvBEdKMv5KUIM7ToWd1A5E?api_key=" + tft_watcher_key)
            rate_limit_remaining = response.headers['X-App-Rate-Limit-Count']
            logging.info(f"Rate limit remaining: {rate_limit_remaining}")
            print(f"Rate limit remaining: {rate_limit_remaining}")
    rankings_list.sort(key=lambda x: x[1], reverse=True)
    return rankings_list


def get_lol_ranked_stats(names):
    rankings_list = []
    for summoner_name in names:
        # Gets account information
        logging.info(f"Making request to Riot API for summoner: {summoner_name}")
        summoner = lol_watcher.summoner.by_name(region=region, summoner_name=summoner_name)

        # Gets LoL rankedStats using summoner's ID
        logging.info(f"Making request to Riot API for ranked stats of summoner: {summoner_name}")
        rankedStats = lol_watcher.league.by_summoner(region=region, encrypted_summoner_id=summoner["id"])

        # Find the object with the "queueType" value of "RANKED_TFT"
        rankedStats = next((stats for stats in rankedStats if stats["queueType"] == "RANKED_SOLO_5x5"), None)

        if rankedStats:
            tier = rankedStats["tier"]
            rank = rankedStats["rank"]
            lp = rankedStats["leaguePoints"]
            tier_division = tier + " " + rank
            ranked_value = rank_to_value(tier_division, lp)
            if tier == "MASTER" or tier == "GRANDMASTER" or tier == "CHALLENGER":
                rank = ""
                tier_division_lp = tier + " " + str(lp)
            else:
                tier_division_lp = tier + " " + rank + " " + str(lp)
            # print(f" {summoner_name} : {ranked_value} : {tier} {rank} {lp} LP ")
        else:
            tier_division = "UNRANKED"
            tier = "UNRANKED"
            lp = 0
            ranked_value = 0
            # print(f" {summoner_name} : {tier}")
            tier_division_lp = tier_division
        rankings_list.append((summoner_name, ranked_value, lp, tier, tier_division_lp))
    rankings_list.sort(key=lambda x: x[1], reverse=True)
    return rankings_list


def get_discord_username(summoner_name):
    discord_ids = {"Sir Mighty Bacon": "<@149681004880199681>", "Settupss": "<@144611125391130624>",
                   "Classiq": "<@155758849582825472>", "Salsa King": "<@315272936053276672>",
                   "Sehnbon": "<@198960489022095360>", "Wyatt1": "<@86595633288351744>",
                   "Gourish": "<@700837976544116808>", "Gabyumi": "<@241712679150944257>",
                   "Mii Chan": "<@180136748091834368>", "meyst": "<@153778413646118912>",
                   "Limited": "<@715430081975025687>", "Z3SIeeper": "<@130242869708587008>",
                   "BlackDrag": "<@244390872983011328>", "Flames": "<@80373001006096384>",
                   "silvah bee": "<@527593111547805696>", "Tiny Cena": "<@154752158854545408>",
                   "Aàrón": "<@64494156914888704>", "5billon": "<@133779784105721856>",
                   "Nappy": "<@170962579974389762>", "KingNeptun3": "<@275435768661540866>",
                   "Mrs Mighty Bacon": "<@251140411043610625>", "cpt stryder": "<@148338461433135104>",
                   "Yazeed": "<@495380694525280276>", "Kenpachi": "<@263107658762944512>",
                   "Goosecan": "<@221019724505546752>", "cancerkween": "<@999785244045615224>",
                   "azote": "<@80372982337241088>", "Kovannate3": "<@194615471226617865>",
                   "ÇatFood": "<@160067484559474688>", "Skrt Skrt Skaarl": "<@272440042251616256>",
                   "NonMaisWallah": "<@520754531525459969>"}
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
    messages = [
        f"{new_summoner} just pulled off a spectacular heist {emoji_codes['business']}, ousting {old_summoner} from position {position} like a sneaky mastermind {emoji_codes['cathiago']}!",
        f"Yeah.. {emoji_codes['sadge']} I'm sorry to announce {new_summoner} has dethroned {old_summoner} from position {position}. Don't ask me how. {emoji_codes['pepeshrug']}. Surely this is deserved. {emoji_codes['scam']}",
        f"{emoji_codes['pogo']} {new_summoner} has kicked {old_summoner} from position {position}. Did you really expect me to praise you for that ? Take this instead: {emoji_codes['pantsgrab']}",
        f"Ladies and gentlemen, let's gather 'round and give a thunderous round of applause to {new_summoner} for a breathtaking achievement! {emoji_codes['peepoflor']} With sheer grace and undeniable skill, {new_summoner} has claimed a well-deserved position in the prestigious top 4 of the illustrious PogO TFT Leaderboard. {emoji_codes['business']} Like a shining star ascending the heavens, they gracefully surpassed the formidable {old_summoner} at position {position}, leaving us all in awe of their remarkable talent. It's a triumph that deserves a standing ovation, a testament to the heights one can reach with unwavering dedication and unparalleled expertise. Let the celebration begin for this TFT maestro, a true master of the arena! {emoji_codes['yeahboi']}",
        f"{emoji_codes['pogo']} ALERT! ALERT! {emoji_codes['pogo']} {new_summoner} has executed a flawless takedown, banishing {old_summoner} from position {position}. It's time to rally the troops and show our support to {new_summoner} by showering them with a barrage of {emoji_codes['pogo']}.",
        f"{emoji_codes['pogo']} {new_summoner} has decisively toppled {old_summoner} from position {position}, leaving no doubt of their supremacy. {emoji_codes['cathiago']}",
        f"NAHHHH THIS {new_summoner} PLAYER MIGHT JUST THE THE BEST PLAYER IN THE WORLD.{emoji_codes['dongerj']} HE LITERALLY JUST TOOK POSITION {position} FROM {old_summoner} JUST LIKE THAT ? {emoji_codes['huh']} IT'S WAY TOO FREE. {new_summoner} IS JUST BUILT DIFFERENT! {emoji_codes['pepestrong']}",
        f"{new_summoner} --> {position} {emoji_codes['pogo']} {old_summoner} --> {emoji_codes['deadge']}",
        f"{emoji_codes['pogo']} BREAKING NEWS! BREAKING NEWS! {emoji_codes['pogo']} A major upset has just occurred in the TFT scene. {new_summoner} has just dethroned {old_summoner} from position {position}. It’s a shocking turn of events, a stunning upset, a colossal blunder. {emoji_codes['aycaramba']} How did this happen? How did this travesty occur? How did this abomination come to be? {emoji_codes['pepeshrug']} We may never know. All we know is that {old_summoner} has just lost their dignity, their honor, their pride. {emoji_codes['sadge']}",
        f"{emoji_codes['pogo']} Hold on as {new_summoner} shakes things up and steals the glory from {old_summoner} at position {position}. {old_summoner} has just been humiliated, disgraced, destroyed. {emoji_codes['huh']} They have been reduced to nothing. {emoji_codes['huh']} They are now irrelevant. {emoji_codes['huh']} They are now forgotten. {emoji_codes['huh']} They are now dead to us. {emoji_codes['deadge']} All hail our new TFT overlord! {new_summoner}",
        f"{emoji_codes['pogo']} Unbelievable chaos has erupted in the TFT realm! Brace yourselves as {new_summoner} shatters the status quo and snatches the crown from {old_summoner} at position {position}. It's an absolute whirlwind of confusion, a mind-bending plot twist, an inexplicable mishap. The world is left scratching its head, questioning the very fabric of reality. {emoji_codes['pogo']} How did the stars align for this calamity? {emoji_codes['huh']} How did the TFT gods allow such an unfathomable catastrophe? {emoji_codes['aycaramba']} How did this confounding enigma come to pass? {emoji_codes['scam']}",
        f"{emoji_codes['pogo']} Attention, esteemed individuals, assemble and be captivated for a momentous announcement! {emoji_codes['pogo']} We stand in awe as {new_summoner} emerges as the undisputed victor, toppling {old_summoner} from their exalted position {position}. {emoji_codes['dongerj']} The path to this remarkable achievement remains shrouded in mystery, with scant details divulged on the hows and whys. {emoji_codes['pepeshrug']} The precise methods and strategies employed may forever elude our understanding, leaving us in awe of the enigma that surrounds this monumental accomplishment. {emoji_codes['yeahboi']} Such is the nature of this astounding feat, a tale woven with threads of intrigue and bewilderment, forever etched in the annals of TFT history. {emoji_codes['business']}"
    ]
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


async def update_leaderboard():
    previous_rankings = []
    # channel = client.get_channel(1118758206840262686) TESTING SERVER
    general_channel = client.get_channel(846551161388662789)
    tft_leaderboard_channel = client.get_channel(1118278946048454726)
    #while True:
    print("collecting ranked stats...")
    rankings_list = await get_tft_ranked_stats()

    # Compare the top 4 summoners in the previous rankings with the top 3 summoners in the new rankings
    for i in range(4):
        if previous_rankings and rankings_list[i][0] != previous_rankings[i][0]:
            current_player = rankings_list[i][0]
            previous_rank = [x for x in range(len(previous_rankings)) if previous_rankings[x][0] == current_player][
                0]
            if i < previous_rank:
                print(rankings_list[i])
                print(previous_rankings[i])
                # Send alert message when rankings have changed and someone ranked up
                await general_channel.send(get_random_message(previous_rankings[i][0], rankings_list[i][0], i + 1))
    previous_rankings = rankings_list
    print("updating leaderboard...")
    # Delete the last leaderboard message if it exists
    if hasattr(update_leaderboard, "last_message") and update_leaderboard.last_message:
        try:
            print("deleting last message...")
            await update_leaderboard.last_message.delete()
        except:
            pass
    # Set up some constants
    NORMAL_FONT_SIZE = 25
    MEDIUM_FONT_SIZE = 23
    SMALL_FONT_SIZE = 21
    RANK_IMAGE_SIZE = (55, 55)
    POGO_IMAGE_SIZE = (40, 40)
    BACKGROUND_IMAGE_PATH = "img/leaderboard_background.png"  # Set the path to your background image here
    BACKGROUND_SIZE = (1366, 757)  # Set the size of your background image here

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
            if index >= len(rankings_list):
                break
            summoner = rankings_list[index]
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
        print("sending updated leaderboard...")
        update_leaderboard.last_message = await tft_leaderboard_channel.send(
            file=discord.File(output, filename="leaderboard.png"))

           # print("waiting 5 minutes before repeating...")
            # Wait for 5 minutes before updating the leaderboard again
           # await asyncio.sleep(300)


async def get_match_history(previous_match_history_ids):
    match_history_ids = []
    general_channel = client.get_channel(846551161388662789)
    for summoner_name in summoner_names_list:
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
        match_history_ids.extend(last_3_games_ids)
        # Check if any ids in last_3_games_ids are present in previous_match_history_ids
        common_ids = set(match_history_ids) == set(previous_match_history_ids)
        logging.info(f"{summoner_name} common ids: {common_ids}")
        print(f"{summoner_name} common ids: {common_ids}")
        placements = []
        if not common_ids:
            for game in ranked_games:
                # Find the player placements in the every match
                for participant in game["info"]["participants"]:
                    if participant["puuid"] == summoner["puuid"]:
                        placements.append(participant["placement"])
                        break
            logging.info(f"{summoner_name} placements: {placements}")
            print(f"{summoner_name} got the following placements: {placements}")
            for i in range(len(placements) - 1):
                if placements[i] == 1 and placements[i + 1] == 1:
                    pogo_emote = "<:PogO:949833186689568768>"
                    await general_channel.send(
                        f"🏆 ATTENTION! {get_discord_username(summoner_name)} got two 1st placements in a row! {pogo_emote} 🏆")
                if placements[i] == 8 and placements[i + 1] == 8:
                    aycaramba_emote = "<:aycaramba:960051307752849448>"
                    await general_channel.send(
                        f"📉 ATTENTION! {get_discord_username(summoner_name)} got two 8th placements in a row! {aycaramba_emote} 📉")

    return match_history_ids


async def check_match_history_streak():
    previous_match_history_ids = []
    logging.info(f"Checking match history...")
    print(f"Checking match history...")
    match_history_ids = await get_match_history(previous_match_history_ids)
    # Save current match history ids
    previous_match_history_ids = match_history_ids
    print(f"previous match history ids: {previous_match_history_ids}")


async def update_tasks():
    while True:
        # Call update_leaderboard every 5 minutes
        client.loop.create_task(update_leaderboard())
        await asyncio.sleep(300)

        # Call check_match_history_streak every 10 minutes
        client.loop.create_task(check_match_history_streak())
        await asyncio.sleep(300)

        client.loop.create_task(update_leaderboard())
        await asyncio.sleep(300)

        # Clear the contents of the app.log file
        with open("app.log", "w") as log_file:
            log_file.truncate()


# =====================
# Discord
# =====================
@client.event
async def on_ready():
    logging.debug("on_ready function called")
    await client.tree.sync()
    print("Success: PogO bot is connected to Discord".format(client))
    client.loop.create_task(update_tasks())


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

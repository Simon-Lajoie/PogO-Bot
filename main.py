import asyncio
import io
from collections import deque
from datetime import datetime, timedelta, timezone
from time import time
import discord
from discord.ext import commands, tasks
from collections import defaultdict
from datetime import datetime, timedelta
import random
from riotwatcher import LolWatcher, ApiError, TftWatcher, RateLimiter
from PIL import Image, ImageDraw, ImageFont
from itertools import combinations
import logging
import os
from dotenv import load_dotenv

intents = discord.Intents.default()
intents.members = True
intents.guilds = True
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

region = 'na1'
summoner_names_list_tft = ["Sir Mighty Bacon", "Settupss", "Classiq", "Wallaby", "Sehnbon", "Gourish", "Ramza",
                           "Gabyumi", "meyst", "Limited", "Z3SIeeper", "BlackDrag", "Flames",
                           "Tiny Cena", "Aàrón", "5billon", "Nappy", "KingNeptun3", "Mrs Mighty Bacon", "cpt stryder",
                           "cancerkween", "Azote", "ÇatFood", "Skrt Skrt Skaarl",
                           "NonMaisWallah", "Fonty", "Oogli", "Lewis Kane", "Maa san", "SETT DEEZ UPSS", "Skyhigh2005",
                           "Zotto", "Evelynn Toes", "Shrektangle", "Wazzaii", "Chopin is Bach", "Andrei"
                           ]
summoner_names_list_lol = ["Sir Mighty Bacon", "Settupss", "Classiq", "Wallaby", "Sehnbon", "Gourish", "Ramza",
                           "Gabyumi", "meyst", "Limited", "Z3SIeeper", "BlackDrag", "Flames",
                           "Tiny Cena", "Aàrón", "5billon", "Nappy", "KingNeptun3", "Mrs Mighty Bacon", "cpt stryder",
                           "cancerkween", "Azote", "ÇatFood", "Skrt Skrt Skaarl", "Maa san",
                           "NonMaisWallah", "Mnesia", "Fonty", "Oogli", "Cowboy Codi", "nasir2", "Skyhigh2005", "Zotto",
                           "Evelynn Toes", "Shrektangle", "Wazzaii", "Chopin is Bach", "Andrei"
                           ]


def get_discord_username(summoner_name):
    discord_ids = {"Sir Mighty Bacon": "<@149681004880199681>", "Settupss": "<@144611125391130624>",
                   "Classiq": "<@155758849582825472>", "Wallaby": "<@315272936053276672>",
                   "Sehnbon": "<@198960489022095360>", "Ramza": "<@86595633288351744>",
                   "Gourish": "<@700837976544116808>", "Gabyumi": "<@241712679150944257>",
                   "Best Pigeon NA": "<@180136748091834368>", "meyst": "<@153778413646118912>",
                   "Limited": "<@715430081975025687>", "Z3SIeeper": "<@130242869708587008>",
                   "BlackDrag": "<@244390872983011328>", "Flames": "<@80373001006096384>",
                   "silvah bee": "<@527593111547805696>", "Tiny Cena": "<@154752158854545408>",
                   "Aàrón": "<@64494156914888704>", "5billon": "<@133779784105721856>",
                   "Nappy": "<@170962579974389762>", "KingNeptun3": "<@275435768661540866>",
                   "Mrs Mighty Bacon": "<@251140411043610625>", "cpt stryder": "<@148338461433135104>",
                   "Yazeed": "<@495380694525280276>", "Kenpachi": "<@263107658762944512>",
                   "cancerkween": "<@999785244045615224>",
                   "azote": "<@80372982337241088>", "Kovannate3": "<@1946154    71226617865>",
                   "ÇatFood": "<@160067484559474688>", "Skrt Skrt Skaarl": "<@272440042251616256>",
                   "NonMaisWallah": "<@520754531525459969>", "Mnesia": "<@402638715849146378>",
                   "Fonty": "<@133458482232819712>", "Oogli": "<@173232033772994560>",
                   "Cowboy Codi": "<@115992535855267844>",
                   "Lewis Kane": "<@913637634767716393", "nasir2": "<@1052819643351433268>",
                   "Skyhigh2005": "<@339383907449569281>", "Zotto": "<@148963530262052864>",
                   "Evelynn Toes": "<@152469092182261761>", "Shrektangle": "<@117811507693223944>",
                   "Wazzaii": "<@399391319300112386>", "Chopin is Bach": "<@112316340844462080>",
                   "Andrei": "<@125330438515458048>"}
    name = discord_ids[summoner_name]
    if name is None:
        name = summoner_name
    return name


# TFT-SUMMONER-V1 : /tft/summoner/v1/summoners/by-puuid/{encryptedPUUID} :  id
def get_tft_summoner_id(summoner_name):
    summoner_ids = {"Sir Mighty Bacon": "0GG54nxtoEItfeHzhyB367L5eSIsq1U8sNE9txqQw6Pxo9o",
                    "Settupss": "w-THN6OPeTdgL2JauMBPkvYaUYgD8WiwiX39mc3Yk4Dcs1k",
                    "Classiq": "FQtC6bnuIM6JzqQGPswTwgoSvEZEa0WucLjaChTRdrKdbAQ",
                    "Wallaby": "MSI8zoZGAnDB6NpMBEHYQwCLvtx_aKmC6fyxBj1mEM55dmg",
                    "Sehnbon": "QHuy9eL2GdDcu3erWravRY1rDshpvfMM6EtjeNnYI7r-YIw",
                    "Ramza": "nkWVBsYJO1fWVq1Wtfx-Bx03fKSo7APYyCxpXzwR5FK_h55b",
                    "Gourish": "9zX1sJAd7RciO6B7GwQODzAvBaQO634peXMAUtOINuX2y_k",
                    "Gabyumi": "8nLXCqx3oDKEJ4pAceeQSr3L0uUAdY4rdTJgXKHh8OyRzoc",
                    "meyst": "dasfJoEy9c_DNWqG8Y30RzK6Fgm-hdE_6dcx7XzL3MzA-Lw",
                    "Limited": "OkZo1rN5o0DDWK5LGwgXDT4k5fd2FHhCRcPv69LulAEqirk",
                    "Z3SIeeper": "u78gFAF4MJ2J4brtythuTE-uPpYEaFNCRK5hbXDLOOjf_3Ck",
                    "BlackDrag": "cmxCpBLbYX48necTpKLBiTn5IM1J0AYWHKiCAC5OcyuG6_o",
                    "Flames": "APXt68Ogg5-pMLP5vdoq1hwpn-wl4sFxJl6GJg4356U3Vbs",
                    "Tiny Cena": "UBLAyVJLtvI0DvNJZc5Ln_ShUKt_DpPJijJNgewxRLTP4Mg",
                    "Aàrón": "hR0VrK_dmuN1_CbI9ea576MSKDKoQfH9_VEd_4iBCjEogLU",
                    "5billon": "C4Ewpnp_HCLtxYT3TXwR-bcQQzIu63dODg7Zc_B298hkm9U",
                    "Nappy": "4ZG-cOVycckEnl86R8h1h0wl0P9c4ZMkdFBJL9cY_-pm55Y",
                    "KingNeptun3": "fPMH_-GawqeVv22Kr5PSAd582K3zRd57C_5m0QZR4Yoy7dw",
                    "Mrs Mighty Bacon": "wMMQdqPaS1ZMobR8SQHcwjbQyB1GpFeg4PoReTKU8HiPpG8",
                    "cpt stryder": "CS5p6zEnufRFlSTe0fF9pQeW_meyyZJmcGN8-ZvmLcQo9LQ",
                    "cancerkween": "zAtWP0dciMVlK5XHahuXW3KDsmGjq0PcJBL3LY-B-3N1Aik",
                    "Azote": "hjyAMX0av2nWPtjMEd3GyyrAeWAx6x-E0iBWiXXVMSkaAGw",
                    "ÇatFood": "6E_MKLcjrxZXf-xZ_JumEpHb2qY6vKs5di52SQyCQPIKBjg",
                    "Skrt Skrt Skaarl": "3Hk5eY4OPC9YtMy0wunkJfrU7OJvLjQdPCtpVpuSJe6T59I",
                    "NonMaisWallah": "O-uH49qtvOCpYCxny_dLNVA8-VP-lg9q8ItA4qjZh7M6RKY",
                    "Fonty": "cJ4MBSz6cOeG8QsYlGo_d926VRLSRyCPQfPgDLNwIsde68Y",
                    "Oogli": "oMsxDlJYVyjMafhFYE-DvG_7Tc8R-PUg-DA8Twj88DY_-aU",
                    "Lewis Kane": "m-a_uIa_oQIaVhliUaITnBLcy0cV01tBQwF04DXxj-9IrEE",
                    "Maa san": "1a-PuFsiNRx_b4CrVJzrt4kdmmWZGFCH0AdvpEeKUWcVMH8",
                    "Mnesia": "b7nHdeLVJ7Zl-fazM4k-KJBy88s1cB8zm_nppsPkNSS7KU8",
                    "Cowboy Codi": "JB8H7801QFiu3GFZAN1i0fT_aaJdra2zM7XbghmS93Ntsa4",
                    "nasir2": "1vJSvGRpUgiltfK1_fY1BaqboL7gCGiuqt8sAAWdRa8brxE",
                    "SETT DEEZ UPSS": "hvMpHFnx9VqcBkdPTAyAOSqaT7kdY9iCiZekfR5y45oHGMpIHX5Js6jOzQ",
                    "Skyhigh2005": "xAm6DMppQhPx0LNH5v6QLAWPJ7LuynhKEVph2GMDPye4MX8",
                    "Zotto": "9ClJmRzP6E034Fb7MnsVy73uHBJaDfDeg7BX-4om45kfdHM",
                    "Evelynn Toes": "CZeYa86XVPDYCwF46CyxmIaOzeOhpqF6gGtssVFvTrZU-Oo",
                    "Shrektangle": "AJeJwbD1HZIGNh6eORY6uGQMmAbCEMrKl-wFdGHhqdEoim0",
                    "Wazzaii": "zUdGoQbWL0X0t-D49NvukUU2uKYL-eFE8MBVuxMjU2yYn-C9",
                    "Chopin is Bach": "6O5aOY2ykeAIPAm0ztZiHtH8Ykm482WEHVDkCTi0K5PA4I0",
                    "Andrei": "3eBPR6YQ2UeXMLDWmwtO1mxkdzWvMcA4sX3r7tYfNi4QZew"
                    }
    return summoner_ids[summoner_name]


# SUMMONER-V4 : /lol/summoner/v4/summoners/by-puuid/{encryptedPUUID} :  id
def get_lol_summoner_id(summoner_name):
    summoner_ids = {"Sir Mighty Bacon": "BGGUjqEm1nar21U8pP_wj7Bv2uyd1Na-03wy7yeZVMRdEv0",
                    "Settupss": "r6XtQGwiHuXfAHfrfvIXXuhOYpyyoUsm2JgC3r_BAVGWYbs",
                    "Classiq": "yYoauMyQZaUfORAaOybCxcKgToviC5W5Yay_uyhZC-aAzYk",
                    "Wallaby": "y37IGgVEke9uG-LLpZa5mlPanyxZi3x9rtJRXF9OW2B-wc8",
                    "Sehnbon": "EbFaesXSJiOZulgc_peh78EfhbBg_Slk74xJmQAWPuM1N4I",
                    "Ramza": "BxEp90dfHbxrE0aYSgayPLb3eh3wqu7SEoUEHEj1aSWdGso_",
                    "Gourish": "3dgqr2I7GQmtQCkdLB_calb0h-UmOyWJVQhjCC_bB-U-Ln4",
                    "Gabyumi": "0j2bXO5OOOeFhe4LX1cGAzEYxBSP8x3xZmIqbuFQVd2j8Yw",
                    "meyst": "g0BTZnymywWaJ39n_oE8XCrNy2hN6Zi0ljnYIXBR5jU2ILs",
                    "Limited": "N0LkC1sOwO-9J_fE2_IHpcEc-B4GArYFD11Jhfh21MklKLg",
                    "Z3SIeeper": "H8mMWxvMNWpxhMoSOaC8m59txmO3ZmLTmAEV1hCIzNrLdZ-b",
                    "BlackDrag": "hLXUGO0f4JSogjsJKhyrXlzzFm27iz5nkLuOczd2YKEOCqw",
                    "Flames": "IZx8e2BrDLu1x7X6pUgzPxMqqKBOMwXrJ59Fgr0W7C3GSjY",
                    "Tiny Cena": "kr9B4wdzki8INVxOyXrvPDqUcdCxMKoDhUc4ytusynhqn7Q",
                    "Aàrón": "HGVC39mIVJauqT3njok44TNPIxMJp9A8sptkhY0CP__bJSc",
                    "5billon": "PCBqQfKevnh_PwJerhJOFOZ8BEZi90HYOBXduWvJl_pMaPg",
                    "Nappy": "6XhgOt9X2zQ_Fe7jo6rsC2d23YCsdPGMygSxjyjQ3dfzMUM",
                    "KingNeptun3": "IK9m0nzKywT8QHETKGGo3x84dxHFWAncogb0Lza-jAvtMFQ",
                    "Mrs Mighty Bacon": "9C7cBE25XnHAq5v79I93sHF870IF-gPEUWeL-wG4UJavp2E",
                    "cpt stryder": "AnWANDBFFi5jTDZabqcnCfs9G3USpUyHsCq0ScoWEwMJt14",
                    "cancerkween": "EpzNVAQqQkqPFRaiT6nbTXvWNRIW9xjwnJagcIOiPLIO1Bc",
                    "Azote": "bXmbhljaXkeKIA5NqOtU5loCKk0iZZfbSjyElSrieruR73s",
                    "ÇatFood": "6yUsSm7sVzOxasogCBtyYu_5XitMPYMH6ImhPvVgJ8Imq4Q",
                    "Skrt Skrt Skaarl": "V5nQ3nav3PLrZA8WINbF0MQ7tSrdLdye-lJ3Y9-4YhvknPw",
                    "Maa san": "4p6IPgfKlB4bxUOVTThObFs65avz47bq8y4uFFuHGIv1gxE",
                    "NonMaisWallah": "vfescDjzqKyE5JlCyoDbERcl2JlkykKxe7-wHZfqmvR9-hY",
                    "Mnesia": "nU10JVyDakgBiVfFxkk87T8L8BsczVlcPqshjZ_2w-mMXzE",
                    "Fonty": "7BMUv4tXI6JEuun6_sz5huI765Uy4QcjlhgsVD5qgsXrZk0",
                    "Oogli": "qwlwdyJ8JhazKg9vT4lC16xZX6KmpLM6Qr5RJmmoaXK8NzQ",
                    "Cowboy Codi": "UUds1L0jQitbbmdu59qJASffV1bvMOcw9LaO37bFTvcRo0U",
                    "nasir2": "m0fr8tpp_XZYazT4LQ4ASMhUDvXbUcp5sYIesRxL_Qu6lWo",
                    "Skyhigh2005": "Q0gF9NCFu0Q-z0hsTlZOp41fupflzwGgbGraoQc_0QxbAUs",
                    "Zotto": "hEXJtbk_gHgNlYTNCzjEt1RbK5TDLlHTf9SvKoEA_9R14C0",
                    "Evelynn Toes": "2fOn-Jh1Ywl0rD40dBAwtO31MLRVQTVY7bDEorZok587Wts",
                    "Shrektangle": "Az2OVpJd1zlChwavlsJJ5smzRVDMVFm1g_chlDdTCNRhk-Q",
                    "Wazzaii": "Q_HNTT3UYCFsbSTeDn-85p0H20fsbgpJ8Lpwh_1R6eeDdoEA",
                    "Chopin is Bach": "HqmOUAf20MrW0CDmZN0A_MNpfdBaK4MpJJGhz2SAc3Q7hLk",
                    "Andrei": "jyIqP2051PUgj1HSH9kY0nhPc3h8mzU-zvsf3k2CqJWAl1c"
                    }
    return summoner_ids[summoner_name]


previous_match_history_ids = []
updated_tft_rankings_list = []
updated_lol_rankings_list = []
loop = client.loop
general_channel_id = 1249887657761443841
tft_leaderboard_channel_id = 1249993766300024842
lol_leaderboard_channel_id = 1249993747119472693


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
        "EMERALD IV": 21,
        "EMERALD III": 22,
        "EMERALD II": 23,
        "EMERALD I": 24,
        "DIAMOND IV": 25,
        "DIAMOND III": 26,
        "DIAMOND II": 27,
        "DIAMOND I": 28,
        "MASTER I": 29,
        "GRANDMASTER I": 29,
        "CHALLENGER I": 29
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
                # logging.info(f"Making request to Riot API for TFT summoner: {summoner_name}")
                # print(f"Making request to Riot API for TFT summoner: {summoner_name}")
                # summoner = tft_watcher.summoner.by_name(region=region, summoner_name=summoner_name)
                summoner_id = get_tft_summoner_id(summoner_name)
                await asyncio.sleep(1)
                # Gets TFT ranked_stats using summoner's ID
                logging.info(f"Making request to Riot API for TFT ranked stats of summoner: {summoner_name}")
                print(f"Making request to Riot API for TFT ranked stats of summoner: {summoner_name}")
                # ranked_stats = tft_watcher.league.by_summoner(region=region, encrypted_summoner_id=summoner["id"])
                ranked_stats = tft_watcher.league.by_summoner(region=region, encrypted_summoner_id=summoner_id)
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

    rankings_list.sort(key=lambda x: (x[1], x[0]), reverse=True)
    return rankings_list


async def update_tft_rankings_list(updated_tft_rankings_list_lock):
    global updated_tft_rankings_list
    while True:
        for i in range(0, len(summoner_names_list_tft), 8):
            batch = summoner_names_list_tft[i:i + 8]
            logging.info(f"Updating TFT rankings for batch: {batch}")
            print(f"Updating TFT rankings for batch: {batch}")
            try:
                batch_rankings = await get_tft_ranked_stats(batch)
            except Exception as e:
                logging.error(f"An error occurred while getting TFT ranked stats for batch {batch}: {e}")
                continue
            async with updated_tft_rankings_list_lock:
                for ranking in batch_rankings:
                    summoner_name = ranking[0]
                    existing_ranking = next((r for r in updated_tft_rankings_list if r[0] == summoner_name), None)
                    if existing_ranking:
                        updated_tft_rankings_list.remove(existing_ranking)
                    updated_tft_rankings_list.append(ranking)
                updated_tft_rankings_list.sort(key=lambda x: (x[1], x[0]), reverse=True)
            logging.info(f"Updated TFT rankings list: {updated_tft_rankings_list}")
            logging.info(f"Waiting 1 minutes until next TFT batch update...")
            await asyncio.sleep(60)


async def update_lol_rankings_list(updated_lol_rankings_list_lock):
    global updated_lol_rankings_list
    while True:
        for i in range(0, len(summoner_names_list_lol), 8):
            batch = summoner_names_list_lol[i:i + 8]
            logging.info(f"Updating LoL rankings for batch: {batch}")
            print(f"Updating LoL rankings for batch: {batch}")
            try:
                batch_rankings = await get_lol_ranked_stats(batch)
            except Exception as e:
                logging.error(f"An error occurred while getting LoL ranked stats for batch {batch}: {e}")
                continue
            async with updated_lol_rankings_list_lock:
                for ranking in batch_rankings:
                    summoner_name = ranking[0]
                    existing_ranking = next((r for r in updated_lol_rankings_list if r[0] == summoner_name), None)
                    if existing_ranking:
                        updated_lol_rankings_list.remove(existing_ranking)
                    updated_lol_rankings_list.append(ranking)
                updated_lol_rankings_list.sort(key=lambda x: (x[1], x[0]), reverse=True)
            logging.info(f"Updated LoL rankings list: {updated_lol_rankings_list}")
            logging.info(f"Waiting 1 minutes until next LoL batch update...")
            print(f"Updated LoL rankings list: {updated_lol_rankings_list}")
            print(f"Waiting 1 minutes until next LoL batch update...")
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
                # logging.info(f"Making request to Riot API for LoL summoner: {summoner_name}")
                # print(f"Making request to Riot API for LoL summoner: {summoner_name}")
                # summoner = lol_watcher.summoner.by_name(region=region, summoner_name=summoner_name)
                summoner_id = get_lol_summoner_id(summoner_name)
                await asyncio.sleep(1)
                # Gets LoL ranked_stats using summoner's ID
                logging.info(f"Making request to Riot API for LoL ranked stats of summoner: {summoner_name}")
                print(f"Making request to Riot API for LoL ranked stats of summoner: {summoner_name}")
                # ranked_stats = lol_watcher.league.by_summoner(region=region, encrypted_summoner_id=summoner["id"])
                ranked_stats = lol_watcher.league.by_summoner(region=region, encrypted_summoner_id=summoner_id)
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

    rankings_list.sort(key=lambda x: (x[1], x[0]), reverse=True)
    return rankings_list


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
    salsa_king_summoner = get_discord_username("Wallaby")
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
        return f"{emoji_codes['pogo']} {new_summoner} has just {gourish_random} {old_summoner} to their rightful place… NOOB! GOOGOO IS A NOOB! AGREED!  {emoji_codes['aycaramba']}"
    if old_summoner == salsa_king_summoner:
        return f"{emoji_codes['pogo']} {new_summoner} has overtaken {old_summoner} to achieve rank {position}, telling {old_summoner} that throughout Heaven and Earth, he alone is The Fraudulent One. {emoji_codes['pogo']}"
    if new_summoner == salsa_king_summoner:
        return f"{emoji_codes['pogo']} {new_summoner} has overtaken {old_summoner} to achieve rank {position}, proving once again that throughout Heaven and Earth, he alone is The Honored One. {emoji_codes['pogo']}"
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
    rankings = await get_lol_ranked_stats(names)
    # balance the teams
    # assign players to teams using the minimax algorithm
    team1, team2 = balance_algorithm(rankings)
    # send the balanced teams back to the user
    print(team1)
    print(team2)
    await ctx.send(f'Team 1: {", ".join(team1)}')
    await ctx.send(f'Team 2: {", ".join(team2)}')


async def update_tft_leaderboard(previous_rankings, message, updated_tft_rankings_list_lock):
    global updated_tft_rankings_list
    async with updated_tft_rankings_list_lock:
        # channel = client.get_channel(1118758206840262686) TESTING SERVER
        general_channel = client.get_channel(general_channel_id)
        tft_leaderboard_channel = client.get_channel(tft_leaderboard_channel_id)

        # Edit the content of the message object to display "refreshing..."
        logging.info("TFT Countdown timer: Refreshing leaderboard...")
        print("Refreshing leaderboard...")
        await message.edit(content="Refreshing leaderboard...")

        logging.info(f"Previous TFT rankings: {previous_rankings}")
        print("Collecting TFT ranked stats...")
        # Compare the top 4 summoners in the previous rankings with the top 3 summoners in the new rankings
        for i in range(4):
            if previous_rankings and updated_tft_rankings_list[i][0] != previous_rankings[i][0]:
                current_player = updated_tft_rankings_list[i][0]
                rank= updated_tft_rankings_list[i][1]
                # Skip if the current player is unranked
                if rank == 0:
                    continue
                player_ranks = [x for x in range(len(previous_rankings)) if previous_rankings[x][0] == current_player]
                if player_ranks:
                    previous_rank = player_ranks[0]
                    if i < previous_rank:
                        print(updated_tft_rankings_list[i])
                        print(previous_rankings[i])
                        logging.info(
                            f"TFT Rankings have changed! {updated_tft_rankings_list[i][0]} has passed {previous_rankings[i][0]}")
                        print(
                            f"TFT Rankings have changed! {updated_tft_rankings_list[i][0]} has passed {previous_rankings[i][0]}")
                        # Send alert message when rankings have changed and someone ranked up
                        await general_channel.send(
                            get_random_message(previous_rankings[i][0], updated_tft_rankings_list[i][0], i + 1))
                        logging.info("TFT Rankings update message sent to TFT Leaderboard chat!")
                        print("TFT Rankings update message sent to TFT Leaderboard chat!")

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

        # WIDTH, HEIGHT OF THE BACKGROUND IMAGE FOR TFT LEADERBOARD
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
    print("Starting TFT countdown timer...")
    await countdown_timer_tft(360, message)


async def update_lol_leaderboard(previous_rankings, message, updated_lol_rankings_list_lock):
    global updated_lol_rankings_list
    async with updated_lol_rankings_list_lock:
        # channel = client.get_channel(1118758206840262686) TESTING SERVER
        general_channel = client.get_channel(general_channel_id)
        lol_leaderboard_channel = client.get_channel(lol_leaderboard_channel_id)

        # Edit the content of the message object to display "refreshing..."
        logging.info("LoL Countdown timer: Refreshing LoL leaderboard...")
        print("Refreshing LoL leaderboard...")
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
                        print(
                            f"LoL Rankings have changed! {updated_lol_rankings_list[i][0]} has passed {previous_rankings[i][0]}")
                        # Send alert message when rankings have changed and someone ranked up
                        # await general_channel.send(
                        #    get_random_message(previous_rankings[i][0], updated_lol_rankings_list[i][0], i + 1))
                        logging.info("LoL Rankings changed message sent!")
                        print("LoL Rankings changed message sent!")

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

        # WIDTH, HEIGHT OF THE BACKGROUND IMAGE FOR LOL LEADERBOARD
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
    print("Starting LoL countdown timer...")
    await countdown_timer_lol(360, message)


async def countdown_timer_tft(time, message):
    logging.info(f"Starting TFT countdown timer with time={time} and message={message.content}")
    print(f"Starting TFT countdown timer with time={time} and message={message.content}")
    # Calculate the number of minutes remaining
    minutes = time // 60

    # Edit the content of the message object to display the time remaining
    await message.edit(content=f"Next update in: {minutes} minutes")
    while time > 0:
        try:
            await asyncio.sleep(1)
            time -= 1
            # logging.info(f"Countdown timer ticked with time={time} and message={message.content}")
            # Calculate the number of minutes and seconds remaining
            minutes, seconds = divmod(time, 60)
            minutes = minutes + 1
            # Check if the content of the message object has been changed to "refreshing..."
            if message.content == "Refreshing TFT leaderboard...":
                logging.info(f"TFT Countdown timer stopped because message content changed to 'refreshing...'")
                print(f"TFT Countdown timer stopped because message content changed to 'refreshing...'")
                # Break out of the while loop to stop the countdown timer
                break

            # Edit the content of the message object to display the time remaining
            if seconds == 59:
                logging.info(f"TFT Countdown timer updated: {minutes} minutes")
                await message.edit(content=f"Next update in: {minutes} minutes")
            elif minutes == 0 and seconds == 10:
                await message.edit(content=f"Next update in: {seconds:2d} seconds")
        except Exception as e:
            print(f"An error occurred in countdown_timer_tft: {e}. Retrying in 5 seconds...")
            await asyncio.sleep(5)  # Wait for 5 seconds before retrying

    logging.info(f"TFT Countdown timer finished with time={time} and message={message.content}")
    print(f"TFT Countdown timer finished with time={time} and message={message.content}")


async def countdown_timer_lol(time, message):
    logging.info(f"Starting LoL countdown timer with time={time} and message={message.content}")
    print(f"Starting LoL countdown timer with time={time} and message={message.content}")
    # Calculate the number of minutes remaining
    minutes = time // 60

    # Edit the content of the message object to display the time remaining
    await message.edit(content=f"Next update in: {minutes} minutes")
    while time > 0:
        try:
            await asyncio.sleep(1)
            time -= 1
            # logging.info(f"Countdown timer ticked with time={time} and message={message.content}")
            # Calculate the number of minutes and seconds remaining
            minutes, seconds = divmod(time, 60)
            minutes = minutes + 1
            # Check if the content of the message object has been changed to "refreshing..."
            if message.content == "Refreshing Soloq leaderboard...":
                logging.info(f"LoL Countdown timer stopped because message content changed to 'refreshing...'")
                print(f"LoL Countdown timer stopped because message content changed to 'refreshing...'")
                # Break out of the while loop to stop the countdown timer
                break

            # Edit the content of the message object to display the time remaining
            if seconds == 59:
                logging.info(f"LoL Countdown timer updated: {minutes} minutes")
                await message.edit(content=f"Next update in: {minutes} minutes")
            elif minutes == 0 and seconds == 10:
                await message.edit(content=f"Next update in: {seconds:2d} seconds")
        except Exception as e:
            print(f"An error occurred in countdown_timer_lol: {e}. Retrying in 5 seconds...")
            await asyncio.sleep(5)  # Wait for 5 seconds before retrying

    logging.info(f"LoL Countdown timer finished with time={time} and message={message.content}")
    print(f"LoL Countdown timer finished with time={time} and message={message.content}")


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
    tft_leaderboard_channel = client.get_channel(tft_leaderboard_channel_id)
    lol_leaderboard_channel = client.get_channel(lol_leaderboard_channel_id)
    previous_tft_rankings = []
    previous_lol_rankings = []

    # Send the initial message once
    try:
        message_tft = await tft_leaderboard_channel.send("Starting TFT leaderboard...")
        message_lol = await lol_leaderboard_channel.send("Starting LoL leaderboard...")
    except Exception as e:
        logging.error(f"Failed to send initial leaderboard messages: {e}")
        return  # Exit if initial messages cannot be sent

    while True:
        task1 = asyncio.create_task(
            update_tft_leaderboard(previous_tft_rankings, message_tft, updated_tft_rankings_list_lock))
        task2 = asyncio.create_task(
            update_lol_leaderboard(previous_lol_rankings, message_lol, updated_lol_rankings_list_lock))

        try:
            await asyncio.gather(task1, task2)
        except Exception as e:
            logging.error(f"An error occurred during leaderboard updates: {e}")
            print(f"An error occurred during leaderboard updates: {e}")
            # Optionally, add a delay before retrying to prevent rapid failure loops
            await asyncio.sleep(10)
            continue  # Continue the loop to attempt updates again


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


@tasks.loop(minutes=5)
async def reset_tracker():
    global action_tracker
    action_tracker = defaultdict(list)
    print("Action tracker reset.")


# =====================
# Discord
# =====================
@client.event
async def on_ready():
    logging.debug("on_ready function called")
    await client.tree.sync()
    print("Success: PogO bot is connected to Discord".format(client))
    tft_leaderboard_channel = client.get_channel(tft_leaderboard_channel_id)
    lol_leaderboard_channel = client.get_channel(lol_leaderboard_channel_id)
    await clear_channel(tft_leaderboard_channel)
    await clear_channel(lol_leaderboard_channel)
    print("Success: PogO bot has cleared the TFT leaderboard channel")
    updated_tft_rankings_list_lock = asyncio.Lock()
    updated_lol_rankings_list_lock = asyncio.Lock()
    client.loop.create_task(update_tasks(updated_tft_rankings_list_lock, updated_lol_rankings_list_lock))
    client.loop.create_task(update_tft_rankings_list(updated_tft_rankings_list_lock))
    client.loop.create_task(update_lol_rankings_list(updated_lol_rankings_list_lock))
    reset_tracker.start()

@client.hybrid_command()
async def balance_teams(ctx, summoner_names):
    await balance(ctx, summoner_names)


@client.event
async def on_message(message):
    message_lower = message.content.lower()
    if message.author == client.user:
        return

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
                channel = client.get_channel(general_channel_id)  # general chat
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
                channel = client.get_channel(general_channel_id)  # general chat
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
                channel = client.get_channel(general_channel_id)  # general chat
                # Send banned message to the channel
                await channel.send(f"{entry.user.mention} was banned! RIP BOZO! <:PogO:949833186689568768>")

#Temporarily to silence user
#@client.event
#async def on_reaction_add(reaction, user):
    #if user.id == 80373001006096384:
    #    await reaction.remove(user)

client.run(client_id)

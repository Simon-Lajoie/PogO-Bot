# main.py

import asyncio
import discord
from discord.ext import commands
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import logging
import os
from dotenv import load_dotenv

# --- Basic Setup ---
load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s:%(levelname)s:%(name)s: %(message)s')

# =================================================================================
# BOT INITIALIZATION
# =================================================================================
intents = discord.Intents.default()
intents.members = True
intents.guilds = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# =================================================================================
# GENERAL EVENTS & COMMANDS
# =================================================================================

@bot.event
async def on_message(message):
    """Handles custom message responses."""
    if message.author == bot.user:
        return

    message_lower = message.content.lower()

    # Example commands, keeping them simple
    responses = {
        'poggiesxdd': ("<:POGGIES:926135482360950824>", None),
        'pogo': (None, "img/UNRANKED.png"),
        'tpogo': (None, "img/tpogo.png"),
        'huhpogo': (None, "img/huhpogo.gif"),
        'caughtpogo': (None, "img/caughtpogo.png"),
        'bigcaughtpogo': (None, "img/bigcaughtpogo.png"),
        'pogoflickleave': (None, "img/pogo_flick_leave.gif")
    }

    if message_lower in responses:
        await message.delete()
        content, file_path = responses[message_lower]
        if file_path:
            await message.channel.send(content, file=discord.File(file_path))
        else:
            await message.channel.send(content)

    if message_lower == "is gourish a noob ?":
        target_user = bot.get_user(700837976544116808)
        await message.channel.send(file=discord.File("assets/img/tpogo.png"))
        if target_user:
            await message.channel.send(f"YES! {target_user.mention} IS A NOOB! AGREED!")

    await bot.process_commands(message)

# =================================================================================
# MAIN EXECUTION BLOCK
# =================================================================================
async def main():
    """The main entry point for the bot."""
    # Load environment variables for API keys
    discord_token = os.environ.get("DISCORD_TOKEN")
    tft_api_key = os.environ.get("TFT_API_KEY")
    lol_api_key = os.environ.get("LOL_API_KEY")

    if not all([discord_token, tft_api_key, lol_api_key]):
        logging.critical(
            "FATAL: Missing one or more required environment variables (DISCORD_TOKEN, TFT_API_KEY, LOL_API_KEY).")
        print("Error: Missing required environment variables. Check your .env file.")
        return

    # Attach API keys to the bot object so cogs can access them
    bot.tft_api_key = tft_api_key
    bot.lol_api_key = lol_api_key

    # Load the leaderboard cog
    # The path uses dots, not slashes. 'cogs.leaderboard_cog' refers to cogs/leaderboard_cog.py
    try:
        logging.info("Loading cogs...")
        await bot.load_extension("cogs.leaderboard_cog")
        await bot.load_extension("cogs.security_cog")
        logging.info("All cogs loaded successfully.")
    except Exception as e:
        logging.critical(f"Failed to load a cog: {e}", exc_info=True)
        return

    # Start the bot
    async with bot:
        await bot.start(discord_token)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except discord.LoginFailure:
        logging.error("FATAL: Improper token passed.")
        print("Error: Improper Discord token provided.")
    except Exception as e:
        logging.exception(f"An unexpected error occurred during bot execution: {e}")
        print(f"An unexpected error occurred: {e}")
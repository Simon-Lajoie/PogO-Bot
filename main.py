# main.py

import asyncio
import discord
from discord.ext import commands
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import logging
import os
from dotenv import load_dotenv

# Import your config for channel IDs used here
import config

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
# ANTI-NUKE LOGIC (This is separate from leaderboards and can stay here)
# =================================================================================
# This could also be moved into its own 'SecurityCog' in the future.
BAN_THRESHOLD = 2
KICK_THRESHOLD = 2
DELETE_THRESHOLD = 2
TIME_FRAME = timedelta(minutes=5)
action_tracker = defaultdict(list)


async def check_actions(user, action_type, threshold):
    """Checks if a user has exceeded an action threshold in a given time frame."""
    now = datetime.now(timezone.utc)
    # Filter out old actions
    action_tracker[action_type] = [action for action in action_tracker[action_type] if now - action[1] < TIME_FRAME]
    # Add the new action
    action_tracker[action_type].append((user, now))
    # Count actions by the specific user
    user_actions = [action for action in action_tracker[action_type] if action[0] == user]
    return len(user_actions) >= threshold


@bot.event
async def on_member_ban(guild, user):
    async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.ban):
        if entry.target.id == user.id:
            logging.info(f"{entry.user} banned {user.name}")
            if await check_actions(entry.user, "ban", BAN_THRESHOLD):
                logging.warning(f"{entry.user} exceeded ban threshold.")
                await guild.ban(entry.user, reason="Exceeded ban threshold")
                channel = bot.get_channel(config.GENERAL_CHANNEL_ID)
                if channel:
                    await channel.send(
                        f"{entry.user.mention} was banned for suspicious activity! RIP BOZO! <:PogO:949833186689568768>")


@bot.event
async def on_member_remove(member):
    # This specifically checks for kicks, as bans are handled above
    async for entry in member.guild.audit_logs(limit=1, action=discord.AuditLogAction.kick):
        if entry.target.id == member.id:
            logging.info(f"{entry.user} kicked {member.name}")
            if await check_actions(entry.user, "kick", KICK_THRESHOLD):
                logging.warning(f"{entry.user} exceeded kick threshold.")
                await member.guild.ban(entry.user, reason="Exceeded kick threshold")
                channel = bot.get_channel(config.GENERAL_CHANNEL_ID)
                if channel:
                    await channel.send(
                        f"{entry.user.mention} was banned for suspicious activity! RIP BOZO! <:PogO:949833186689568768>")


@bot.event
async def on_guild_channel_delete(channel):
    async for entry in channel.guild.audit_logs(limit=1, action=discord.AuditLogAction.channel_delete):
        if entry.target.id == channel.id:
            logging.info(f"{entry.user} deleted channel {channel.name}")
            if await check_actions(entry.user, "delete", DELETE_THRESHOLD):
                logging.warning(f"{entry.user} exceeded delete threshold.")
                await channel.guild.ban(entry.user, reason="Exceeded delete threshold")
                alert_channel = bot.get_channel(config.GENERAL_CHANNEL_ID)
                if alert_channel:
                    await alert_channel.send(
                        f"{entry.user.mention} was banned for suspicious activity! RIP BOZO! <:PogO:949833186689568768>")


# =================================================================================
# GENERAL EVENTS & COMMANDS (Also fine to keep here)
# =================================================================================
# This could also be moved into its own 'FunCog' or 'GeneralCog' in the future.
@bot.event
async def on_ready():
    """Called when the bot is connected and ready."""
    logging.info(f"Logged in as {bot.user.name} ({bot.user.id})")
    print(f"Logged in as {bot.user.name}")
    print("------")


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
        logging.info("Loading leaderboard_cog...")
        await bot.load_extension("cogs.leaderboard_cog")
        logging.info("leaderboard_cog loaded successfully.")
    except Exception as e:
        logging.critical(f"Failed to load leaderboard_cog: {e}", exc_info=True)
        # You might want to stop the bot if a critical cog fails to load
        # await bot.close()
        # return

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
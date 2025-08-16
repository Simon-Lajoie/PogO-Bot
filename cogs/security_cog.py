# cogs/security_cog.py

import discord
from discord.ext import commands
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import logging
import config

class SecurityCog(commands.Cog):
    """A cog for handling server security and anti-nuke features."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # These constants and the tracker are now instance variables
        self.ban_threshold = 2
        self.kick_threshold = 2
        self.delete_threshold = 2
        self.time_frame = timedelta(minutes=5)
        self.action_tracker = defaultdict(list)

    async def _check_actions(self, user, action_type, threshold):
        """
        Checks if a user has exceeded an action threshold in a given time frame.
        This is now a helper method of the class.
        """
        now = datetime.now(timezone.utc)
        # Filter out old actions
        self.action_tracker[action_type] = [
            action for action in self.action_tracker[action_type] if now - action[1] < self.time_frame
        ]
        # Add the new action
        self.action_tracker[action_type].append((user, now))
        # Count actions by the specific user
        user_actions = [action for action in self.action_tracker[action_type] if action[0] == user]
        return len(user_actions) >= threshold

    # Use @commands.Cog.listener() decorator for events inside a cog
    @commands.Cog.listener()
    async def on_member_ban(self, guild, user):
        async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.ban):
            if entry.target.id == user.id:
                logging.info(f"{entry.user} banned {user.name}")
                if await self._check_actions(entry.user, "ban", self.ban_threshold):
                    logging.warning(f"{entry.user} exceeded ban threshold.")
                    await guild.ban(entry.user, reason="Exceeded ban threshold")
                    # Use self.bot to get the channel
                    channel = self.bot.get_channel(config.GENERAL_CHANNEL_ID)
                    if channel:
                        await channel.send(
                            f"{entry.user.mention} was banned for suspicious activity! RIP BOZO! <:PogO:949833186689568768>")

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        # This specifically checks for kicks
        async for entry in member.guild.audit_logs(limit=1, action=discord.AuditLogAction.kick):
            if entry.target.id == member.id:
                logging.info(f"{entry.user} kicked {member.name}")
                if await self._check_actions(entry.user, "kick", self.kick_threshold):
                    logging.warning(f"{entry.user} exceeded kick threshold.")
                    await member.guild.ban(entry.user, reason="Exceeded kick threshold")
                    channel = self.bot.get_channel(config.GENERAL_CHANNEL_ID)
                    if channel:
                        await channel.send(
                            f"{entry.user.mention} was banned for suspicious activity! RIP BOZO! <:PogO:949833186689568768>")

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        async for entry in channel.guild.audit_logs(limit=1, action=discord.AuditLogAction.channel_delete):
            if entry.target.id == channel.id:
                logging.info(f"{entry.user} deleted channel {channel.name}")
                if await self._check_actions(entry.user, "delete", self.delete_threshold):
                    logging.warning(f"{entry.user} exceeded delete threshold.")
                    await channel.guild.ban(entry.user, reason="Exceeded delete threshold")
                    alert_channel = self.bot.get_channel(config.GENERAL_CHANNEL_ID)
                    if alert_channel:
                        await alert_channel.send(
                            f"{entry.user.mention} was banned for suspicious activity! RIP BOZO! <:PogO:949833186689568768>")

# This setup function is required for the bot to load the cog
async def setup(bot: commands.Bot):
    await bot.add_cog(SecurityCog(bot))
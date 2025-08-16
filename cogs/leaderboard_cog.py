# cogs/leaderboard_cog.py

import discord
from discord.ext import commands, tasks
import asyncio
import logging
import random
from datetime import datetime, timedelta

from utils import ImageGenerator, RiotAPIClient
import config
import itertools

class LeaderboardCog(commands.Cog):
    """A cog to manage and display LoL and TFT leaderboards."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.image_generator = ImageGenerator(font_path=config.FONT_PATH)
        self.tasks_started = False
        self.summoner_batch_cycler = None

        tft_api_key = self.bot.tft_api_key
        lol_api_key = self.bot.lol_api_key

        self.leaderboards = {
            "TFT": {
                "client": RiotAPIClient(tft_api_key, config.REGION),
                "channel_id": config.TFT_LEADERBOARD_CHANNEL_ID,
                "background_path": config.TFT_BACKGROUND_PATH,
                "queue_type": config.TFT_QUEUE_TYPE,
                "get_summoner_id_func": config.tft_summoner_ids.get,
                "current_rankings": [],
                "previous_rankings": [],
                "image_message": None,
                "timer_message": None,
                "next_update_time": None,
                "last_displayed_text": "",
                "lock": asyncio.Lock()
            },
            "LoL": {
                "client": RiotAPIClient(lol_api_key, config.REGION),
                "channel_id": config.LOL_LEADERBOARD_CHANNEL_ID,
                "background_path": config.LOL_BACKGROUND_PATH,
                "queue_type": config.LOL_QUEUE_TYPE,
                "get_summoner_id_func": config.lol_summoner_ids.get,
                "current_rankings": [],
                "previous_rankings": [],
                "image_message": None,
                "timer_message": None,
                "next_update_time": None,
                "last_displayed_text": "",
                "lock": asyncio.Lock()
            }
        }

    @commands.Cog.listener()
    async def on_ready(self):
        """Runs once the bot is ready. Performs initial setup."""
        if not self.tasks_started:
            # --- SETUP THE ROLLING BATCHES ---
            all_summoners = config.summoner_names_list[:]
            random.shuffle(all_summoners)
            batches = [all_summoners[i:i + config.API_BATCH_SIZE] for i in
                       range(0, len(all_summoners), config.API_BATCH_SIZE)]
            self.summoner_batch_cycler = itertools.cycle(batches)

            logging.info("Bot is ready. Cleaning up old leaderboard messages...")
            await asyncio.gather(
                self._cleanup_channel("TFT"),
                self._cleanup_channel("LoL")
            )

            logging.info("Performing initial full data fetch for leaderboards...")
            # --- USE A NEW ONE-TIME FULL FETCH FUNCTION ---
            await self._initial_full_fetch()

            logging.info("Starting regular background tasks for leaderboards.")
            self.fetcher_task.start()
            self.updater_task.start()
            self.countdown_task.start()
            self.tasks_started = True

    # --- ONE-TIME FULL FETCH FOR STARTUP ---
    async def _initial_full_fetch(self):
        """Fetches data for ALL players once on startup."""
        all_summoners = config.summoner_names_list[:]
        # We can process all batches in parallel on startup for speed
        all_batches = [all_summoners[i:i + config.API_BATCH_SIZE] for i in
                       range(0, len(all_summoners), config.API_BATCH_SIZE)]

        tasks = []
        for batch in all_batches:
            tasks.append(self._fetch_and_update_batch("TFT", batch))
            tasks.append(self._fetch_and_update_batch("LoL", batch))

        await asyncio.gather(*tasks)
        logging.info("Initial full fetch completed.")

    # --- HELPER FUNCTION FOR CLEANUP ---
    async def _cleanup_channel(self, game_type: str):
        """Deletes any messages sent by the bot in the leaderboard channel."""
        lb = self.leaderboards[game_type]
        try:
            channel = self.bot.get_channel(lb["channel_id"])
            if not channel:
                logging.error(f"[{game_type}] Cannot clean channel {lb['channel_id']}: Not found.")
                return

            # Fetch last 5 messages and delete any that are from our bot
            async for message in channel.history(limit=5):
                if message.author.id == self.bot.user.id:
                    await message.delete()
                    logging.info(f"[{game_type}] Deleted old bot message {message.id}")
        except discord.Forbidden:
            logging.error(f"[{game_type}] Missing permissions to delete messages in channel {lb['channel_id']}.")
        except Exception as e:
            logging.error(f"[{game_type}] Error during channel cleanup: {e}")

    def cog_unload(self):
        """Gracefully stop all background tasks."""
        self.fetcher_task.cancel()
        self.updater_task.cancel()
        self.countdown_task.cancel()

    # --- Data Fetching Loop ---
    @tasks.loop(seconds=config.RANK_FETCH_INTERVAL_SECONDS)
    async def fetcher_task(self):
        """Periodically fetches ONE BATCH of player ranks to create a rolling update."""
        if self.summoner_batch_cycler is None:
            return # Don't run if not initialized yet

        # Get the next batch from our infinite cycler
        batch_to_fetch = next(self.summoner_batch_cycler)
        logging.info(f"Fetching rolling update for batch: {batch_to_fetch}")

        # Process this single batch for both games
        await asyncio.gather(
            self._fetch_and_update_batch("TFT", batch_to_fetch),
            self._fetch_and_update_batch("LoL", batch_to_fetch)
        )

    async def _fetch_and_update_batch(self, game_type: str, summoner_batch: list):
        """Helper to fetch and process a batch of summoners for a specific game type."""
        lb = self.leaderboards[game_type]

        async def process_summoner(name):
            # ... (this inner function does not need to be changed) ...
            puuid = lb["get_summoner_id_func"](name)
            if not puuid:
                return None
            stats = await lb["client"].get_ranked_stats_by_puuid(puuid, game_type)
            if stats is None:
                return None
            ranked_stats = next((s for s in stats if s.get("queueType") == lb["queue_type"]), None)
            if ranked_stats:
                tier = ranked_stats.get("tier", "UNRANKED")
                rank = ranked_stats.get("rank", "")
                lp = ranked_stats.get("leaguePoints", 0)
                tier_division = f"{tier} {rank}"
                rank_value = config.ranks.get(tier_division, 0) * 100 + lp
                tier_division_lp = f"{tier} {rank} {lp} LP"
                if tier in ["MASTER", "GRANDMASTER", "CHALLENGER"]:
                    tier_division_lp = f"{tier} {lp} LP"
                return name, rank_value, lp, tier, tier_division_lp
            else:
                return name, 0, 0, "UNRANKED", "UNRANKED"

        # Fetch all summoners in the batch concurrently
        results = await asyncio.gather(*(process_summoner(name) for name in summoner_batch))

        # Filter out any failed lookups
        batch_rankings = [r for r in results if r is not None]

        # Log the result for each summoner in the processed batch
        for ranking_data in batch_rankings:
            name, _, _, _, tier_division_lp = ranking_data
            logging.info(f"[{game_type}] Fetched: {name:<16} -> {tier_division_lp}")
        # The ":<16" part adds padding to the name for clean alignment in the logs.

        # Update the shared list under a lock
        async with lb["lock"]:
            rankings_map = {ranking[0]: ranking for ranking in lb["current_rankings"]}

            for ranking in batch_rankings:
                summoner_name = ranking[0]
                rankings_map[summoner_name] = ranking

            updated_list = list(rankings_map.values())
            updated_list.sort(key=lambda x: x[1], reverse=True)

            lb["current_rankings"] = updated_list

            logging.info(f"[{game_type}] Batch applied. Total players now: {len(lb['current_rankings'])}")

    # --- Leaderboard Image Updater Loop ---
    @tasks.loop(seconds=config.LEADERBOARD_UPDATE_INTERVAL_SECONDS)
    async def updater_task(self):
        """Periodically calls the main display update function."""
        await asyncio.gather(
            self._update_leaderboard_display("TFT"),
            self._update_leaderboard_display("LoL")
        )

    @updater_task.before_loop
    async def before_updater(self):
        """Waits until the bot is ready before the first run of the task."""
        await self.bot.wait_until_ready()

    @tasks.loop(seconds=1.0)
    async def countdown_task(self):
        """Updates the countdown timer messages every second."""
        for game_type, lb in self.leaderboards.items():
            if not lb["timer_message"] or not lb["next_update_time"]:
                continue  # Nothing to count down for yet

            time_remaining = lb["next_update_time"] - datetime.now()
            seconds_left = max(0, int(time_remaining.total_seconds()))

            new_text = self._format_countdown_text(seconds_left)

            if new_text and new_text != lb["last_displayed_text"]:
                try:
                    await lb["timer_message"].edit(content=new_text)
                    lb["last_displayed_text"] = new_text
                except discord.NotFound:
                    logging.warning(f"[{game_type}] Timer message not found, will be recreated on next update.")
                    lb["timer_message"] = None  # Clear message so it gets recreated
                except discord.HTTPException as e:
                    logging.error(f"[{game_type}] Failed to edit timer message: {e}")

    async def _update_leaderboard_display(self, game_type: str):
        """Fetches data, generates image, and updates Discord messages."""
        lb = self.leaderboards[game_type]

        async with lb["lock"]:
            # ... (Data preparation logic is unchanged) ...
            current_rankings = lb["current_rankings"][:]
            if not current_rankings:
                logging.warning(f"[{game_type}] No rankings available to generate image.")
                return
            await self._check_and_notify_rank_changes(game_type, current_rankings)
            lb["previous_rankings"] = current_rankings[:]

        # ... (Image generation is unchanged) ...
        image_buffer = self.image_generator.generate_leaderboard_image(current_rankings, lb["background_path"])
        if image_buffer is None:
            logging.error(f"[{game_type}] Failed to generate leaderboard image.")
            return

        try:
            channel = self.bot.get_channel(lb["channel_id"])
            if not channel:
                logging.error(f"[{game_type}] Channel {lb['channel_id']} not found.")
                return

            # --- MESSAGE HANDLING LOGIC ---
            # 1. Delete old messages
            if lb["timer_message"]: await lb["timer_message"].delete()
            if lb["image_message"]: await lb["image_message"].delete()

            # 2. Post new messages (Timer first, then Image for better order)
            update_interval = config.LEADERBOARD_UPDATE_INTERVAL_SECONDS
            lb["next_update_time"] = datetime.now() + timedelta(seconds=update_interval)
            initial_timer_text = self._format_countdown_text(update_interval)

            new_timer_message = await channel.send(content=initial_timer_text)
            new_image_message = await channel.send(file=discord.File(image_buffer, filename=f"{game_type}_leaderboard.png")
            )

            # 3. Store the new message objects for the next cycle
            lb["timer_message"] = new_timer_message
            lb["image_message"] = new_image_message
            lb["last_displayed_text"] = initial_timer_text

            logging.info(f"[{game_type}] Successfully posted new leaderboard.")

        except discord.NotFound:
            logging.warning(f"[{game_type}] An old message was already deleted. Resetting.")
            lb["timer_message"], lb["image_message"] = None, None  # Reset state
        except Exception as e:
            logging.error(f"[{game_type}] An error occurred during display update: {e}", exc_info=True)

    # --- Helper function to format countdown text ---
    def _format_countdown_text(self, seconds: int) -> str | None:
        """Formats the remaining time into a user-friendly string."""
        if seconds <= 0:
            return "Updating now..."
        if seconds <= 10:
            return f"Next update in: {seconds} seconds"

        minutes = (seconds + 59) // 60  # Round up to the nearest minute
        if minutes == 1:
            return "Next update in: 1 minute"
        else:
            return f"Next update in: {minutes} minutes"

    async def _check_and_notify_rank_changes(self, game_type: str, new_rankings: list):
        """Compares old and new rankings and sends a message if there's a change."""
        lb = self.leaderboards[game_type]
        previous_rankings = lb["previous_rankings"]

        # Only compare if we have a previous state to compare to
        if not previous_rankings:
            # The calling function will set the initial state. Nothing to do here.
            return

        # Compare the top players (e.g., top 4 or 5)
        comparison_range = min(4, len(new_rankings),
                               len(previous_rankings))  # Changed to 4 as per your original request
        for i in range(comparison_range):
            new_player = new_rankings[i][0]
            old_player = previous_rankings[i][0]

            if new_player != old_player:
                old_player_indices = [idx for idx, p in enumerate(previous_rankings) if p[0] == new_player]
                if old_player_indices and old_player_indices[0] > i:
                    logging.info(
                        f"[{game_type}] Rank change detected! {new_player} overtook {old_player} for rank {i + 1}.")
                    await self._send_rank_change_alert(game_type, new_player, old_player, i + 1)

    def _get_random_alert_message(self, game_type: str, new_summoner_name: str, old_summoner_name: str,
                                  position: int) -> str:
        """Generates a randomized, fun message for a rank change."""
        new_summoner = config.discord_ids.get(new_summoner_name, new_summoner_name)
        old_summoner = config.discord_ids.get(old_summoner_name, old_summoner_name)

        messages = [
            f"{new_summoner} just pulled off a spectacular heist {config.emoji_codes.get('business', '')}, ousting {old_summoner} from position {position} like a sneaky mastermind {config.emoji_codes.get('cathiago', '')}!",
            f"Yeah.. {config.emoji_codes.get('sadge', '')} I'm sorry to announce {new_summoner} has dethroned {old_summoner} from position {position}. Don't ask me how. {config.emoji_codes.get('pepeshrug', '')}. Surely this is deserved. {config.emoji_codes.get('scam', '')}",
            f"{config.emoji_codes.get('pogo', '')} {new_summoner} has kicked {old_summoner} from position {position}. Did you really expect me to praise you for that ? Take this instead: {config.emoji_codes.get('pantsgrab', '')}",
            f"{config.emoji_codes.get('pogo', '')} ALERT! ALERT! {config.emoji_codes.get('pogo', '')} {new_summoner} has executed a flawless takedown, banishing {old_summoner} from position {position}. It's time to rally the troops and show our support to {new_summoner} by showering them with a barrage of {config.emoji_codes.get('pogo', '')}.",
            f"{config.emoji_codes.get('pogo', '')} {new_summoner} has decisively toppled {old_summoner} from position {position}, leaving no doubt of their supremacy. {config.emoji_codes.get('cathiago', '')}",
            f"NAHHHH THIS {new_summoner} PLAYER MIGHT JUST THE THE BEST PLAYER IN THE WORLD.{config.emoji_codes.get('dongerj', '')} HE LITERALLY JUST TOOK POSITION {position} FROM {old_summoner} JUST LIKE THAT ? {config.emoji_codes.get('huh', '')} IT'S WAY TOO FREE. {new_summoner} IS JUST BUILT DIFFERENT! {config.emoji_codes.get('pepestrong', '')}",
            f"{new_summoner} --> {position} {config.emoji_codes.get('pogo', '')} {old_summoner} --> {config.emoji_codes.get('deadge', '')}",
            f"{config.emoji_codes.get('pogo', '')} BREAKING NEWS! BREAKING NEWS! {config.emoji_codes.get('pogo', '')} A major upset has just occurred. {new_summoner} has just dethroned {old_summoner} from position {position}. It's a shocking turn of events, a stunning upset, a colossal blunder. {config.emoji_codes.get('aycaramba', '')}",
            f"{config.emoji_codes.get('pogo', '')} Hold on as {new_summoner} shakes things up and steals the glory from {old_summoner} at position {position}. {old_summoner} has just been humiliated, disgraced, destroyed. {config.emoji_codes.get('huh', '')} They have been reduced to nothing. {config.emoji_codes.get('huh', '')} They are now forgotten. {config.emoji_codes.get('huh', '')}",
            f"{config.emoji_codes.get('pogo', '')} Ladies and gentlemen, gather 'round! Witness the rise of {new_summoner} as they conquer position {position} and send {old_summoner} packing! {config.emoji_codes.get('pantsgrab', '')} It's like watching a legendary underdog story unfold before our eyes. {config.emoji_codes.get('business', '')}",
            f"{config.emoji_codes.get('pogo', '')} Hey {old_summoner}, guess who just took your spot at position {position}? {config.emoji_codes.get('scam', '')} Oh right, it's {new_summoner}! {config.emoji_codes.get('deadge', '')} {config.emoji_codes.get('aycaramba', '')} Looks like someone could use a lesson or two... Get ready to learn TFT buddy. {config.emoji_codes.get('pogo', '')}",
            f"{config.emoji_codes.get('pogo', '')} Brace yourselves for the rise of {new_summoner}! They've outshined {old_summoner} at position {position}. {config.emoji_codes.get('peepoflor', '')} Meanwhile, {old_summoner} seems to be lost in the shadows of defeat. {config.emoji_codes.get('sadge', '')} Better luck next time, {old_summoner}, you'll need it! {config.emoji_codes.get('pogo', '')}",
            f"{config.emoji_codes.get('pogo', '')} Brace yourselves, ladies and gentlemen, because we have a new champion in town! {config.emoji_codes.get('pepestrong', '')} {new_summoner} has just obliterated {old_summoner} from position {position}, leaving no room for doubt. It's a devastating blow, a crushing defeat, a humiliating loss. {config.emoji_codes.get('deadge', '')}",
            f"{config.emoji_codes.get('pogo', '')} Hold on to your seats, folks, because we have a wild ride ahead of us! {config.emoji_codes.get('pogo', '')} {new_summoner} has just pulled off a miraculous feat, snatching position {position} from {old_summoner} in a nail-biting showdown.",
            f"{config.emoji_codes.get('pogo', '')} Wow! Wow! Wow! {config.emoji_codes.get('pogo', '')} {new_summoner} has just outplayed {old_summoner} from position {position}, showing us all what this game is all about. {config.emoji_codes.get('yeahboi', '')} It's a dazzling show, a thrilling game, a spectacular victory. {config.emoji_codes.get('dongerj', '')}",
            f"{config.emoji_codes.get('pogo', '')} {new_summoner} has just taken position {position} from {old_summoner}. {config.emoji_codes.get('business', '')} In a cruel display of humiliation, {new_summoner} has left a message for us: This game is just all luck no skills, unlucky buddy {config.emoji_codes.get('scam', '')}",
            f"{config.emoji_codes.get('pogo', '')} OOF! {old_summoner} just got destroyed by {new_summoner}, who took position {position} from them. {config.emoji_codes.get('aycaramba', '')} Mortdog sends his regards, unlucky buddy {config.emoji_codes.get('pantsgrab', '')}",
            f"{config.emoji_codes.get('huh', '')} HUH... {old_summoner} just got outplayed by {new_summoner}, who snatched position {position} from them. Maybe you just didn’t hit this game, surely you will hit next game {config.emoji_codes.get('scam', '')} 📉",
            f"{config.emoji_codes.get('pogo', '')} What a tragedy.. Surely. {config.emoji_codes.get('pogo', '')} {old_summoner} just got annihilated by {new_summoner}, who claimed position {position} from them. Who balances this game? {config.emoji_codes.get('pepeshrug', '')} Unlucky buddy. Take this L {config.emoji_codes.get('sadge', '')}",
            f"{config.emoji_codes.get('pogo', '')} {old_summoner} just got humiliated by {new_summoner}, who kicked them from position {position}. RIP BOZO. 🤡 You won’t be missed {config.emoji_codes.get('deadge', '')}",
            f"{old_summoner} got yeeted from {position} by {new_summoner}! {config.emoji_codes.get('pogo', '')} Take this L. {config.emoji_codes.get('pantsgrab', '')}",
            f"{new_summoner} humiliated {old_summoner} for {position}! {config.emoji_codes.get('absolutecinema', '')} Get lost, noob. {config.emoji_codes.get('pogo', '')}",
            f"{new_summoner} clowning {old_summoner} at {position}! {config.emoji_codes.get('pogo', '')} Bald move, bro. {config.emoji_codes.get('wallabyBald', '')}",
            f"{new_summoner} rolled {old_summoner} for {position}! {config.emoji_codes.get('pogo', '')} You're washed up. {config.emoji_codes.get('pepestrong', '')}",
            f"{old_summoner} got scammed by {new_summoner} at {position}! {config.emoji_codes.get('scam', '')} Unlucky, buddy. {config.emoji_codes.get('pogo', '')}",
            f"{new_summoner} dunked {old_summoner} from {position}! {config.emoji_codes.get('pogo', '')} You're irrelevant now. {config.emoji_codes.get('deadge', '')}",
            f"{old_summoner} got smoked by {new_summoner} at {position}! {config.emoji_codes.get('pogo', '')} What was that? {config.emoji_codes.get('huh', '')}",
            f"{new_summoner} toppled {old_summoner} at {position}! {config.emoji_codes.get('dongerj', '')} You're done for. {config.emoji_codes.get('pogo', '')}",
            f"{old_summoner} got kicked from {position} by {new_summoner}! {config.emoji_codes.get('pogo', '')} See ya, bud. {config.emoji_codes.get('salute', '')}",
            f"{new_summoner} crushed {old_summoner} at {position}! {config.emoji_codes.get('pogo', '')} It's over for you. {config.emoji_codes.get('joever', '')}",
            f"{new_summoner} outplayed {old_summoner} at {position}! {config.emoji_codes.get('icant', '')} Can't believe you choked. {config.emoji_codes.get('pogo', '')}",
            f"{new_summoner} snatched {position} from {old_summoner}! {config.emoji_codes.get('xdd', '')} You're irrelevant now. {config.emoji_codes.get('pogo', '')}",
            f"{old_summoner} got bodied by {new_summoner} at {position}! {config.emoji_codes.get('pogo', '')} What's your excuse? {config.emoji_codes.get('yamesy', '')}",
            f"{new_summoner} sent {old_summoner} packing from {position}! {config.emoji_codes.get('barack', '')} You're history. {config.emoji_codes.get('pogo', '')}",
            f"{old_summoner} got laughed off {position} by {new_summoner}! {config.emoji_codes.get('hah', '')} Pathetic showing. {config.emoji_codes.get('pogo', '')}",
            f"{new_summoner} slapped {old_summoner} from {position}! {config.emoji_codes.get('pogo', '')} Here's your flowers. {config.emoji_codes.get('peepoflor', '')}",
            f"{new_summoner} owned {old_summoner} at {position}! {config.emoji_codes.get('business', '')} You're a ghost now. {config.emoji_codes.get('pogo', '')}",
            f"{old_summoner} got wrecked by {new_summoner} at {position}! {config.emoji_codes.get('pogo', '')} Take this L. {config.emoji_codes.get('sadge', '')}",
            f"{new_summoner} erased {old_summoner} from {position}! {config.emoji_codes.get('pogo', '')} Really, dude? {config.emoji_codes.get('buffet', '')}",
            f"{new_summoner} dethroned {old_summoner} at {position}! {config.emoji_codes.get('pogo', '')} Smirky victory. {config.emoji_codes.get('cathiago', '')}",
            f"{old_summoner} got outplayed by {new_summoner} at {position}! {config.emoji_codes.get('yeahboi', '')} You're finished. {config.emoji_codes.get('pogo', '')}",
            f"{new_summoner} annihilated {old_summoner} at {position}! {config.emoji_codes.get('pogo', '')} Total disaster. {config.emoji_codes.get('aycaramba', '')}",
            f"{old_summoner} got clowned by {new_summoner} at {position}! {config.emoji_codes.get('pogo', '')} You're irrelevant. {config.emoji_codes.get('pepeshrug', '')}",
            f"{new_summoner} crushed {old_summoner} from {position}! {config.emoji_codes.get('pogo', '')} RIP, you're gone. {config.emoji_codes.get('deadge', '')}"
        ]
        return f"**{game_type.upper()}**: " + random.choice(messages)

    async def _send_rank_change_alert(self, game_type: str, new_summoner: str, old_summoner: str, position: int):
        """Sends a randomized, fun message to the general channel about a rank change."""
        channel = self.bot.get_channel(config.GENERAL_CHANNEL_ID)
        if not channel:
            logging.error("General channel for alerts not found.")
            return

        message = self._get_random_alert_message(game_type, new_summoner, old_summoner, position)

        try:
            await channel.send(message)
        except discord.HTTPException as e:
            logging.error(f"Failed to send rank change alert: {e}")


# This setup function is required for the bot to load the cog
async def setup(bot: commands.Bot):
    await bot.add_cog(LeaderboardCog(bot))
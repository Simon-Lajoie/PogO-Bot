# PogO-Bot
PogO Bot is a Discord bot mainly for Riot Games related content. It has several features to enhance Discord server experience.

## Features
- **LoL & TFT Ranked Leaderboard**: PogO Bot uses the Pillow library to generate and update a TFT ranked leaderboard for the users in your Discord server every 6 minutes. The bot retrieves summoner information and ranked stats for each person on the list through Riot Games API calls. PogO Bot uses a custom algorithm to generate a score for each player based on their ranked data, allowing them to be sorted by rank on the leaderboard. The bot gathers data every minute instead of all at once to spread API calls.

- **Top 4 Spot Notifications**: The top 4 spots on the leaderboard are highly coveted. Whenever a player overtakes another player in the top 4, the bot will post a humorous message in the general chat to praise or roast the players involved.

- **Custom Emotes**: PogO Bot has several typing commands that can replace certain words with custom emotes. For example, typing “PogO” will replace your message with a PogO emote.

## Example of Teamfight Tactics leaderboard by PogO Bot
![image](https://github.com/Simon-Lajoie/PogO-Bot/assets/123536951/4bc85e0e-860a-47eb-93ef-81fe3edbcca7)

## Example of League of Legends leaderboard by PogO Bot
![image](https://github.com/Simon-Lajoie/PogO-Bot/assets/123536951/98d72a47-e4dd-4f2e-882e-5e4217f74364)

## Usage
- Currently, PogO Bot is only available for use in a private Discord server community and is not open to other Discord servers.

## Commands
- PogO: Replaces your message with a PogO emote.
- T PogO: Replaces your message with a T PogO emote.

## Technologies
* Python
* Libraries: Discord, Pillow

## Author
* Simon Lajoie

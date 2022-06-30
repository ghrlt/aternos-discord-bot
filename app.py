from python_aternos import Client

import discord
from discord.ext import commands

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(
	command_prefix=commands.when_mentioned_or('aternos!'),
	description="Obtain your Aternos servers status and control them!",
	intents=intents
)




bot.run(os.env.get('token'))
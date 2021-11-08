import discord
from discord.ext import commands

bot = commands.Bot(command_prefix="!", description="")

@bot.event
async def on_ready():
  bot.load_extension("cogs.music")

bot.run("token")

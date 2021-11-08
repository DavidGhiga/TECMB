import discord
from discord.ext import commands

bot = commands.Bot(command_prefix="!", description="")

@bot.event
async def on_ready():
  bot.load_extension("cogs.music")

bot.run("ODk3NDk3OTAxNTY2MTYwOTA2.YWWiDg.v0-H91vUWhUQw0uz-t_L4TROKZg")

"""
Copyright 2020 ethanolchik (class Ethan.#0027)

You may not redistribute a copy of this code without granted permission.
If redistribution was granted, you shall not charge for the code.
"""
import math
import re
from urllib.parse import quote

import discord
import lavalink
from discord.ext import commands, tasks


# ----- define constants ----- #
url_rx = re.compile("https?:\\/\\/(?:www\\.)?.+")
EMBED_COLOR = 0xFFFFFF
DEL_AFTER_TIME = 5
# ---------------------------- #
print(lavalink.__version__)

class LavalinkVoiceClient(discord.VoiceClient):
    """
    This is the preferred way to handle external voice sending
    This client will be created via a cls in the connect method of the channel
    see the following documentation:
    https://discordpy.readthedocs.io/en/latest/api.html#voiceprotocol
    """

    def __init__(self, client: discord.Client, channel: discord.abc.Connectable):
        self.client = client
        self.channel = channel
        # ensure there exists a client already
        if hasattr(self.client, 'lavalink'):
            self.lavalink = self.client.lavalink
        else:
            self.client.lavalink = lavalink.Client(client.user.id)
            self.client.lavalink.add_node(
                    'localhost',
                    2333,
                    'youshallnotpass',
                    'eu',
                    'default-node')
            self.lavalink = self.client.lavalink

    async def on_voice_server_update(self, data):
        # the data needs to be transformed before being handed down to
        # voice_update_handler
        lavalink_data = {
                't': 'VOICE_SERVER_UPDATE',
                'd': data
                }
        await self.lavalink.voice_update_handler(lavalink_data)

    async def on_voice_state_update(self, data):
        # the data needs to be transformed before being handed down to
        # voice_update_handler
        lavalink_data = {
                't': 'VOICE_STATE_UPDATE',
                'd': data
                }
        await self.lavalink.voice_update_handler(lavalink_data)

    async def connect(self, *, timeout: float, reconnect: bool) -> None:
        """
        Connect the bot to the voice channel and create a player_manager
        if it doesn't exist yet.
        """
        # ensure there is a player_manager when creating a new voice_client
        self.lavalink.player_manager.create(guild_id=self.channel.guild.id)
        await self.channel.guild.change_voice_state(channel=self.channel)

    async def disconnect(self, *, force: bool) -> None:
        """
        Handles the disconnect.
        Cleans up running player and leaves the voice client.
        """
        player = self.lavalink.player_manager.get(self.channel.guild.id)

        # no need to disconnect if we are not connected
        if not force and not player.is_connected:
            return

        # None means disconnect
        await self.channel.guild.change_voice_state(channel=None)

        # update the channel_id of the player to None
        # this must be done because the on_voice_state_update that
        # would set channel_id to None doesn't get dispatched after the 
        # disconnect
        player.channel_id = None
        self.cleanup()

class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.paginator_queue = dict()
        self.open_menus = dict()
        bot.open_menus = self.open_menus
        # This ensures the client isn't overwritten during cog reloads.
        if not hasattr(bot, 'lavalink'):  # This ensures the client isn't overwritten during cog reloads.
            bot.lavalink = lavalink.Client(bot.user.id)
            bot.lavalink.add_node('127.0.0.1', 2333, 'youshallnotpass', 'eu',
                                  'default-node')  # Host, Port, Password, Region, Name
            bot.add_listener(bot.lavalink.voice_update_handler, 'on_socket_response')

        bot.lavalink.add_event_hook(self.track_hook)

    async def track_hook(self, event):
        if isinstance(event, lavalink.events.QueueEndEvent):
            guild_id = int(event.player.guild_id)
            await self.connect_to(guild_id, None)

    def cog_unload(self):
        """ Cog unload handler. This removes any event hooks that were registered. """
        self.bot.lavalink._event_hooks.clear()

    async def cog_before_invoke(self, ctx):
        """ Command before-invoke handler. """
        guild_check = ctx.guild is not None

        if guild_check:
            await self.ensure_voice(ctx)

        return guild_check
    
    async def connect_to(self, guild_id: int, channel_id: str):
        """ Connects to the given voicechannel ID. A channel_id of `None` means disconnect. """
        ws = self.bot._connection._get_websocket(guild_id)
        await ws.voice_state(str(guild_id), channel_id)

    @staticmethod
    def rq_check(ctx):
        return (
            ctx.author.id
            == ctx.bot.lavalink.player_manager.get(ctx.guild.id).current.requester
        )

    @commands.command(aliases=["p"])
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def play(self, ctx, *, query: str):
        """ Searches and plays a song from a given query. """
        player = self.bot.lavalink.player_manager.get(ctx.guild.id)

        query = query.strip("<>")

        if not url_rx.match(query):
            query = f"ytsearch:{query}"

        results = await player.node.get_tracks(query)

        if not results or not results["tracks"]:
            return await ctx.send("Nothing found!", delete_after=DEL_AFTER_TIME)

        embed = discord.Embed(color=EMBED_COLOR)

        if results["loadType"] == "PLAYLIST_LOADED":
            tracks = results["tracks"]

            for track in tracks:
                player.add(requester=ctx.author.id, track=track)

                
            await ctx.send(f'added {results["playlistInfo"]["name"]} to the queue.')
        else:
            track = results["tracks"][0]
            await ctx.send(f"added {track['info']['title']} to the queue.")
            player.add(requester=ctx.author.id, track=track)

        if not player.is_playing:
            await player.play()

    @commands.command(aliases=["forceskip"])
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def skip(self, ctx):
        """ Skips the current track. """
        player = self.bot.lavalink.player_manager.get(ctx.guild.id)

        if not player.is_playing:
            return await ctx.send(
                f"Not playing.", delete_after=DEL_AFTER_TIME
            )

        await player.skip()
        embed = discord.Embed(title="Skipped.", color=EMBED_COLOR)
        await ctx.send(embed=embed, delete_after=DEL_AFTER_TIME)

    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def stop(self, ctx):
        """ Stops the player and clears its queue. """
        player = self.bot.lavalink.player_manager.get(ctx.guild.id)

        if not player.is_playing:
            return await ctx.send(
                f"Not playing.", delete_after=DEL_AFTER_TIME
            )

        player.queue.clear()
        await player.stop()
        embed = discord.Embed(
            title=f"Stopped. (Queue cleared)", color=EMBED_COLOR
        )
        await ctx.send(embed=embed, delete_after=DEL_AFTER_TIME)

    @commands.command(aliases=["q"])
    @commands.cooldown(1, 2, commands.BucketType.user)
    async def queue(self, ctx, page: int = 1):
        """ Shows the player's queue. """
        player = self.bot.lavalink.player_manager.get(ctx.guild.id)

        if not player.queue:
            return await ctx.send(
                f"Nothing is in the queue.", delete_after=DEL_AFTER_TIME
            )

        items_per_page = 10
        pages = math.ceil(len(player.queue) / items_per_page)

        start = (page - 1) * items_per_page
        end = start + items_per_page

        queue_list = ""
        for index, track in enumerate(player.queue[start:end], start=start):
            queue_list += f"{index + 1}. [**{track.title}**]({track.uri})\n"

        embed = discord.Embed(
            colour=EMBED_COLOR,
            description=f'{len(player.queue)} {"tracks" if len(player.queue) > 1 else "track"}\n\n{queue_list}',
        )
        embed.set_footer(text=f"Viewing page {page}/{pages}")
        await ctx.send(embed=embed)

    @commands.command(aliases=["resume"])
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def pause(self, ctx):
        """ Pauses/Resumes the current track. """
        player = self.bot.lavalink.player_manager.get(ctx.guild.id)

        if not player.is_playing:
            return await ctx.send(
                f"Not playing.", delete_after=DEL_AFTER_TIME
            )

        if player.paused:
            await player.set_pause(False)
            embed = discord.Embed(title=f"Resumed", color=EMBED_COLOR)
            await ctx.send(embed=embed, delete_after=DEL_AFTER_TIME)
        else:
            await player.set_pause(True)
            embed = discord.Embed(title=f"Paused", color=EMBED_COLOR)
            await ctx.send(embed=embed, delete_after=DEL_AFTER_TIME)

    @commands.command(aliases=["loop"])
    @commands.cooldown(1, 2, commands.BucketType.user)
    async def repeat(self, ctx):
        """ Repeats the current song until the command is invoked again. """
        player = self.bot.lavalink.player_manager.get(ctx.guild.id)

        if not player.is_playing:
            embed = discord.Embed(
                title=f"Nothing playing.", color=EMBED_COLOR
            )
            return await ctx.send(embed=embed, delete_after=DEL_AFTER_TIME)

        player.repeat = not player.repeat
        embed = discord.Embed(
            title=f"Repeat "
            + ("`ON`" if player.repeat else "`OFF`"),
            color=EMBED_COLOR,
        )
        await ctx.send(embed=embed, delete_after=DEL_AFTER_TIME)

    @commands.command(aliases=["dc"])
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def disconnect(self, ctx):
        """ Disconnects the player from the voice channel and clears its queue. """
        player = self.bot.lavalink.player_manager.get(ctx.guild.id)

        if not player.is_connected:
            embed = discord.Embed(title="Not connected.", color=EMBED_COLOR)
            return await ctx.send(embed=embed, delete_after=DEL_AFTER_TIME)

        if not ctx.author.voice or (
            player.is_connected
            and ctx.author.voice.channel.id != int(player.channel_id)
        ):
            embed = discord.Embed(
                title="Please get in my voicechannel first.", color=EMBED_COLOR
            )

            return await ctx.send(embed=embed, delete_after=DEL_AFTER_TIME)

        player.queue.clear()
        await player.stop()
        await self.connect_to(ctx.guild.id, None)
        embed = discord.Embed(title=f"Disconnected", color=EMBED_COLOR)
        await ctx.send(embed=embed, delete_after=DEL_AFTER_TIME)

    async def ensure_voice(self, ctx):
        """ This check ensures that the bot and command author are in the same voicechannel. """
        player = self.bot.lavalink.player_manager.create(
            ctx.guild.id, endpoint=str(ctx.guild.region)
        )
        should_connect = ctx.command.name in ("play",)

        if not ctx.author.voice or not ctx.author.voice.channel:
            raise commands.CommandInvokeError("Join a voicechannel first.")

        if not player.is_connected:
            if not should_connect:
                raise commands.CommandInvokeError("Not connected.")

            permissions = ctx.author.voice.channel.permissions_for(ctx.me)

            if not permissions.connect or not permissions.speak:
                raise commands.CommandInvokeError(
                    "I need the `CONNECT` and `SPEAK` permissions."
                )

            player.store("channel", ctx.channel.id)
            await self.connect_to(ctx.guild.id, str(ctx.author.voice.channel.id))
        else:
            if int(player.channel_id) != ctx.author.voice.channel.id:
                raise commands.CommandInvokeError("You need to be in my voicechannel.")


def setup(bot):
    bot.add_cog(Music(bot))

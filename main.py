import discord
from discord.ext import commands
from datetime import datetime
import os

# --- CONFIGURATION ---
# We get the token from Railway's "Variables" tab later
TOKEN = os.getenv("DISCORD_TOKEN") 
SWC_ROLE_NAME = "Senior Workflow Coordinator" 

EMOJI_TO_FILE = {
    "QB": "QUARTR BATCH FILE",
    "QL": "QUARTR LIVE FILE",
    "HP": "HP FILE",
    "AB": "AIERA BATCH FILE",
    "AL": "AIERA LIVE FILE",
    "🇶": "QUARTR BATCH FILE", 
    "🇱": "QUARTR LIVE FILE",  
    "🇭": "HP FILE",          
    "🇦": "AIERA BATCH FILE", 
}
# ---------------------

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')

@bot.event
async def on_raw_reaction_add(payload):
    if payload.user_id == bot.user.id:
        return

    emoji_name = payload.emoji.name
    
    if emoji_name in EMOJI_TO_FILE:
        guild = bot.get_guild(payload.guild_id)
        if not guild: return

        reactor = guild.get_member(payload.user_id)
        if not reactor: return
        
        user_role_names = [role.name for role in reactor.roles]
        
        if SWC_ROLE_NAME not in user_role_names:
            return

        try:
            channel = bot.get_channel(payload.channel_id)
            message = await channel.fetch_message(payload.message_id)
            editor = message.author
        except:
            return

        if editor.bot:
            return

        current_unix_time = int(datetime.now().timestamp())
        time_tag = f"<t:{current_unix_time}:F>" 
        file_type = EMOJI_TO_FILE[emoji_name]

        dm_content = (
            f"Hello {editor.mention}, you have been assigned a **{file_type}** at {time_tag}. Please start on them immediately.\n\n"
            f"Reminder that if no movement is observed on your file for at least 5 minutes, and if your file is at risk of breaching TAT, SWC may REASSIGN your file without prior notice.\n\n"
            f"If you will take longer on a file, keep @Senior Workflow Coordinator properly appraised. Include your reasons."
        )

        try:
            await editor.send(dm_content)
            await message.add_reaction("✅")
        except discord.Forbidden:
            await channel.send(f"{editor.mention} ⚠️ I cannot DM you. You are assigned: **{file_type}** at {time_tag}. Please start on them immediately.")

if TOKEN:
    bot.run(TOKEN)
else:
    print("Error: DISCORD_TOKEN not found in environment variables.")

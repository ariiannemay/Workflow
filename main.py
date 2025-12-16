import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
import os
from flask import Flask
from threading import Thread

# --- KEEP ALIVE SECTION ---
app = Flask('')

@app.route('/')
def home():
    return "I am alive!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()
# ---------------------------

# --- CONFIGURATION ---
TOKEN = os.getenv("DISCORD_TOKEN") 
SWC_ROLE_NAME = "Senior Workflow Coordinator" 

# EMOJI MAPPING (For Reaction Assignments)
EMOJI_TO_FILE = {
    "QB": "QUARTR BATCH FILE",
    "QL": "QUARTR LIVE FILE",
    "HP": "HP FILE",
    "AB": "AIERA BATCH FILE",
    "AL": "AIERA LIVE FILE",
    # Unicode Fallbacks (Blue Squares)
    "🇶": "QUARTR FILE", 
    "🇭": "HP FILE",          
    "🇦": "AIERA FILE", 
}

# FILE TYPES (For Slash Command Assignments)
FILE_CHOICES = [
    app_commands.Choice(name="Aiera Live", value="AIERA LIVE FILE"),
    app_commands.Choice(name="Aiera Batch", value="AIERA BATCH FILE"),
    app_commands.Choice(name="HP File", value="HP FILE"),
    app_commands.Choice(name="Quartr Live", value="QUARTR LIVE FILE"),
    app_commands.Choice(name="Quartr Batch", value="QUARTR BATCH FILE"),
]

# --- THE QUEUE (Stored in memory) ---
# List of dictionaries: [{'user': Member, 'time': unix_timestamp}]
work_queue = []

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# --- HELPER FUNCTIONS ---
def is_swc(interaction: discord.Interaction):
    """Check if user has SWC role"""
    user_roles = [role.name for role in interaction.user.roles]
    return SWC_ROLE_NAME in user_roles

async def assign_logic(user, file_type, channel):
    """Reusable logic for sending the DM and the Public Message"""
    current_unix_time = int(datetime.now().timestamp())
    time_tag = f"<t:{current_unix_time}:F>" 
    
    # 1. THE DM CONTENT
    dm_content = (
        f"# Hello {user.mention}! You have been assigned a **{file_type}** at {time_tag}.\n\n" 
        f"## Please start on them immediately.\n\n"
        f"### REMINDERS:\n\n"
        f"- If no movement is observed on your file for at least 5 minutes, and if your file is at risk of breaching TAT, Senior Workflow Coordinator may REASSIGN your file without prior notice.\n"
        f"- If you will take longer on a file, keep the SWC properly appraised. Include your reasons and estimated TAT."
    )

    # 2. SEND DM
    try:
        await user.send(dm_content)
    except discord.Forbidden:
        await channel.send(f"{user.mention} ⚠️ I cannot DM you, but you are assigned.")

    # 3. PUBLIC CONFIRMATION (As requested)
    # <t:x:F> gives full date time, <t:x:t> gives just short time (e.g. 4:30 PM)
    await channel.send(f"✅ {user.mention} has been assigned a **{file_type}** at {time_tag}.")


# --- BOT EVENTS ---

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    try:
        # Sync the slash commands so they appear in Discord
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Failed to sync commands: {e}")

@bot.event
async def on_message(message):
    # Prevent bot from replying to itself
    if message.author.bot:
        return

    # Check for "Available" trigger
    if message.content.strip().lower() == "available":
        # Check if already in queue
        if any(item['user'].id == message.author.id for item in work_queue):
            await message.add_reaction("⚠️") # Already queued
        else:
            work_queue.append({
                'user': message.author,
                'time': int(datetime.now().timestamp())
            })
            await message.add_reaction("📝") # Added to queue

    await bot.process_commands(message)

# --- SLASH COMMANDS ---

@bot.tree.command(name="available", description="Add yourself to the work queue")
async def available(interaction: discord.Interaction):
    if any(item['user'].id == interaction.user.id for item in work_queue):
        await interaction.response.send_message("You are already in the queue!", ephemeral=True)
        return

    work_queue.append({
        'user': interaction.user,
        'time': int(datetime.now().timestamp())
    })
    await interaction.response.send_message(f"{interaction.user.mention} added to the queue.", ephemeral=False)

@bot.tree.command(name="optout", description="Remove yourself from the queue")
async def optout(interaction: discord.Interaction):
    global work_queue
    # Filter out the user
    original_len = len(work_queue)
    work_queue = [item for item in work_queue if item['user'].id != interaction.user.id]
    
    if len(work_queue) < original_len:
        await interaction.response.send_message("You have been removed from the queue.", ephemeral=True)
    else:
        await interaction.response.send_message("You were not in the queue.", ephemeral=True)

@bot.tree.command(name="queue", description="Show the current waiting list (SWC Only)")
async def show_queue(interaction: discord.Interaction):
    if not is_swc(interaction):
        await interaction.response.send_message("⛔ SWC Access Only.", ephemeral=True)
        return

    if not work_queue:
        await interaction.response.send_message("The queue is empty.", ephemeral=True)
        return

    # Generate the list
    msg = "**Current Work Queue:**\n"
    for idx, item in enumerate(work_queue, 1):
        # <t:timestamp:F> shows full date/time localized to the viewer
        msg += f"--- {idx}. {item['user'].display_name} - Queued at <t:{item['time']}:F>\n"

    await interaction.response.send_message(msg, ephemeral=False)

@bot.tree.command(name="remove", description="Remove a specific user from the queue (SWC Only)")
async def remove_user(interaction: discord.Interaction, member: discord.Member):
    if not is_swc(interaction):
        await interaction.response.send_message("⛔ SWC Access Only.", ephemeral=True)
        return

    global work_queue
    work_queue = [item for item in work_queue if item['user'].id != member.id]
    await interaction.response.send_message(f"Removed {member.display_name} from the queue.", ephemeral=False)

@bot.tree.command(name="resetqueue", description="Clear the entire queue (SWC Only)")
async def reset_queue(interaction: discord.Interaction):
    if not is_swc(interaction):
        await interaction.response.send_message("⛔ SWC Access Only.", ephemeral=True)
        return

    work_queue.clear()
    await interaction.response.send_message("🔄 The queue has been reset to 0.", ephemeral=False)

@bot.tree.command(name="assign", description="Assign a file to a user (SWC Only)")
@app_commands.choices(file_type=FILE_CHOICES)
async def assign(interaction: discord.Interaction, member: discord.Member, file_type: app_commands.Choice[str]):
    if not is_swc(interaction):
        await interaction.response.send_message("⛔ SWC Access Only.", ephemeral=True)
        return

    # Defer response because DMs might take a second
    await interaction.response.defer()

    # Reuse the logic function
    await assign_logic(member, file_type.value, interaction.channel)

    # If they were in the queue, remove them automatically? (Optional, but usually good workflow)
    # Uncomment the next 2 lines if you want auto-remove on assign:
    # global work_queue
    # work_queue = [item for item in work_queue if item['user'].id != member.id]

    await interaction.followup.send("Assignment Processed.", ephemeral=True)

# --- REACTION EVENT (Legacy support + Public Message update) ---

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
        
        # Check SWC Role
        user_role_names = [role.name for role in reactor.roles]
        if SWC_ROLE_NAME not in user_role_names:
            return

        try:
            channel = bot.get_channel(payload.channel_id)
            message = await channel.fetch_message(payload.message_id)
            editor = message.author
        except:
            return

        if editor.bot: return

        # Get File Type
        file_type = EMOJI_TO_FILE[emoji_name]

        # Use the shared logic to DM and Publicly Post
        await assign_logic(editor, file_type, channel)

        # Mark with emoji to show it's done
        await message.add_reaction("📩")

# START THE SERVER
keep_alive()

# START THE BOT
if TOKEN:
    bot.run(TOKEN)
else:
    print("Error: DISCORD_TOKEN not found.")

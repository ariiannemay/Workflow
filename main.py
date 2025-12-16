import discord
from discord.ext import commands
from discord import app_commands, ui
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

FILE_CHOICES = [
    app_commands.Choice(name="Aiera Live", value="AIERA LIVE FILE"),
    app_commands.Choice(name="Aiera Batch", value="AIERA BATCH FILE"),
    app_commands.Choice(name="HP File", value="HP FILE"),
    app_commands.Choice(name="Quartr Live", value="QUARTR LIVE FILE"),
    app_commands.Choice(name="Quartr Batch", value="QUARTR BATCH FILE"),
]

# --- THE QUEUE ---
work_queue = []

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# --- HELPER FUNCTIONS ---
def is_swc(interaction: discord.Interaction):
    user_roles = [role.name for role in interaction.user.roles]
    return SWC_ROLE_NAME in user_roles

def get_time_tag():
    current_unix_time = int(datetime.now().timestamp())
    return f"<t:{current_unix_time}:F>"

# --- SHARED ASSIGNMENT LOGIC ---
async def assign_logic(user, file_type, channel):
    time_tag = get_time_tag()
    
    # 1. Remove from Queue if present
    global work_queue
    if any(item['user'].id == user.id for item in work_queue):
        work_queue = [item for item in work_queue if item['user'].id != user.id]

    # 2. DM Content
    dm_content = (
        f"# Hello {user.mention}! You have been assigned a **{file_type}** at {time_tag}.\n\n" 
        f"## Please start on them immediately.\n\n"
        f"### REMINDERS:\n\n"
        f"- If no movement is observed on your file for at least 5 minutes, and if your file is at risk of breaching TAT, Senior Workflow Coordinator may REASSIGN your file without prior notice.\n"
        f"- If you will take longer on a file, keep the SWC properly appraised. Include your reasons and estimated TAT."
    )

    # 3. Send DM
    try:
        await user.send(dm_content)
    except discord.Forbidden:
        await channel.send(f"{user.mention} ⚠️ I cannot DM you, but you are assigned.")

    # 4. Public Message (Briefcase)
    await channel.send(f"💼 {user.mention} has been assigned a **{file_type}** at {time_tag}.")

# --- MODALS (POPUPS) ---

class AvailabilityModal(ui.Modal):
    def __init__(self, title_text):
        super().__init__(title=title_text)

    name = ui.TextInput(label="Name", placeholder="Your full name")
    time_affected = ui.TextInput(label="Date and Time Affected", placeholder="e.g. Dec 25, 4pm-9am")
    change_type = ui.TextInput(label="Change Requested", placeholder="Available --> Unavailable OR Unavailable --> Available")
    reason = ui.TextInput(label="Reason", style=discord.TextStyle.paragraph)

    async def on_submit(self, interaction: discord.Interaction):
        # Build the message
        msg = (
            f"**{self.title} Request**\n"
            f"**Name:** {self.name.value}\n"
            f"**Date/Time:** {self.time_affected.value}\n"
            f"**Change:** {self.change_type.value}\n"
            f"**Reason:** {self.reason.value}"
        )
        await interaction.response.send_message(msg)

class TATDelayModal(ui.Modal, title="TAT Delay Report"):
    file_name = ui.TextInput(label="File Name")
    reason = ui.TextInput(label="Reason for TAT delay", style=discord.TextStyle.paragraph)

    async def on_submit(self, interaction: discord.Interaction):
        msg = (
            f"**TAT Delay Reported**\n"
            f"**Editor:** {interaction.user.mention}\n"
            f"**File Name:** {self.file_name.value}\n"
            f"**Reason:** {self.reason.value}\n"
            f"@{SWC_ROLE_NAME}" # Mentions the role if it exists and is mentionable
        )
        await interaction.response.send_message(msg)

class FileUpdateModal(ui.Modal, title="File Update"):
    file_name = ui.TextInput(label="File Name")
    update_text = ui.TextInput(label="File Update", style=discord.TextStyle.paragraph)
    status = ui.TextInput(label="File Status", placeholder="e.g. FDF, WIP, Uploading")

    async def on_submit(self, interaction: discord.Interaction):
        msg = (
            f"**File Update**\n"
            f"**Editor:** {interaction.user.mention}\n"
            f"**File Name:** {self.file_name.value}\n"
            f"**File Update:** {self.update_text.value}\n"
            f"**File Status:** {self.status.value}\n"
            f"@{SWC_ROLE_NAME}"
        )
        await interaction.response.send_message(msg)

# --- VIEWS (For Right Click Assignment Menu) ---
class AssignView(ui.View):
    def __init__(self, member: discord.Member, channel):
        super().__init__()
        self.member = member
        self.channel = channel

    @discord.ui.select(
        placeholder="Select File Type to Assign...",
        options=[
            discord.SelectOption(label="Aiera Live", value="AIERA LIVE FILE"),
            discord.SelectOption(label="Aiera Batch", value="AIERA BATCH FILE"),
            discord.SelectOption(label="HP File", value="HP FILE"),
            discord.SelectOption(label="Quartr Live", value="QUARTR LIVE FILE"),
            discord.SelectOption(label="Quartr Batch", value="QUARTR BATCH FILE"),
        ]
    )
    async def select_callback(self, interaction: discord.Interaction, select: ui.Select):
        # Perform assignment
        file_type = select.values[0]
        await interaction.response.defer() # Acknowledge the click so it doesn't fail
        await assign_logic(self.member, file_type, self.channel)
        await interaction.followup.send(f"Assigned {file_type} to {self.member.display_name}", ephemeral=True)


# --- BOT EVENTS ---

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Failed to sync commands: {e}")

@bot.event
async def on_message(message):
    if message.author.bot: return

# Inside on_message event...
    if message.content.strip().lower() == "available":
        if any(item['user'].id == message.author.id for item in work_queue):
            await message.add_reaction("⚠️") 
        else:
            work_queue.append({
                'user': message.author,
                'time': int(datetime.now().timestamp())
            })
            
            # 1. Public Message
            await message.channel.send(f"{message.author.mention} is available for a file. Added to the queue.")
            
            # 2. DM Message
            queue_pos = len(work_queue)
            time_tag = get_time_tag()
            
            dm_content = (
                f"You are added to the queue. As of {time_tag}, you are at queue #{queue_pos}.\n\n"
                f"**IMPORTANT REMINDERS:**\n"
                f"- Audio project assignments are NOT preference-based. Audio projects will be drawn from the available queue and assigned by SWCs according to coverage and TAT needs.\n"
                f"- Queue numbers are NOT a guarantee that files will be assigned chronologically.\n"
                f"- Please be reminded of our Reminder on Eligibility for Audio Project Assignments: https://discord.com/channels/1391591320677519431/1391595956247728219/1450362680966774805"
            )

            try:
                await message.author.send(dm_content)
            except:
                pass

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
    
    # Public Response
    await interaction.response.send_message(f"{interaction.user.mention} is available for a file. Added to the queue.")
    
    # DM Response
    queue_pos = len(work_queue)
    time_tag = get_time_tag()
    
    dm_content = (
        f"You are added to the queue. As of {time_tag}, you are at queue #{queue_pos}.\n\n"
        f"**IMPORTANT REMINDERS:**\n"
        f"- Audio project assignments are NOT preference-based. Audio projects will be drawn from the available queue and assigned by SWCs according to coverage and TAT needs.\n"
        f"- Queue numbers are NOT a guarantee that files will be assigned chronologically.\n"
        f"- Please be reminded of our Reminder on Eligibility for Audio Project Assignments: https://discord.com/channels/1391591320677519431/1391595956247728219/1450362680966774805"
    )

    try:
        await interaction.user.send(dm_content)
    except:
        pass

@bot.tree.command(name="optout", description="Remove yourself from the queue")
async def optout(interaction: discord.Interaction):
    global work_queue
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

    # Build Embed
    embed = discord.Embed(title="Current Work Queue", color=discord.Color.blue())
    desc = ""
    for idx, item in enumerate(work_queue, 1):
        # Format: 1. @User - Queued at Time
        desc += f"**{idx}.** {item['user'].mention} - Queued at <t:{item['time']}:F>\n"
    
    embed.description = desc
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="remove", description="Remove a specific user from the queue (SWC Only)")
async def remove_user(interaction: discord.Interaction, member: discord.Member):
    if not is_swc(interaction):
        await interaction.response.send_message("⛔ SWC Access Only.", ephemeral=True)
        return

    global work_queue
    work_queue = [item for item in work_queue if item['user'].id != member.id]
    await interaction.response.send_message(f"Removed {member.mention} from the queue.", ephemeral=False)

@bot.tree.command(name="resetqueue", description="Clear the entire queue (SWC Only)")
async def reset_queue(interaction: discord.Interaction):
    if not is_swc(interaction):
        await interaction.response.send_message("⛔ SWC Access Only.", ephemeral=True)
        return

    work_queue.clear()
    time_tag = get_time_tag()
    await interaction.response.send_message(f"🔄 The queue has been reset as of {time_tag}", ephemeral=False)

@bot.tree.command(name="assign", description="Assign a file to a user (SWC Only)")
@app_commands.choices(file_type=FILE_CHOICES)
async def assign(interaction: discord.Interaction, member: discord.Member, file_type: app_commands.Choice[str]):
    if not is_swc(interaction):
        await interaction.response.send_message("⛔ SWC Access Only.", ephemeral=True)
        return

    # Defer interaction (loading state)
    await interaction.response.defer(ephemeral=True)

    # Perform Logic
    await assign_logic(member, file_type.value, interaction.channel)

    # Confirm to SWC (Ephemeral)
    await interaction.followup.send("Assignment processed.", ephemeral=True)

@bot.tree.command(name="askfileupdate", description="Ask a user for an update on their file")
async def ask_update(interaction: discord.Interaction, user: discord.Member):
    await interaction.response.send_message(f"{user.mention}, please provide an update on your file.")

# --- FORM COMMANDS ---

@bot.tree.command(name="plannedavailability", description="Submit planned availability change")
async def planned(interaction: discord.Interaction):
    await interaction.response.send_modal(AvailabilityModal(title_text="Planned Availability"))

@bot.tree.command(name="unplannedavailability", description="Submit unplanned availability change")
async def unplanned(interaction: discord.Interaction):
    await interaction.response.send_modal(AvailabilityModal(title_text="Unplanned Availability"))

@bot.tree.command(name="tatdelay", description="Report a TAT delay")
async def tat_delay(interaction: discord.Interaction):
    await interaction.response.send_modal(TATDelayModal())

@bot.tree.command(name="fileupdate", description="Provide a file update")
async def file_update(interaction: discord.Interaction):
    await interaction.response.send_modal(FileUpdateModal())

# --- CONTEXT MENU COMMANDS (RIGHT CLICK) ---

@bot.tree.context_menu(name="Assign a File")
async def context_assign(interaction: discord.Interaction, member: discord.Member):
    if not is_swc(interaction):
        await interaction.response.send_message("⛔ SWC Access Only.", ephemeral=True)
        return
    
    # Send a view with a dropdown menu, only visible to SWC
    await interaction.response.send_message(
        f"Select file type for {member.mention}:", 
        view=AssignView(member, interaction.channel), 
        ephemeral=True
    )

@bot.tree.context_menu(name="Remove from Queue")
async def context_remove(interaction: discord.Interaction, member: discord.Member):
    if not is_swc(interaction):
        await interaction.response.send_message("⛔ SWC Access Only.", ephemeral=True)
        return

    global work_queue
    work_queue = [item for item in work_queue if item['user'].id != member.id]
    await interaction.response.send_message(f"Removed {member.mention} from the queue.", ephemeral=False)


# --- EMOJI LISTENER (LEGACY) ---
@bot.event
async def on_raw_reaction_add(payload):
    if payload.user_id == bot.user.id: return
    
    if payload.emoji.name in EMOJI_TO_FILE:
        guild = bot.get_guild(payload.guild_id)
        if not guild: return
        reactor = guild.get_member(payload.user_id)
        if not reactor: return
        
        user_role_names = [role.name for role in reactor.roles]
        if SWC_ROLE_NAME not in user_role_names: return

        try:
            channel = bot.get_channel(payload.channel_id)
            message = await channel.fetch_message(payload.message_id)
            editor = message.author
        except: return

        if editor.bot: return

        file_type = EMOJI_TO_FILE[payload.emoji.name]
        await assign_logic(editor, file_type, channel)
        await message.add_reaction("💼")

# START
keep_alive()
if TOKEN:
    bot.run(TOKEN)

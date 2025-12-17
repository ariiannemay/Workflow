import discord
from discord.ext import commands
from discord import app_commands, ui
from datetime import datetime
import os
import json
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
SWC_ROLE_IDS = [1391602377672491198, 1450395825208299582]

EMOJI_TO_FILE = {
    "QB": "QUARTR BATCH FILE",
    "QL": "QUARTR LIVE FILE",
    "HP": "HP FILE",
    "AB": "AIERA BATCH FILE",
    "AL": "AIERA LIVE FILE",
    "🇶": "QUARTR FILE", 
    "🇭": "HP FILE",           
    "🇦": "AIERA FILE", 
}

FILE_CHOICES = [
    app_commands.Choice(name="Aiera Live", value="AIERA LIVE FILE"),
    app_commands.Choice(name="Aiera Batch", value="AIERA BATCH FILE"),
    app_commands.Choice(name="HP File", value="HP FILE"),
    app_commands.Choice(name="Quartr Live", value="QUARTR LIVE FILE"),
    app_commands.Choice(name="Quartr Batch", value="QUARTR BATCH FILE"),
]

# --- PERSISTENCE & DATA MANAGEMENT ---
QUEUE_FILE = "queue.json"
CONFIG_FILE = "config.json"

# Global Variables
work_queue = []
server_configs = {} 
available_cooldowns = {} 

def load_data():
    global work_queue, server_configs
    if os.path.exists(QUEUE_FILE):
        try:
            with open(QUEUE_FILE, "r") as f:
                work_queue = json.load(f)
                print(f"Loaded {len(work_queue)} users from queue file.")
        except Exception as e:
            print(f"Error loading queue: {e}")
            work_queue = []
    
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                server_configs = json.load(f)
        except Exception as e:
            server_configs = {}

def save_queue():
    try:
        with open(QUEUE_FILE, "w") as f:
            json.dump(work_queue, f)
    except Exception as e:
        print(f"Failed to save queue: {e}")

def save_config():
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(server_configs, f)
    except Exception as e:
        print(f"Failed to save config: {e}")

# --- HELPER FUNCTIONS ---
def is_swc(interaction: discord.Interaction):
    if not isinstance(interaction.user, discord.Member): return False
    if any(role.id in SWC_ROLE_IDS for role in interaction.user.roles):
        return True
    user_role_names = [role.name for role in interaction.user.roles]
    return SWC_ROLE_NAME in user_role_names

def get_time_tag():
    current_unix_time = int(datetime.now().timestamp())
    return f"<t:{current_unix_time}:F>"

async def send_log(guild, content=None, embed=None):
    if not guild: return
    guild_id_str = str(guild.id)
    if guild_id_str in server_configs:
        channel_id = server_configs[guild_id_str]
        channel = guild.get_channel(channel_id)
        if channel:
            try:
                await channel.send(content=content, embed=embed)
            except:
                pass

# --- SHARED ASSIGNMENT LOGIC ---
async def assign_logic(user, file_type, channel, assigner):
    time_tag = get_time_tag()
    global work_queue
    in_queue = False
    if any(item['user_id'] == user.id for item in work_queue):
        work_queue = [item for item in work_queue if item['user_id'] != user.id]
        save_queue()
        in_queue = True

    dm_content = (
        f"# Hello {user.mention}! You have been assigned a **{file_type}** at {time_tag}.\n\n" 
        f"## Please start on them immediately.\n\n"
        f"### REMINDERS:\n\n"
        f"- If no movement is observed on your file for at least 5 minutes, and if your file is at risk of breaching TAT, the SWCs may REASSIGN your file without prior notice.\n"
        f"- If you will take longer on a file, keep the SWCs properly appraised. Include your reasons and estimated TAT."
    )

    try:
        await user.send(dm_content)
        await channel.send(f"💼 {user.mention} has been assigned a **{file_type}** at {time_tag}.")
    except discord.Forbidden:
        await channel.send(f"⚠️ {user.mention} (I cannot DM you) — You have been assigned a **{file_type}** at {time_tag}. Please check your privacy settings.")

    log_embed = discord.Embed(title="File Assigned", color=discord.Color.green())
    log_embed.add_field(name="Editor", value=f"{user.display_name} ({user.id})", inline=True)
    log_embed.add_field(name="File Type", value=file_type, inline=True)
    log_embed.add_field(name="Assigned By", value=assigner.display_name, inline=False)
    log_embed.set_footer(text=f"Was in queue: {in_queue}")
    await send_log(channel.guild, embed=log_embed)

# --- TAT CALCULATOR LOGIC ---
class TATModal(ui.Modal):
    def __init__(self, file_type):
        super().__init__(title=f"TAT Calculator: {file_type}")
        self.file_type = file_type
    audio_len = ui.TextInput(label="Audio Length", placeholder="HH:MM:SS (e.g. 01:30:00)", max_length=8)
    async def on_submit(self, interaction: discord.Interaction):
        time_str = self.audio_len.value.strip()
        try:
            parts = list(map(int, time_str.split(':')))
            if len(parts) == 3: h, m, s = parts
            elif len(parts) == 2: h, m, s = 0, parts[0], parts[1]
            else: raise ValueError
            total_seconds = h * 3600 + m * 60 + s
            ah_decimal = total_seconds / 3600
        except:
            await interaction.response.send_message("❌ Invalid format. Please use HH:MM:SS", ephemeral=True)
            return

        fr_tat = 0
        sv_tat = 0
        overall_tat = 0
        
        if "Quartr" in self.file_type:
            fr_tat = total_seconds * 0.5
            sv_tat = total_seconds * 1.5
            overall_tat = total_seconds * 2.0
        elif "Aiera" in self.file_type:
            fr_tat = total_seconds * 0.5
            sv_tat = total_seconds * 0.3 
            overall_tat = total_seconds * 3.5 
        elif "HP" in self.file_type:
            overall_tat = 90 * 60 
        
        def fmt(seconds):
            if seconds == 0: return "N/A"
            m, s = divmod(seconds, 60)
            h, m = divmod(m, 60)
            return f"{int(h):02d}:{int(m):02d}:{int(s):02d}"

        msg = (
            f"# TAT Calculator\n"
            f"**`Audio Length:`** {time_str}\n"
            f"**`Audio Hour:`** {ah_decimal:.2f}]\n"
            f"**`FR TAT`:** {fmt(fr_tat)}\n"
            f"__**`SV TAT:`** {fmt(sv_tat)}__\n" 
            f"**`OVERALL TAT:`** {fmt(overall_tat)}\n\n"
            f"-# You can also use this Workflow Logger for TATs: https://fdeditor-workflowtimer.vercel.app/"
        )
        await interaction.response.send_message(msg, ephemeral=True)

class TATView(ui.View):
    def __init__(self):
        super().__init__()
    @discord.ui.select(
        placeholder="Select File Type to Calculate...",
        options=[
            discord.SelectOption(label="Quartr File", value="Quartr"),
            discord.SelectOption(label="Aiera File", value="Aiera"),
            discord.SelectOption(label="HP File", value="HP"),
        ]
    )
    async def select_callback(self, interaction: discord.Interaction, select: ui.Select):
        await interaction.response.send_modal(TATModal(select.values[0]))

# --- MODALS (FORMS) ---
class AvailabilityModal(ui.Modal):
    def __init__(self, title_text):
        super().__init__(title=title_text)
    time_affected = ui.TextInput(label="Date and Time Affected", placeholder="e.g. Dec 25, 4pm-9am")
    change_type = ui.TextInput(label="Change Requested", placeholder="Available --> Unavailable OR Unavailable --> Available")
    reason = ui.TextInput(label="Reason", style=discord.TextStyle.paragraph)

    async def on_submit(self, interaction: discord.Interaction):
        msg = (
            f"## {self.title} Request\n"
            f"- **`EDITOR:`** {interaction.user.mention}\n"
            f"- **`DATE AND TIME AFFECTED:`** {self.time_affected.value}\n"
            f"- **`CHANGE REQUESTED:`** {self.change_type.value}\n"
            f"- **`REASON:`** {self.reason.value}"
        )
        await interaction.response.send_message(msg)
        
        # LOGS AS EMBED ONLY
        log_embed = discord.Embed(title=f"{self.title} Request", color=discord.Color.orange())
        log_embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        log_embed.add_field(name="Time Affected", value=self.time_affected.value, inline=False)
        log_embed.add_field(name="Change Type", value=self.change_type.value, inline=False)
        log_embed.add_field(name="Reason", value=self.reason.value, inline=False)
        await send_log(interaction.guild, embed=log_embed)

class PermissionTATModal(ui.Modal, title="Permission to exceed TAT"):
    file_name = ui.TextInput(label="File Name")
    reason = ui.TextInput(label="Reason for TAT delay", style=discord.TextStyle.paragraph)

    async def on_submit(self, interaction: discord.Interaction):
        msg = (
            f"## Permission to exceed TAT\n"
            f"- **`EDITOR:`** {interaction.user.mention}\n"
            f"- **`FILE NAME:`** {self.file_name.value}\n"
            f"- **`REASON:`** {self.reason.value}"
        )
        await interaction.response.send_message(msg)
        
        # LOGS AS EMBED ONLY
        log_embed = discord.Embed(title="Permission to exceed TAT", color=discord.Color.red())
        log_embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        log_embed.add_field(name="File Name", value=self.file_name.value, inline=True)
        log_embed.add_field(name="Reason", value=self.reason.value, inline=False)
        await send_log(interaction.guild, embed=log_embed)

class FileUpdateModal(ui.Modal, title="File Update"):
    file_name = ui.TextInput(label="File Name")
    update_text = ui.TextInput(label="File Update", style=discord.TextStyle.paragraph)
    status = ui.TextInput(label="File Status", placeholder="e.g. FDF, SV, FR")

    async def on_submit(self, interaction: discord.Interaction):
        msg = (
            f"## File Update\n"
            f"**EDITOR:** {interaction.user.mention}\n"
            f"**FILE NAME:** {self.file_name.value}\n"
            f"**FILE UPDATE:** {self.update_text.value}\n"
            f"**FILE STATUS:** {self.status.value}"
        )
        await interaction.response.send_message(msg)
        # File updates usually aren't logged to the admin channel to reduce spam, but if you want to, add it here.

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
        file_type = select.values[0]
        await interaction.response.defer() 
        await assign_logic(self.member, file_type, self.channel, interaction.user)
        await interaction.followup.send(f"Assigned {file_type} to {self.member.display_name}", ephemeral=True)


# --- BOT SETUP ---
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    load_data()
    print(f'Logged in as {bot.user}')
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Failed to sync commands: {e}")

@bot.event
async def on_message(message):
    if message.author.bot: return

    if message.content.strip().lower() == "available":
        if any(item['user_id'] == message.author.id for item in work_queue):
            await message.add_reaction("✍🏼") 
        else:
            work_queue.append({
                'user_id': message.author.id,
                'name': message.author.display_name,
                'time': int(datetime.now().timestamp())
            })
            save_queue()
            
            await message.reply(f"👋🏼 {message.author.mention} is available for a file. Added to the queue.", mention_author=True)
            
            queue_pos = len(work_queue)
            time_tag = get_time_tag()
            dm_content = (
                f"You are added to the queue. As of {time_tag}, you are at queue #{queue_pos}.\n\n"
                f"**IMPORTANT REMINDERS:**\n"
                f"- Audio project assignments are NOT preference-based.\n"
                f"- Queue numbers are **NOT a guarantee** that files will be assigned chronologically.\n"
                f"- Please be reminded of our *Reminder on Eligibility for Audio Project Assignments.*"
            )
            try:
                await message.author.send(dm_content)
            except:
                pass
            
            log_embed = discord.Embed(title="User Available", description=f"{message.author.mention} joined the queue.", color=discord.Color.blue())
            await send_log(message.guild, embed=log_embed)

    await bot.process_commands(message)


# --- SLASH COMMANDS ---

@bot.tree.command(name="setlogchannel", description="Set the channel where bot logs will be sent")
@app_commands.default_permissions(administrator=True)
@app_commands.guild_only() 
async def set_log_channel(interaction: discord.Interaction):
    if not is_swc(interaction):
        await interaction.response.send_message("⛔ SWC Access Only.", ephemeral=True)
        return
    server_configs[str(interaction.guild_id)] = interaction.channel_id
    save_config()
    await interaction.response.send_message(f"✅ Logging channel set to {interaction.channel.mention}", ephemeral=True)

@bot.tree.command(name="tattimer", description="Calculate TAT deadlines for a file")
async def tattimer(interaction: discord.Interaction):
    await interaction.response.send_message("Select a file type to calculate TAT:", view=TATView(), ephemeral=True)

@bot.tree.command(name="available", description="Add yourself to the work queue")
async def available(interaction: discord.Interaction):
    last_used = available_cooldowns.get(interaction.user.id, 0)
    now_ts = datetime.now().timestamp()
    if now_ts - last_used < 30:
        await interaction.response.send_message("⏳ Please wait a moment before using this again.", ephemeral=True)
        return
    available_cooldowns[interaction.user.id] = now_ts

    if any(item['user_id'] == interaction.user.id for item in work_queue):
        await interaction.response.send_message("You are already in the queue!", ephemeral=True)
        return

    work_queue.append({
        'user_id': interaction.user.id,
        'name': interaction.user.display_name,
        'time': int(datetime.now().timestamp())
    })
    save_queue()
    await interaction.response.send_message(f"👋🏼 {interaction.user.mention} is available for a file. Added to the queue.")
    
    queue_pos = len(work_queue)
    time_tag = get_time_tag()
    dm_content = (
        f"You are added to the queue. As of {time_tag}, you are at queue #{queue_pos}.\n\n"
        f"**IMPORTANT REMINDERS:**\n"
        f"- Audio project assignments are NOT preference-based.\n"
        f"- Queue numbers are **NOT a guarantee** that files will be assigned chronologically.\n"
        f"- Please be reminded of our *Reminder on Eligibility for Audio Project Assignments.*"
    )
    try:
        await interaction.user.send(dm_content)
    except:
        pass
    log_embed = discord.Embed(title="User Available", description=f"{interaction.user.mention} joined via command.", color=discord.Color.blue())
    await send_log(interaction.guild, embed=log_embed)

@bot.tree.command(name="optout", description="Remove yourself from the queue")
async def optout(interaction: discord.Interaction):
    global work_queue
    original_len = len(work_queue)
    work_queue = [item for item in work_queue if item['user_id'] != interaction.user.id]
    save_queue()
    if len(work_queue) < original_len:
        await interaction.response.send_message("You have removed yourself from the queue.", ephemeral=True)
        # LOG AS EMBED
        log_embed = discord.Embed(description=f"📤 {interaction.user.mention} opted out of queue.", color=discord.Color.light_grey())
        await send_log(interaction.guild, embed=log_embed)
    else:
        await interaction.response.send_message("You were not in the queue.", ephemeral=True)

@bot.tree.command(name="queue", description="Show the current waiting list")
@app_commands.default_permissions(administrator=True)
@app_commands.guild_only() 
async def show_queue(interaction: discord.Interaction):
    if not is_swc(interaction):
        await interaction.response.send_message("⛔ SWC Access Only.", ephemeral=True)
        return
    if not work_queue:
        await interaction.response.send_message("The queue is empty.", ephemeral=True)
        return
    current_time_tag = get_time_tag()
    embed = discord.Embed(title="Current Work Queue", color=discord.Color.blue())
    desc = f"**As of:** {current_time_tag}\n\n"
    for idx, item in enumerate(work_queue, 1):
        member = interaction.guild.get_member(item['user_id'])
        name_display = member.mention if member else item['name']
        desc += f"**{idx}.** {name_display} | <t:{item['time']}:R>\n"
    embed.description = desc
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="remove", description="Remove a specific user from the queue")
@app_commands.default_permissions(administrator=True)
@app_commands.guild_only() 
async def remove_user(interaction: discord.Interaction, member: discord.Member):
    if not is_swc(interaction):
        await interaction.response.send_message("⛔ SWC Access Only.", ephemeral=True)
        return
    global work_queue
    work_queue = [item for item in work_queue if item['user_id'] != member.id]
    save_queue()
    await interaction.response.send_message(f"✔️ Removed {member.mention} from the queue.", ephemeral=True)
    
    # LOG AS EMBED
    log_embed = discord.Embed(title="User Removed from Queue", color=discord.Color.red())
    log_embed.add_field(name="User", value=member.mention, inline=True)
    log_embed.add_field(name="Removed By", value=interaction.user.mention, inline=True)
    await send_log(interaction.guild, embed=log_embed)

@bot.tree.command(name="resetqueue", description="Clear the entire queue")
@app_commands.default_permissions(administrator=True)
@app_commands.guild_only() 
async def reset_queue(interaction: discord.Interaction):
    if not is_swc(interaction):
        await interaction.response.send_message("⛔ SWC Access Only.", ephemeral=True)
        return
    work_queue.clear()
    save_queue()
    time_tag = get_time_tag()
    await interaction.response.send_message(f"🔄 The queue has been reset as of {time_tag}", ephemeral=False)
    
    # LOG AS EMBED
    log_embed = discord.Embed(description=f"🔄 Queue reset by {interaction.user.mention}", color=discord.Color.red())
    await send_log(interaction.guild, embed=log_embed)

@bot.tree.command(name="assign", description="Assign a file to a user")
@app_commands.choices(file_type=FILE_CHOICES)
@app_commands.default_permissions(administrator=True)
@app_commands.guild_only() 
async def assign(interaction: discord.Interaction, member: discord.Member, file_type: app_commands.Choice[str]):
    if not is_swc(interaction):
        await interaction.response.send_message("⛔ SWC Access Only.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    await assign_logic(member, file_type.value, interaction.channel, interaction.user)
    await interaction.followup.send("Assignment processed.", ephemeral=True)

@bot.tree.command(name="askfileupdate", description="Ask a user for an update on their file")
@app_commands.default_permissions(administrator=True)
@app_commands.guild_only() 
async def ask_update(interaction: discord.Interaction, user: discord.Member):
    if not is_swc(interaction):
        await interaction.response.send_message("⛔ SWC Access Only.", ephemeral=True)
        return
    await interaction.response.send_message(f"🔍 {user.mention}, please provide an update on your file.")

@bot.tree.command(name="reassign_notif", description="Notify editor of reassignment")
@app_commands.default_permissions(administrator=True)
@app_commands.guild_only() 
async def reassign_notif(interaction: discord.Interaction, member: discord.Member):
    if not is_swc(interaction):
        await interaction.response.send_message("⛔ SWC Access Only.", ephemeral=True)
        return
    try:
        await member.send(f"⚠️ {member.mention}, your file has been REASSIGNED due to idleness.")
        await interaction.response.send_message(f"✅ Notification sent to {member.mention}.", ephemeral=True)
        
        # LOG AS EMBED
        log_embed = discord.Embed(title="Reassignment Notice Sent", color=discord.Color.orange())
        log_embed.add_field(name="Editor", value=member.mention, inline=True)
        log_embed.add_field(name="Sent By", value=interaction.user.mention, inline=True)
        await send_log(interaction.guild, embed=log_embed)
    except discord.Forbidden:
        await interaction.response.send_message(f"❌ Could not DM {member.mention}.", ephemeral=True)

# --- FORM COMMANDS ---
@bot.tree.command(name="plannedavailability", description="Submit planned availability change")
async def planned(interaction: discord.Interaction):
    await interaction.response.send_modal(AvailabilityModal(title_text="Planned Availability"))

@bot.tree.command(name="unplannedavailability", description="Submit unplanned availability change")
async def unplanned(interaction: discord.Interaction):
    await interaction.response.send_modal(AvailabilityModal(title_text="Unplanned Availability"))

@bot.tree.command(name="tatdelay", description="Ask permission to exceed TAT")
async def tat_delay(interaction: discord.Interaction):
    await interaction.response.send_modal(PermissionTATModal())

@bot.tree.command(name="fileupdate", description="Provide a file update")
async def file_update(interaction: discord.Interaction):
    await interaction.response.send_modal(FileUpdateModal())

# --- CONTEXT MENU COMMANDS (RIGHT CLICK) ---
@bot.tree.context_menu(name="Assign a File")
@app_commands.default_permissions(administrator=True)
@app_commands.guild_only() 
async def context_assign(interaction: discord.Interaction, member: discord.Member):
    if not is_swc(interaction):
        await interaction.response.send_message("⛔ SWC Access Only.", ephemeral=True)
        return
    await interaction.response.send_message(
        f"Select file type for {member.mention}:", 
        view=AssignView(member, interaction.channel), 
        ephemeral=True
    )

@bot.tree.context_menu(name="Remove from Queue")
@app_commands.default_permissions(administrator=True)
@app_commands.guild_only() 
async def context_remove(interaction: discord.Interaction, member: discord.Member):
    if not is_swc(interaction):
        await interaction.response.send_message("⛔ SWC Access Only.", ephemeral=True)
        return
    global work_queue
    work_queue = [item for item in work_queue if item['user_id'] != member.id]
    save_queue()
    await interaction.response.send_message(f"✔️ Removed {member.mention} from the queue.", ephemeral=True)
    
    # LOG AS EMBED
    log_embed = discord.Embed(title="User Removed (Context Menu)", color=discord.Color.red())
    log_embed.add_field(name="User", value=member.mention, inline=True)
    log_embed.add_field(name="Removed By", value=interaction.user.mention, inline=True)
    await send_log(interaction.guild, embed=log_embed)

@bot.tree.context_menu(name="Ask for Update")
@app_commands.default_permissions(administrator=True)
@app_commands.guild_only() 
async def context_ask_update(interaction: discord.Interaction, member: discord.Member):
    if not is_swc(interaction):
        await interaction.response.send_message("⛔ SWC Access Only.", ephemeral=True)
        return
    await interaction.response.send_message(f"🔍 {member.mention}, please provide an update on your file.")

# --- NEW CONTEXT MENU: ADD TO QUEUE ---
@bot.tree.context_menu(name="Add to Queue")
@app_commands.default_permissions(administrator=True)
@app_commands.guild_only()
async def context_add_queue(interaction: discord.Interaction, member: discord.Member):
    # 1. Security Check
    if not is_swc(interaction):
        await interaction.response.send_message("⛔ SWC Access Only.", ephemeral=True)
        return

    # 2. Check if already in queue
    global work_queue
    if any(item['user_id'] == member.id for item in work_queue):
        await interaction.response.send_message(f"{member.mention} is already in the queue!", ephemeral=True)
        return

    # 3. Add to Queue
    work_queue.append({
        'user_id': member.id,
        'name': member.display_name,
        'time': int(datetime.now().timestamp())
    })
    save_queue()

    # 4. Public Confirmation (The Wave)
    await interaction.response.send_message(f"👋🏼 {member.mention} is added to the queue.")

    # 5. DM the User (Identical to /available)
    queue_pos = len(work_queue)
    time_tag = get_time_tag()
    dm_content = (
        f"You are added to the queue. As of {time_tag}, you are at queue #{queue_pos}.\n\n"
        f"**IMPORTANT REMINDERS:**\n"
        f"- Audio project assignments are NOT preference-based.\n"
        f"- Queue numbers are **NOT a guarantee** that files will be assigned chronologically.\n"
        f"- Please be reminded of our *Reminder on Eligibility for Audio Project Assignments.*"
    )
    try:
        await member.send(dm_content)
    except:
        pass

    # 6. Log it (Embed)
    log_embed = discord.Embed(title="User Added to Queue (Admin)", color=discord.Color.blue())
    log_embed.add_field(name="User", value=member.mention, inline=True)
    log_embed.add_field(name="Added By", value=interaction.user.mention, inline=True)
    await send_log(interaction.guild, embed=log_embed)

# --- EMOJI LISTENER (LEGACY) ---
@bot.event
async def on_raw_reaction_add(payload):
    if payload.user_id == bot.user.id: return
    if payload.emoji.name in EMOJI_TO_FILE:
        guild = bot.get_guild(payload.guild_id)
        if not guild: return
        reactor = guild.get_member(payload.user_id)
        if not reactor: return
        
        is_swc_reactor = False
        if any(role.id in SWC_ROLE_IDS for role in reactor.roles):
            is_swc_reactor = True
        elif SWC_ROLE_NAME in [role.name for role in reactor.roles]:
            is_swc_reactor = True

        if not is_swc_reactor: return

        try:
            channel = bot.get_channel(payload.channel_id)
            message = await channel.fetch_message(payload.message_id)
            editor = message.author
        except: return
        if editor.bot: return
        file_type = EMOJI_TO_FILE[payload.emoji.name]
        await assign_logic(editor, file_type, channel, reactor)
        await message.add_reaction("💼")

# START
keep_alive()
if TOKEN:
    bot.run(TOKEN)

import discord
from discord.ext import commands
from discord import app_commands, ui
from datetime import datetime
import os
import json
from flask import Flask
from threading import Thread
import asyncio

# --- KEEP ALIVE SECTION ---
app = Flask('')

@app.route('/')
def home():
    return "I am alive!"

def run():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))

def keep_alive():
    t = Thread(target=run)
    t.start()
# ---------------------------

# --- CONFIGURATION ---
TOKEN = os.getenv("DISCORD_TOKEN")
SWC_ROLE_NAME = "Senior Workflow Coordinator"
SWC_ROLE_IDS = [1391602377672491198, 1450395825208299582]

FILE_CHOICES = [
    app_commands.Choice(name="Aiera Live", value="AIERA LIVE FILE"),
    app_commands.Choice(name="Aiera Batch", value="AIERA BATCH FILE"),
    app_commands.Choice(name="HP File", value="HP FILE"),
    app_commands.Choice(name="Quartr Live", value="QUARTR LIVE FILE"),
    app_commands.Choice(name="Quartr Batch", value="QUARTR BATCH FILE"),
]

TIME_BLOCK_CHOICES = [
    app_commands.Choice(name="00:00 - 08:00 EST", value="00:00 - 08:00 EST"),
    app_commands.Choice(name="08:00 - 16:00 EST", value="08:00 - 16:00 EST"),
    app_commands.Choice(name="16:00 - 00:00 EST", value="16:00 - 00:00 EST"),
]

# --- PERSISTENCE ---
QUEUE_FILE = "queue.json"
CONFIG_FILE = "config.json"

work_queue = []
server_configs = {}
available_cooldowns = {}

def load_data():
    global work_queue, server_configs
    if os.path.exists(QUEUE_FILE):
        try:
            with open(QUEUE_FILE, "r") as f:
                work_queue = json.load(f)
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

def parse_audio_time(time_str):
    try:
        time_str = time_str.strip()
        parts = list(map(int, time_str.split(':')))
        if len(parts) == 3: h, m, s = parts
        elif len(parts) == 2: h, m, s = 0, parts[0], parts[1]
        else: return None
        return h * 3600 + m * 60 + s
    except:
        return None

def format_seconds(seconds):
    if seconds == 0: return "N/A"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"

def calculate_tats(file_type, total_seconds):
    fr_tat = 0
    sv_tat = 0
    overall_tat = 0

    if "HP" in file_type:
        overall_tat = 90 * 60 
        return {"FR": "N/A", "SV": "N/A", "OVERALL": "01:30:00"}
    else:
        fr_tat = total_seconds * 0.5
        sv_tat = total_seconds * 1.5
        overall_tat = total_seconds * 2.0
        
    return {
        "FR": format_seconds(fr_tat),
        "SV": format_seconds(sv_tat),
        "OVERALL": format_seconds(overall_tat)
    }

async def send_log(guild, content=None, embed=None, view=None):
    if not guild: return False
    guild_id_str = str(guild.id)
    if guild_id_str in server_configs:
        channel_id = server_configs[guild_id_str]
        channel = guild.get_channel(channel_id)
        if channel:
            try:
                await channel.send(content=content, embed=embed, view=view)
                return True
            except:
                return False
    return False

# --- ASSIGNMENT SYSTEM ---

class ReceiptModal(ui.Modal, title="Confirm File Receipt"):
    file_name_input = ui.TextInput(label="File Name", placeholder="Enter the exact file name...")

    async def on_submit(self, interaction: discord.Interaction):
        if self.view:
            self.view.stop()
        try:
            await interaction.message.edit(view=None)
        except:
            pass
        await interaction.response.send_message(f"🔖 {interaction.user.mention} confirms receipt of **{self.file_name_input.value}**")

class AssignmentConfirmView(ui.View):
    def __init__(self, assigned_user_id, channel, assigned_user_mention):
        super().__init__(timeout=300) # 5 Min Timeout
        self.assigned_user_id = assigned_user_id
        self.channel = channel
        self.assigned_user_mention = assigned_user_mention
        self.message = None 

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.assigned_user_id:
            await interaction.response.send_message("⛔ You cannot verify a file assigned to someone else.", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        # 1. Disable the buttons on the original message first
        if self.message:
            try:
                await self.message.edit(view=None)
            except:
                pass # Message might be deleted already

        text = f"⚠️ {self.assigned_user_mention} failed to confirm receipt of file within 5 minutes."

        # 2. Try to REPLY to the original message
        if self.message:
            try:
                await self.message.reply(text)
                return # Exit if reply was successful
            except:
                pass # Continue to fallback if reply failed (e.g. message deleted)

        # 3. Fallback: Send to channel normally if reply failed
        await self.channel.send(text)

    @ui.button(label="Received", style=discord.ButtonStyle.green, emoji="📥")
    async def received_btn(self, interaction: discord.Interaction, button: ui.Button):
        modal = ReceiptModal()
        modal.view = self 
        await interaction.response.send_modal(modal)

    @ui.button(label="Not Received", style=discord.ButtonStyle.red, emoji="❌")
    async def not_received_btn(self, interaction: discord.Interaction, button: ui.Button):
        self.stop()
        try:
            await interaction.message.edit(view=None)
        except:
            pass
        await interaction.response.send_message(f"🔖 {interaction.user.mention} has not received the file. Contact SWC.")

# --- RESTORED: ASSIGN VIEW FOR CONTEXT MENU ---
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
        await assign_logic(self.member, file_type, self.channel, interaction.user, file_name=None, audio_length=None)
        await interaction.followup.send(f"Assigned {file_type} to {self.member.display_name}", ephemeral=True)

# --- CORE ASSIGN LOGIC ---
async def assign_logic(user, file_type, channel, assigner, file_name=None, audio_length=None):
    time_tag = get_time_tag()
    global work_queue
    in_queue = False
    
    if any(item['user_id'] == user.id for item in work_queue):
        work_queue = [item for item in work_queue if item['user_id'] != user.id]
        save_queue()
        in_queue = True

    view = AssignmentConfirmView(user.id, channel, user.mention)
    msg_content = f"💼 {user.mention} has been assigned a **{file_type}** at {time_tag}."
    
    footer_text = "Please be mindful of your TATs."
    embed = None
    
    if file_name and audio_length:
        total_seconds = parse_audio_time(audio_length)
        if total_seconds:
            tats = calculate_tats(file_type, total_seconds)
            embed = discord.Embed(color=discord.Color.blue())
            embed.set_footer(text=f"TAT Info | Audio: {audio_length}\nFR: {tats['FR']} | SV: {tats['SV']} | OVERALL: {tats['OVERALL']}\n\n{footer_text}")
    
    if not embed:
        msg_content += f"\n\n{footer_text}"
    elif embed and not embed.footer.text:
         embed.set_footer(text=footer_text)

    public_msg = await channel.send(content=msg_content, embed=embed, view=view)
    view.message = public_msg 
    jump_url = public_msg.jump_url

    dm_content = (
        f"# Hello {user.mention}!\n"
        f"# You have been assigned a **{file_type}** at {time_tag}.\n\n" 
        f"## Please start on them immediately and [confirm receipt]({jump_url}) in the channel.\n\n"
        f"### REMINDERS:\n\n"
        f"- If no movement is observed on your file for at least 5 minutes, and if your file is at risk of breaching TAT, the SWCs may REASSIGN your file without prior notice.\n"
        f"- If you will take longer on a file, keep the SWCs properly appraised. Include your reasons and estimated TAT."
    )

    try:
        await user.send(dm_content)
    except discord.Forbidden:
        await channel.send(f"⚠️ {user.mention} (I cannot DM you) — You have been assigned a **{file_type}** at {time_tag}.")

    log_embed = discord.Embed(title="File Assigned", color=discord.Color.green())
    log_embed.add_field(name="Editor", value=user.mention, inline=False)
    log_embed.add_field(name="File Type", value=file_type, inline= False)
    if file_name: log_embed.add_field(name="File Name", value=file_name, inline=False)
    log_embed.add_field(name="Assigned By", value=assigner.mention, inline=False)
    log_embed.set_footer(text=f"Was in queue: {in_queue}")
    await send_log(channel.guild, embed=log_embed)

# --- MODALS ---
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
        log_embed = discord.Embed(title=f"{self.title} Request", color=discord.Color.orange())
        log_embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        log_embed.add_field(name="Editor", value=interaction.user.mention, inline=False)
        log_embed.add_field(name="Time Affected", value=self.time_affected.value, inline=False)
        log_embed.add_field(name="Change Type", value=self.change_type.value, inline=False)
        log_embed.add_field(name="Reason", value=self.reason.value, inline=False)
        await interaction.response.send_message(msg)
        await send_log(interaction.guild, embed=log_embed)

class TATDelayNoticeModal(ui.Modal, title="TAT Delay Notice"):
    file_name = ui.TextInput(label="File Name")
    reason = ui.TextInput(label="Reason for TAT delay", style=discord.TextStyle.paragraph)

    async def on_submit(self, interaction: discord.Interaction):
        msg = (
            f"## TAT Delay Notice\n"
            f"- **`EDITOR:`** {interaction.user.mention}\n"
            f"- **`FILE NAME:`** {self.file_name.value}\n"
            f"- **`REASON:`** {self.reason.value}"
        )
        log_embed = discord.Embed(title="TAT Delay Notice", color=discord.Color.red())
        log_embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        log_embed.add_field(name="Editor", value=interaction.user.mention, inline=False)
        log_embed.add_field(name="File Name", value=self.file_name.value, inline= False)
        log_embed.add_field(name="Reason", value=self.reason.value, inline=False)
        await interaction.response.send_message(msg)
        await send_log(interaction.guild, embed=log_embed)

class FileUpdateModal(ui.Modal, title="File Update"):
    file_name = ui.TextInput(label="File Name")
    update_text = ui.TextInput(label="File Update", style=discord.TextStyle.paragraph)
    status = ui.TextInput(label="File Status", placeholder="e.g. FDF, SV, FR")

    async def on_submit(self, interaction: discord.Interaction):
        msg = (
            f"## File Update\n"
            f"- **`EDITOR:`** {interaction.user.mention}\n"
            f"- **`FILE NAME:`** {self.file_name.value}\n"
            f"- **`FILE UPDATE:`** {self.update_text.value}\n"
            f"- **`FILE STATUS:`** {self.status.value}"
        )
        await interaction.response.send_message(msg)

class RevertRequestModal(ui.Modal, title="Revert Request"):
    file_name = ui.TextInput(label="File Name")
    file_link = ui.TextInput(label="File Link (Optional)", required=False)
    reason = ui.TextInput(label="Reason", style=discord.TextStyle.paragraph)
    notes = ui.TextInput(label="Notes (Optional)", style=discord.TextStyle.paragraph, required=False)

    async def on_submit(self, interaction: discord.Interaction):
        msg = (
            f"## Revert Request\n"
            f"- **`EDITOR:`** {interaction.user.mention}\n"
            f"- **`FILE NAME:`** {self.file_name.value}\n"
            f"- **`FILE LINK:`** {self.file_link.value if self.file_link.value else 'N/A'}\n"
            f"- **`REASON:`** {self.reason.value}\n"
            f"- **`NOTES:`** {self.notes.value if self.notes.value else 'N/A'}"
        )
        await interaction.channel.send(content=msg, view=RevertView(interaction.user, msg))
        await interaction.response.send_message("✅ Revert Request posted in this channel.", ephemeral=True)

class ReworkReportModal(ui.Modal, title="Rework Report"):
    file_info = ui.TextInput(label="File Name & Link")
    file_type = ui.TextInput(label="File Type", placeholder="e.g. Aiera Batch, Aiera Live, HP...")
    changes_req = ui.TextInput(label="Changes Requested (Number)", placeholder="0")
    changes_app = ui.TextInput(label="Changes Applied (Number)", placeholder="0")
    inv_changes = ui.TextInput(label="Invalid Changes", style=discord.TextStyle.paragraph)

    async def on_submit(self, interaction: discord.Interaction):
        msg = (
            f"## Rework Report\n"
            f"- **`EDITOR:`** {interaction.user.mention}\n"
            f"- **`FILE NAME & LINK:`** {self.file_info.value}\n"
            f"- **`FILE TYPE:`** {self.file_type.value}\n"
            f"- **`CHANGES REQUESTED:`** {self.changes_req.value}\n"
            f"- **`CHANGES APPLIED:`** {self.changes_app.value}\n"
            f"- **`INVALID CHANGES:`** {self.inv_changes.value}"
        )
        await interaction.channel.send(content=msg, view=ReworkView(interaction.user, msg))
        await interaction.response.send_message("✅ Rework Report posted in this channel.", ephemeral=True)

# --- VIEWS (BUTTONS) ---
class RevertView(ui.View):
    def __init__(self, target_user: discord.Member, original_msg_content: str):
        super().__init__(timeout=None) 
        self.target_user = target_user
        self.original_msg_content = original_msg_content

    async def send_dm(self, interaction, status):
        log_url = interaction.message.jump_url
        try:
            await self.target_user.send(f"Hello {self.target_user.mention}, your [revert request]({log_url}) was **{status}**.")
        except:
            await interaction.followup.send("❌ Could not DM user.", ephemeral=True)

    @ui.button(label="Revert", style=discord.ButtonStyle.green, custom_id="rev_approve")
    async def approve(self, interaction: discord.Interaction, button: ui.Button):
        if not is_swc(interaction): return await interaction.response.send_message("⛔ SWC Only", ephemeral=True)
        await interaction.response.defer()
        await self.send_dm(interaction, "APPROVED")
        new_content = self.original_msg_content.replace("## Revert Request", "## Revert Request [APPROVED]")
        self.clear_items()
        self.add_item(ui.Button(label="Reverted", style=discord.ButtonStyle.green, disabled=True))
        await interaction.message.edit(content=new_content, view=self)
        await interaction.followup.send("✅ Revert marked as DONE.", ephemeral=True)

    @ui.button(label="Deny", style=discord.ButtonStyle.red, custom_id="rev_deny")
    async def deny(self, interaction: discord.Interaction, button: ui.Button):
        if not is_swc(interaction): return await interaction.response.send_message("⛔ SWC Only", ephemeral=True)
        await interaction.response.defer()
        await self.send_dm(interaction, "DENIED")
        new_content = self.original_msg_content.replace("## Revert Request", "## Revert Request [DENIED]")
        self.clear_items()
        self.add_item(ui.Button(label="Denied", style=discord.ButtonStyle.red, disabled=True))
        await interaction.message.edit(content=new_content, view=self)
        await interaction.followup.send("❌ Revert marked as DENIED.", ephemeral=True)

class ReworkView(ui.View):
    def __init__(self, target_user: discord.Member, original_msg_content: str):
        super().__init__(timeout=None)
        self.target_user = target_user
        self.original_msg_content = original_msg_content

    async def send_dm(self, interaction, status):
        log_url = interaction.message.jump_url
        try:
            await self.target_user.send(f"Hello {self.target_user.mention}, your [rework report]({log_url}) was **{status}**.")
        except:
            await interaction.followup.send("❌ Could not DM user.", ephemeral=True)

    @ui.button(label="Validate", style=discord.ButtonStyle.green, custom_id="rew_valid")
    async def validate(self, interaction: discord.Interaction, button: ui.Button):
        if not is_swc(interaction): return await interaction.response.send_message("⛔ SWC Only", ephemeral=True)
        await interaction.response.defer()
        await self.send_dm(interaction, "VALIDATED")
        new_content = self.original_msg_content.replace("## Rework Report", "## Rework Report [VALIDATED]")
        self.clear_items()
        self.add_item(ui.Button(label="Validated", style=discord.ButtonStyle.green, disabled=True))
        await interaction.message.edit(content=new_content, view=self)
        await interaction.followup.send("✅ User notified (Validated).", ephemeral=True)

    @ui.button(label="Note", style=discord.ButtonStyle.blurple, custom_id="rew_note")
    async def note(self, interaction: discord.Interaction, button: ui.Button):
        if not is_swc(interaction): return await interaction.response.send_message("⛔ SWC Only", ephemeral=True)
        await interaction.response.defer()
        await self.send_dm(interaction, "NOTED")
        new_content = self.original_msg_content.replace("## Rework Report", "## Rework Report [NOTED]")
        self.clear_items()
        self.add_item(ui.Button(label="Noted", style=discord.ButtonStyle.blurple, disabled=True))
        await interaction.message.edit(content=new_content, view=self)
        await interaction.followup.send("📝 User notified (Noted).", ephemeral=True)

# --- HELP SYSTEM ---
class HelpSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Editor Commands", description="General commands for editors", emoji="📝"),
            discord.SelectOption(label="SWC Commands", description="Admin/SWC Only commands", emoji="🛡️"),
            discord.SelectOption(label="Forms & Requests", description="Various submission forms", emoji="📋"),
        ]
        super().__init__(placeholder="Select a category for help...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        embed = discord.Embed(title="Bot Help Menu", color=discord.Color.blue())
        
        if self.values[0] == "Editor Commands":
            embed.description = "**General Commands**"
            embed.add_field(name="/available", value="Add yourself to the work queue with a time block.", inline=False)
            embed.add_field(name="/optout", value="Remove yourself from the queue.", inline=False)
            embed.add_field(name="/tattimer", value="Calculate TAT deadlines for a specific file length.", inline=False)
            embed.add_field(name="Text Command: 'available'", value="Type `available` in chat to join queue (Legacy).", inline=False)
        
        elif self.values[0] == "SWC Commands":
            embed.description = "**SWC / Admin Commands**"
            embed.add_field(name="/assign", value="Assign a file to a user (starts TAT timer).", inline=False)
            embed.add_field(name="/queue", value="View the current waiting list.", inline=False)
            embed.add_field(name="/remove", value="Force remove a user from the queue.", inline=False)
            embed.add_field(name="/resetqueue", value="Clear the entire queue.", inline=False)
            embed.add_field(name="/askfileupdate", value="Ping a user asking for a status update.", inline=False)
            embed.add_field(name="/setlogchannel", value="Set where bot logs are sent.", inline=False)
            embed.add_field(name="Context Menus", value="Right Click User > Apps > Assign, Remove, etc.", inline=False)

        elif self.values[0] == "Forms & Requests":
            embed.description = "**Forms & Request Commands**"
            embed.add_field(name="/plannedavailability", value="Submit planned schedule changes.", inline=False)
            embed.add_field(name="/unplannedavailability", value="Submit unplanned schedule changes.", inline=False)
            embed.add_field(name="/tatdelay", value="Submit a TAT Delay Notice.", inline=False)
            embed.add_field(name="/fileupdate", value="Submit a general file update/status.", inline=False)
            embed.add_field(name="/revertrequest", value="Request a file revert (Requires SWC approval).", inline=False)
            embed.add_field(name="/reworkreport", value="Submit a rework report (Requires SWC validation).", inline=False)

        await interaction.response.edit_message(embed=embed, view=self.view)

class HelpView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.add_item(HelpSelect())

# --- BOT SETUP ---
class MyBot(commands.Bot):
    async def setup_hook(self):
        # We add the views here so they work after restart (Persistence)
        self.add_view(RevertView(None, ""))
        self.add_view(ReworkView(None, ""))

intents = discord.Intents.default()
intents.members = True # Ensure this is ON in Dev Portal
intents.message_content = True

# Disable default help command so we can make our own
bot = MyBot(command_prefix="fd!", intents=intents, help_command=None)

@bot.event
async def on_ready():
    load_data()
    print(f'Logged in as {bot.user}')

# --- HELP COMMANDS ---
@bot.tree.command(name="help", description="Show the help menu")
async def slash_help(interaction: discord.Interaction):
    embed = discord.Embed(title="Bot Help Menu", description="Select a category below to view commands.", color=discord.Color.blue())
    await interaction.response.send_message(embed=embed, view=HelpView(), ephemeral=True)

@bot.command(name="help")
async def text_help(ctx):
    embed = discord.Embed(title="Bot Help Menu", description="Select a category below to view commands.", color=discord.Color.blue())
    await ctx.send(embed=embed, view=HelpView())

@bot.command(name="sync")
async def sync(ctx, option: str = None):
    # Security check
    if not any(role.id in SWC_ROLE_IDS for role in ctx.author.roles) and not ctx.author.guild_permissions.administrator:
        await ctx.send("⛔ You do not have permission to sync.")
        return
    
    msg = await ctx.send("🔄 Processing sync...")
    try:
        if option == "clear":
            # This wipes commands to fix duplicates
            bot.tree.clear_commands(guild=ctx.guild)
            await bot.tree.sync(guild=ctx.guild)
            await msg.edit(content="✅ Local guild commands cleared. Now run `fd!sync` to load the fresh code.")
        else:
            # THIS IS THE FIX for "Synced 0"
            # It copies the global commands (defined in code) to the current guild
            bot.tree.copy_global_to(guild=ctx.guild)
            synced = await bot.tree.sync(guild=ctx.guild)
            await msg.edit(content=f"✅ Synced {len(synced)} command(s) to this server.")
    except Exception as e:
        await msg.edit(content=f"❌ Sync failed: {e}")

@bot.event
async def on_message(message):
    if message.author.bot: return

    # --- DUPLICATE "AVAILABLE" CHECK ---
    if message.content.strip().lower() == "available":
        existing_entry = next((item for item in work_queue if item['user_id'] == message.author.id), None)
        
        if existing_entry:
            try:
                await message.delete(delay=3) 
            except:
                pass
            
            queue_link = existing_entry.get('jump_url', 'the queue channel')
            warn_msg = (
                f"You are already in the [queue]({queue_link}). "
                f"Please avoid sending multiple requests for files and ensure you are requesting files within your assigned time block."
            )
            try:
                await message.author.send(warn_msg)
            except:
                pass 
            return 

        # --- TEXT COMMAND (Legacy Support) ---
        entry = {
            'user_id': message.author.id,
            'name': message.author.display_name,
            'time': int(datetime.now().timestamp()),
            'time_block': "Unspecified (Text Command)",
            'jump_url': message.jump_url
        }
        work_queue.append(entry)
        save_queue()
        
        await message.reply(f"👋🏼 {message.author.mention} is available for a file.\n-# - Requesting Editor's default Time Block is 00:00 - 08:00 EST).", mention_author=True)
        
        queue_pos = len(work_queue)
        time_tag = get_time_tag()
        dm_content = (
            f"# Hello {message.author.mention}!\n"
            f"# You are added to the queue at {time_tag}.\n\n"
            f"**IMPORTANT REMINDERS:**\n"
            f"- Audio project assignments are NOT preference-based.\n"
            f"- Queue numbers are **NOT a guarantee** that files will be assigned chronologically.\n"
            f"- Please be reminded of our *[Reminder on Eligibility for Audio Project Assignments](https://discord.com/channels/1391591320677519431/1391595956247728219/1450362680966774805).*\n"
            f"- All requests are still subject to review and approval. Outside of these default blocks, regular audio project assignments cannot be guaranteed, as assignments depend on volume projections, coverage needs, and performance-based prioritization.\n"
            f"- If your block is revised and approved, you may only receive audio project assignments if there is a surplus in the queue during your updated availability window."
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
@app_commands.describe(file_type="Type of file", audio_length="Duration as HH:MM:SS")
@app_commands.choices(file_type=FILE_CHOICES)
async def tattimer(interaction: discord.Interaction, file_type: app_commands.Choice[str], audio_length: str):
    total_seconds = parse_audio_time(audio_length)
    if total_seconds is None:
        await interaction.response.send_message("❌ Invalid format. Please use HH:MM:SS (e.g., 01:30:00)", ephemeral=True)
        return

    tats = calculate_tats(file_type.value, total_seconds)
    ah_decimal = total_seconds / 3600

    msg = (
        f"# TAT Calculator\n"
        f"**`File Type:`** {file_type.name}\n"
        f"**`Audio Length:`** {audio_length}\n"
        f"**`Audio Hour:`** {ah_decimal:.2f}\n"
        f"**`FR TAT:`** {tats['FR']}\n"
        f"__**`SV TAT:`** {tats['SV']}__\n" 
        f"**`OVERALL TAT:`** {tats['OVERALL']}\n\n"
        f"-# You can also use this Workflow Logger for TATs: https://fdeditor-workflowtimer.vercel.app/"
    )
    await interaction.response.send_message(msg, ephemeral=True)

@bot.tree.command(name="available", description="Add yourself to the work queue")
@app_commands.describe(time_block="Choose your default time block as indicated in the sheets")
@app_commands.choices(time_block=TIME_BLOCK_CHOICES)
async def available(interaction: discord.Interaction, time_block: app_commands.Choice[str]):
    last_used = available_cooldowns.get(interaction.user.id, 0)
    now_ts = datetime.now().timestamp()
    if now_ts - last_used < 600:
        await interaction.response.send_message("⏳ Please wait a moment before using this again.", ephemeral=True)
        return
    available_cooldowns[interaction.user.id] = now_ts

    existing_entry = next((item for item in work_queue if item['user_id'] == interaction.user.id), None)
    if existing_entry:
        queue_link = existing_entry.get('jump_url', 'the queue channel')
        warn_msg = (
            f"You are already in the [queue]({queue_link}). "
            f"Please avoid sending multiple requests for files and ensure you are requesting files within your assigned time block."
        )
        await interaction.response.send_message(warn_msg, ephemeral=True)
        return

    await interaction.response.send_message(f"👋🏼 {interaction.user.mention} is available for a file.\n-# - Requesting Editor's default Time Block is {time_block.value}.")
    msg = await interaction.original_response()
    
    work_queue.append({
        'user_id': interaction.user.id,
        'name': interaction.user.display_name,
        'time': int(datetime.now().timestamp()),
        'time_block': time_block.value,
        'jump_url': msg.jump_url
    })
    save_queue()
    
    queue_pos = len(work_queue)
    time_tag = get_time_tag()
    dm_content = (
        f"# Hello {interaction.user.mention}!\n"
        f"# You are added to the queue at {time_tag}.\n\n"
        f"**IMPORTANT REMINDERS:**\n"
        f"- Audio project assignments are NOT preference-based.\n"
        f"- Queue numbers are **NOT a guarantee** that files will be assigned chronologically.\n"
        f"- Please be reminded of our *[Reminder on Eligibility for Audio Project Assignments](https://discord.com/channels/1391591320677519431/1391595956247728219/1450362680966774805).*\n"
        f"- All requests are still subject to review and approval. Outside of these default blocks, regular audio project assignments cannot be guaranteed, as assignments depend on volume projections, coverage needs, and performance-based prioritization.\n"
        f"- If your block is revised and approved, you may only receive audio project assignments if there is a surplus in the queue during your updated availability window."
    )
    try:
        await interaction.user.send(dm_content)
    except:
        pass
        
    log_embed = discord.Embed(title="User Joined the Queue", description=f"{interaction.user.mention} joined the queue via command.", color=discord.Color.blue())
    log_embed.add_field(name="Time Block", value=time_block.value)
    await send_log(interaction.guild, embed=log_embed)

@bot.tree.command(name="optout", description="Remove yourself from the queue")
async def optout(interaction: discord.Interaction):
    global work_queue
    original_len = len(work_queue)
    work_queue = [item for item in work_queue if item['user_id'] != interaction.user.id]
    save_queue()
    if len(work_queue) < original_len:
        await interaction.response.send_message("You have removed yourself from the queue.", ephemeral=True)
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
    
    await interaction.response.defer(ephemeral=True)

    if not work_queue:
        await interaction.followup.send("The queue is empty.", ephemeral=True)
        return
    
    current_time_tag = get_time_tag()
    embed = discord.Embed(title="Current Work Queue", color=discord.Color.blue())
    desc = f"**As of:** {current_time_tag}\n\n"
    
    display_limit = 15
    for idx, item in enumerate(work_queue[:display_limit], 1):
        member = interaction.guild.get_member(item['user_id'])
        name_display = member.mention if member else item['name']
        tb = item.get('time_block', 'N/A')
        desc += f"**{idx}.** {name_display} | Block: `{tb}` | <t:{item['time']}:R>\n"
        
    if len(work_queue) > display_limit:
        desc += f"\n...and {len(work_queue) - display_limit} more."
        
    embed.description = desc
    await interaction.followup.send(embed=embed, ephemeral=True)

@bot.tree.command(name="remove", description="Remove a specific user from the queue")
@app_commands.default_permissions(administrator=True)
@app_commands.guild_only() 
async def remove_user(interaction: discord.Interaction, member: discord.Member):
    if not is_swc(interaction):
        await interaction.response.send_message("⛔ SWC Access Only.", ephemeral=True)
        return
    global work_queue
    
    found = False
    for item in work_queue:
        if item['user_id'] == member.id:
            found = True
            break
            
    if not found:
        await interaction.response.send_message(f"❌ {member.mention} is not in the queue.", ephemeral=True)
        return

    work_queue = [item for item in work_queue if item['user_id'] != member.id]
    save_queue()
    await interaction.response.send_message(f"✔️ Removed {member.mention} from the queue.", ephemeral=True)
    
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
    
    log_embed = discord.Embed(description=f"🔄 Queue reset by {interaction.user.mention}", color=discord.Color.red())
    await send_log(interaction.guild, embed=log_embed)

@bot.tree.command(name="assign", description="Assign a file to a user")
@app_commands.describe(file_name="Optional: Name of the file", audio_length="Optional: HH:MM:SS")
@app_commands.choices(file_type=FILE_CHOICES)
@app_commands.default_permissions(administrator=True)
@app_commands.guild_only() 
async def assign(interaction: discord.Interaction, member: discord.Member, file_type: app_commands.Choice[str], file_name: str = None, audio_length: str = None):
    if not is_swc(interaction):
        await interaction.response.send_message("⛔ SWC Access Only.", ephemeral=True)
        return
    
    await interaction.response.defer(ephemeral=False)
    await assign_logic(member, file_type.value, interaction.channel, interaction.user, file_name, audio_length)
    await interaction.followup.send("Assignment processed.", ephemeral=False)

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
        await member.send(f"⚠️ {member.mention}, your file has been REASSIGNED due to inactivity.")
        await interaction.response.send_message(f"✅ Notification sent to {member.mention}.", ephemeral=True)
        
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
    await interaction.response.send_modal(TATDelayNoticeModal())

@bot.tree.command(name="fileupdate", description="Provide a file update")
async def file_update(interaction: discord.Interaction):
    await interaction.response.send_modal(FileUpdateModal())

# --- CONTEXT MENU COMMANDS ---

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
    
    found = False
    for item in work_queue:
        if item['user_id'] == member.id:
            found = True
            break
            
    if not found:
        await interaction.response.send_message(f"❌ {member.mention} is not in the queue.", ephemeral=True)
        return

    work_queue = [item for item in work_queue if item['user_id'] != member.id]
    save_queue()
    await interaction.response.send_message(f"✔️ Removed {member.mention} from the queue.", ephemeral=True)
    
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

@bot.tree.context_menu(name="Add to Queue")
@app_commands.default_permissions(administrator=True)
@app_commands.guild_only()
async def context_add_queue(interaction: discord.Interaction, member: discord.Member):
    if not is_swc(interaction):
        await interaction.response.send_message("⛔ SWC Access Only.", ephemeral=True)
        return

    global work_queue
    if any(item['user_id'] == member.id for item in work_queue):
        await interaction.response.send_message(f"{member.mention} is already in the queue!", ephemeral=True)
        return

    default_tb = "Assigned by Admin"

    work_queue.append({
        'user_id': member.id,
        'name': member.display_name,
        'time': int(datetime.now().timestamp()),
        'time_block': default_tb
    })
    save_queue()

    await interaction.response.send_message(f"👋🏼 {member.mention} is added to the queue.", ephemeral=True)

    queue_pos = len(work_queue)
    time_tag = get_time_tag()
    dm_content = (
        f"You are added to the [Queue Status](https://discord.com/channels/{interaction.guild_id}). As of {time_tag}, you are at queue #{queue_pos}.\n\n"
        f"**IMPORTANT REMINDERS:**\n"
        f"- Audio project assignments are NOT preference-based.\n"
        f"- Queue numbers are **NOT a guarantee** that files will be assigned chronologically.\n"
        f"- Please be reminded of our *[Reminder on Eligibility for Audio Project Assignments](https://discord.com/channels/1391591320677519431/1391595956247728219/1450362680966774805).*"
    )
    try:
        await member.send(dm_content)
    except:
        pass

    log_embed = discord.Embed(title="User Added to Queue (Admin)", color=discord.Color.blue())
    log_embed.add_field(name="User", value=member.mention, inline=True)
    log_embed.add_field(name="Added By", value=interaction.user.mention, inline=True)
    await send_log(interaction.guild, embed=log_embed)

@bot.tree.command(name="revertrequest", description="Submit a request for file revert")
@app_commands.guild_only() 
async def revert_request(interaction: discord.Interaction):
    await interaction.response.send_modal(RevertRequestModal())

@bot.tree.command(name="reworkreport", description="Submit a report for file rework")
@app_commands.guild_only() 
async def rework_report(interaction: discord.Interaction):
    await interaction.response.send_modal(ReworkReportModal())

# START
keep_alive()
if TOKEN:
    bot.run(TOKEN)

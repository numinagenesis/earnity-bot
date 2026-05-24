import discord
from discord import app_commands
from discord.ext import tasks
import requests
import os
from dotenv import load_dotenv
import asyncio

load_dotenv()

# ── CONFIG ──────────────────────────────────────────────
SUPABASE_URL  = os.getenv("SUPABASE_URL")
SUPABASE_KEY  = os.getenv("SUPABASE_KEY")
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

# ── RANK MAPPINGS ────────────────────────────────────────
RANK_ROLE_MAP = {
    "SSS": 1500123701406863410,
    "SS":  1500123445063581797,
    "S":   1500135229778825358,
    "A":   1500135270878679241,
    "B":   1500135308555980940,
    "C":   1500137961457717420,
    "D":   1500138038800552138,
    "E":   1500122986206855198,
}
ALL_RANK_ROLE_IDS = set(RANK_ROLE_MAP.values())
WAITING_ROOM_ROLE = "Waiting Room"

ITEM_EMOJIS = {
    "shard_fire":         "🔥 Shard Fire",
    "shard_nature":       "🌿 Shard Nature",
    "shard_wind":         "💨 Shard Wind",
    "shard_water":        "🌊 Shard Water",
    "shard_lightning":    "⚡ Shard Lightning",
    "shard_rock":         "🪨 Shard Rock",
    "elemental_fire":     "🔥 Fire Elemental",
    "elemental_nature":   "🌿 Nature Elemental",
    "elemental_wind":     "💨 Wind Elemental",
    "elemental_water":    "🌊 Water Elemental",
    "elemental_lightning":"⚡ Lightning Elemental",
    "elemental_rock":     "🪨 Rock Elemental",
    "hp_potion":          "❤️ HP Potion",
    "mp_potion":          "💙 MP Potion",
    "nuke":               "💣 Nuke",
    "drain":              "🌀 Drain",
    "rug":                "🪤 Rug",
    "shield":             "🛡️ Shield",
}

# ── SUPABASE HELPERS ─────────────────────────────────────
def sb_get(table, params):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    res = requests.get(url, headers=HEADERS, params=params)
    return res.json()

def calculate_rank(score: int) -> str:
    if score >= 9000: return "SSS"
    elif score >= 6000: return "SS"
    elif score >= 3500: return "S"
    elif score >= 2000: return "A"
    elif score >= 1000: return "B"
    elif score >= 500:  return "C"
    elif score >= 100:  return "D"
    else: return "E"

def fetch_player(discord_id: str):
    try:
        data = sb_get("profiles", {
            "discord_id": f"eq.{discord_id}",
            "select": "id,username,discord_id,contribution_score,guild_id,guilds!fk_profiles_guild(id,name,guild_master_id)",
            "limit": 1
        })
        return data[0] if data else None
    except Exception:
        return None

def fetch_all_verified_players():
    all_players = []
    limit, offset = 1000, 0
    while True:
        try:
            data = sb_get("profiles", {
                "discord_id": "not.is.null",
                "select": "id,discord_id,username,contribution_score,guild_id,guilds!fk_profiles_guild(id,name,guild_master_id)",
                "limit": limit,
                "offset": offset
            })
            if not isinstance(data, list) or not data:
                break
            all_players.extend(data)
            if len(data) < limit:
                break
            offset += limit
        except Exception:
            break
    print(f"[DB] Fetched {len(all_players)} verified players")
    return all_players

def get_inventory(user_id: str) -> list:
    try:
        data = sb_get("inventories", {
            "user_id": f"eq.{user_id}",
            "select": "item_type,quantity",
            "quantity": "gt.0"
        })
        return [i for i in data if i.get("quantity", 0) > 0] if isinstance(data, list) else []
    except Exception:
        return []

def call_transfer(sender_id, receiver_id, item_type, quantity) -> dict:
    try:
        res = requests.post(
            f"{SUPABASE_URL}/rest/v1/rpc/transfer_item",
            headers=HEADERS,
            json={"p_sender_id": sender_id, "p_receiver_id": receiver_id,
                  "p_item_type": item_type, "p_quantity": quantity}
        )
        return res.json()
    except Exception as e:
        return {"success": False, "message": str(e)}

def pick_emoji(name: str) -> str:
    n = name.lower()
    if any(w in n for w in ["fire", "flame", "firethernity"]): return "🔥"
    elif any(w in n for w in ["shadow", "dark", "night"]): return "🌑"
    elif any(w in n for w in ["storm", "thunder", "闪电"]): return "⚡"
    elif any(w in n for w in ["dragon"]): return "🐉"
    elif any(w in n for w in ["hunt", "hunter"]): return "🏹"
    elif any(w in n for w in ["sea", "ocean", "wave", "seaway"]): return "🌊"
    elif any(w in n for w in ["matrix", "cyber", "tech", "chain", "hubchain"]): return "💻"
    elif any(w in n for w in ["nomad", "wander"]): return "🧭"
    elif any(w in n for w in ["insider", "elite"]): return "👁️"
    elif any(w in n for w in ["adorable", "angel"]): return "✨"
    elif any(w in n for w in ["salva", "war", "battle"]): return "⚔️"
    elif any(w in n for w in ["富", "趋势", "web3", "致富"]): return "💰"
    elif any(w in n for w in ["mei", "meigui", "rose"]): return "🌹"
    elif any(w in n for w in ["jun", "sun", "工会"]): return "☀️"
    elif any(w in n for w in ["dajjal", "chaos", "demon"]): return "👿"
    else: return "🏰"

# ── BOT SETUP ────────────────────────────────────────────
intents = discord.Intents.default()
intents.members = True

class Bot(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()

bot = Bot()

# ── ROLE ASSIGNMENT ──────────────────────────────────────
async def assign_roles_to_member(member: discord.Member, player: dict) -> list[str]:
    server   = member.guild
    assigned = []
    roles_to_add = []

    # Rank role
    score = player.get("contribution_score") or 0
    rank_role_id = RANK_ROLE_MAP.get(calculate_rank(score))
    if rank_role_id:
        rank_role = server.get_role(rank_role_id)
        if rank_role:
            roles_to_add.append(rank_role)
            assigned.append(rank_role.name)

    # Guild role + master role
    guild_data = player.get("guilds")
    if guild_data:
        guild_name = guild_data.get("name")
        if guild_name:
            guild_role = discord.utils.get(server.roles, name=guild_name)
            if guild_role:
                roles_to_add.append(guild_role)
                assigned.append(guild_name)

            if guild_data.get("guild_master_id") == player.get("id"):
                master_role = discord.utils.get(server.roles, name=f"{guild_name} | Master")
                if master_role:
                    roles_to_add.append(master_role)
                    assigned.append(master_role.name)

    # Remove Waiting Room
    waiting = discord.utils.get(server.roles, name=WAITING_ROOM_ROLE)
    if waiting and waiting in member.roles:
        await member.remove_roles(waiting, reason="Verified")

    if roles_to_add:
        await member.add_roles(*roles_to_add, reason="Role sync")

    return assigned

# ── UI CLASSES ───────────────────────────────────────────
class RecipientModal(discord.ui.Modal):
    def __init__(self, sender_profile):
        super().__init__(title="Who do you want to send to?")
        self.sender_profile = sender_profile
        self.recipient_input = discord.ui.TextInput(
            label="Recipient username (in-game)",
            placeholder="e.g. vegmerisa",
            min_length=1,
            max_length=50
        )
        self.add_item(self.recipient_input)

    async def on_submit(self, interaction: discord.Interaction):
        recipient_name = self.recipient_input.value.strip()

        # Find recipient by username
        try:
            data = sb_get("profiles", {
                "username": f"eq.{recipient_name}",
                "select": "id,username,discord_id,contribution_score,guild_id",
                "limit": 1
            })
            receiver_profile = data[0] if data else None
        except Exception:
            receiver_profile = None

        if not receiver_profile:
            await interaction.response.send_message(
                f"❌ Player `{recipient_name}` not found.", ephemeral=True
            )
            return

        if receiver_profile["id"] == self.sender_profile["id"]:
            await interaction.response.send_message("❌ You can't transfer to yourself.", ephemeral=True)
            return

        # Get sender inventory
        inventory = get_inventory(self.sender_profile["id"])
        if not inventory:
            await interaction.response.send_message("❌ Your inventory is empty.", ephemeral=True)
            return

        # Get receiver inventory
        recv_inventory = get_inventory(receiver_profile["id"])

        # Build embed showing both inventories
        embed = discord.Embed(title="📦 Item Transfer", color=0x5865f2)
        embed.add_field(
            name=f"📤 Your Inventory ({self.sender_profile['username']})",
            value="\n".join(
                f"{ITEM_EMOJIS.get(i['item_type'], i['item_type'])} × {i['quantity']}"
                for i in inventory
            ) or "Empty",
            inline=True
        )
        embed.add_field(
            name=f"📥 {receiver_profile['username']}'s Inventory",
            value="\n".join(
                f"{ITEM_EMOJIS.get(i['item_type'], i['item_type'])} × {i['quantity']}"
                for i in recv_inventory
            ) or "Empty",
            inline=True
        )
        embed.set_footer(text="Select an item to send ↓")

        await interaction.response.send_message(
            embed=embed,
            view=ItemSelectView(self.sender_profile, inventory, receiver_profile),
            ephemeral=True
        )


class TransferStartView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Transfer", style=discord.ButtonStyle.primary, custom_id="transfer_start", emoji="📦")
    async def start_transfer(self, interaction: discord.Interaction, button: discord.ui.Button):
        sender_profile = fetch_player(str(interaction.user.id))
        if not sender_profile:
            await interaction.response.send_message("❌ Your account isn't linked. Run /verify first.", ephemeral=True)
            return
        await interaction.response.send_modal(RecipientModal(sender_profile))


class TransferConfirmView(discord.ui.View):
    def __init__(self, sender_profile, receiver_profile, item_type, quantity):
        super().__init__(timeout=60)
        self.sender_profile   = sender_profile
        self.receiver_profile = receiver_profile
        self.item_type        = item_type
        self.quantity         = quantity

    @discord.ui.button(label="✅ Confirm", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.sender_profile.get("discord_id"):
            await interaction.response.send_message("❌ Only the sender can confirm.", ephemeral=True)
            return
        for child in self.children:
            child.disabled = True
        await interaction.message.edit(view=self)
        result = call_transfer(self.sender_profile["id"], self.receiver_profile["id"], self.item_type, self.quantity)
        if result.get("success"):
            embed = discord.Embed(title="✅ Transfer Complete", color=0x00ff88)
            embed.add_field(name="Item", value=ITEM_EMOJIS.get(self.item_type, self.item_type), inline=True)
            embed.add_field(name="Qty", value=str(self.quantity), inline=True)
            embed.add_field(name="From", value=self.sender_profile["username"], inline=True)
            embed.add_field(name="To", value=self.receiver_profile["username"], inline=True)
            embed.add_field(name="Remaining", value=str(result.get("sender_remaining", 0)), inline=True)
            embed.set_footer(text="Earnity ︱ Item Transfer")
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.response.send_message(f"❌ {result.get('message', 'Transfer failed')}", ephemeral=True)

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.sender_profile.get("discord_id"):
            await interaction.response.send_message("❌ Only the sender can cancel.", ephemeral=True)
            return
        for child in self.children:
            child.disabled = True
        await interaction.message.edit(view=self)
        await interaction.response.send_message("❌ Transfer cancelled.", ephemeral=True)


class ItemSelect(discord.ui.Select):
    def __init__(self, inventory, receiver_profile):
        self.receiver_profile = receiver_profile
        options = [
            discord.SelectOption(
                label=ITEM_EMOJIS.get(i["item_type"], i["item_type"]),
                value=i["item_type"],
                description=f"Owned: {i['quantity']}"
            ) for i in inventory
        ]
        super().__init__(placeholder="Select an item...", options=options[:25])

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(
            QuantityModal(self.view.sender_profile, self.receiver_profile, self.values[0])
        )


class ItemSelectView(discord.ui.View):
    def __init__(self, sender_profile, inventory, receiver_profile):
        super().__init__(timeout=60)
        self.sender_profile = sender_profile
        self.add_item(ItemSelect(inventory, receiver_profile))


class QuantityModal(discord.ui.Modal):
    def __init__(self, sender_profile, receiver_profile, item_type):
        super().__init__(title="How many to transfer?")
        self.sender_profile   = sender_profile
        self.receiver_profile = receiver_profile
        self.item_type        = item_type
        self.qty_input = discord.ui.TextInput(label="Quantity", placeholder="e.g. 1", min_length=1, max_length=5)
        self.add_item(self.qty_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            qty = int(self.qty_input.value)
            if qty < 1: raise ValueError
        except ValueError:
            await interaction.response.send_message("❌ Invalid quantity.", ephemeral=True)
            return
        embed = discord.Embed(title="📦 Confirm Transfer", color=0xf5a623)
        embed.add_field(name="From", value=self.sender_profile["username"], inline=True)
        embed.add_field(name="To", value=self.receiver_profile["username"], inline=True)
        embed.add_field(name="Item", value=ITEM_EMOJIS.get(self.item_type, self.item_type), inline=False)
        embed.add_field(name="Quantity", value=str(qty), inline=True)
        embed.set_footer(text="This action cannot be undone • Expires in 60s")
        await interaction.response.send_message(
            embed=embed,
            view=TransferConfirmView(self.sender_profile, self.receiver_profile, self.item_type, qty),
            ephemeral=True
        )

# ── SLASH COMMANDS ───────────────────────────────────────
@bot.tree.command(name="verify", description="Link your game account and receive your roles")
async def verify(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    discord_id = str(interaction.user.id)
    player = fetch_player(discord_id)
    if not player:
        await interaction.followup.send(
            "❌ **Account not linked.**\n\nYour Discord isn't connected to a game profile.\n"
            "Go to earnity.fun → Login with Discord, then try again.",
            ephemeral=True
        )
        return
    try:
        assigned = await assign_roles_to_member(interaction.user, player)
        role_list = "\n".join(f"• {r}" for r in assigned) if assigned else "No new roles"
        await interaction.followup.send(
            f"✅ **Verified as `{player['username']}`**\n\nRoles assigned:\n{role_list}",
            ephemeral=True
        )
    except discord.Forbidden:
        await interaction.followup.send("❌ Bot lacks permission to assign roles. Contact an admin.", ephemeral=True)


@bot.tree.command(name="syncall", description="[Admin] Force sync all verified members")
@app_commands.default_permissions(administrator=True)
async def syncall(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    players = fetch_all_verified_players()
    player_map = {p["discord_id"]: p for p in players if p.get("discord_id")}
    count, failed = 0, 0
    async for member in interaction.guild.fetch_members(limit=None):
        if member.bot:
            continue
        player = player_map.get(str(member.id))
        if not player:
            continue
        try:
            await assign_roles_to_member(member, player)
            count += 1
            await asyncio.sleep(1.0)
        except Exception:
            failed += 1
    if not auto_sync.is_running():
        auto_sync.start()
    await interaction.followup.send(f"✅ Synced **{count}** members. Failed: **{failed}**", ephemeral=True)


@bot.tree.command(name="whois", description="[Admin] Check a member's game profile")
@app_commands.default_permissions(administrator=True)
async def whois(interaction: discord.Interaction, member: discord.Member):
    await interaction.response.defer(ephemeral=True)
    player = fetch_player(str(member.id))
    if not player:
        await interaction.followup.send(f"❌ {member.mention} has no linked game account.", ephemeral=True)
        return
    guild_name = player.get("guilds", {}).get("name", "None") if player.get("guilds") else "None"
    score = player.get("contribution_score", 0)
    rank = calculate_rank(score)
    await interaction.followup.send(
        f"👤 **{player['username']}**\nRank: `{rank}` ({score} pts) | Guild: `{guild_name}`",
        ephemeral=True
    )


@bot.tree.command(name="transfer", description="Send items to another player")
@app_commands.describe(recipient="The Discord user to send items to")
async def transfer(interaction: discord.Interaction, recipient: discord.Member):
    await interaction.response.defer(ephemeral=True)
    if interaction.user.id == recipient.id:
        await interaction.followup.send("❌ You can't transfer to yourself.", ephemeral=True)
        return
    sender_profile = fetch_player(str(interaction.user.id))
    if not sender_profile:
        await interaction.followup.send("❌ Your account isn't linked. Run /verify first.", ephemeral=True)
        return
    receiver_profile = fetch_player(str(recipient.id))
    if not receiver_profile:
        await interaction.followup.send("❌ Recipient has no linked game account.", ephemeral=True)
        return
    inventory = get_inventory(sender_profile["id"])
    if not inventory:
        await interaction.followup.send("❌ Your inventory is empty.", ephemeral=True)
        return
    embed = discord.Embed(
        title="📦 Item Transfer",
        description=f"Sending to **{receiver_profile['username']}**\nSelect an item from your inventory:",
        color=0x5865f2
    )
    await interaction.followup.send(embed=embed, view=ItemSelectView(sender_profile, inventory, receiver_profile), ephemeral=True)


@bot.tree.command(name="setupguilds", description="[Admin] Create all guild roles and channels")
@app_commands.default_permissions(administrator=True)
async def setupguilds(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    try:
        data = sb_get("guilds", {"select": "id,name", "limit": 500})
    except Exception as e:
        await interaction.followup.send(f"❌ DB error: {e}", ephemeral=True)
        return

    server = interaction.guild
    everyone = server.default_role
    created_roles, created_channels, skipped = [], [], []

    category = None
    for cat in server.categories:
        if "GUILD" in cat.name.upper() and "WAR" in cat.name.upper():
            category = cat
            break
    if not category:
        category = await server.create_category("🛡️ 【 ɢᴜɪʟᴅ ᴡᴀʀ ʀᴏᴏᴍꜱ 】")

    for g in data:
        guild_name = g["name"]
        emoji = pick_emoji(guild_name)

        role = discord.utils.get(server.roles, name=guild_name)
        if not role:
            role = await server.create_role(name=guild_name, reason="Guild setup")
            created_roles.append(f"{guild_name} → {role.id}")
        else:
            skipped.append(f"{guild_name} → {role.id}")

        master_role_name = f"{guild_name} | Master"
        if not discord.utils.get(server.roles, name=master_role_name):
            mr = await server.create_role(name=master_role_name, reason="Guild master setup")
            created_roles.append(f"{master_role_name} → {mr.id}")
        await asyncio.sleep(0.5)

        if not discord.utils.get(server.text_channels, topic=f"guild:{guild_name}"):
            overwrites = {
                everyone: discord.PermissionOverwrite(view_channel=False),
                role: discord.PermissionOverwrite(view_channel=True, send_messages=True),
                server.me: discord.PermissionOverwrite(view_channel=True)
            }
            await server.create_text_channel(
                name=f"╰─➤ {emoji} ︱ {guild_name}",
                category=category,
                overwrites=overwrites,
                topic=f"guild:{guild_name}",
                reason="Guild setup"
            )
            created_channels.append(guild_name)
        await asyncio.sleep(0.7)

    with open("guild_roles.txt", "w") as f:
        f.write("GUILD ROLE IDs\n==============\n")
        for r in created_roles + skipped:
            f.write(r + "\n")

    await interaction.followup.send(
        f"✅ **Guild Setup Done!**\n\n"
        f"Roles created: **{len(created_roles)}**\n"
        f"Channels created: **{len(created_channels)}**\n"
        f"Already existed: **{len(skipped)}**",
        ephemeral=True
    )


@bot.tree.command(name="setuptransfer", description="[Admin] Create transfer channel with persistent embed")
@app_commands.default_permissions(administrator=True)
async def setuptransfer(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    server = interaction.guild
    everyone = server.default_role

    category = discord.utils.get(server.categories, name="【 MARKETPLACE 】")
    if not category:
        category = await server.create_category("【 MARKETPLACE 】")

    channel_name = "╰─➤ 📦 ︱ item-transfer"
    channel = discord.utils.get(server.text_channels, name=channel_name)
    if not channel:
        channel = await server.create_text_channel(
            name=channel_name,
            category=category,
            overwrites={
                everyone: discord.PermissionOverwrite(view_channel=True, send_messages=False),
                server.me: discord.PermissionOverwrite(view_channel=True, send_messages=True)
            }
        )

    embed = discord.Embed(
        title="📦 Item Transfer",
        description=(
            "Send items directly to another player for free.\n"
            "No coins needed — just their Discord tag.\n\n"
            "**How to transfer:**\n"
            "• Click the button or use `/transfer @user`\n"
            "• Select your item and quantity\n"
            "• Confirm to complete"
        ),
        color=0x5865f2
    )
    embed.set_footer(text="Earnity ︱ Item Transfer System")
    await channel.send(embed=embed, view=TransferStartView())
    await interaction.followup.send(f"✅ Transfer channel created: {channel.mention}", ephemeral=True)


# ── AUTO SYNC ────────────────────────────────────────────
@tasks.loop(hours=6)
async def auto_sync():
    print("[Sync] Starting scheduled role sync...")
    players = fetch_all_verified_players()
    player_map = {p["discord_id"]: p for p in players if p.get("discord_id")}
    count = 0
    for discord_guild in bot.guilds:
        async for member in discord_guild.fetch_members(limit=None):
            if member.bot:
                continue
            player = player_map.get(str(member.id))
            if not player:
                continue
            try:
                await assign_roles_to_member(member, player)
                count += 1
                await asyncio.sleep(1.0)
            except Exception as e:
                print(f"[Sync] Failed for {member.id}: {e}")
    print(f"[Sync] Done. Synced {count} members.")


# ── EVENTS ───────────────────────────────────────────────
@bot.event
async def on_ready():
    print(f"✅ Bot online as {bot.user}")
    print("[Info] Use /syncall to sync manually. Auto-sync runs every 6h after first /syncall.")
    bot.add_view(TransferStartView())


@bot.event
async def on_member_join(member: discord.Member):
    player = fetch_player(str(member.id))
    if player:
        try:
            await assign_roles_to_member(member, player)
            print(f"[AutoVerify] {member.name} verified on join")
        except Exception as e:
            print(f"[AutoVerify] Failed for {member.name}: {e}")
    else:
        waiting = discord.utils.get(member.guild.roles, name=WAITING_ROOM_ROLE)
        if waiting:
            await member.add_roles(waiting)


bot.run(DISCORD_TOKEN)

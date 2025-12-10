# gacha_main.py (FINAL LOGIC IMPLEMENTATION with updated loot pools and PITY SYSTEM)
import discord
from discord.ext import commands
import sqlite3
import random
import time
from discord import app_commands

# Assuming bot_config is available and defined elsewhere
from bot_config import GACHA_CHANNEL_ID, MODERATOR_ROLE_IDS, DB_NAME 

# --- LOOT POOLS & CONSTANTS ---
RATE_5_STAR = 0.006  # 0.6% base rate
RATE_4_STAR = 0.05   # 5.0% base rate
PITY_5_STAR_HARD = 60 # New Hard Pity at 60 pulls
PITY_30_CHANCE = 0.5 # 50% chance at pull 30

# UPDATED: Loot table based on the new structure provided (using integer keys for logic)
LOOT_TABLE = {
    3: [
        "Scrap Grade Weapon", "Scrap Grade Armor", 
        "50 XP Crystal", "100 XP Crystal", 
        "10,000 Crowns", "5 Totems (Tamer)", "6 VP Items (Forager)"
    ],
    4: [
        "Named Grade Weapon", "Named Grade Armor",
        "250 XP Crystal", "25,000 Crowns",
        "10 Totems (Tamer)", "15 VP Items (Forager)"
    ],
    5: [
        "Exalted Grade Weapon", "Exalted Grade Armor", "20% XP Multiplier (1 Week)",
        "500 XP Crystal", "50,000 Crowns",
        "20 Totems (Tamer)", "25 VP Items (Forager)"
    ]
}

# Mapping rarity to a color for the embed
RARITY_COLORS = {
    5: 0xFFD700, # Gold
    4: 0xADD8E6, # Light Blue
    3: 0x90EE90, # Light Green
}

RARITY_EMOJI = {
    5: "🌟",
    4: "🔸",
    3: "▪️",
}

# --- DATABASE HELPERS ---
def _get_conn():
    return sqlite3.connect(DB_NAME)

def get_user_pity_data(user_id):
    conn = _get_conn()
    try:
        c = conn.cursor()
        c.execute("SELECT * FROM pity WHERE user_id = ?", (user_id,))
        data = c.fetchone()
        if data:
            return {"pity_5_star": data[1], "pity_4_star": data[2], "total_pulls": data[3]}
        return {"pity_5_star": 0, "pity_4_star": 0, "total_pulls": 0}
    finally:
        conn.close()

def update_pity_data(user_id, pity_5_star, pity_4_star, total_pulls):
    conn = _get_conn()
    try:
        c = conn.cursor()
        c.execute("""
            INSERT INTO pity (user_id, pity_5_star, pity_4_star, total_pulls)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                pity_5_star = excluded.pity_5_star,
                pity_4_star = excluded.pity_4_star,
                total_pulls = excluded.total_pulls
        """, (user_id, pity_5_star, pity_4_star, total_pulls))
        conn.commit()
    finally:
        conn.close()

def add_item_to_inventory(user_id, item_name):
    conn = _get_conn()
    try:
        c = conn.cursor()
        c.execute("""
            INSERT INTO inventory (user_id, item_name, quantity)
            VALUES (?, ?, 1)
            ON CONFLICT(user_id, item_name) DO UPDATE SET
                quantity = quantity + 1
        """, (user_id, item_name))
        conn.commit()
    finally:
        conn.close()

def log_pull_history(user_id, item_name, rarity):
    conn = _get_conn()
    timestamp = int(time.time())
    try:
        c = conn.cursor()
        c.execute("""
            INSERT INTO pull_history (user_id, item_name, rarity, timestamp)
            VALUES (?, ?, ?, ?)
        """, (user_id, item_name, rarity, timestamp))
        conn.commit()
    finally:
        conn.close()

# --- NEW: Retrieve Inventory Data ---
def get_user_inventory(user_id):
    conn = _get_conn()
    try:
        c = conn.cursor()
        # Fetch all items and their quantities for the user
        c.execute("SELECT item_name, quantity FROM inventory WHERE user_id = ? ORDER BY quantity DESC, item_name ASC", (user_id,))
        return c.fetchall() # Returns a list of (item_name, quantity) tuples
    finally:
        conn.close()

# --- NEW: Retrieve Pull History Data ---
def get_user_history(user_id, limit=10):
    conn = _get_conn()
    try:
        c = conn.cursor()
        # Fetch recent pull history, limited to `limit`
        c.execute("SELECT item_name, rarity, timestamp FROM pull_history WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?", (user_id, limit))
        return c.fetchall() # Returns a list of (item_name, rarity, timestamp) tuples
    finally:
        conn.close()


# --- CORE GACHA PULL LOGIC (UNCHANGED) ---

def pull_gacha_single(user_id, pity_data):
    # Use pity_5_star as the single main pity counter since last 5-star
    pity = pity_data["pity_5_star"]
    pity += 1 # 1. Increment pity at start of pull

    rarity = 3
    
    # 2. HARD PITY (60)
    if pity >= PITY_5_STAR_HARD:
        rarity = 5
        
    # 3. 50/50 CHANCE (30)
    elif pity == 30:
        if random.random() < PITY_30_CHANCE: # 50% chance success
            rarity = 5
        else: # 50% chance failure, but it's the 30th pull, so it guarantees a 4-star
            rarity = 4
            
    # 4. SOFT PITY (Every 10 pulls, not covered by the above)
    elif pity % 10 == 0:
        rarity = 4
    
    # 5. RANDOM ROLL (Standard Rates) - only roll if no pity condition was met (rarity still 3)
    else:
        roll = random.random()
        if roll < RATE_5_STAR:
            rarity = 5
        elif roll < RATE_5_STAR + RATE_4_STAR:
            rarity = 4
        # else rarity remains 3

    # 6. Get Item & Update Pity
    item_name = random.choice(LOOT_TABLE[rarity])
    
    # Update pity_data dictionary for the next pull
    pity_data["pity_5_star"] = pity # Set the counter to the *new* pity value
    pity_data["total_pulls"] += 1
    
    if rarity == 5:
        pity_data["pity_5_star"] = 0 # Reset pity counter upon getting a 5-star
        pity_data["pity_4_star"] = 0 # Reset 4-star tracker too (for consistency/unused DB field)
    # Note: 4-star pull does not reset pity in this new system.
        
    return rarity, item_name, pity_data


# --- UTILITY (Kept as is) ---
def is_gacha_channel_interaction(interaction: discord.Interaction):
    # Assuming GACHA_CHANNEL_ID is a single ID
    return interaction.channel_id == GACHA_CHANNEL_ID

def is_gacha_channel_context(ctx: commands.Context):
    # Assuming GACHA_CHANNEL_ID is a single ID
    return ctx.channel.id == GACHA_CHANNEL_ID

# --- EMBED FORMATTER FUNCTIONS ---

# Helper to format the list of items from the wish
def format_item_list_for_embed(results):
    description = []
    
    # 5-Star Items
    if results[5]:
        description.append("### 🌟 5-STAR ITEM(S) 🌟")
        description.extend(f"**{RARITY_EMOJI[5]} {item}**" for item in results[5])
        
    # 4-Star Items
    if results[4]:
        description.append("\n### 🔸 4-STAR ITEM(S) 🔸")
        description.extend(f"*{RARITY_EMOJI[4]} {item}*" for item in results[4])

    # 3-Star Items
    if results[3]:
        # Only show a brief summary of 3-star items to save space
        count_3_star = len(results[3])
        description.append(f"\n**{RARITY_EMOJI[3]} {count_3_star} x 3-Star Item(s)**")
        
    return "\n".join(description)

# --- WISH PROCESSOR (Slash Command - Now Uses Embed) ---
async def _process_wish(interaction: discord.Interaction, amount: int):
    await interaction.response.defer()
    
    user_id = interaction.user.id
    pity_data = get_user_pity_data(user_id)
    results = {5: [], 4: [], 3: []}
    
    # 1. Perform Gacha Pulls
    for _ in range(amount):
        rarity, item_name, pity_data = pull_gacha_single(user_id, pity_data)
        
        results[rarity].append(item_name)
        
        # 2. Database writes
        add_item_to_inventory(user_id, item_name)
        log_pull_history(user_id, item_name, rarity)
        
    # 3. Update Pity Data
    update_pity_data(user_id, pity_data["pity_5_star"], pity_data["pity_4_star"], pity_data["total_pulls"])
    
    # 4. Format and send results in an Embed
    embed = discord.Embed(
        title=f"💫 {interaction.user.display_name}'s {amount} Wish Results",
        description=format_item_list_for_embed(results),
        color=RARITY_COLORS.get(max(results.keys()), discord.Color.green()) if any(results.values()) else discord.Color.dark_grey(),
        # Removed timestamp=datetime.now(timezone.utc)
    )
    
    # Pity Footer
    pity_footer = (
        f"Pulls until Guaranteed 5-Star: {PITY_5_STAR_HARD - pity_data['pity_5_star']} "
        f"({pity_data['pity_5_star']}/{PITY_5_STAR_HARD})"
    )
    embed.set_footer(text=pity_footer)
    embed.set_thumbnail(url=interaction.user.avatar.url if interaction.user.avatar else None)
    
    await interaction.followup.send(embed=embed)


# --- WISH PROCESSOR (Text Command - Now Uses Embed) ---
async def _text_process_wish(ctx: commands.Context, amount: int):
    user_id = ctx.author.id
    pity_data = get_user_pity_data(user_id)
    results = {5: [], 4: [], 3: []}
    
    # 1. Perform Gacha Pulls
    async with ctx.typing():
        for _ in range(amount):
            rarity, item_name, pity_data = pull_gacha_single(user_id, pity_data)
            
            results[rarity].append(item_name)
            
            # 2. Database writes
            add_item_to_inventory(user_id, item_name)
            log_pull_history(user_id, item_name, rarity)
            
        # 3. Update Pity Data
        update_pity_data(user_id, pity_data["pity_5_star"], pity_data["pity_4_star"], pity_data["total_pulls"])
    
    # 4. Format and send results in an Embed
    embed = discord.Embed(
        title=f"💫 {ctx.author.display_name}'s {amount} Wish Results",
        description=format_item_list_for_embed(results),
        color=RARITY_COLORS.get(max(results.keys()), discord.Color.green()) if any(results.values()) else discord.Color.dark_grey(),
        # Removed timestamp
    )
    
    # Pity Footer
    pity_footer = (
        f"Pulls until Guaranteed 5-Star: {PITY_5_STAR_HARD - pity_data['pity_5_star']} "
        f"({pity_data['pity_5_star']}/{PITY_5_STAR_HARD})"
    )
    embed.set_footer(text=pity_footer)
    embed.set_thumbnail(url=ctx.author.avatar.url if ctx.author.avatar else None)
    
    await ctx.send(embed=embed)


# --- INVENTORY PROCESSOR (Functional with Embed) ---
async def _process_inventory(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True) 
    user_id = interaction.user.id
    inventory_items = get_user_inventory(user_id)
    
    embed = discord.Embed(
        title=f"🎒 {interaction.user.display_name}'s Inventory",
        color=discord.Color.blue(),
    )
    embed.set_thumbnail(url=interaction.user.avatar.url if interaction.user.avatar else None)

    if not inventory_items:
        embed.description = "Your inventory is empty! Use **/wish** to get some items."
    else:
        inventory_text = ""
        for item_name, quantity in inventory_items:
            rarity_emoji = "📦"
            for r, items in LOOT_TABLE.items():
                if item_name in items:
                    rarity_emoji = RARITY_EMOJI.get(r, "📦")
                    break
            
            line = f"{rarity_emoji} **{item_name}** x{quantity}\n"
            if len(inventory_text) + len(line) > 1024: 
                break 
            inventory_text += line
            
        embed.add_field(name="Item Name (Quantity)", value=inventory_text, inline=False)
        embed.set_footer(text=f"Total unique items: {len(inventory_items)}")
    
    await interaction.followup.send(embed=embed, ephemeral=True)


# --- HISTORY PROCESSOR (Functional with Embed) ---
async def _process_history(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    user_id = interaction.user.id
    history_items = get_user_history(user_id, limit=20)
    
    embed = discord.Embed(
        title=f"📜 {interaction.user.display_name}'s Recent Pull History",
        color=discord.Color.purple(),
    )
    embed.set_thumbnail(url=interaction.user.avatar.url if interaction.user.avatar else None)

    if not history_items:
        embed.description = "You haven't made any wishes yet! Use **/wish** to start."
    else:
        history_text = ""
        for item_name, rarity, timestamp in history_items:
            # Use Discord's relative timestamp format
            rarity_emoji = RARITY_EMOJI.get(rarity, "❓")
            
            line = f"{rarity_emoji} **{item_name}** (<t:{timestamp}:R>)\n"
            if len(history_text) + len(line) > 1024:
                break
            history_text += line
            
        embed.add_field(name="Item Name (Time Pulled)", value=history_text, inline=False)
        embed.set_footer(text=f"Showing {len(history_items)} most recent pulls.")
    
    await interaction.followup.send(embed=embed, ephemeral=True)


# --- PITY PROCESSOR (Functional with Embed) ---
async def _process_pity(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    user_id = interaction.user.id
    pity_data = get_user_pity_data(user_id)
    
    current_pity = pity_data['pity_5_star']
    pulls_to_guarantee = PITY_5_STAR_HARD - current_pity
    
    embed = discord.Embed(
        title=f"📊 {interaction.user.display_name}'s Pity Status",
        color=discord.Color.gold(),
    )
    embed.set_thumbnail(url=interaction.user.avatar.url if interaction.user.avatar else None)
    
    # Pity Field
    embed.add_field(
        name="🌟 5-Star Pity Counter", 
        value=f"You are **{current_pity}** pulls into the 5-star guarantee cycle.", 
        inline=False
    )
    
    # Guarantee Field
    guarantee_value = f"**{pulls_to_guarantee}** pulls remaining for a guaranteed 5-Star item."
    if current_pity == 0:
        guarantee_value = "Your last pull was a 5-Star, or you've just started! **60** pulls to go."
    elif pulls_to_guarantee <= 10 and pulls_to_guarantee > 0:
        guarantee_value = f"🚨 **{pulls_to_guarantee}** pulls remaining! You are close to the hard pity!"

    embed.add_field(
        name="Pull to Guarantee", 
        value=guarantee_value, 
        inline=False
    )
    
    # Total Pulls Field
    embed.add_field(
        name="Total Lifetime Pulls", 
        value=f"You have made a total of **{pity_data['total_pulls']}** wishes.", 
        inline=True
    )

    embed.set_footer(text=f"Hard Pity is at {PITY_5_STAR_HARD} pulls.")
    
    await interaction.followup.send(embed=embed, ephemeral=True)


# --- Placeholder functions (Updated to point to functional processors) ---
async def _process_use(interaction: discord.Interaction, item: str):
    await interaction.response.send_message(f"Using item: **{item}** (Placeholder: Logic to consume item and apply effect).", ephemeral=True)

async def _process_leaderboard(interaction: discord.Interaction):
    await interaction.response.send_message(f"Showing pull leaderboard (Placeholder: Requires global data retrieval).", ephemeral=True)

async def _process_stats(interaction: discord.Interaction):
    # Stats is similar to pity, show pity as the main stat
    await _process_pity(interaction) 


# --- TEXT COMMAND PLACEHOLDERS (Updated to use functional processes) ---
async def _text_process_inventory(ctx: commands.Context):
    user_id = ctx.author.id
    inventory_items = get_user_inventory(user_id)
    
    embed = discord.Embed(
        title=f"🎒 {ctx.author.display_name}'s Inventory",
        color=discord.Color.blue(),
    )
    
    if not inventory_items:
        embed.description = "Your inventory is empty! Use `!wish` to get some items."
    else:
        inventory_text = "\n".join(f"**{item_name}** x{quantity}" for item_name, quantity in inventory_items[:15])
        embed.add_field(name="Item Name (Quantity)", value=inventory_text, inline=False)
        
    await ctx.send(embed=embed)

async def _text_process_use(ctx: commands.Context, item: str):
    await ctx.send(f"Using item: **{item}** (Placeholder: Logic to consume item and apply effect).")

async def _text_process_history(ctx: commands.Context):
    user_id = ctx.author.id
    history_items = get_user_history(user_id, limit=10)

    embed = discord.Embed(
        title=f"📜 {ctx.author.display_name}'s Recent Pull History",
        color=discord.Color.purple(),
    )

    if not history_items:
        embed.description = "You haven't made any wishes yet! Use `!wish` to start."
    else:
        history_text = ""
        for item_name, rarity, timestamp in history_items:
            rarity_emoji = RARITY_EMOJI.get(rarity, "❓")
            line = f"{rarity_emoji} **{item_name}** (<t:{timestamp}:R>)\n"
            history_text += line
        embed.add_field(name="Item Name (Time Pulled)", value=history_text, inline=False)
        
    await ctx.send(embed=embed)

async def _text_process_leaderboard(ctx: commands.Context):
    await ctx.send(f"Showing pull leaderboard (Placeholder - TEXT).")

async def _text_process_stats(ctx: commands.Context):
    # This serves as the text command for both !pity and !stats
    user_id = ctx.author.id
    pity_data = get_user_pity_data(user_id)
    
    current_pity = pity_data['pity_5_star']
    pulls_to_guarantee = PITY_5_STAR_HARD - current_pity
    
    embed = discord.Embed(
        title=f"📊 {ctx.author.display_name}'s Pity Status/Stats",
        color=discord.Color.gold(),
    )
    
    embed.add_field(
        name="🌟 5-Star Pity Counter", 
        value=f"**{current_pity} / {PITY_5_STAR_HARD}** pulls into the guarantee cycle.", 
        inline=False
    )
    embed.add_field(
        name="Pulls to Guarantee", 
        value=f"**{pulls_to_guarantee}** pulls remaining.", 
        inline=True
    )
    embed.add_field(
        name="Total Lifetime Pulls", 
        value=f"**{pity_data['total_pulls']}** wishes made.", 
        inline=True
    )
    
    await ctx.send(embed=embed)


# --- COG CLASS (Commands) ---
class GachaCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # SLASH COMMANDS
    @app_commands.command(name="wish", description="Perform gacha pulls (1 or 10)")
    @app_commands.describe(amount="The number of wishes to perform (1 or 10).")
    async def slash_wish(self, interaction: discord.Interaction, amount: app_commands.Range[int, 1, 10] = 1):
        if not is_gacha_channel_interaction(interaction):
            await interaction.response.send_message("🚫 Wrong channel. Please use the designated gacha channel.", ephemeral=True)
            return
        if amount not in [1, 10]:
            await interaction.response.send_message("🚫 You can only wish 1 or 10 times at once.", ephemeral=True)
            return
        await _process_wish(interaction, amount)

    @app_commands.command(name="inventory", description="View your inventory")
    async def slash_inventory(self, interaction: discord.Interaction):
        if not is_gacha_channel_interaction(interaction):
            await interaction.response.send_message("🚫 Wrong channel. Please use the designated gacha channel.", ephemeral=True)
            return
        await _process_inventory(interaction)

    @app_commands.command(name="use", description="Use an item from your inventory")
    async def slash_use(self, interaction: discord.Interaction, item: str):
        if not is_gacha_channel_interaction(interaction):
            await interaction.response.send_message("🚫 Wrong channel. Please use the designated gacha channel.", ephemeral=True)
            return
        await _process_use(interaction, item)

    @app_commands.command(name="history", description="View your recent pull history")
    async def slash_history(self, interaction: discord.Interaction):
        if not is_gacha_channel_interaction(interaction):
            await interaction.response.send_message("🚫 Wrong channel. Please use the designated gacha channel.", ephemeral=True)
            return
        await _process_history(interaction)

    @app_commands.command(name="pity", description="View your current 5-star pity status")
    async def slash_pity(self, interaction: discord.Interaction):
        if not is_gacha_channel_interaction(interaction):
            await interaction.response.send_message("🚫 Wrong channel. Please use the designated gacha channel.", ephemeral=True)
            return
        await _process_pity(interaction)
        
    @app_commands.command(name="leaderboard", description="View the pull leaderboard")
    async def slash_leaderboard(self, interaction: discord.Interaction):
        if not is_gacha_channel_interaction(interaction):
            await interaction.response.send_message("🚫 Wrong channel. Please use the designated gacha channel.", ephemeral=True)
            return
        await _process_leaderboard(interaction)

    @app_commands.command(name="stats", description="View your gacha stats (e.g., total pulls, pity)")
    async def slash_stats(self, interaction: discord.Interaction):
        if not is_gacha_channel_interaction(interaction):
            await interaction.response.send_message("🚫 Wrong channel. Please use the designated gacha channel.", ephemeral=True)
            return
        await _process_stats(interaction)


    # TEXT COMMANDS
    @commands.command(name="wish", description="Perform gacha pulls (1 or 10)")
    async def text_wish(self, ctx: commands.Context, amount: int = 1):
        if not is_gacha_channel_context(ctx):
            await ctx.send("🚫 Wrong channel. Please use the designated gacha channel.")
            return
        if amount not in [1, 10]:
            await ctx.send("🚫 You can only wish 1 or 10 times at once.")
            return
        await _text_process_wish(ctx, amount)

    @commands.command(name="inventory", description="View your inventory")
    async def text_inventory(self, ctx: commands.Context):
        if not is_gacha_channel_context(ctx):
            await ctx.send("🚫 Wrong channel. Please use the designated gacha channel.")
            return
        await _text_process_inventory(ctx)

    @commands.command(name="use", description="Use an item from your inventory")
    async def text_use(self, ctx: commands.Context, item: str):
        if not is_gacha_channel_context(ctx):
            await ctx.send("🚫 Wrong channel. Please use the designated gacha channel.")
            return
        await _text_process_use(ctx, item)

    @commands.command(name="history", description="View your recent pull history")
    async def text_history(self, ctx: commands.Context):
        if not is_gacha_channel_context(ctx):
            await ctx.send("🚫 Wrong channel. Please use the designated gacha channel.")
            return
        await _text_process_history(ctx)
        
    @commands.command(name="pity", description="View your current 5-star pity status")
    async def text_pity(self, ctx: commands.Context):
        if not is_gacha_channel_context(ctx):
            await ctx.send("🚫 Wrong channel. Please use the designated gacha channel.")
            return
        await _text_process_stats(ctx)

    @commands.command(name="leaderboard", description="View the pull leaderboard")
    async def text_leaderboard(self, ctx: commands.Context):
        if not is_gacha_channel_context(ctx):
            await ctx.send("🚫 Wrong channel. Please use the designated gacha channel.")
            return
        await _text_process_leaderboard(ctx)

    @commands.command(name="stats", description="View your gacha stats")
    async def text_stats(self, ctx: commands.Context):
        if not is_gacha_channel_context(ctx):
            await ctx.send("🚫 Wrong channel. Please use the designated gacha channel.")
            return
        await _text_process_stats(ctx)


    # MODERATOR COMMAND (Slash & Text)
    @app_commands.command(name="setpity", description="Set a user's pity values (moderator only)")
    @app_commands.checks.has_any_role(*MODERATOR_ROLE_IDS)
    async def slash_setpity(self, interaction: discord.Interaction, member: discord.Member, pity_5: int = 0, pity_4: int = 0, total_pulls: int = 0):
        
        # Check if the user has any of the moderator roles (using the role IDs)
        if not any(r.id in MODERATOR_ROLE_IDS for r in interaction.user.roles):
            await interaction.response.send_message("🚫 You do not have permission to use this command.", ephemeral=True)
            return

        update_pity_data(member.id, pity_5, pity_4, total_pulls)
        await interaction.response.send_message(
            f"✅ Pity data for {member.mention} updated:\n"
            f"   - **Main Pity Counter**: `{pity_5}/{PITY_5_STAR_HARD}`\n"
            f"   - **Total lifetime pulls**: `{total_pulls}`", 
            ephemeral=True
        )
    
    @commands.command(name="setpity", description="Set a user's pity values (moderator only)")
    @commands.has_any_role(*MODERATOR_ROLE_IDS)
    async def text_setpity(self, ctx: commands.Context, member: discord.Member, pity_5: int = 0, pity_4: int = 0, total_pulls: int = 0):
        
        update_pity_data(member.id, pity_5, pity_4, total_pulls)
        await ctx.send(
            f"✅ Pity data for {member.mention} updated:\n"
            f"   - **Main Pity Counter**: `{pity_5}/{PITY_5_STAR_HARD}`\n"
            f"   - **Total lifetime pulls**: `{total_pulls}`"
        )


# --- COG SETUP FUNCTION ---
async def setup(bot):
    await bot.add_cog(GachaCog(bot))

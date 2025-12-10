# gacha_main.py 
import discord
from discord.ext import commands
import sqlite3
import random
import time
import re

from bot_config import GACHA_CHANNEL_ID, MODERATOR_ROLE_ID, DB_NAME

# --- LOOT POOLS & CONSTANTS ---
RATE_5_STAR = 0.006
RATE_4_STAR = 0.05

LOOT_TABLE = {
    3: [
        "Rusted Seax", "Padded Furs & Wood", "10% XP Multiplier Token (1 Use)",
        "50 XP Crystal", "100 XP Crystal", "1,000 Crowns"
    ],
    4: [
        "Huscarl Bearded Axe", "Huscarl Lamellar", "10% XP Multiplier Token (1 Week)",
        "250 XP Crystal", "10,000 Crowns", "The Einherjar’s Edge", "The Einherjar’s Hauberk"
    ],
    5: [
        "Exalted Grade Item", "20% XP Multiplier (1 Week)",
        "500 XP Crystal", "50,000 Crowns", "Legendary Warhorn"
    ]
}

# --- DATABASE HELPERS (open/close per call for safety) ---
def _get_conn():
    # Uses DB_NAME imported from bot_config
    return sqlite3.connect(DB_NAME)

def get_user_pity_data(user_id):
    conn = _get_conn()
    try:
        c = conn.cursor()
        c.execute("SELECT pity_5_star, pity_4_star, total_pulls FROM pity WHERE user_id = ?", (user_id,))
        res = c.fetchone()
        if res:
            return {"pity_5_star": res[0], "pity_4_star": res[1], "total_pulls": res[2]}
        else:
            c.execute("INSERT INTO pity (user_id, pity_5_star, pity_4_star, total_pulls) VALUES (?, 0, 0, 0)", (user_id,))
            conn.commit()
            return {"pity_5_star": 0, "pity_4_star": 0, "total_pulls": 0}
    except sqlite3.OperationalError:
        return {"pity_5_star": 0, "pity_4_star": 0, "total_pulls": 0}
    finally:
        conn.close()

def update_pity_data(user_id, pity_5, pity_4, total_pulls):
    conn = _get_conn()
    try:
        c = conn.cursor()
        c.execute("""
            INSERT OR REPLACE INTO pity (user_id, pity_5_star, pity_4_star, total_pulls)
            VALUES (?, ?, ?, ?)
        """, (user_id, pity_5, pity_4, total_pulls))
        conn.commit()
    except sqlite3.OperationalError:
        pass
    finally:
        conn.close()

def add_item_to_inventory(user_id, item_name, quantity):
    conn = _get_conn()
    try:
        c = conn.cursor()
        c.execute("""
            INSERT OR IGNORE INTO inventory (user_id, item_name, quantity) 
            VALUES (?, ?, 0)
        """, (user_id, item_name))
        c.execute("""
            UPDATE inventory 
            SET quantity = quantity + ? 
            WHERE user_id = ? AND item_name = ?
        """, (quantity, user_id, item_name))
        conn.commit()
    except sqlite3.OperationalError:
        pass
    finally:
        conn.close()

def log_pull_history(user_id, item_name, rarity):
    conn = _get_conn()
    try:
        c = conn.cursor()
        timestamp = int(time.time())
        c.execute("""
            INSERT INTO pull_history (user_id, item_name, rarity, timestamp) 
            VALUES (?, ?, ?, ?)
        """, (user_id, item_name, rarity, timestamp))
        conn.commit()
    except sqlite3.OperationalError:
        pass
    finally:
        conn.close()

def remove_item_from_inventory(user_id, item_name, quantity):
    conn = _get_conn()
    try:
        c = conn.cursor()
        c.execute("""
            UPDATE inventory 
            SET quantity = quantity - ? 
            WHERE user_id = ? AND item_name = ? AND quantity >= ?
        """, (quantity, user_id, item_name, quantity))
        c.execute("DELETE FROM inventory WHERE user_id = ? AND item_name = ? AND quantity <= 0", (user_id, item_name))
        conn.commit()
        return c.rowcount > 0
    except sqlite3.OperationalError:
        return False
    finally:
        conn.close()

# --- RANDOM LOOT HELPERS ---
def get_random_item(rarity):
    return random.choice(LOOT_TABLE[rarity])

def perform_pull(current_pity_5, current_pity_4):
    pity_5 = current_pity_5 + 1
    pity_4 = current_pity_4 + 1
    rarity = 3
    note = ""

    rate_5_star_actual = RATE_5_STAR
    if pity_5 >= 50:
        rate_5_star_actual += (pity_5 - 50) * 0.06

    if pity_5 >= 60:
        rarity = 5
        note = "[HARD PITY]"
    elif random.random() < rate_5_star_actual:
        rarity = 5
        note = "[LUCKY PULL]"

    if rarity != 5:
        if pity_4 >= 10:
            rarity = 4
            note = "[GUARANTEED 4-STAR]"
        elif random.random() < RATE_4_STAR:
            rarity = 4
            note = "[LUCKY PULL]"

    if rarity == 5:
        pity_5_new = 0
        pity_4_new = 0
    elif rarity == 4:
        pity_5_new = pity_5
        pity_4_new = 0
    else:
        pity_5_new = pity_5
        pity_4_new = pity_4

    item = get_random_item(rarity)
    stars = "★★★★★" if rarity == 5 else ("★★★★" if rarity == 4 else "★★★")
    color = discord.Color.gold() if rarity == 5 else (discord.Color.purple() if rarity == 4 else discord.Color.light_grey())

    return {
        "rarity": rarity,
        "item": item,
        "stars": stars,
        "note": note,
        "pity_5_after": pity_5_new,
        "pity_4_after": pity_4_new,
        "color": color
    }

# --------------------------------------------------------------------------
# --- THE CHANNEL CHECK FUNCTION ---
# --------------------------------------------------------------------------
def is_gacha_channel(ctx):
    """Custom check to ensure the command is run in the designated gacha channel."""
    return ctx.channel.id == GACHA_CHANNEL_ID

# --- THE COG CLASS ---
class GachaCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # --- CUSTOM ERROR HANDLER FOR THE CHECK (FIXED) ---
    @commands.Cog.listener()
    async def on_application_command_error(self, ctx, error):
        # Unwrap the error if it's wrapped in ApplicationCommandInvokeError
        if isinstance(error, commands.ApplicationCommandInvokeError):
            error = error.original
            
        if isinstance(error, commands.CheckFailure):
            # Handle channel restriction error (for user commands)
            if ctx.command.name in ['wish', 'pity', 'inventory', 'use', 'history', 'leaderboard', 'stats']:
                gacha_channel = ctx.bot.get_channel(GACHA_CHANNEL_ID)
                if gacha_channel:
                    channel_mention = gacha_channel.mention
                else:
                    channel_mention = f"the designated channel (ID: `{GACHA_CHANNEL_ID}`)"

                await ctx.respond(
                    f"🚫 **Wrong Channel!** Please use gacha commands like **`/{ctx.command.name}`** only in {channel_mention}.",
                    ephemeral=True
                )
                return
            
            # Handle role restriction error (for /setpity)
            elif ctx.command.name == 'setpity':
                await ctx.respond("❌ **Permission Denied.** You must have the Moderator role to use this command.", ephemeral=True)
                return

        # If the error was not a handled CheckFailure, pass it along.
        await self.bot.on_application_command_error(ctx, error)

    # --- WISH COMMAND ---
    @commands.slash_command(name="wish", description="Wishes on the Entropy Banner.")
    @commands.check(is_gacha_channel)
    @discord.option("amount", type=int, description="Number of wishes (1 or 10)", min_value=1, max_value=10)
    async def wish(self, ctx: discord.ApplicationContext, amount: int):
        user_id = ctx.author.id

        if amount not in [1, 10]:
            await ctx.respond("❌ You can only perform **1-pulls** or **10-pulls**.", ephemeral=True)
            return

        await ctx.defer() 

        data = get_user_pity_data(user_id)
        current_total_pulls = data["total_pulls"]
        results = []

        temp_pity_5 = data["pity_5_star"]
        temp_pity_4 = data["pity_4_star"]

        for _ in range(amount):
            result = perform_pull(temp_pity_5, temp_pity_4)
            results.append(result)

            add_item_to_inventory(user_id, result["item"], 1)
            log_pull_history(user_id, result["item"], result["rarity"])

            temp_pity_5 = result["pity_5_after"]
            temp_pity_4 = result["pity_4_after"]

        new_total_pulls = current_total_pulls + amount
        update_pity_data(user_id, temp_pity_5, temp_pity_4, new_total_pulls)

        rarity_groups = {5: [], 4: [], 3: []}
        for r in results:
            rarity_groups[r["rarity"]].append(r)

        embed = discord.Embed(
            title=f"✨ Entropy Banner Calibration Results ({amount}-Pull) ✨",
            color=discord.Color.blue()
        )

        if rarity_groups[5]:
            content = "\n".join([f"{r['stars']} **{r['item']}** {r['note']}" for r in rarity_groups[5]])
            embed.add_field(name="👑 EXALTED (★★★★★)", value=content, inline=False)
            embed.color = rarity_groups[5][0]["color"]

        if rarity_groups[4]:
            content = "\n".join([f"{r['stars']} **{r['item']}** {r['note']}" for r in rarity_groups[4]])
            embed.add_field(name="💎 RARE (★★★★)", value=content, inline=False)
            if not rarity_groups[5]:
                embed.color = rarity_groups[4][0]["color"]

        if rarity_groups[3]:
            content = "\n".join([f"{r['stars']} **{r['item']}**" for r in rarity_groups[3]])
            embed.add_field(name=f"⚙️ COMMON (★★★) x{len(rarity_groups[3])}", value=content, inline=False)

        embed.add_field(
            name="Pity Status",
            value=(
                f"**Pulls made:** {amount}\n"
                f"**Next 5★ Pity:** {temp_pity_5}/60\n"
                f"**Next 4★ Pity:** {temp_pity_4}/10\n"
                f"**Total pulls:** {new_total_pulls}"
            ),
            inline=False
        )

        embed.set_footer(text=f"Calibrator for {ctx.author.display_name}")
        await ctx.followup.send(embed=embed)

    # --- PITY CHECK COMMAND ---
    @commands.slash_command(name="pity", description="Checks your current pity count and total pulls.")
    @commands.check(is_gacha_channel)
    async def pity_check(self, ctx: discord.ApplicationContext):
        user_id = ctx.author.id

        data = get_user_pity_data(user_id)
        pity_5 = data["pity_5_star"]
        pity_4 = data["pity_4_star"]
        total_pulls = data["total_pulls"]

        embed = discord.Embed(
            title="Pity Calibration Check 🔭",
            description=f"**{ctx.author.display_name}**'s current status on the Entropy Banner.",
            color=discord.Color.dark_teal()
        )

        embed.add_field(
            name="🌟 5-Star Pity",
            value=f"**{pity_5}/60**\n*You are guaranteed a 5★ by the 60th pull (Soft Pity starts at 50).*",
            inline=False
        )
        embed.add_field(
            name="✨ 4-Star Pity",
            value=f"**{pity_4}/10**\n*You are guaranteed a 4★ or higher by the 10th pull.*",
            inline=False
        )
        embed.add_field(
            name="📈 Lifetime Status",
            value=f"**Total Pulls Made:** {total_pulls}",
            inline=False
        )

        await ctx.respond(embed=embed)

    # --- INVENTORY COMMAND ---
    @commands.slash_command(name="inventory", description="Shows the items you currently own.")
    @commands.check(is_gacha_channel)
    async def inventory(self, ctx: discord.ApplicationContext):
        await ctx.defer() 
        
        user_id = ctx.author.id

        conn = _get_conn()
        try:
            c = conn.cursor()
            c.execute("SELECT item_name, quantity FROM inventory WHERE user_id = ? AND quantity > 0 ORDER BY quantity DESC", (user_id,))
            items = c.fetchall()
        finally:
            conn.close()

        embed = discord.Embed(
            title=f"🎒 {ctx.author.display_name}'s Inventory",
            color=discord.Color.dark_purple()
        )

        if not items:
            embed.description = "Your inventory is currently empty! Use `/wish` to acquire items."
        else:
            item_list = []
            for name, quantity in items:
                emoji = "💰" if "Crowns" in name else ("💎" if "Crystal" in name else "⚔️")
                item_list.append(f"{emoji} **{name}** x{quantity}")

            content = "\n".join(item_list[:20])

            embed.add_field(name="Held Items", value=content, inline=False)
            if len(items) > 20:
                embed.set_footer(text=f"Showing 20 of {len(items)} unique item types.")

        await ctx.followup.send(embed=embed)

    # --- USE COMMAND ---
    @commands.slash_command(name="use", description="Consumes an item from your inventory.")
    @commands.check(is_gacha_channel)
    @discord.option("item_name", description="The full name of the item you want to use.")
    @discord.option("amount", type=int, description="The amount to use (defaults to 1)", default=1, min_value=1)
    async def use(self, ctx: discord.ApplicationContext, item_name: str, amount: int):
        user_id = ctx.author.id

        if "Crystal" not in item_name and "Crowns" not in item_name:
            await ctx.respond("❌ This item cannot be consumed with the `/use` command (only Crystals and Crowns are currently usable).", ephemeral=True)
            return

        if not remove_item_from_inventory(user_id, item_name, amount):
            await ctx.respond(f"❌ You do not have **{amount}** of **{item_name}**.", ephemeral=True)
            return

        try:
            item_value_str = item_name.split()[0].replace(',', '')
            item_value = int(item_value_str)
            total_value = item_value * amount

            if "Crystal" in item_name:
                await ctx.respond(f"✅ Consumed **{amount}**x **{item_name}**. Gained **{total_value:,}** experience.")

            elif "Crowns" in item_name:
                await ctx.respond(f"✅ Consumed **{amount}**x **{item_name}**. Gained **{total_value:,}** Crowns currency.")

        except (ValueError, IndexError):
            await ctx.respond(f"⚠️ **{item_name}** was consumed, but its value could not be reliably calculated. No specific bonus applied.", ephemeral=True)

    # --- HISTORY COMMAND ---
    @commands.slash_command(name="history", description="Shows your last 10 pulls from the Entropy Banner.")
    @commands.check(is_gacha_channel)
    async def history(self, ctx: discord.ApplicationContext):
        await ctx.defer() 
        
        user_id = ctx.author.id

        conn = _get_conn()
        try:
            c = conn.cursor()
            c.execute("""
                SELECT item_name, rarity, timestamp 
                FROM pull_history 
                WHERE user_id = ? 
                ORDER BY timestamp DESC 
                LIMIT 10
            """, (user_id,))
            history_items = c.fetchall()
        finally:
            conn.close()

        embed = discord.Embed(
            title=f"📜 {ctx.author.display_name}'s Pull History (Last 10)",
            color=discord.Color.light_grey()
        )

        if not history_items:
            embed.description = "No pull history found. Start your calibration with `/wish`!"
        else:
            pull_list = []
            for item_name, rarity, timestamp in history_items:
                stars = "★★★★★" if rarity == 5 else ("★★★★" if rarity == 4 else "★★★")
                pull_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(timestamp))
                pull_list.append(f"{stars} **{item_name}** (`{pull_time}`)")

            embed.description = "\n".join(pull_list)

        await ctx.followup.send(embed=embed)

    # --- LEADERBOARD COMMAND ---
    @commands.slash_command(name="leaderboard", description="Shows users with the most total pulls.")
    @commands.check(is_gacha_channel)
    async def leaderboard(self, ctx: discord.ApplicationContext):
        await ctx.defer() 
        
        conn = _get_conn()
        try:
            c = conn.cursor()
            c.execute("""
                SELECT user_id, total_pulls 
                FROM pity 
                ORDER BY total_pulls DESC 
                LIMIT 10
            """)
            top_pullers = c.fetchall()
        finally:
            conn.close()

        embed = discord.Embed(
            title="🏆 Top 10 Entropy Calibrators",
            description="Ranked by total pulls made on the banner.",
            color=discord.Color.gold()
        )

        if not top_pullers:
            embed.description = "No pulls recorded yet!"
        else:
            leaderboard_content = []
            for i, (user_id, total_pulls) in enumerate(top_pullers):
                user_mention = f"<@{user_id}>"
                rank = i + 1
                trophy = "🥇" if rank == 1 else ("🥈" if rank == 2 else ("🥉" if rank == 3 else f"**{rank}.**"))
                leaderboard_content.append(f"{trophy} {user_mention} — **{total_pulls:,}** pulls")

            embed.description = "\n".join(leaderboard_content)

        await ctx.followup.send(embed=embed)

    # --- STATS COMMAND ---
    @commands.slash_command(name="stats", description="Shows global statistics for the Entropy Banner.")
    @commands.check(is_gacha_channel)
    async def stats(self, ctx: discord.ApplicationContext):
        await ctx.defer() 
        
        conn = _get_conn()
        try:
            c = conn.cursor()
            c.execute("SELECT SUM(total_pulls) FROM pity")
            total_pulls = c.fetchone()[0] or 0

            c.execute("SELECT COUNT(id) FROM pull_history WHERE rarity = 5")
            five_star_count = c.fetchone()[0] or 0

            c.execute("SELECT COUNT(id) FROM pull_history WHERE rarity = 4")
            four_star_count = c.fetchone()[0] or 0
        finally:
            conn.close()

        five_star_rate = (five_star_count / total_pulls * 100) if total_pulls > 0 else 0
        four_star_rate = (four_star_count / total_pulls * 100) if total_pulls > 0 else 0

        embed = discord.Embed(
            title="📊 Global Entropy Banner Statistics",
            color=discord.Color.teal()
        )

        embed.add_field(
            name="Global Pulls",
            value=f"**Total Pulls Made:** {total_pulls:,}",
            inline=False
        )

        embed.add_field(
            name="5-Star Rate",
            value=f"**{five_star_count:,}** 5★ Items Pulled\n**Rate:** {five_star_rate:.3f}% (Expected: {RATE_5_STAR * 100}%)",
            inline=False
        )

        embed.add_field(
            name="4-Star Rate",
            value=f"**{four_star_count:,}** 4★ Items Pulled\n**Rate:** {four_star_rate:.3f}% (Expected: {RATE_4_STAR * 100}%)",
            inline=False
        )

        await ctx.followup.send(embed=embed)

    # --- MODERATOR COMMAND: /setpity ---
    @commands.slash_command(name="setpity", description="[MOD] Manually sets a user's 5-star and 4-star pity counts.")
    @commands.has_role(MODERATOR_ROLE_ID)
    @discord.option("target_user", type=discord.Member, description="The user whose pity you are setting.")
    @discord.option("pity_5_star", type=int, description="New 5-star pity count (0-60).", min_value=0, max_value=60)
    @discord.option("pity_4_star", type=int, description="New 4-star pity count (0-10).", min_value=0, max_value=10)
    async def setpity(self, ctx: discord.ApplicationContext, target_user: discord.Member, pity_5_star: int, pity_4_star: int):
        current_data = get_user_pity_data(target_user.id)
        current_total_pulls = current_data["total_pulls"]

        update_pity_data(target_user.id, pity_5_star, pity_4_star, current_total_pulls)

        embed = discord.Embed(
            title="✅ Pity Set Successfully",
            description=f"Moderator {ctx.author.mention} has updated the pity data for {target_user.mention}.",
            color=discord.Color.green()
        )
        embed.add_field(name="New 5-Star Pity", value=f"**{pity_5_star}/60**", inline=True)
        embed.add_field(name="New 4-Star Pity", value=f"**{pity_4_star}/10**", inline=True)
        embed.add_field(name="Total Pulls Preserved", value=f"**{current_total_pulls}**", inline=False)

        await ctx.respond(embed=embed)


# --- SETUP FUNCTION (Guaranteed to return None) ---
def setup(bot):
    bot.add_cog(GachaCog(bot))
    return None

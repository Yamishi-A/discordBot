# xp_reporter_main.py
# FINAL – Manual Review System + Mod Credit + Correct Multipliers

import discord
import re
import math
from discord.ext import commands
from bot_config import INPUT_CHANNEL_IDS, OUTPUT_CHANNEL_IDS, SUBMISSION_APPROVER_ROLE_IDS

EMOJI_STR1 = "⭐"
BASE_CROWNS = 500

# ────────────────────────
# Training Tiers
# ────────────────────────
TRAINING_TIERS = [
    (1, 10, 100, 1),
    (11, 20, 150, 2),
    (21, 30, 200, 3),
]

def get_training_tier_data(level: int) -> dict:
    for min_lvl, max_lvl, xp, tier in TRAINING_TIERS:
        if min_lvl <= level <= max_lvl:
            return {"base_xp": xp, "tier": tier}
    return {"base_xp": 100, "tier": 1}

# ────────────────────────
# Activity Multipliers
# ────────────────────────
ACTIVITY_MULTIPLIERS = {
    "solo training": 1.0,
    "troll mission": 1.0,
    "afk training i": 1.0,
    "afk training ii": 1.0,
    "afk training iii": 1.15,
}

# Review-only multipliers
REVIEW_MULTIPLIERS = {
    "battle": 4.0,
    "wholesome": 2.5,
}

ACTIVITY_ALIASES = {
    "afk farm i": "afk training i",
    "afk farm ii": "afk training ii",
    "afk farm iii": "afk training iii",
    "afk i": "afk training i",
    "afk ii": "afk training ii",
    "afk iii": "afk training iii",
    "afk 1": "afk training i",
    "afk 2": "afk training ii",
    "afk 3": "afk training iii",
    "solo train": "solo training",
}

REVIEW_KEYWORDS = {"battle", "wholesome", "dungeon"}

# ────────────────────────
# Cog
# ────────────────────────
class XPReporterCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.pending_reviews = {}  # review_message_id -> submission data
        self._cached_mod_ping = None

    # ────────────────────────
    # Parsing
    # ────────────────────────
    def _parse(self, message):
        content = message.content

        name_match = re.search(r"\*\*Character Name\(s\):\*\*\s*(.+)", content, re.I)
        level_match = re.search(r"\*\*Character Level:\*\*\s*(\d+)", content, re.I)
        prog_match = re.search(
            r"\*\*Type of Progression:\*\*(.*?)(?=\*\*|\Z)",
            content,
            re.I | re.S
        )
        xp_boost_match = re.search(r"\*\*Boost\(s\) for XP:\*\*\s*(\d+)%", content, re.I)
        crowns_boost_match = re.search(r"\*\*Boost\(s\) for Crowns:\*\*\s*(\d+)%", content, re.I)

        progression = prog_match.group(1).strip() if prog_match else None
        progression_key = (progression or "").lower().replace("farm", "training").strip()
        progression_key = ACTIVITY_ALIASES.get(progression_key, progression_key)

        return {
            "name": name_match.group(1).strip() if name_match else None,
            "level": int(level_match.group(1)) if level_match else None,
            "progression": progression,
            "progression_key": progression_key,
            "xp_boost": int(xp_boost_match.group(1)) / 100 if xp_boost_match else 0.0,
            "crowns_boost": int(crowns_boost_match.group(1)) / 100 if crowns_boost_match else 0.0,
            "author": message.author,
            "channel": message.channel,
        }

    # ────────────────────────
    # Message Listener
    # ────────────────────────
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return

        if message.channel.id not in INPUT_CHANNEL_IDS:
            return

        if not message.content.lower().startswith("**character name(s):**"):
            return

        data = self._parse(message)

        missing = [k for k in ("name", "level", "progression") if not data.get(k)]
        if missing:
            await message.add_reaction("❌")
            await message.channel.send(
                f"{message.author.mention}, missing required fields: {', '.join(missing)}",
                delete_after=20
            )
            return

        activity = data["progression_key"]

        # ── Auto-approved
        if activity in ACTIVITY_MULTIPLIERS:
            await self._process_submission(message, data)
            return

        # ── Manual review
        if any(k in activity for k in REVIEW_KEYWORDS):
            await message.add_reaction("❓")

            if self._cached_mod_ping is None:
                self._cached_mod_ping = " ".join(
                    role.mention
                    for rid in SUBMISSION_APPROVER_ROLE_IDS
                    if (role := message.guild.get_role(rid))
                )

            embed = discord.Embed(
                title="⚠️ Manual Review Required",
                description=f"{self._cached_mod_ping}\nSubmitted by {message.author.mention}",
                color=discord.Color.orange()
            )
            embed.add_field(name="Character(s)", value=data["name"], inline=True)
            embed.add_field(name="Level", value=data["level"], inline=True)
            embed.add_field(
                name="Progression",
                value=data["progression"].title(),
                inline=False
            )
            embed.set_footer(text="React with ✅ to approve or ❌ to deny")

            review_msg = await message.channel.send(embed=embed)
            await review_msg.add_reaction("✅")
            await review_msg.add_reaction("❌")

            self.pending_reviews[review_msg.id] = data
            return

        # ── Invalid progression
        await message.add_reaction("❌")
        await message.channel.send(
            f"{message.author.mention}, invalid progression type.",
            delete_after=15
        )

    # ────────────────────────
    # Reaction Listener
    # ────────────────────────
    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        if user.bot:
            return

        if reaction.message.id not in self.pending_reviews:
            return

        if not any(role.id in SUBMISSION_APPROVER_ROLE_IDS for role in user.roles):
            return

        data = self.pending_reviews.pop(reaction.message.id)

        if reaction.emoji == "❌":
            await reaction.message.channel.send(
                f"❌ Submission denied by {user.mention}."
            )
            return

        if reaction.emoji == "✅":
            await self._process_submission(
                reaction.message,
                data,
                reviewer=user
            )

    # ────────────────────────
    # Processing
    # ────────────────────────
    async def _process_submission(self, message, data, reviewer=None):
        tier = get_training_tier_data(data["level"])

        multiplier = (
            REVIEW_MULTIPLIERS.get(data["progression_key"])
            or ACTIVITY_MULTIPLIERS.get(data["progression_key"], 1.0)
        )

        final_xp = math.floor(
            tier["base_xp"] * multiplier * (1 + data["xp_boost"])
        )

        gains = [f"{final_xp} XP"]

        try:
            idx = INPUT_CHANNEL_IDS.index(data["channel"].id)
            output_channel = self.bot.get_channel(OUTPUT_CHANNEL_IDS[idx])
        except Exception:
            output_channel = data["channel"]

        embed = discord.Embed(
            title="✅ Progression Logged",
            description=f"Submitted by {data['author'].mention}",
            color=discord.Color.green()
        )
        embed.add_field(name="Character(s)", value=data["name"], inline=True)
        embed.add_field(name="Level", value=data["level"], inline=True)
        embed.add_field(name="Training Tier", value=f"TT{tier['tier']}", inline=True)
        embed.add_field(
            name=f"{EMOJI_STR1} Total Gains",
            value=f"**{', '.join(gains)}**",
            inline=False
        )

        if reviewer:
            embed.set_footer(text=f"Approved by {reviewer.display_name}")

        await output_channel.send(embed=embed)
        await message.add_reaction("✅")

# ────────────────────────
# Setup
# ────────────────────────
async def setup(bot):
    await bot.add_cog(XPReporterCog(bot))

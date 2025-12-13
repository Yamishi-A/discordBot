# xp_reporter_main.py (FINAL – CASE-INSENSITIVE, FORMAT-COMPATIBLE, MOD-REVIEW FLOW)
# Fully supports the user's exact submission format
# - Ignores Channel(s)
# - Case-insensitive everywhere
# - Normalizes AFK FARM -> AFK TRAINING
# - Auto-approve / Mod-review / Hard-deny logic
# - Mods approve via ✅ / ❌ reactions

import discord
import re
import math
import logging
from discord.ext import commands
from bot_config import INPUT_CHANNEL_IDS, OUTPUT_CHANNEL_IDS, SUBMISSION_APPROVER_ROLE_IDS

# --------------------------------------------------
# LOGGING
# --------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("xp_reporter")

# --------------------------------------------------
# CONSTANTS
# --------------------------------------------------
EMOJI_STR1 = "⭐"
BASE_CROWNS = 500

# --------------------------------------------------
# TRAINING TIERS
# --------------------------------------------------
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

# --------------------------------------------------
# ACTIVITY RULES
# --------------------------------------------------
AUTO_APPROVED = {
    "solo training",
    "troll mission",
    "afk training i",
    "afk training ii",
    "afk training iii",
}

REVIEW_KEYWORDS = {"wholesome", "battle", "dungeon"}

ACTIVITY_MULTIPLIERS = {
    "solo training": 1.0,
    "troll mission": 1.0,
    "afk training i": 1.0,
    "afk training ii": 1.0,
    "afk training iii": 1.15,
}

# --------------------------------------------------
# COG
# --------------------------------------------------
class XPReporterCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.pending_reviews = {}  # message_id -> parsed data
        self._cached_mod_ping = None

    # --------------------------------------------------
    # PARSER (STRICT CORE, FLEXIBLE TEXT)
    # --------------------------------------------------
    def _parse(self, message):
        content = message.content
        try:
            name = re.search(r"\*\*Character Name\(s\):\*\*\s*(.+)", content, re.I).group(1).strip()
            level = int(re.search(r"\*\*Character Level:\*\*\s*(\d+)", content, re.I).group(1))
            progression = re.search(
                r"\*\*Type of Progression:\*\*(.*?)(?=\*\*|\Z)",
                content,
                re.I | re.S
            ).group(1).strip()

            xp_boost_match = re.search(
                r"\*\*Boost\(s\) for XP:\*\*\s*(\d+)%",
                content,
                re.I
            )
            crowns_boost_match = re.search(
                r"\*\*Boost\(s\) for Crowns:\*\*\s*(\d+)%",
                content,
                re.I
            )

            xp_boost = int(xp_boost_match.group(1)) / 100 if xp_boost_match else 0.0
            crowns_boost = int(crowns_boost_match.group(1)) / 100 if crowns_boost_match else 0.0

            progression_key = progression.lower().strip()

            # Normalization (AFK FARM -> AFK TRAINING)
            progression_key = progression_key.replace("farm", "training")

            return {
                "valid": True,
                "name": name,
                "level": level,
                "progression": progression,
                "progression_key": progression_key,
                "xp_boost": xp_boost,
                "crowns_boost": crowns_boost,
            }
        except Exception:
            return {"valid": False}

    # --------------------------------------------------
    # MESSAGE LISTENER
    # --------------------------------------------------
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return

        if not message.content.lower().startswith("**character name(s):**"):
            return

        data = self._parse(message)

        # -------- FORMAT FAILURE --------
        if not data.get("valid"):
            await message.add_reaction("❌")
            await message.channel.send(
                f"{message.author.mention}, submission denied. Please follow the required format exactly.",
                delete_after=15
            )
            return

        activity = data["progression_key"]

        # -------- AUTO APPROVED --------
        if activity in AUTO_APPROVED:
            await self._process_submission(message, data)
            return

        # -------- NEEDS MOD REVIEW --------
        if any(keyword in activity for keyword in REVIEW_KEYWORDS):
            await message.add_reaction("❓")

            if self._cached_mod_ping is None:
                self._cached_mod_ping = " ".join(
                    role.mention
                    for rid in SUBMISSION_APPROVER_ROLE_IDS
                    if (role := message.guild.get_role(rid))
                )

            await message.channel.send(
                f"⚠️ **Manual Review Required**\n"
                f"Submission by {message.author.mention} requires approval.\n"
                f"{self._cached_mod_ping}\n\n"
                f"React to the original message with ✅ to approve or ❌ to deny."
            )

            self.pending_reviews[message.id] = data
            return

        # -------- HARD DENY --------
        await message.add_reaction("❌")
        await message.channel.send(
            f"{message.author.mention}, submission denied. Invalid progression type.",
            delete_after=15
        )

    # --------------------------------------------------
    # MOD REACTION HANDLER
    # --------------------------------------------------
    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        if user.bot:
            return

        message = reaction.message

        if message.id not in self.pending_reviews:
            return

        if not any(role.id in SUBMISSION_APPROVER_ROLE_IDS for role in user.roles):
            return

        data = self.pending_reviews.pop(message.id)

        if reaction.emoji == "❌":
            await message.channel.send(f"❌ Submission denied by {user.mention}.")
            return

        if reaction.emoji == "✅":
            await self._process_submission(message, data)

    # --------------------------------------------------
    # PROCESSING
    # --------------------------------------------------
    async def _process_submission(self, message, data):
        tier_data = get_training_tier_data(data["level"])
        base_multiplier = ACTIVITY_MULTIPLIERS.get(data["progression_key"], 1.0)

        final_xp = math.floor(
            tier_data["base_xp"] * base_multiplier * (1 + data["xp_boost"])
        )

        final_crowns = (
            int(BASE_CROWNS * (1 + data["crowns_boost"]))
            if data["progression_key"] == "troll mission"
            else 0
        )

        rift_tokens = tier_data["tier"] if data["progression_key"] == "troll mission" else 0

        gains = [f"{final_xp} XP"]
        if final_crowns > 0:
            gains.append(f"{final_crowns} Crowns")
        if rift_tokens > 0:
            gains.append(f"{rift_tokens} Rift Tokens")

        # Output channel mapping (fallback safe)
        try:
            idx = INPUT_CHANNEL_IDS.index(message.channel.id)
            output_channel = self.bot.get_channel(OUTPUT_CHANNEL_IDS[idx])
        except Exception:
            output_channel = message.channel

        await message.add_reaction("✅")

        embed = discord.Embed(
            title=f"✅ Progression Logged: {data['progression'].title()}",
            description=f"Submitted by {message.author.mention}",
            color=discord.Color.green(),
        )

        embed.add_field(name="Character(s)", value=data["name"], inline=True)
        embed.add_field(name="Level", value=data["level"], inline=True)
        embed.add_field(name="Training Tier", value=f"TT{tier_data['tier']}", inline=True)
        embed.add_field(name=f"{EMOJI_STR1} Total Gains", value=f"**{', '.join(gains)}**", inline=False)

        await output_channel.send(embed=embed)

# --------------------------------------------------
# SETUP
# --------------------------------------------------
async def setup(bot):
    await bot.add_cog(XPReporterCog(bot))

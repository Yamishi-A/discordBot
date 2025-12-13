# xp_reporter_main.py (UPGRADED – Smart Errors, Activity Aliases, Mod Approval + Preview Embed)

import discord
import re
import math
from discord.ext import commands
from bot_config import INPUT_CHANNEL_IDS, OUTPUT_CHANNEL_IDS, SUBMISSION_APPROVER_ROLE_IDS

EMOJI_STR1 = "⭐"
BASE_CROWNS = 500

# Training tiers
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

# Activity multipliers & aliases
ACTIVITY_MULTIPLIERS = {
    "solo training": 1.0,
    "troll mission": 1.0,
    "afk training i": 1.0,
    "afk training ii": 1.0,
    "afk training iii": 1.15,
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
    "troll mission": "troll mission",
}

REVIEW_KEYWORDS = {"wholesome", "battle", "dungeon"}

class XPReporterCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.pending_reviews = {}
        self._cached_mod_ping = None

    def _parse(self, message):
        content = message.content
        try:
            name_match = re.search(r"\*\*Character Name\(s\):\*\*\s*(.+)", content, re.I)
            level_match = re.search(r"\*\*Character Level:\*\*\s*(\d+)", content, re.I)
            progression_match = re.search(r"\*\*Type of Progression:\*\*(.*?)(?=\*\*|\Z)", content, re.I | re.S)
            xp_boost_match = re.search(r"\*\*Boost\(s\) for XP:\*\*\s*(\d+)%", content, re.I)
            crowns_boost_match = re.search(r"\*\*Boost\(s\) for Crowns:\*\*\s*(\d+)%", content, re.I)

            name = name_match.group(1).strip() if name_match else None
            level = int(level_match.group(1)) if level_match else None
            progression = progression_match.group(1).strip() if progression_match else None

            xp_boost = int(xp_boost_match.group(1))/100 if xp_boost_match else 0.0
            crowns_boost = int(crowns_boost_match.group(1))/100 if crowns_boost_match else 0.0

            progression_key = (progression or '').lower().replace('farm', 'training').strip()
            progression_key = ACTIVITY_ALIASES.get(progression_key, progression_key)

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

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return

        if message.channel.id not in INPUT_CHANNEL_IDS:
            return

        if not message.content.lower().startswith('**character name(s):**'):
            return

        data = self._parse(message)

        missing_fields = []
        if not data.get('name'): missing_fields.append('Character Name')
        if not data.get('level'): missing_fields.append('Character Level')
        if not data.get('progression'): missing_fields.append('Type of Progression')

        if missing_fields:
            await message.add_reaction('❌')
            await message.channel.send(
                f"{message.author.mention}, submission denied. Missing required field(s): {', '.join(missing_fields)}",
                delete_after=20
            )
            return

        activity = data['progression_key']

        # Auto-approved
        if activity in ACTIVITY_MULTIPLIERS:
            await self._process_submission(message, data)
            return

        # Needs review
        if any(k in activity for k in REVIEW_KEYWORDS):
            await message.add_reaction('❓')
            if self._cached_mod_ping is None:
                self._cached_mod_ping = ' '.join(
                    role.mention for rid in SUBMISSION_APPROVER_ROLE_IDS if (role := message.guild.get_role(rid))
                )
            preview_embed = discord.Embed(
                title=f"⚠️ Review Required: {data['progression'].title()}",
                description=f"Submitted by {message.author.mention}",
                color=discord.Color.orange()
            )
            preview_embed.add_field(name='Character(s)', value=data['name'], inline=True)
            preview_embed.add_field(name='Level', value=data['level'], inline=True)
            preview_embed.add_field(name='Predicted Gains', value='XP: ??, Crowns: ??, Rift Tokens: ??', inline=False)
            await message.channel.send(embed=preview_embed)
            self.pending_reviews[message.id] = data
            return

        # Hard deny
        await message.add_reaction('❌')
        await message.channel.send(f"{message.author.mention}, submission denied. Invalid progression type.", delete_after=15)

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        if user.bot or reaction.message.id not in self.pending_reviews:
            return
        if not any(role.id in SUBMISSION_APPROVER_ROLE_IDS for role in user.roles):
            return

        data = self.pending_reviews.pop(reaction.message.id)
        if reaction.emoji == '❌':
            await reaction.message.channel.send(f"❌ Submission denied by {user.mention}.")
            return
        if reaction.emoji == '✅':
            await self._process_submission(reaction.message, data)

    async def _process_submission(self, message, data):
        tier_data = get_training_tier_data(data['level'])
        base_multiplier = ACTIVITY_MULTIPLIERS.get(data['progression_key'], 1.0)

        final_xp = math.floor(tier_data['base_xp'] * base_multiplier * (1 + data['xp_boost']))
        final_crowns = int(BASE_CROWNS * (1 + data['crowns_boost'])) if data['progression_key'] == 'troll mission' else 0
        rift_tokens = tier_data['tier'] if data['progression_key'] == 'troll mission' else 0

        gains = [f"{final_xp} XP"]
        if final_crowns > 0: gains.append(f"{final_crowns} Crowns")
        if rift_tokens > 0: gains.append(f"{rift_tokens} Rift Tokens")

        # Output channel
        try:
            idx = INPUT_CHANNEL_IDS.index(message.channel.id)
            output_channel = self.bot.get_channel(OUTPUT_CHANNEL_IDS[idx])
        except Exception:
            output_channel = message.channel

        await message.add_reaction('✅')

        embed = discord.Embed(
            title=f"✅ Progression Logged: {data['progression'].title()}",
            description=f"Submitted by {message.author.mention}",
            color=discord.Color.green()
        )
        embed.add_field(name="Character(s)", value=data['name'], inline=True)
        embed.add_field(name="Level", value=data['level'], inline=True)
        embed.add_field(name="Training Tier", value=f"TT{tier_data['tier']}", inline=True)
        embed.add_field(name=f"{EMOJI_STR1} Total Gains", value=f"**{', '.join(gains)}**", inline=False)

        await output_channel.send(embed=embed)

async def setup(bot):
    await bot.add_cog(XPReporterCog(bot))

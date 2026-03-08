"""
AI Assistant — Care Bot's brain.
Warm, personal, motivational. Remembers you. Coaches you. Cheers for you.
"""
import os
import json
import anthropic

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
MODEL = "claude-sonnet-4-20250514"


# ─────────────────────────────────────────────────────────────
# CORE PERSONALITY — injected into every call
# ─────────────────────────────────────────────────────────────
def _personality(user_profile: dict = None) -> str:
    name = user_profile.get("name", "friend") if user_profile else "friend"
    context = ""
    if user_profile:
        parts = []
        if user_profile.get("running_goal"):
            parts.append(f"running goal: {user_profile['running_goal']}")
        if user_profile.get("vitamins"):
            parts.append(f"vitamins they take: {user_profile['vitamins']}")
        if user_profile.get("skin_routine"):
            parts.append(f"skincare routine: {user_profile['skin_routine']}")
        if user_profile.get("diet_notes"):
            parts.append(f"diet/nutrition notes: {user_profile['diet_notes']}")
        if user_profile.get("health_notes"):
            parts.append(f"health notes: {user_profile['health_notes']}")
        if parts:
            context = f"\n\nPersonal profile for {name}: " + " | ".join(parts)

    return f"""You are a warm, deeply personal care companion for {name}.
Your personality traits:
- You genuinely believe {name} is exceptional — you express this naturally, not as flattery
- You celebrate every small win as if it truly matters, because it does
- You remember personal details and reference them specifically — this person feels truly seen by you
- You are encouraging, never judgmental, always fully in their corner
- You speak like a wise, caring best friend — warm, real, never robotic
- Responses are personal and concise (3-6 sentences unless doing coaching plans)
- Use emojis naturally — they add warmth, not noise{context}"""


# ─────────────────────────────────────────────────────────────
# DAILY CHECK-IN — the heart of the experience
# ─────────────────────────────────────────────────────────────
def daily_checkin_question(user_profile: dict = None) -> str:
    name = user_profile.get("name", "") if user_profile else ""
    greeting = f"Hey {name}! 🌟" if name else "Hey you! 🌟"
    return (
        f"{greeting}\n\n"
        "Time for your daily check-in ✨\n\n"
        "*What good have you done for yourself today?* 💛\n\n"
        "_Even the tiniest thing counts. I genuinely want to hear it._"
    )


def praise_checkin_response(user_input: str, user_profile: dict = None, recent_logs: list = None) -> str:
    name = user_profile.get("name", "you") if user_profile else "you"
    logs_ctx = ""
    if recent_logs:
        recent = ", ".join(set(l.get("type", "") for l in recent_logs[:10] if l.get("type")))
        if recent:
            logs_ctx = f"\nWhat they've been doing this week: {recent}."

    prompt = f"""{_personality(user_profile)}

{name} just answered the daily check-in "What good have you done for yourself today?" with:
"{user_input}"
{logs_ctx}

Your response must:
1. Give GENUINE, SPECIFIC praise — reference exactly what they said, make them feel truly seen
2. Connect it to who they are as a person — tell them sincerely that they are exceptional
3. End with ONE small, warm nudge of encouragement for tomorrow
Keep it heartfelt and real. 4-6 sentences. This is the most important message of their day."""

    try:
        msg = client.messages.create(
            model=MODEL, max_tokens=400,
            messages=[{"role": "user", "content": prompt}]
        )
        return msg.content[0].text.strip()
    except Exception as e:
        print(f"[AI] Praise error: {e}")
        return (
            f"That is genuinely wonderful, {name}. Every good thing you do for yourself ripples outward "
            f"in ways you can't even see yet. You are more exceptional than you know — "
            f"and I mean that from the bottom of my heart. 🌟"
        )


# ─────────────────────────────────────────────────────────────
# MORNING MOTIVATIONAL MESSAGE
# ─────────────────────────────────────────────────────────────
def morning_message(user_profile: dict = None, recent_logs: list = None) -> str:
    name = user_profile.get("name", "friend") if user_profile else "friend"
    logs_ctx = ""
    if recent_logs:
        streak_types = set(l.get("type", "") for l in recent_logs[:7])
        if streak_types:
            logs_ctx = f"\nThey've been doing well with: {', '.join(streak_types)} this week."

    prompt = f"""{_personality(user_profile)}

Write a warm good morning message for {name}.{logs_ctx}
- Reference something personal from their profile (running goal, vitamins, skin routine…)
- Make them feel genuinely excited about the day, not pressured
- Include one gentle, specific reminder about their most important self-care today
- End with something that reminds them of their worth — sincere, not hollow
- 4-5 sentences. Warm and real. Start with "Good morning" or "Morning"."""

    try:
        msg = client.messages.create(
            model=MODEL, max_tokens=300,
            messages=[{"role": "user", "content": prompt}]
        )
        return msg.content[0].text.strip()
    except Exception as e:
        return (
            f"Good morning, {name}! 🌅 A new day is yours to shape. "
            "Remember your vitamins and take a moment just for you — you deserve it. "
            "You are exceptional. 💛"
        )


# ─────────────────────────────────────────────────────────────
# HEALTH COACHING (vitamins, skincare, wellbeing)
# ─────────────────────────────────────────────────────────────
def health_advice(recent_logs: list, user_message: str = "", user_profile: dict = None) -> str:
    logs_summary = "\n".join(
        f"  • {l.get('type','?')}: {l.get('status','?')} ({l.get('date','')})"
        for l in (recent_logs or [])[:15]
    ) or "  (no logs yet — just getting started!)"

    query = user_message or "Give me a personal health summary and one thing to focus on today."

    prompt = f"""{_personality(user_profile)}

Recent activity log:
{logs_summary}

User: {query}

Respond as their personal health coach and biggest supporter. 
Reference specific patterns you see in the logs.
If they've been consistent — celebrate it genuinely, be specific.
If there are gaps — be gentle and encouraging, never shaming, always forward-looking.
Always end with something that makes them feel proud of themselves."""

    try:
        msg = client.messages.create(
            model=MODEL, max_tokens=450,
            messages=[{"role": "user", "content": prompt}]
        )
        return msg.content[0].text.strip()
    except Exception as e:
        return "You're doing amazing just by checking in with yourself. That matters. Keep going — you've got this! 💊✨"


# ─────────────────────────────────────────────────────────────
# RUNNING COACH
# ─────────────────────────────────────────────────────────────
def running_coach(user_message: str, run_history: list = None, user_profile: dict = None) -> str:
    goal = (user_profile or {}).get("running_goal", "general fitness through running")

    history_ctx = ""
    if run_history:
        history_ctx = "\n\nTheir recent runs:\n" + "\n".join(
            f"  • {r.get('date','?')}: {r.get('distance','?')} km "
            f"in {r.get('duration','?')} min — {r.get('notes','')}"
            for r in run_history[:10]
        )

    prompt = f"""{_personality(user_profile)}

You are also their personal running coach. Their running goal: {goal}.{history_ctx}

User: {user_message}

Give specific, personalised running advice.
- If they share a run result — celebrate it genuinely and specifically
- Reference their goal and show them how today connects to it
- Include practical tips (pace, recovery, form, pre/post-run nutrition if relevant)
- If they're building up distance, give context on the progression
- Always end with something that reminds them how capable they are"""

    try:
        msg = client.messages.create(
            model=MODEL, max_tokens=550,
            messages=[{"role": "user", "content": prompt}]
        )
        return msg.content[0].text.strip()
    except Exception as e:
        return "Every run makes you stronger — even the hard ones. You've got this! 🏃‍♀️💪"


def generate_training_plan(current_fitness: str, user_profile: dict = None, goal_race: str = None) -> str:
    running_goal = (user_profile or {}).get("running_goal", "improve running fitness")
    name = (user_profile or {}).get("name", "you")

    prompt = f"""{_personality(user_profile)}

Create a personalised 4-week running training plan for {name}.
Current fitness level: {current_fitness}
Running goal: {running_goal}
{f"Goal race/event: {goal_race}" if goal_race else ""}

Format as a clear weekly plan with:
Week 1-4 broken down Mon–Sun:
- Run type (easy run / tempo / intervals / long run / rest / cross-train)
- Distance in km
- Key focus theme for the week
- One personal encouraging note per week that connects to their goal

Make it achievable but progressive. They are exceptional and will surprise themselves."""

    try:
        msg = client.messages.create(
            model=MODEL, max_tokens=1200,
            messages=[{"role": "user", "content": prompt}]
        )
        return msg.content[0].text.strip()
    except Exception as e:
        return "I couldn't generate a plan right now — try `/runplan` again shortly! 🏃"


# ─────────────────────────────────────────────────────────────
# NUTRITION
# ─────────────────────────────────────────────────────────────
def nutrition_advice(user_message: str, user_profile: dict = None) -> str:
    diet_ctx = ""
    if user_profile and user_profile.get("diet_notes"):
        diet_ctx = f"\nTheir dietary notes/preferences: {user_profile['diet_notes']}"
    run_ctx = ""
    if user_profile and user_profile.get("running_goal"):
        run_ctx = f"\nThey're a runner with goal: {user_profile['running_goal']} — consider fueling."

    prompt = f"""{_personality(user_profile)}

You are also their personal nutritionist.{diet_ctx}{run_ctx}

User: {user_message}

Give practical, science-backed advice tailored to everything you know about them.
Be warm, not clinical. Never shame any food choices — only build up.
If they're a runner, weave in fueling/recovery nutrition where relevant.
End with something encouraging about their effort to nourish themselves."""

    try:
        msg = client.messages.create(
            model=MODEL, max_tokens=500,
            messages=[{"role": "user", "content": prompt}]
        )
        return msg.content[0].text.strip()
    except Exception as e:
        return "Nourishing yourself is one of the most loving things you can do — you're doing great! 🥗💛"


# ─────────────────────────────────────────────────────────────
# TASK BREAKDOWN
# ─────────────────────────────────────────────────────────────
def break_down_task(task_description: str) -> dict | None:
    prompt = f"""Break this task into small, actionable Kanban steps for one person.
Return ONLY valid JSON — no markdown fences, no explanation:
{{
  "task_name": "short title (max 60 chars)",
  "priority": "High" | "Medium" | "Low",
  "estimated_days": <integer>,
  "steps": [
    {{
      "step": "clear, concrete action",
      "duration": "e.g. 30 min",
      "due_offset_days": <integer>
    }}
  ]
}}
3-7 steps. Practical and achievable.

Task: {task_description}"""

    try:
        msg = client.messages.create(
            model=MODEL, max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )
        text = msg.content[0].text.strip()
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text.strip())
    except Exception as e:
        print(f"[AI] Task breakdown error: {e}")
        return None


# ─────────────────────────────────────────────────────────────
# GENERAL CHAT — full personality, context-aware
# ─────────────────────────────────────────────────────────────
def chat(user_message: str, user_profile: dict = None) -> str:
    prompt = f"""{_personality(user_profile)}

Commands you can suggest: /run, /logrun, /runplan, /health, /log, /nutrition, /addtask, /tasks, /reminders, /checkin, /me

User: {user_message}

Respond naturally and warmly. Reference their profile if relevant. Guide to commands if helpful."""

    try:
        msg = client.messages.create(
            model=MODEL, max_tokens=350,
            messages=[{"role": "user", "content": prompt}]
        )
        return msg.content[0].text.strip()
    except Exception as e:
        return "I'm here for you always — try /help to see everything I can do! 💛"

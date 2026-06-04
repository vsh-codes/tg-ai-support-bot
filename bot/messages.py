"""
All user-facing and admin text strings.

Keeping them in one file makes copy edits trivial and sets up the project
for translation later — swap this module for one with `gettext` calls and
nothing else has to change.
"""

WELCOME = (
    "👋 Hi! I'm here to help with questions about {company_name}.\n\n"
    "Just send me your question and I'll do my best to answer based on "
    "what I know. If I can't help, I'll connect you with a human."
)

THINKING = "🤔 Looking that up..."

RATE_LIMITED = (
    "You've sent a lot of messages recently. "
    "Please wait a few minutes before sending more — this protects "
    "our service from abuse. Need urgent help? Type /human."
)

ERROR_GENERIC = (
    "Something went wrong on my side. "
    "Please try again in a moment, or type /human to reach a person."
)

ESCALATION_USER_MESSAGE = (
    "✅ I've notified a human agent. Someone will get back to you shortly.\n\n"
    "Meanwhile, feel free to keep asking me anything — I'll still try to help."
)

# Admin templates
ADMIN_ESCALATION_TEMPLATE = (
    "🚨 <b>Escalation needed</b>\n\n"
    "<b>User:</b> {full_name} {username}\n"
    "<b>User ID:</b> <code>{user_id}</code>\n"
    "<b>Reason:</b> {reason}\n\n"
    "<b>Recent conversation:</b>\n{transcript}\n\n"
    "Use /takeover {user_id} to pause the AI and reply directly."
)

ADMIN_STATS_TEMPLATE = (
    "📊 <b>Bot statistics</b>\n\n"
    "<b>Today:</b> {today_messages} messages from {today_users} users\n"
    "<b>This week:</b> {week_messages} messages from {week_users} users\n"
    "<b>All time:</b> {total_messages} messages from {total_users} users\n\n"
    "<b>Escalations today:</b> {today_escalations}\n"
    "<b>Knowledge base:</b> {kb_chunks} chunks indexed"
)

ADMIN_ONLY = "This command is for admins only."

KB_RELOADED = "✅ Knowledge base reloaded — {chunks} chunks indexed from {files} files."

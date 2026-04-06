import os
import json
import time
import random
import threading
import re
from datetime import datetime
import telebot
from flask import Flask
from playwright.sync_api import sync_playwright
from playwright_stealth import stealth_sync

# ============= FLASK WEB SERVER =============
app = Flask(__name__)

@app.route('/')
def home():
    return "🤖 Bot is running!", 200

@app.route('/health')
def health():
    return "OK", 200

def run_web():
    app.run(host='0.0.0.0', port=8080)

# ============= CONFIG =============
API_TOKEN = "8623039191:AAErxthmUyJAZV-xsEP2I_OY5rW_IUc6_8Q"
OWNER_ID = 8336576838
OWNER_USERNAME = "@pruvn"
DB_FILE = "sessions.json"

bot = telebot.TeleBot(API_TOKEN, parse_mode='HTML')
active_reports = {}
user_states = {}
MAX_ACCOUNTS_PER_USER = 4
MAX_REPORT_LIMIT = 2000

REPORT_REASONS = {
    "1": {"name": "💢 Hate Speech", "value": "hate_speech"},
    "2": {"name": "😔 Bullying/Harassment", "value": "bullying"},
    "3": {"name": "🔫 Violence", "value": "violence"},
    "4": {"name": "💰 Scam/Fraud", "value": "scam"},
    "5": {"name": "🔞 Nudity/Sexual Content", "value": "nudity"},
    "6": {"name": "🤕 Self Harm", "value": "self_harm"}
}

# ============= DATABASE =============
def load_db():
    if not os.path.exists(DB_FILE):
        return {"users": {}, "admins": []}
    with open(DB_FILE, 'r') as f:
        return json.load(f)

def save_db(data):
    with open(DB_FILE, 'w') as f:
        json.dump(data, f, indent=4)

def get_user_sessions(user_id):
    db = load_db()
    user_data = db.get("users", {}).get(str(user_id), {})
    return user_data.get("sessions", {})

def save_user_session(user_id, nickname, session_data):
    db = load_db()
    if str(user_id) not in db["users"]:
        db["users"][str(user_id)] = {"sessions": {}, "paired": []}
    db["users"][str(user_id)]["sessions"][nickname] = session_data
    save_db(db)

def delete_user_session(user_id, nickname):
    db = load_db()
    if str(user_id) in db["users"]:
        if nickname in db["users"][str(user_id)]["sessions"]:
            del db["users"][str(user_id)]["sessions"][nickname]
            save_db(db)
            return True
    return False

def get_paired_accounts(user_id):
    db = load_db()
    return db.get("users", {}).get(str(user_id), {}).get("paired", [])

def set_paired_accounts(user_id, paired_list):
    db = load_db()
    if str(user_id) not in db["users"]:
        db["users"][str(user_id)] = {"sessions": {}, "paired": []}
    db["users"][str(user_id)]["paired"] = paired_list
    save_db(db)

def is_admin(user_id):
    db = load_db()
    return user_id == OWNER_ID or str(user_id) in db.get("admins", [])

def extract_username_from_url(url):
    match = re.search(r'instagram\.com/([a-zA-Z0-9_.]+)', url)
    return match.group(1) if match else None

def take_screenshot(page, step_name, user_id):
    try:
        os.makedirs("screenshots", exist_ok=True)
        timestamp = int(time.time())
        filename = f"screenshots/{user_id}_{step_name}_{timestamp}.png"
        page.screenshot(path=filename)
        with open(filename, 'rb') as photo:
            bot.send_photo(user_id, photo, caption=f"📸 {step_name}")
        os.remove(filename)
        return True
    except:
        return False

def take_profile_screenshot(session_data, username, user_id):
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=['--disable-blink-features=AutomationControlled', '--no-sandbox']
            )
            context = browser.new_context(storage_state=session_data)
            page = context.new_page()
            stealth_sync(page)
            
            profile_url = f"https://www.instagram.com/{username}/"
            page.goto(profile_url, timeout=15000, wait_until='networkidle')
            time.sleep(2)
            
            os.makedirs("screenshots", exist_ok=True)
            timestamp = int(time.time())
            filename = f"screenshots/target_{username}_{timestamp}.png"
            page.screenshot(path=filename)
            
            with open(filename, 'rb') as photo:
                bot.send_photo(user_id, photo, caption=f"📸 Target Profile: @{username}")
            
            os.remove(filename)
            browser.close()
            return True
    except:
        return False

# ============= SESSION VALIDATION =============
def validate_session(session_data):
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=['--disable-blink-features=AutomationControlled', '--no-sandbox']
            )
            context = browser.new_context(storage_state=session_data)
            page = context.new_page()
            stealth_sync(page)
            
            page.goto("https://www.instagram.com/", timeout=10000)
            time.sleep(2)
            
            result = 'login' not in page.url
            browser.close()
            return result
    except:
        return False

# ============= REPORT FUNCTION =============
def report_account(session_data, username, reason):
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-images',
                    '--disable-css'
                ]
            )
            context = browser.new_context(storage_state=session_data)
            context.route("**/*", lambda route: route.abort() if route.request.resource_type in ["image", "font", "stylesheet", "svg", "media"] else route.continue_())
            page = context.new_page()
            stealth_sync(page)
            
            profile_url = f"https://www.instagram.com/{username}/"
            page.goto(profile_url, timeout=15000, wait_until='domcontentloaded')
            time.sleep(random.uniform(0.5, 1))
            
            menu_btn = page.wait_for_selector('svg[aria-label="Options"]', timeout=5000)
            menu_btn.click()
            time.sleep(random.uniform(0.3, 0.6))
            
            report_btn = page.wait_for_selector('button:has-text("Report")', timeout=3000)
            report_btn.click()
            time.sleep(random.uniform(0.3, 0.6))
            
            reason_btn = page.wait_for_selector(f'button:has-text("{reason}")', timeout=3000)
            reason_btn.click()
            time.sleep(random.uniform(0.3, 0.6))
            
            submit_btn = page.wait_for_selector('button:has-text("Submit")', timeout=3000)
            submit_btn.click()
            time.sleep(random.uniform(0.5, 1))
            
            browser.close()
            return True
    except:
        return False

# ============= REPORT WORKER =============
def report_worker(report_id, user_id, accounts, username, reason, report_limit):
    account_list = list(accounts.items())
    account_index = 0
    reports_sent = 0
    success_count = 0
    fail_count = 0
    
    while reports_sent < report_limit and active_reports.get(report_id, False):
        nickname, session_data = account_list[account_index % len(account_list)]
        
        success = report_account(session_data, username, reason)
        
        if success:
            success_count += 1
            bot.send_message(user_id, f"✅ Report #{reports_sent + 1} submitted by {nickname}\nTarget: @{username}")
        else:
            fail_count += 1
        
        reports_sent += 1
        account_index += 1
        time.sleep(random.uniform(1, 3))
    
    bot.send_message(user_id, f"📊 REPORTING COMPLETED!\n✅ Successful: {success_count}\n❌ Failed: {fail_count}\n🎯 Target: @{username}")
    active_reports[report_id] = False

# ============= HELP COMMAND =============
@bot.message_handler(commands=['help'])
def cmd_help(message):
    user_id = message.from_user.id
    
    help_text = """
<b>🔥 INSTAGRAM REPORT BOT - COMPLETE GUIDE 🔥</b>

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>📌 HOW TO GET SESSION ID:</b>

<b>Method 1 - Kiwi Browser (Recommended for Mobile):</b>
1. Download <b>Kiwi Browser</b> from Play Store
2. Open instagram.com and login
3. Tap 3 dots → <b>Developer Tools</b>
4. Go to <b>Application</b> tab → <b>Cookies</b>
5. Copy <b>sessionid</b> value

<b>Method 2 - Chrome Mobile:</b>
1. Open instagram.com in Chrome and login
2. Tap <b>🔒 lock icon</b> in address bar
3. Tap <b>Cookies</b> → <b>instagram.com</b>
4. Copy <b>sessionid</b> value

<b>Method 3 - PC/Laptop:</b>
1. Open Chrome, login to instagram.com
2. Press <b>F12</b> → <b>Application</b> tab
3. <b>Cookies</b> → <b>https://www.instagram.com</b>
4. Copy <b>sessionid</b> value

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>📌 HOW TO USE THE BOT:</b>

<b>1️⃣ /login</b>
• Send your Instagram session ID
• Bot will validate and save account
• Auto-nickname: acc1, acc2, acc3, acc4

<b>2️⃣ /pair</b>
• Single account = Auto-paired
• Multiple accounts: Send nicknames (acc1-acc2)

<b>3️⃣ /report</b>
• Send target username or URL
• Bot shows profile screenshot for confirmation
• Enter report limit (1-2000)
• Select reason (1-6)

<b>4️⃣ /status</b>
• Check active reports

<b>5️⃣ /stop</b>
• Stop current reporting

<b>6️⃣ /stopall</b>
• Stop all active reports

<b>7️⃣ /logout</b>
• Remove an account

<b>8️⃣ /cancel</b>
• Cancel ongoing operation

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>⚔️ REPORT REASONS:</b>

1 - 💢 Hate Speech
2 - 😔 Bullying/Harassment
3 - 🔫 Violence
4 - 💰 Scam/Fraud
5 - 🔞 Nudity/Sexual Content
6 - 🤕 Self Harm

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>📊 ACCOUNT LIMITS:</b>

• Max accounts per user: <b>4</b>
• Max reports per target: <b>2000</b>
• Safe reports/day per account: <b>50-100</b>

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>⚠️ IMPORTANT TIPS:</b>

• Keep 2-4 seconds gap between reports
• Don't report too fast (account may ban)
• Session lasts 7-30 days
• Use /logout to remove old accounts

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>👑 OWNER ONLY:</b>

/add_admin <user_id> <name>
/remove_admin <user_id>
/adminlist

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>Made by {OWNER_USERNAME}</b>
"""
    
    bot.reply_to(message, help_text, parse_mode='HTML')

# ============= BOT COMMANDS =============
@bot.message_handler(commands=['start'])
def cmd_start(message):
    user_id = message.from_user.id
    
    text = f"""🔥 INSTAGRAM REPORT BOT 🔥

📌 Commands:
/help - Complete user guide
/login - Add Instagram account (using session ID)
/pair - Pair accounts for reporting
/unpair - Remove paired accounts
/report - Start mass reporting
/status - View active reports
/stop - Stop current report
/stopall - Stop all reports
/logout - Remove account
/cancel - Cancel current operation

📊 Account Limit: {MAX_ACCOUNTS_PER_USER}
🎯 Report Limit: {MAX_REPORT_LIMIT} per target
🔄 Round Robin System

Type /help for detailed guide!

Made by {OWNER_USERNAME}"""
    
    if user_id == OWNER_ID:
        text += "\n\n👑 Owner Commands:\n/add_admin\n/remove_admin\n/adminlist"
    
    bot.reply_to(message, text)

@bot.message_handler(commands=['cancel'])
def cmd_cancel(message):
    user_id = message.from_user.id
    if user_id in user_states:
        del user_states[user_id]
    bot.reply_to(message, "❌ Operation cancelled!")

@bot.message_handler(commands=['login'])
def cmd_login(message):
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        bot.reply_to(message, f"❌ Unauthorized! Contact {OWNER_USERNAME}")
        return
    
    sessions = get_user_sessions(user_id)
    if len(sessions) >= MAX_ACCOUNTS_PER_USER:
        bot.reply_to(message, f"❌ You already have {MAX_ACCOUNTS_PER_USER} accounts! Use /logout to remove one.")
        return
    
    login_instructions = """
<b>🔐 SESSION ID LOGIN</b>

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>📱 How to get Session ID (Mobile):</b>

<b>Method 1 - Kiwi Browser (Easiest):</b>
1. Download <b>Kiwi Browser</b> from Play Store
2. Open instagram.com and login
3. Tap 3 dots → <b>Developer Tools</b>
4. <b>Application</b> tab → <b>Cookies</b>
5. Copy <b>sessionid</b> value

<b>Method 2 - Chrome Mobile:</b>
1. Login to instagram.com in Chrome
2. Tap <b>🔒 lock icon</b> in address bar
3. <b>Cookies</b> → <b>instagram.com</b>
4. Copy <b>sessionid</b> value

<b>Method 3 - PC/Laptop:</b>
1. Chrome me instagram.com login karo
2. <b>F12</b> → <b>Application</b> tab
3. <b>Cookies</b> → <b>instagram.com</b>
4. <b>sessionid</b> copy karo

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>📤 Send your session ID now:</b>
Example: <code>72192435484%3Aabc123xyz...</code>

Type /cancel to abort.
"""
    
    user_states[user_id] = {"step": "session_id"}
    bot.reply_to(message, login_instructions, parse_mode='HTML')

@bot.message_handler(commands=['pair'])
def cmd_pair(message):
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        bot.reply_to(message, f"❌ Unauthorized! Contact {OWNER_USERNAME}")
        return
    
    sessions = get_user_sessions(user_id)
    
    if not sessions:
        bot.reply_to(message, "❌ No accounts found! Use /login first.")
        return
    
    if len(sessions) == 1:
        set_paired_accounts(user_id, list(sessions.keys()))
        bot.reply_to(message, f"✅ Auto-paired! Using account: {list(sessions.keys())[0]}\n\nUse /report to start reporting.")
    else:
        session_list = "\n".join([f"• {name}" for name in sessions.keys()])
        user_states[user_id] = {"step": "pair", "sessions": sessions}
        bot.reply_to(message, f"Your accounts:\n{session_list}\n\nSend nicknames to pair (e.g., acc1-acc2):")

@bot.message_handler(commands=['unpair'])
def cmd_unpair(message):
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        bot.reply_to(message, f"❌ Unauthorized! Contact {OWNER_USERNAME}")
        return
    
    set_paired_accounts(user_id, [])
    bot.reply_to(message, "✅ All accounts unpaired!")

@bot.message_handler(commands=['report'])
def cmd_report(message):
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        bot.reply_to(message, f"❌ Unauthorized! Contact {OWNER_USERNAME}")
        return
    
    paired = get_paired_accounts(user_id)
    
    if not paired:
        bot.reply_to(message, "❌ No paired accounts! Use /pair first.")
        return
    
    sessions = get_user_sessions(user_id)
    paired_sessions = {name: sessions[name]["storage_state"] for name in paired if name in sessions}
    
    if not paired_sessions:
        bot.reply_to(message, "❌ Paired accounts not found! Please login again.")
        return
    
    user_states[user_id] = {"step": "target", "sessions": paired_sessions}
    bot.reply_to(message, "🎯 Send Instagram profile URL or username:\n\nExample: https://www.instagram.com/username/ or just username")

@bot.message_handler(commands=['status'])
def cmd_status(message):
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        bot.reply_to(message, f"❌ Unauthorized! Contact {OWNER_USERNAME}")
        return
    
    active = [rid for rid in active_reports if active_reports[rid] and rid.startswith(str(user_id))]
    if active:
        text = "⚔️ ACTIVE REPORTS\n\n"
        for rid in active:
            text += f"📌 {rid}\n"
        bot.reply_to(message, text)
    else:
        bot.reply_to(message, "No active reports.")

@bot.message_handler(commands=['stop'])
def cmd_stop(message):
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        bot.reply_to(message, f"❌ Unauthorized! Contact {OWNER_USERNAME}")
        return
    
    for rid in list(active_reports.keys()):
        if rid.startswith(str(user_id)) and active_reports[rid]:
            active_reports[rid] = False
            bot.reply_to(message, f"✅ Reporting stopped!")
            return
    bot.reply_to(message, "❌ No active report found!")

@bot.message_handler(commands=['stopall'])
def cmd_stopall(message):
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        bot.reply_to(message, f"❌ Unauthorized! Contact {OWNER_USERNAME}")
        return
    
    for rid in list(active_reports.keys()):
        active_reports[rid] = False
    active_reports.clear()
    bot.reply_to(message, "✅ All reports stopped!")

@bot.message_handler(commands=['logout'])
def cmd_logout(message):
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        bot.reply_to(message, f"❌ Unauthorized! Contact {OWNER_USERNAME}")
        return
    
    sessions = get_user_sessions(user_id)
    
    if not sessions:
        bot.reply_to(message, "❌ No accounts found!")
        return
    
    session_list = "\n".join([f"• {name}" for name in sessions.keys()])
    user_states[user_id] = {"step": "logout", "sessions": list(sessions.keys())}
    bot.reply_to(message, f"Your accounts:\n{session_list}\n\nSend nickname to remove:")

# ============= OWNER ONLY COMMANDS =============
@bot.message_handler(commands=['add_admin'])
def cmd_add_admin(message):
    if message.from_user.id != OWNER_ID:
        return
    
    try:
        parts = message.text.split()
        admin_id = int(parts[1])
        admin_name = parts[2] if len(parts) > 2 else f"Admin_{admin_id}"
        db = load_db()
        if str(admin_id) not in db.get("admins", []):
            db.setdefault("admins", []).append(str(admin_id))
            save_db(db)
            bot.reply_to(message, f"✅ Admin {admin_name} added!")
        else:
            bot.reply_to(message, "❌ Already an admin!")
    except:
        bot.reply_to(message, "Usage: /add_admin <user_id> <name>")

@bot.message_handler(commands=['remove_admin'])
def cmd_remove_admin(message):
    if message.from_user.id != OWNER_ID:
        return
    
    try:
        parts = message.text.split()
        admin_id = int(parts[1])
        db = load_db()
        if str(admin_id) in db.get("admins", []):
            db["admins"].remove(str(admin_id))
            save_db(db)
            bot.reply_to(message, f"✅ Admin {admin_id} removed!")
        else:
            bot.reply_to(message, "❌ Not an admin!")
    except:
        bot.reply_to(message, "Usage: /remove_admin <user_id>")

@bot.message_handler(commands=['adminlist'])
def cmd_adminlist(message):
    if message.from_user.id != OWNER_ID:
        return
    
    db = load_db()
    admins = db.get("admins", [])
    text = "<b>👑 ADMIN LIST</b>\n\n"
    text += f"👤 OWNER: {OWNER_USERNAME}\n"
    text += f"🆔 ID: <code>{OWNER_ID}</code>\n\n"
    if admins:
        text += "<b>📋 ADMINS:</b>\n"
        for aid in admins:
            text += f"• <code>{aid}</code>\n"
    else:
        text += "No admins"
    bot.reply_to(message, text, parse_mode='HTML')

# ============= CONVERSATION HANDLER =============
@bot.message_handler(func=lambda message: message.from_user.id in user_states)
def handle_conversation(message):
    user_id = message.from_user.id
    state = user_states[user_id]
    step = state.get("step")
    
    # Session ID login flow
    if step == "session_id":
        session_id = message.text.strip()
        
        # Create session data from session ID
        session_data = {
            "cookies": [{
                "name": "sessionid",
                "value": session_id,
                "domain": ".instagram.com",
                "path": "/",
                "httpOnly": True,
                "secure": True
            }],
            "origins": []
        }
        
        loading = bot.reply_to(message, "⏳ Validating session...")
        
        # Validate session
        if validate_session(session_data):
            # Take screenshot of logged in account
            bot.edit_message_text("📸 Taking profile screenshot...", loading.chat.id, loading.message_id)
            
            try:
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True)
                    context = browser.new_context()
                    context.add_cookies([{
                        "name": "sessionid",
                        "value": session_id,
                        "domain": ".instagram.com",
                        "path": "/"
                    }])
                    page = context.new_page()
                    stealth_sync(page)
                    
                    page.goto("https://www.instagram.com/", timeout=10000)
                    time.sleep(2)
                    
                    # Get username from profile
                    profile_link = page.query_selector('a[href^="/"]')
                    username = "unknown"
                    if profile_link:
                        href = profile_link.get_attribute('href')
                        username = href.replace('/', '')
                    
                    os.makedirs("screenshots", exist_ok=True)
                    timestamp = int(time.time())
                    filename = f"screenshots/{user_id}_login_{timestamp}.png"
                    page.screenshot(path=filename)
                    
                    with open(filename, 'rb') as photo:
                        bot.send_photo(user_id, photo, caption=f"✅ Logged in as: @{username}\n\nSession valid!")
                    
                    os.remove(filename)
                    browser.close()
                    
                    nickname = f"acc{len(get_user_sessions(user_id)) + 1}"
                    save_user_session(user_id, nickname, session_data)
                    bot.send_message(user_id, f"✅ Account saved!\n\nNickname: {nickname}\n\nUse /pair to add to army.")
            except:
                nickname = f"acc{len(get_user_sessions(user_id)) + 1}"
                save_user_session(user_id, nickname, session_data)
                bot.send_message(user_id, f"✅ Session saved!\n\nNickname: {nickname}\n\nUse /pair to add to army.")
        else:
            bot.edit_message_text("❌ Invalid session ID! Please check and try again.\n\nUse /login to retry.\n\nType /help for instructions.", loading.chat.id, loading.message_id)
        
        del user_states[user_id]
    
    # Pair flow
    elif step == "pair":
        nicknames = re.split(r'[-,\s]+', message.text.strip())
        sessions = state.get("sessions", {})
        valid = [n for n in nicknames if n in sessions]
        
        if not valid:
            bot.reply_to(message, "❌ No valid accounts!")
            return
        
        if len(valid) > MAX_ACCOUNTS_PER_USER:
            bot.reply_to(message, f"❌ Max {MAX_ACCOUNTS_PER_USER} accounts allowed!")
            return
        
        set_paired_accounts(user_id, valid)
        bot.reply_to(message, f"✅ Paired: {', '.join(valid)}\n\nUse /report to start.")
        del user_states[user_id]
    
    # Logout flow
    elif step == "logout":
        nickname = message.text.strip()
        sessions = state.get("sessions", [])
        
        if nickname not in sessions:
            bot.reply_to(message, f"❌ '{nickname}' not found!")
            return
        
        if delete_user_session(user_id, nickname):
            paired = get_paired_accounts(user_id)
            if nickname in paired:
                paired.remove(nickname)
                set_paired_accounts(user_id, paired)
            bot.reply_to(message, f"✅ '{nickname}' removed!")
        else:
            bot.reply_to(message, f"❌ Failed to remove!")
        
        del user_states[user_id]
    
    # Report flow - target
    elif step == "target":
        user_input = message.text.strip()
        
        if "instagram.com/" in user_input:
            username = extract_username_from_url(user_input)
            if not username:
                bot.reply_to(message, "❌ Invalid URL! Send correct Instagram URL:")
                return
        else:
            username = user_input.lower().replace("@", "")
            if not re.match(r'^[a-zA-Z0-9_.]+$', username):
                bot.reply_to(message, "❌ Invalid username! Send valid username or URL:")
                return
        
        user_states[user_id]["target_username"] = username
        user_states[user_id]["step"] = "confirm_profile"
        
        # Take screenshot of target profile
        bot.send_message(user_id, "📸 Fetching target profile screenshot...")
        
        paired = get_paired_accounts(user_id)
        sessions = get_user_sessions(user_id)
        first_account = paired[0] if paired else None
        
        if first_account and first_account in sessions:
            take_profile_screenshot(sessions[first_account]["storage_state"], username, user_id)
        
        user_states[user_id]["step"] = "limit"
        bot.reply_to(message, f"📊 Enter report limit (1-{MAX_REPORT_LIMIT}):")
    
    # Report flow - limit
    elif step == "limit":
        try:
            report_limit = int(message.text.strip())
            if 1 <= report_limit <= MAX_REPORT_LIMIT:
                user_states[user_id]["report_limit"] = report_limit
                user_states[user_id]["step"] = "reason"
                
                reasons_text = "📋 Select reason:\n\n"
                for key, reason in REPORT_REASONS.items():
                    reasons_text += f"{key}. {reason['name']}\n"
                bot.reply_to(message, reasons_text + "\nSend number (1-6):")
            else:
                bot.reply_to(message, f"❌ Limit 1-{MAX_REPORT_LIMIT}!")
        except:
            bot.reply_to(message, f"❌ Send a valid number!")
    
    # Report flow - reason
    elif step == "reason":
        selected = None
        for key, reason in REPORT_REASONS.items():
            if message.text.strip() == key:
                selected = reason['value']
                break
        
        if selected:
            target = user_states[user_id]["target_username"]
            limit = user_states[user_id]["report_limit"]
            sessions = user_states[user_id]["sessions"]
            
            report_id = f"{user_id}_{int(time.time())}"
            active_reports[report_id] = True
            
            thread = threading.Thread(
                target=report_worker,
                args=(report_id, user_id, sessions, target, selected, limit),
                daemon=True
            )
            thread.start()
            
            bot.reply_to(message, f"⚔️ REPORTING STARTED!\n🎯 @{target}\n🔢 {limit} reports\n👥 {len(sessions)} accounts\nUse /stop to stop.")
            del user_states[user_id]
        else:
            bot.reply_to(message, "❌ Invalid! Send 1-6:")

# ============= NON-ADMIN HANDLER =============
@bot.message_handler(func=lambda message: True)
def handle_non_admin(message):
    user_id = message.from_user.id
    
    if user_id in user_states or is_admin(user_id):
        return
    
    bot.reply_to(message, 
        f"⚠️ You are not authorized to use this bot.\n"
        f"Your ID: <code>{user_id}</code>\n"
        f"Contact owner: {OWNER_USERNAME} to get access.\n\n"
        f"Type /help to see bot features.",
        parse_mode='HTML')

# ============= MAIN =============
if __name__ == "__main__":
    print("="*60)
    print("🔥 INSTAGRAM REPORT BOT 🔥")
    print(f"👑 Owner: {OWNER_USERNAME} (ID: {OWNER_ID})")
    print(f"📁 Database: {DB_FILE}")
    print("="*60)
    print("✅ Bot running...")
    print("✅ Session-based Login (No OTP/Timeout)")
    print("✅ /help command added with complete guide")
    print("="*60)
    
    os.makedirs("screenshots", exist_ok=True)
    
    threading.Thread(target=run_web, daemon=True).start()
    
    try:
        bot.remove_webhook()
    except:
        pass
    
    bot.infinity_polling()
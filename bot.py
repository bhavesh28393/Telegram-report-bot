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

# ============= CONFIG =============
API_TOKEN = "8623039191:AAH4ZBGdbaTKVinsgjz0SdXhas2JKQzSqbQ"
OWNER_ID = 8336576838
OWNER_USERNAME = "@pruvn"
DB_FILE = "sessions.json"

bot = telebot.TeleBot(API_TOKEN, parse_mode='HTML')
active_reports = {}
user_states = {}
user_logins = {}
MAX_ACCOUNTS_PER_USER = 4
MAX_REPORT_LIMIT = 2000

# Flask app for keep-alive (Render needs a web server)
app = Flask(__name__)

@app.route('/')
def home():
    return "🤖 Instagram Report Bot is running!"

# Report reasons
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

def add_admin(admin_id):
    db = load_db()
    if str(admin_id) not in db.get("admins", []):
        db.setdefault("admins", []).append(str(admin_id))
        save_db(db)
        return True
    return False

def remove_admin(admin_id):
    db = load_db()
    if str(admin_id) in db.get("admins", []):
        db["admins"].remove(str(admin_id))
        save_db(db)
        return True
    return False

def get_admins():
    db = load_db()
    return db.get("admins", [])

def extract_username_from_url(url):
    match = re.search(r'instagram\.com/([a-zA-Z0-9_.]+)', url)
    if match:
        return match.group(1)
    return None

def take_profile_screenshot(session_data, username):
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(storage_state=session_data)
            page = context.new_page()
            stealth_sync(page)
            
            profile_url = f"https://www.instagram.com/{username}/"
            page.goto(profile_url, timeout=10000, wait_until='networkidle')
            time.sleep(1)
            
            screenshot_path = f"screenshots/{username}_{int(time.time())}.png"
            os.makedirs("screenshots", exist_ok=True)
            page.screenshot(path=screenshot_path)
            
            browser.close()
            return screenshot_path
    except Exception as e:
        print(f"Screenshot error: {e}")
        return None

# ============= INSTAGRAM LOGIN =============
def instagram_login(username, password, verification_method=None, verification_code=None):
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=False,
                args=['--disable-blink-features=AutomationControlled', '--no-sandbox']
            )
            context = browser.new_context()
            page = context.new_page()
            stealth_sync(page)
            
            page.goto("https://www.instagram.com/", timeout=15000)
            time.sleep(2)
            
            try:
                accept_btn = page.wait_for_selector('button:has-text("Accept")', timeout=3000)
                if accept_btn:
                    accept_btn.click()
                    time.sleep(1)
            except:
                pass
            
            username_input = page.wait_for_selector('input[name="username"]', timeout=10000)
            username_input.fill(username)
            time.sleep(0.5)
            
            password_input = page.query_selector('input[name="password"]')
            password_input.fill(password)
            time.sleep(0.5)
            
            login_btn = page.query_selector('button[type="submit"]')
            login_btn.click()
            time.sleep(3)
            
            if "challenge" in page.url or "two-factor" in page.url:
                if verification_method and verification_code:
                    code_input = page.wait_for_selector('input[name="verificationCode"]', timeout=10000)
                    code_input.fill(verification_code)
                    time.sleep(0.5)
                    submit_btn = page.query_selector('button[type="submit"]')
                    submit_btn.click()
                    time.sleep(3)
                else:
                    return {"status": "verification_needed", "method": verification_method}
            
            if "accounts/login" not in page.url and "challenge" not in page.url:
                storage_state = context.storage_state()
                browser.close()
                return {"status": "success", "storage_state": storage_state}
            else:
                browser.close()
                return {"status": "failed", "error": "Invalid credentials"}
    except Exception as e:
        return {"status": "failed", "error": str(e)}

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
            page.goto(profile_url, timeout=8000, wait_until='domcontentloaded')
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
    except Exception as e:
        print(f"Report error: {e}")
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
            bot.send_message(user_id, 
                f"✅ Report #{reports_sent + 1} submitted by {nickname}\n"
                f"Target: @{username}\n"
                f"Reason: {reason}")
        else:
            fail_count += 1
        
        reports_sent += 1
        account_index += 1
        time.sleep(random.uniform(1, 3))
    
    status_text = f"📊 REPORTING COMPLETED!\n\n"
    status_text += f"✅ Successful: {success_count}\n"
    status_text += f"❌ Failed: {fail_count}\n"
    status_text += f"🎯 Target: @{username}"
    
    bot.send_message(user_id, status_text)
    active_reports[report_id] = False

# ============= BOT COMMANDS =============
@bot.message_handler(commands=['start'])
def cmd_start(message):
    user_id = message.from_user.id
    
    text = f"""🔥 INSTAGRAM REPORT BOT 🔥

📌 Commands:
/login - Add Instagram account
/pair - Pair accounts for reporting
/unpair - Remove paired accounts
/report - Start mass reporting
/status - View active reports
/stop - Stop current report
/logout - Remove account
/cancel - Cancel current operation

📊 Account Limit: {MAX_ACCOUNTS_PER_USER}
🎯 Report Limit: {MAX_REPORT_LIMIT} per target
🔄 Round Robin System

Made by {OWNER_USERNAME}"""
    
    if user_id == OWNER_ID:
        text += """

👑 Owner Commands:
/add_admin - Add admin
/remove_admin - Remove admin
/adminlist - List all admins
/broadcast - Message all users"""
    elif is_admin(user_id):
        text += """

👑 Admin Commands:
/broadcast - Message all users"""
    
    bot.reply_to(message, text)

# ============= NON-ADMIN HANDLER =============
@bot.message_handler(func=lambda m: True, content_types=['text'])
def handle_non_admin(message):
    user_id = message.from_user.id
    
    # Skip if user is owner or admin
    if user_id == OWNER_ID or is_admin(user_id):
        return
    
    # Skip command messages
    if message.text.startswith('/'):
        return
    
    # Send access denied message
    bot.reply_to(message, 
        f"⚠️ <b>Access Denied!</b>\n\n"
        f"❌ You are not authorized to use this bot.\n"
        f"🆔 Your Telegram ID: <code>{user_id}</code>\n\n"
        f"📩 Please send this ID to {OWNER_USERNAME} to get access.\n\n"
        f"🔒 This bot is for authorized users only.",
        parse_mode='HTML')

# ============= OWNER COMMANDS =============
@bot.message_handler(commands=['add_admin'])
def cmd_add_admin(message):
    if message.from_user.id != OWNER_ID:
        return
    
    try:
        parts = message.text.split()
        if len(parts) < 2:
            bot.reply_to(message, "Usage: /add_admin <user_id>")
            return
        
        admin_id = int(parts[1])
        
        if admin_id == OWNER_ID:
            bot.reply_to(message, "❌ Owner is already admin!")
            return
        
        if add_admin(admin_id):
            bot.reply_to(message, f"✅ User {admin_id} is now an admin!")
        else:
            bot.reply_to(message, f"❌ User {admin_id} is already an admin!")
    except:
        bot.reply_to(message, "❌ Invalid user ID!")

@bot.message_handler(commands=['remove_admin'])
def cmd_remove_admin(message):
    if message.from_user.id != OWNER_ID:
        return
    
    try:
        parts = message.text.split()
        if len(parts) < 2:
            bot.reply_to(message, "Usage: /remove_admin <user_id>")
            return
        
        admin_id = int(parts[1])
        
        if admin_id == OWNER_ID:
            bot.reply_to(message, "❌ Cannot remove owner!")
            return
        
        if remove_admin(admin_id):
            bot.reply_to(message, f"✅ User {admin_id} is no longer an admin!")
        else:
            bot.reply_to(message, f"❌ User {admin_id} was not an admin!")
    except:
        bot.reply_to(message, "❌ Invalid user ID!")

@bot.message_handler(commands=['adminlist'])
def cmd_adminlist(message):
    if message.from_user.id != OWNER_ID:
        return
    
    admins = get_admins()
    text = "<b>👑 ADMIN LIST</b>\n\n"
    text += f"👤 OWNER: {OWNER_USERNAME}\n\n"
    
    if admins:
        text += "<b>📋 ADMINS:</b>\n"
        for aid in admins:
            text += f"• <code>{aid}</code>\n"
    else:
        text += "No other admins"
    
    bot.reply_to(message, text, parse_mode='HTML')

@bot.message_handler(commands=['broadcast'])
def cmd_broadcast(message):
    if not is_admin(message.from_user.id):
        return
    
    text = message.text.replace('/broadcast', '', 1).strip()
    if not text:
        bot.reply_to(message, "Usage: /broadcast <message>")
        return
    
    db = load_db()
    users = db.get('users', [])
    
    status = bot.reply_to(message, f"📢 Broadcasting to {len(users)} users...")
    sent = 0
    
    for uid in users:
        try:
            bot.send_message(int(uid), f"📢 ANNOUNCEMENT\n\n{text}")
            sent += 1
            time.sleep(0.05)
        except:
            pass
    
    bot.edit_message_text(f"✅ Sent to {sent} users", status.chat.id, status.message_id)

# ============= ACCOUNT COMMANDS =============
@bot.message_handler(commands=['login'])
def cmd_login(message):
    if not is_admin(message.from_user.id):
        return
    
    user_id = message.from_user.id
    sessions = get_user_sessions(user_id)
    
    if len(sessions) >= MAX_ACCOUNTS_PER_USER:
        bot.reply_to(message, f"❌ You already have {MAX_ACCOUNTS_PER_USER} accounts! Use /logout to remove one.")
        return
    
    user_states[user_id] = {"step": "username"}
    bot.reply_to(message, "🔐 Send Instagram username (without @):\n\nType /cancel to abort.")

@bot.message_handler(commands=['cancel'])
def cmd_cancel(message):
    user_id = message.from_user.id
    if user_id in user_states:
        del user_states[user_id]
    if user_id in user_logins:
        del user_logins[user_id]
    bot.reply_to(message, "❌ Current operation cancelled!")

@bot.message_handler(commands=['pair'])
def cmd_pair(message):
    if not is_admin(message.from_user.id):
        return
    
    user_id = message.from_user.id
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
        bot.reply_to(message, f"Your accounts:\n{session_list}\n\nSend nicknames to pair (e.g., acc1-acc2 or acc1,acc2):\nMax {MAX_ACCOUNTS_PER_USER} accounts")

@bot.message_handler(commands=['unpair'])
def cmd_unpair(message):
    if not is_admin(message.from_user.id):
        return
    
    user_id = message.from_user.id
    set_paired_accounts(user_id, [])
    bot.reply_to(message, "✅ All accounts unpaired! Use /pair to create new army.")

@bot.message_handler(commands=['report'])
def cmd_report(message):
    if not is_admin(message.from_user.id):
        return
    
    user_id = message.from_user.id
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
    bot.reply_to(message, "🎯 Send Instagram profile URL or username:\n\nExample: https://www.instagram.com/username/\nor: username")

@bot.message_handler(commands=['status'])
def cmd_status(message):
    if not is_admin(message.from_user.id):
        return
    
    user_id = message.from_user.id
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
    if not is_admin(message.from_user.id):
        return
    
    user_id = message.from_user.id
    for rid in list(active_reports.keys()):
        if rid.startswith(str(user_id)) and active_reports[rid]:
            active_reports[rid] = False
            bot.reply_to(message, f"✅ Reporting stopped for {rid}")
            return
    bot.reply_to(message, "❌ No active report found!")

@bot.message_handler(commands=['logout'])
def cmd_logout(message):
    if not is_admin(message.from_user.id):
        return
    
    user_id = message.from_user.id
    sessions = get_user_sessions(user_id)
    
    if not sessions:
        bot.reply_to(message, "❌ No accounts found!")
        return
    
    session_list = "\n".join([f"• {name}" for name in sessions.keys()])
    user_states[user_id] = {"step": "logout", "sessions": list(sessions.keys())}
    bot.reply_to(message, f"Your accounts:\n{session_list}\n\nSend nickname to remove:")

# ============= CONVERSATION HANDLERS =============
@bot.message_handler(func=lambda message: True)
def handle_conversation(message):
    user_id = message.from_user.id
    
    if user_id not in user_states:
        return
    
    state = user_states[user_id]
    step = state.get("step")
    
    # Login flow
    if step == "username":
        username = message.text.strip().lower().replace("@", "")
        user_logins[user_id] = {"username": username}
        user_states[user_id]["step"] = "password"
        bot.reply_to(message, "🔑 Send password:")
        
    elif step == "password":
        password = message.text.strip()
        user_logins[user_id]["password"] = password
        user_states[user_id]["step"] = "verification"
        bot.reply_to(message, "🔐 Login in progress...")
        
        result = instagram_login(user_logins[user_id]["username"], user_logins[user_id]["password"])
        
        if result["status"] == "success":
            nickname = f"acc{len(get_user_sessions(user_id)) + 1}"
            save_user_session(user_id, nickname, result["storage_state"])
            bot.reply_to(message, f"✅ Login successful!\n\nNickname: {nickname}\n\nUse /pair to start reporting.")
            del user_states[user_id]
            del user_logins[user_id]
            
        elif result["status"] == "verification_needed":
            user_states[user_id]["verification"] = True
            bot.reply_to(message, "📱 Verification required!\n\nSend 'SMS' or 'Email' to receive code:")
            
        else:
            bot.reply_to(message, f"❌ Login failed: {result.get('error', 'Unknown error')}\n\nUse /login to try again.")
            del user_states[user_id]
            del user_logins[user_id]
            
    elif step == "verification" and state.get("verification"):
        method = message.text.strip().lower()
        if method in ["sms", "email"]:
            user_states[user_id]["method"] = method
            user_states[user_id]["step"] = "verification_code"
            bot.reply_to(message, f"🔢 Send the {method.upper()} verification code:")
        else:
            bot.reply_to(message, "❌ Please send 'SMS' or 'Email'")
            
    elif step == "verification_code":
        code = message.text.strip()
        result = instagram_login(
            user_logins[user_id]["username"],
            user_logins[user_id]["password"],
            user_states[user_id].get("method"),
            code
        )
        
        if result["status"] == "success":
            nickname = f"acc{len(get_user_sessions(user_id)) + 1}"
            save_user_session(user_id, nickname, result["storage_state"])
            bot.reply_to(message, f"✅ Login successful!\n\nNickname: {nickname}\n\nUse /pair to start reporting.")
            del user_states[user_id]
            del user_logins[user_id]
        else:
            bot.reply_to(message, "❌ Verification failed! Use /login to try again.")
            del user_states[user_id]
            del user_logins[user_id]
    
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
        bot.reply_to(message, f"✅ Paired accounts: {', '.join(valid)}\n\nUse /report to start reporting.")
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
            bot.reply_to(message, f"❌ Failed to remove '{nickname}'!")
        
        del user_states[user_id]
    
    # Report flow
    elif step == "target":
        user_input = message.text.strip()
        
        if "instagram.com/" in user_input:
            username = extract_username_from_url(user_input)
            if not username:
                bot.reply_to(message, "❌ Invalid Instagram URL! Please send correct URL.")
                return
        else:
            username = user_input.lower().replace("@", "")
            if not re.match(r'^[a-zA-Z0-9_.]+$', username):
                bot.reply_to(message, "❌ Invalid username! Please send valid Instagram username or URL.")
                return
        
        user_states[user_id]["target_username"] = username
        user_states[user_id]["step"] = "confirm"
        
        loading_msg = bot.reply_to(message, "📸 Fetching profile screenshot...")
        
        paired = get_paired_accounts(user_id)
        sessions = get_user_sessions(user_id)
        first_account = paired[0] if paired else None
        
        if first_account and first_account in sessions:
            screenshot_path = take_profile_screenshot(sessions[first_account]["storage_state"], username)
            
            if screenshot_path:
                with open(screenshot_path, 'rb') as photo:
                    bot.send_photo(user_id, photo, caption=f"📸 Is this the correct account?\n\nUsername: @{username}\n\nReply with 'yes' to confirm or 'no' to cancel.")
                os.remove(screenshot_path)
            else:
                bot.reply_to(message, f"⚠️ Could not fetch screenshot.\n\nUsername: @{username}\n\nReply with 'yes' to confirm or 'no' to cancel.")
        else:
            bot.reply_to(message, f"⚠️ Account: @{username}\n\nReply with 'yes' to confirm or 'no' to cancel.")
    
    elif step == "confirm":
        confirmation = message.text.strip().lower()
        
        if confirmation == "yes":
            user_states[user_id]["step"] = "limit"
            bot.reply_to(message, f"📊 Enter report limit (1-{MAX_REPORT_LIMIT}):\n\nHow many reports to send?")
        elif confirmation == "no":
            bot.reply_to(message, "❌ Operation cancelled! Use /report to try again.")
            del user_states[user_id]
        else:
            bot.reply_to(message, "❌ Please reply with 'yes' to confirm or 'no' to cancel.")
    
    elif step == "limit":
        try:
            report_limit = int(message.text.strip())
            if 1 <= report_limit <= MAX_REPORT_LIMIT:
                user_states[user_id]["report_limit"] = report_limit
                user_states[user_id]["step"] = "reason"
                
                reasons_text = "📋 Select report reason:\n\n"
                for key, reason in REPORT_REASONS.items():
                    reasons_text += f"{key}. {reason['name']}\n"
                reasons_text += f"\nSend the number (1-{len(REPORT_REASONS)}) or reason name:"
                
                bot.reply_to(message, reasons_text)
            else:
                bot.reply_to(message, f"❌ Report limit must be between 1 and {MAX_REPORT_LIMIT}!\n\nPlease enter a valid number:")
        except ValueError:
            bot.reply_to(message, f"❌ Please enter a valid number (1-{MAX_REPORT_LIMIT}):")
    
    elif step == "reason":
        user_input = message.text.strip().lower()
        
        selected_reason = None
        selected_key = None
        for key, reason in REPORT_REASONS.items():
            if user_input == key or user_input == reason['value'] or user_input == reason['name'].lower():
                selected_reason = reason['value']
                selected_key = key
                break
        
        if selected_reason:
            target_username = user_states[user_id]["target_username"]
            report_limit = user_states[user_id]["report_limit"]
            sessions = user_states[user_id]["sessions"]
            
            report_id = f"{user_id}_{int(time.time())}"
            active_reports[report_id] = True
            
            thread = threading.Thread(
                target=report_worker,
                args=(report_id, user_id, sessions, target_username, selected_reason, report_limit),
                daemon=True
            )
            thread.start()
            
            bot.reply_to(message, 
                f"⚔️ REPORTING STARTED!\n\n"
                f"🎯 Target: @{target_username}\n"
                f"📝 Reason: {REPORT_REASONS[selected_key]['name']}\n"
                f"🔢 Limit: {report_limit} reports\n"
                f"👥 Accounts: {len(sessions)}\n"
                f"🔄 Mode: Round Robin\n\n"
                f"📨 You'll receive updates for each report!\n"
                f"Use /stop to stop reporting.")
            
            del user_states[user_id]
        else:
            bot.reply_to(message, "❌ Invalid reason! Please select a valid option.")

# ============= MAIN =============
if __name__ == "__main__":
    print("="*60)
    print("🔥 INSTAGRAM REPORT BOT 🔥")
    print(f"👑 Owner: {OWNER_USERNAME} (ID: {OWNER_ID})")
    print(f"📁 Database: {DB_FILE}")
    print(f"📊 Max Report Limit: {MAX_REPORT_LIMIT}")
    print("="*60)
    print("✅ Bot running...")
    
    os.makedirs("screenshots", exist_ok=True)
    
    # Start web server for keep-alive
    def run_web():
        app.run(host='0.0.0.0', port=8080)
    
    web_thread = threading.Thread(target=run_web, daemon=True)
    web_thread.start()
    
    try:
        bot.remove_webhook()
        print("✅ Webhook removed")
    except:
        pass
    
    bot.infinity_polling()

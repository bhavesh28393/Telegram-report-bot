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

# ============= FLASK WEB SERVER (Keep Alive) =============
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
user_logins = {}
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
    except:
            return None

# ============= SMART INSTAGRAM LOGIN WITH OTP HANDLING =============
def instagram_login_smart(user_id, username, password, verification_method=None, verification_code=None, retry_count=0):
    """Smart login that handles OTP and shows available options"""
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=['--disable-blink-features=AutomationControlled', '--no-sandbox']
            )
            context = browser.new_context()
            page = context.new_page()
            stealth_sync(page)
            
            # Send status update
            bot.send_message(user_id, "🌐 Opening Instagram...")
            
            page.goto("https://www.instagram.com/", timeout=15000)
            time.sleep(2)
            
            # Accept cookies if present
            try:
                accept_btn = page.wait_for_selector('button:has-text("Accept")', timeout=3000)
                if accept_btn:
                    accept_btn.click()
                    time.sleep(1)
            except:
                pass
            
            # Enter username
            username_input = page.wait_for_selector('input[name="username"]', timeout=10000)
            username_input.fill(username)
            time.sleep(0.5)
            
            # Enter password
            password_input = page.query_selector('input[name="password"]')
            password_input.fill(password)
            time.sleep(0.5)
            
            # Click login
            login_btn = page.query_selector('button[type="submit"]')
            login_btn.click()
            time.sleep(3)
            
            # Check for verification/challenge
            if "challenge" in page.url or "two-factor" in page.url:
                # Try to find verification options (SMS or Email)
                bot.send_message(user_id, "🔐 Verification required!")
                
                # Check what options are available
                page_content = page.content()
                
                # Look for phone/email options
                options = []
                if "sms" in page_content.lower() or "phone" in page_content.lower():
                    options.append("sms")
                if "email" in page_content.lower():
                    options.append("email")
                
                # If we already have a method and code, submit it
                if verification_method and verification_code:
                    bot.send_message(user_id, f"📱 Sending {verification_method.upper()} code...")
                    
                    # Try to find code input
                    code_input = page.wait_for_selector('input[name="verificationCode"]', timeout=10000)
                    code_input.fill(verification_code)
                    time.sleep(0.5)
                    
                    submit_btn = page.query_selector('button[type="submit"]')
                    submit_btn.click()
                    time.sleep(3)
                    
                    # Check if login successful
                    if "accounts/login" not in page.url and "challenge" not in page.url:
                        storage_state = context.storage_state()
                        browser.close()
                        return {"status": "success", "storage_state": storage_state}
                    else:
                        if retry_count < 2:
                            browser.close()
                            return instagram_login_smart(user_id, username, password, verification_method, verification_code, retry_count + 1)
                        else:
                            browser.close()
                            return {"status": "failed", "error": "Invalid verification code"}
                
                # First time - ask user for method
                else:
                    browser.close()
                    return {"status": "verification_needed", "options": options if options else ["sms", "email"]}
            
            # Check if login successful (no verification needed)
            if "accounts/login" not in page.url and "challenge" not in page.url:
                storage_state = context.storage_state()
                browser.close()
                return {"status": "success", "storage_state": storage_state}
            else:
                browser.close()
                return {"status": "failed", "error": "Invalid username or password"}
                
    except Exception as e:
        if retry_count < 2:
            return instagram_login_smart(user_id, username, password, verification_method, verification_code, retry_count + 1)
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
        text += "\n\n👑 Owner Commands:\n/add_admin\n/remove_admin\n/adminlist"
    
    bot.reply_to(message, text)

@bot.message_handler(commands=['cancel'])
def cmd_cancel(message):
    user_id = message.from_user.id
    if user_id in user_states:
        del user_states[user_id]
    if user_id in user_logins:
        del user_logins[user_id]
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
    
    user_states[user_id] = {"step": "username"}
    bot.reply_to(message, "🔐 Send Instagram username (without @):\n\nType /cancel to abort.")

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
        bot.reply_to(message, "🔐 Logging in...")
        
        # Call smart login function
        result = instagram_login_smart(user_id, user_logins[user_id]["username"], user_logins[user_id]["password"])
        
        if result["status"] == "success":
            nickname = f"acc{len(get_user_sessions(user_id)) + 1}"
            save_user_session(user_id, nickname, result["storage_state"])
            bot.reply_to(message, f"✅ Login successful!\n\nNickname: {nickname}\n\nUse /pair to start reporting.")
            del user_states[user_id]
            del user_logins[user_id]
            
        elif result["status"] == "verification_needed":
            user_states[user_id]["verification"] = True
            options = result.get("options", ["sms", "email"])
            options_text = "/".join(options).upper()
            bot.reply_to(message, f"📱 Verification required!\n\nSend '{options_text}' to receive code:")
            
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
        result = instagram_login_smart(
            user_id,
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
        selected_key = None
        for key, reason in REPORT_REASONS.items():
            if message.text.strip() == key or message.text.strip().lower() == reason['value']:
                selected = reason['value']
                selected_key = key
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
        f"Contact owner: {OWNER_USERNAME} to get access.",
        parse_mode='HTML')

# ============= MAIN =============
if __name__ == "__main__":
    print("="*60)
    print("🔥 INSTAGRAM REPORT BOT 🔥")
    print(f"👑 Owner: {OWNER_USERNAME} (ID: {OWNER_ID})")
    print(f"📁 Database: {DB_FILE}")
    print("="*60)
    print("✅ Bot running on Render...")
    print("✅ Flask web server running on port 8080")
    print("✅ Smart Login with OTP Support Active")
    print("="*60)
    
    os.makedirs("screenshots", exist_ok=True)
    
    # Start Flask web server in background
    threading.Thread(target=run_web, daemon=True).start()
    
    try:
        bot.remove_webhook()
        print("✅ Webhook removed")
    except:
        pass
    
    bot.infinity_polling()
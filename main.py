import os
import logging
import ipaddress
import json
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters, ConversationHandler
from jdatetime import date as jdate

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# States for conversation
MAIN_MENU, WALLET, BUY_DNS, ADMIN_PANEL, SELECT_LOCATION, SELECT_IP_TYPE, CONFIRM_PURCHASE = range(7)

# Data storage
USER_DATA_FILE = "user_data.json"
SERVER_DATA_FILE = "server_data.json"
BOT_CONFIG_FILE = "bot_config.json"

# Default configurations
DEFAULT_BOT_CONFIG = {
    "is_active": True,
    "admins": ["7240662021"],  # Replace with your Telegram ID
}

DEFAULT_SERVER_DATA = {
    "locations": {
        "germany": {"active": True, "flag": "🇩🇪", "name": "آلمان", "ipv4_cidr": ["185.220.70.0/24"], "ipv6_prefix": ["2001:ac8:20::/48"], "price": 18000},
        "finland": {"active": True, "flag": "🇫🇮", "name": "فنلاند", "ipv4_cidr": ["192.168.2.0/24"], "ipv6_prefix": ["2001:db8:3::", "2001:db8:4::"], "price": 22500},
        "albania": {"active": True, "flag": "🇦🇱", "name": "آلبانی", "ipv4_cidr": ["192.168.3.0/24"], "ipv6_prefix": ["2001:db8:5::", "2001:db8:6::"], "price": 16500},
        "turkey": {"active": True, "flag": "🇹🇷", "name": "ترکیه", "ipv4_cidr": ["192.168.4.0/24"], "ipv6_prefix": ["2001:db8:7::", "2001:db8:8::"], "price": 19500},
        "russia": {"active": True, "flag": "🇷🇺", "name": "روسیه", "ipv4_cidr": ["192.168.5.0/24"], "ipv6_prefix": ["2001:db8:9::", "2001:db8:10::"], "price": 15000}
    },
    "prices": {
        "dns_package": 30000 #Price for the DNS package
    }
}

DEFAULT_USER_DATA = {}

# Helper functions to load and save data
def load_data(file_path, default_data):
    try:
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as file:
                return json.load(file)
        return default_data
    except Exception as e:
        logger.error(f"Error loading data from {file_path}: {e}")
        return default_data

def save_data(file_path, data):
    try:
        with open(file_path, 'w', encoding='utf-8') as file:
            json.dump(data, file, ensure_ascii=False, indent=4)
        return True
    except Exception as e:
        logger.error(f"Error saving data to {file_path}: {e}")
        return False

# Load initial data
user_data = load_data(USER_DATA_FILE, DEFAULT_USER_DATA)
server_data = load_data(SERVER_DATA_FILE, DEFAULT_SERVER_DATA)
bot_config = load_data(BOT_CONFIG_FILE, DEFAULT_BOT_CONFIG)

# IP Address Generation Functions
def load_used_addresses():
    try:
        if os.path.exists("used_addresses.json"):
            with open("used_addresses.json", 'r', encoding='utf-8') as file:
                return json.load(file)
        return {"ipv4": {}, "ipv6": {}}
    except Exception as e:
        logger.error(f"Error loading used addresses: {e}")
        return {"ipv4": {}, "ipv6": {}}

def save_used_addresses(used_addresses):
    try:
        with open("used_addresses.json", 'w', encoding='utf-8') as file:
            json.dump(used_addresses, file, ensure_ascii=False, indent=4)
        return True
    except Exception as e:
        logger.error(f"Error saving used addresses: {e}")
        return False

def generate_ipv4(cidr_or_list):
    """Generate a new IPv4 address from one of the CIDR ranges that hasn't been used before"""
    # Load used addresses
    used_addresses = load_used_addresses()
    
    # Handle both single CIDR and list of CIDRs
    cidr_list = [cidr_or_list] if isinstance(cidr_or_list, str) else cidr_or_list
    
    # Shuffle the CIDR list to randomize selection
    import random
    random.shuffle(cidr_list)
    
    # Try each CIDR range until we find an available address
    for cidr in cidr_list:
        # Initialize CIDR tracking if needed
        if cidr not in used_addresses["ipv4"]:
            used_addresses["ipv4"][cidr] = []
        
        # Generate addresses from the network
        network = ipaddress.IPv4Network(cidr)
        total_addresses = network.num_addresses
        used_count = len(used_addresses["ipv4"][cidr])
        
        # If all addresses used in this CIDR, try the next one
        if used_count >= total_addresses:
            logger.warning(f"All IPv4 addresses in {cidr} have been used. Trying another range.")
            continue
        
        # Generate a random address from the network
        available_hosts = list(network.hosts())
        
        # Shuffle the list to get random IPs
        random.shuffle(available_hosts)
        
        # Find an unused address
        for ip in available_hosts:
            ip_str = str(ip)
            if ip_str not in used_addresses["ipv4"][cidr]:
                # Record this IP as used
                used_addresses["ipv4"][cidr].append(ip_str)
                save_used_addresses(used_addresses)
                return ip_str
    
    # If all ranges are exhausted, reuse from the first range (with warning)
    logger.warning(f"All IPv4 addresses in all ranges have been used. Reusing addresses.")
    first_cidr = cidr_list[0]
    if used_addresses["ipv4"][first_cidr]:
        return used_addresses["ipv4"][first_cidr][0]
    
    # Absolute fallback (should not reach here)
    return str(ipaddress.IPv4Network(cidr_list[0])[1])

def generate_ipv6(prefix_or_list, start=0, count=100, suffix="1"):
    """Generate IPv6 addresses in the format 2001:ac8:20**:****:****::0/1"""
    # Load used addresses
    used_addresses = load_used_addresses()
    
    # Handle both single prefix and list of prefixes
    import random
    prefix_list = [prefix_or_list] if isinstance(prefix_or_list, str) else prefix_or_list
    
    # Shuffle the prefix list to randomize selection
    random.shuffle(prefix_list)
    
    # Try each prefix until we find an available address
    for prefix in prefix_list:
        # Initialize prefix tracking if needed
        if prefix not in used_addresses["ipv6"]:
            used_addresses["ipv6"][prefix] = []
        
        # Generate a new unique address
        network = ipaddress.IPv6Network(prefix)
        prefix_parts = str(network.network_address).split(':')[:3]  # Get first 3 parts
        
        # Try up to 50 times to generate a unique address for this prefix
        for _ in range(50):
            # Generate random parts for the middle sections
            part1 = f"{random.randint(1, 9999):04x}"
            part2 = f"{random.randint(1, 9999):04x}"

            # Format according to the required pattern
            formatted_ip = f"{prefix_parts[0]}:{prefix_parts[1]}:{prefix_parts[2]}:{part1}:{part2}::{suffix}"
            
            # Check if it's already used
            if formatted_ip not in used_addresses["ipv6"][prefix]:
                # Record this IP as used
                used_addresses["ipv6"][prefix].append(formatted_ip)
                save_used_addresses(used_addresses)
                return formatted_ip
        
        # If we couldn't find a unique address, try the next prefix
        logger.warning(f"Failed to generate unique IPv6 address for {prefix}. Trying another prefix.")
    
    # If all prefixes are exhausted, reuse from the first prefix (with warning)
    first_prefix = prefix_list[0]
    logger.warning(f"All IPv6 addresses in all prefixes have been exhausted. Reusing oldest address.")
    if used_addresses["ipv6"][first_prefix]:
        return used_addresses["ipv6"][first_prefix][0]
    
    # Absolute fallback (should not reach here)
    part1 = f"{random.randint(1, 9999):04x}"
    part2 = f"{random.randint(1, 9999):04x}"
    prefix_parts = str(ipaddress.IPv6Network(first_prefix).network_address).split(':')[:3]
    formatted_ip = f"{prefix_parts[0]}:{prefix_parts[1]}:{prefix_parts[2]}:{part1}:{part2}::{suffix}"
    used_addresses["ipv6"][first_prefix].append(formatted_ip)
    save_used_addresses(used_addresses)
    return formatted_ip

def generate_ipv6_pair(prefix):
    """Generate a pair of IPv6 addresses with ::0 and ::1 endings"""
    part1 = generate_ipv6(prefix, suffix="0")
    part2 = generate_ipv6(prefix, suffix="1")
    return part1, part2

# Check if user is admin
def is_admin(user_id):
    return str(user_id) in bot_config.get("admins", [])

# Create user if not exists
def ensure_user_exists(user_id, username):
    user_id = str(user_id)
    if user_id not in user_data:
        user_data[user_id] = {
            "username": username,
            "balance": 0,
            "services": [],
            "joined_at": datetime.now().isoformat()
        }
        save_data(USER_DATA_FILE, user_data)
    return user_data[user_id]

# Function to convert Gregorian date to Persian date
def gregorian_to_persian(date_str):
    try:
        gregorian_date = datetime.fromisoformat(date_str).date()
        persian_date = jdate(gregorian_date.year, gregorian_date.month, gregorian_date.day)
        return persian_date.strftime('%Y/%m/%d')
    except ValueError:
        return "تاریخ نامعتبر"

# Command handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    ensure_user_exists(user.id, user.username)

    if not bot_config.get("is_active", True) and not is_admin(user.id):
        await update.message.reply_text("ربات در حال حاضر غیرفعال است. لطفا بعدا مراجعه کنید.")
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton("🌐 خرید DNS", callback_data="buy_dns")],
        [InlineKeyboardButton("💰 کیف پول", callback_data="wallet"), 
         InlineKeyboardButton("📋 سرویس های من", callback_data="my_services")],
        [InlineKeyboardButton("👤 حساب کاربری", callback_data="user_profile"),
         InlineKeyboardButton("➕ افزایش موجودی", callback_data="add_balance")] # Add "Add Balance" button
    ]

    if is_admin(user.id):
        keyboard.append([InlineKeyboardButton("👑 پنل مدیریت", callback_data="admin_panel")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"سلام {user.first_name}! به ربات فروش DNS خوش آمدید.",
        reply_markup=reply_markup
    )

    return MAIN_MENU

async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "user_profile":
        user_info = ensure_user_exists(user_id, query.from_user.username)
        join_date = datetime.fromisoformat(user_info['joined_at']).strftime('%Y-%m-%d')
        persian_date = gregorian_to_persian(user_info['joined_at'])
        services_count = len(user_info.get('services', []))

        keyboard = [
            [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            f"👤 *اطلاعات حساب کاربری*\n\n"
            f"🆔 شناسه کاربری: `{user_id}`\n"
            f"👤 نام کاربری: @{user_info['username'] or 'بدون نام کاربری'}\n"
            f"💰 موجودی: {user_info['balance']} تومان\n"
            f"📊 تعداد سرویس‌ها: {services_count}\n"
            f"📅 تاریخ عضویت: {persian_date}",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return MAIN_MENU

    elif query.data == "wallet":
        user_info = ensure_user_exists(user_id, query.from_user.username)
        keyboard = [
            [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            f"💰 موجودی کیف پول شما: {user_info['balance']} تومان",
            reply_markup=reply_markup
        )
        return WALLET

    elif query.data == "buy_dns":
        # Check if any locations are active
        active_locations = [loc for loc, data in server_data['locations'].items() if data['active']]
        if not active_locations:
            await query.edit_message_text(
                "در حال حاضر هیچ لوکیشنی برای خرید فعال نیست.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_main")]])
            )
            return MAIN_MENU

        keyboard = []
        for loc_code, loc_data in server_data['locations'].items():
            if loc_data['active']:
                # Use location-specific price instead of the general package price
                location_price = loc_data.get('price', server_data['prices']['dns_package'])
                keyboard.append([
                    InlineKeyboardButton(
                        f"{loc_data['flag']} {loc_data['name']} - {location_price:,} تومان", 
                        callback_data=f"direct_purchase_{loc_code}"
                    )
                ])

        keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_main")])
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "🌍 لطفا لوکیشن مورد نظر خود را انتخاب کنید:\n"
            "(هر سرویس شامل یک آدرس IPv4 و یک آدرس IPv6 می‌باشد)",
            reply_markup=reply_markup
        )
        return SELECT_LOCATION

    elif query.data == "my_services":
        user_info = ensure_user_exists(user_id, query.from_user.username)
        if not user_info.get('services', []):
            await query.edit_message_text(
                "شما هنوز سرویسی خریداری نکرده‌اید.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_main")]])
            )
        else:
            message = "📋 *سرویس‌های شما:*\n\n"
            for index, service in enumerate(user_info.get('services', []), 1):
                loc_data = server_data['locations'][service['location']]
                message += f"*سرویس {index}:*\n"
                # عدم نمایش نوع سرویس و فقط نمایش لوکیشن و آدرس و تاریخ
                message += f"🔹 لوکیشن: {loc_data['flag']} {loc_data['name']}\n"
                message += f"🔹 آدرس: `{service['address']}`\n"
                purchase_date = datetime.fromisoformat(service['purchase_date'])
                persian_purchase_date = gregorian_to_persian(service['purchase_date'])

                # Check if expiration_date exists (for backward compatibility)
                if 'expiration_date' in service:
                    expiration_date = datetime.fromisoformat(service['expiration_date'])
                    persian_expiration_date = gregorian_to_persian(service['expiration_date'])
                    message += f"🔹 تاریخ خرید: {persian_purchase_date}\n"
                    message += f"🔹 تاریخ انقضا: {persian_expiration_date}\n\n"
                else:
                    message += f"🔹 تاریخ خرید: {persian_purchase_date}\n\n"

            await query.edit_message_text(
                message,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_main")]]),
                parse_mode='Markdown'
            )
        return MAIN_MENU

    elif query.data == "admin_panel" and is_admin(user_id):
        keyboard = [
            [InlineKeyboardButton("👥 مدیریت کاربران", callback_data="manage_users")],
            [InlineKeyboardButton("🌐 مدیریت سرورها", callback_data="manage_servers")],
            [InlineKeyboardButton("⚙️ تنظیمات ربات", callback_data="bot_settings")],
            [InlineKeyboardButton("📊 آمار", callback_data="stats")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "👑 پنل مدیریت",
            reply_markup=reply_markup
        )
        return ADMIN_PANEL

    elif query.data == "back_to_main":
        keyboard = [
            [InlineKeyboardButton("🌐 خرید DNS", callback_data="buy_dns")],
            [InlineKeyboardButton("💰 کیف پول", callback_data="wallet"), 
             InlineKeyboardButton("📋 سرویس های من", callback_data="my_services")],
            [InlineKeyboardButton("👤 حساب کاربری", callback_data="user_profile"),
             InlineKeyboardButton("➕ افزایش موجودی", callback_data="add_balance")] # Add "Add Balance" button
        ]

        if is_admin(user_id):
            keyboard.append([InlineKeyboardButton("👑 پنل مدیریت", callback_data="admin_panel")])

        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "منوی اصلی:",
            reply_markup=reply_markup
        )
        return MAIN_MENU

    return MAIN_MENU

# States for payment receipt
PAYMENT_RECEIPT, PAYMENT_AMOUNT = range(10, 12)

async def wallet_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "add_balance":
        # Payment plans
        keyboard = [
            [
                InlineKeyboardButton("50,000 تومان", callback_data="payment_50000"),
                InlineKeyboardButton("100,000 تومان", callback_data="payment_100000"),
                InlineKeyboardButton("200,000 تومان", callback_data="payment_200000")
            ],
            [
                InlineKeyboardButton("300,000 تومان", callback_data="payment_300000"),
                InlineKeyboardButton("500,000 تومان", callback_data="payment_500000"),
                InlineKeyboardButton("1,000,000 تومان", callback_data="payment_1000000")
            ],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_wallet")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "💰 لطفا مبلغ مورد نظر برای افزایش موجودی را انتخاب کنید:",
            reply_markup=reply_markup
        )
        return WALLET

    elif query.data.startswith("payment_"):
        amount = int(query.data.split("_")[1])
        formatted_amount = f"{amount:,}"
        context.user_data["payment_amount"] = amount

        await query.edit_message_text(
            f"💳 برای افزایش موجودی به مبلغ {formatted_amount} تومان، لطفا به کارت زیر واریز کنید:\n\n"
            f"```\n6219 8619 4308 4037\n```\n"
            f"به نام: امیرحسین سیاهبالایی\n\n"
            f"پس از واریز، تصویر رسید پرداخت را ارسال کنید یا شماره پیگیری را بنویسید:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_wallet")]]),
            parse_mode='Markdown'
        )
        return PAYMENT_RECEIPT

    elif query.data == "back_to_wallet":
        user_info = ensure_user_exists(user_id, query.from_user.username)
        keyboard = [
            [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            f"💰 موجودی کیف پول شما: {user_info['balance']:,} تومان",
            reply_markup=reply_markup
        )
        return WALLET

    return MAIN_MENU

async def payment_receipt_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    user_id = str(user.id)
    payment_amount = context.user_data.get("payment_amount", 0)

    # Check if user has sent a photo (receipt) or text (tracking number)
    if update.message.photo:
        # Get the photo file_id
        photo_file_id = update.message.photo[-1].file_id
        context.user_data["payment_receipt_photo"] = photo_file_id
        receipt_type = "تصویر رسید"
    else:
        # Assume it's a tracking number
        tracking_number = update.message.text
        context.user_data["payment_receipt_text"] = tracking_number
        receipt_type = f"شماره پیگیری: {tracking_number}"

    # Store pending payment request
    if "pending_payments" not in user_data:
        user_data["pending_payments"] = {}

    payment_id = f"pay_{datetime.now().strftime('%Y%m%d%H%M%S')}_{user_id}"
    user_data["pending_payments"][payment_id] = {
        "user_id": user_id,
        "username": user.username,
        "amount": payment_amount,
        "timestamp": datetime.now().isoformat(),
        "status": "pending",
        "receipt_type": "photo" if update.message.photo else "text",
        "receipt_data": photo_file_id if update.message.photo else tracking_number
    }
    save_data(USER_DATA_FILE, user_data)

    # Notify user
    await update.message.reply_text(
        f"✅ درخواست افزایش موجودی شما به مبلغ {payment_amount:,} تومان با موفقیت ثبت شد.\n"
        f"نوع رسید: {receipt_type}\n\n"
        f"درخواست شما در صف بررسی توسط مدیران قرار گرفت. "
        f"پس از تایید، موجودی کیف پول شما به‌روز خواهد شد."
    )

    # Forward receipt to all admins
    for admin_id in bot_config.get("admins", []):
        try:
            # Send notification to admin
            admin_message = (
                f"🔔 *درخواست افزایش موجودی جدید*\n\n"
                f"👤 کاربر: {user.full_name} (@{user.username or 'بدون نام کاربری'})\n"
                f"🆔 شناسه کاربر: `{user_id}`\n"
                f"💰 مبلغ: {payment_amount:,} تومان\n"
                f"🕒 زمان: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"🧾 نوع رسید: {receipt_type}\n"
            )

            # Create approve/reject buttons
            keyboard = [
                [
                    InlineKeyboardButton("✅ تایید", callback_data=f"approve_payment_{payment_id}"),
                    InlineKeyboardButton("❌ رد", callback_data=f"reject_payment_{payment_id}")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            # Send text notification first
            notification = await context.bot.send_message(
                chat_id=admin_id,
                text=admin_message,
                parse_mode='Markdown',
                reply_markup=reply_markup
            )

            # Then forward the receipt photo or text
            if update.message.photo:
                await context.bot.send_photo(
                    chat_id=admin_id,
                    photo=photo_file_id,
                    caption=f"🧾 رسید پرداخت کاربر {user.full_name} - {payment_amount:,} تومان",
                    reply_to_message_id=notification.message_id
                )

        except Exception as e:
            logger.error(f"Error notifying admin {admin_id}: {e}")

    return MAIN_MENU

async def location_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if query.data.startswith("direct_purchase_"):
        location = query.data.split("_")[2]
        context.user_data["selected_location"] = location
        context.user_data["selected_ip_type"] = "dns_package" # For price reference

        await direct_purchase(update, context)
        return CONFIRM_PURCHASE

    elif query.data.startswith("location_"):
        # This part should not be reached with the new changes
        location = query.data.split("_")[1]
        context.user_data["selected_location"] = location

        keyboard = [
            [InlineKeyboardButton("IPv4", callback_data="ip_type_ipv4")],
            [InlineKeyboardButton("IPv6", callback_data="ip_type_ipv6")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_locations")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        loc_data = server_data['locations'][location]
        await query.edit_message_text(
            f"شما لوکیشن {loc_data['flag']} {loc_data['name']} را انتخاب کردید.\n"
            "لطفا نوع IP مورد نظر خود را انتخاب کنید:",
            reply_markup=reply_markup
        )
        return SELECT_IP_TYPE

    elif query.data == "back_to_locations":
        keyboard = []
        for loc_code, loc_data in server_data['locations'].items():
            if loc_data['active']:
                # Use location-specific price instead of the general package price
                location_price = loc_data.get('price', server_data['prices']['dns_package'])
                keyboard.append([
                    InlineKeyboardButton(
                        f"{loc_data['flag']} {loc_data['name']} - {location_price:,} تومان", 
                        callback_data=f"direct_purchase_{loc_code}"
                    )
                ])

        keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_main")])
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "🌍 لطفا لوکیشن مورد نظر خود را انتخاب کنید:\n"
            "(هر سرویس شامل یک آدرس IPv4 و یک آدرس IPv6 می‌باشد)",
            reply_markup=reply_markup
        )
        return SELECT_LOCATION

    return MAIN_MENU

async def ip_type_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user_info = ensure_user_exists(user_id, query.from_user.username)

    if query.data.startswith("ip_type_"):
        ip_type = query.data.split("_")[2]
        location = context.user_data.get("selected_location")
        price = server_data['prices'][ip_type]

        context.user_data["selected_ip_type"] = ip_type

        # Generate IP addresses for both IPv4 and IPv6
        # برای IPv4
        cidr = server_data['locations'][location]['ipv4_cidr'][0]
        ipv4_address = next(generate_ipv4(cidr))

        # برای IPv6
        prefix = server_data['locations'][location]['ipv6_prefix'][0]
        ipv6_address = next(generate_ipv6(prefix))

        # ذخیره هر دو آدرس
        context.user_data["selected_ipv4"] = ipv4_address
        context.user_data["selected_ipv6"] = ipv6_address

        # ذخیره آدرس انتخابی کاربر برای سازگاری با کد قبلی
        if ip_type == "ipv4":
            context.user_data["selected_ip"] = ipv4_address
        else:
            context.user_data["selected_ip"] = ipv6_address

        keyboard = [
            [InlineKeyboardButton("✅ تایید و خرید", callback_data="confirm_purchase")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_ip_type")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        loc_data = server_data['locations'][location]
        await query.edit_message_text(
            f"جزئیات خرید:\n\n"
            f"🌍 لوکیشن: {loc_data['flag']} {loc_data['name']}\n"
            f"🔢 نوع IP: {ip_type.upper()}\n"
            f"🔗 آدرس IPv4: `{ipv4_address}`\n"
            f"🔗 آدرس IPv6: `{ipv6_address}`\n"
            f"💰 قیمت: {price} تومان\n\n"
            f"موجودی فعلی شما: {user_info['balance']} تومان",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return CONFIRM_PURCHASE

    elif query.data == "back_to_ip_type":
        location = context.user_data.get("selected_location")
        keyboard = [
            [InlineKeyboardButton("IPv4", callback_data="ip_type_ipv4")],
            [InlineKeyboardButton("IPv6", callback_data="ip_type_ipv6")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_locations")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        loc_data = server_data['locations'][location]
        await query.edit_message_text(
            f"شما لوکیشن {loc_data['flag']} {loc_data['name']} را انتخاب کردید.\n"
            "لطفا نوع IP مورد نظر خود را انتخاب کنید:",
            reply_markup=reply_markup
        )
        return SELECT_IP_TYPE

    return MAIN_MENU

async def confirm_purchase_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user_info = ensure_user_exists(user_id, query.from_user.username)

    if query.data == "confirm_purchase":
        ip_type = context.user_data.get("selected_ip_type")
        location = context.user_data.get("selected_location")
        ipv4_address = context.user_data.get("selected_ipv4")
        ipv6_address = context.user_data.get("selected_ipv6")
        
        # حالا از قیمت پکیج کامل استفاده می‌کنیم
        price = server_data['prices']['dns_package']

        if user_info['balance'] < price:
            await query.edit_message_text(
                "❌ موجودی کیف پول شما کافی نیست.\n"
                "لطفا ابتدا موجودی خود را افزایش دهید.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_main")]])
            )
            return MAIN_MENU

        # Process purchase
        user_info['balance'] -= price

        # اضافه کردن هر دو سرویس IPv4 و IPv6 به حساب کاربر
        if 'services' not in user_info:
            user_info['services'] = []

        # Calculate expiration date (30 days from now)
        purchase_date = datetime.now()
        expiration_date = purchase_date + timedelta(days=30)
        persian_expiration_date = gregorian_to_persian(expiration_date.isoformat())

        # ایجاد یک سرویس جدید به جای دو سرویس IPv4 و IPv6 جداگانه
        service = {
            "location": location,
            "address": f"{ipv4_address}\n{ipv6_address}",
            "purchase_date": purchase_date.isoformat(),
            "expiration_date": expiration_date.isoformat()
        }

        # اضافه کردن سرویس به کاربر
        user_info['services'].append(service)
        save_data(USER_DATA_FILE, user_data)

        loc_data = server_data['locations'][location]

        await query.edit_message_text(
            f"✅ *خرید شما با موفقیت انجام شد!*\n\n"
            f"🌍 لوکیشن: {loc_data['flag']} {loc_data['name']}\n"
            f"⏱ مدت اعتبار: 30 روز (تا {persian_expiration_date})\n\n"
            f"🔹 *آدرس IPv4:*\n`{ipv4_address}`\n\n"
            f"🔹 *آدرس IPv6:*\n`{ipv6_address}`\n\n"
            f"💰 قیمت: {price} تومان\n"
            f"💰 موجودی جدید: {user_info['balance']} تومان",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data="back_to_main")]]),
            parse_mode='Markdown'
        )
        return MAIN_MENU

    elif query.data == "back_to_ip_type":
        location = context.user_data.get("selected_location")
        keyboard = [
            [InlineKeyboardButton("IPv4", callback_data="ip_type_ipv4")],
            [InlineKeyboardButton("IPv6", callback_data="ip_type_ipv6")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_locations")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        loc_data = server_data['locations'][location]
        await query.edit_message_text(
            f"شما لوکیشن {loc_data['flag']} {loc_data['name']} را انتخاب کردید.\n"
            "لطفا نوع IP مورد نظر خود را انتخاب کنید:",
            reply_markup=reply_markup
        )
        return SELECT_IP_TYPE

    return MAIN_MENU

async def direct_purchase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user_info = ensure_user_exists(user_id, query.from_user.username)
    location = context.user_data.get("selected_location")
    loc_data = server_data['locations'][location]
    price = loc_data.get('price', server_data['prices']['dns_package']) # Price for the package

    # Generate addresses
    cidrs = loc_data['ipv4_cidr']  # Use all available CIDR ranges
    ipv4_address = generate_ipv4(cidrs)  # Directly use the return value

    # Get a random IPv6 prefix if multiple are available
    import random
    prefixes = loc_data['ipv6_prefix']
    prefix = random.choice(prefixes)
    ipv6_address_0, ipv6_address_1 = generate_ipv6_pair(prefix)

    # Store in context
    context.user_data["selected_ipv4"] = ipv4_address
    context.user_data["selected_ipv6_0"] = ipv6_address_0
    context.user_data["selected_ipv6_1"] = ipv6_address_1

    # Show confirmation message with details
    keyboard = [
        [InlineKeyboardButton("✅ تایید و خرید", callback_data="confirm_direct_purchase")],
        [InlineKeyboardButton("🔙 انصراف", callback_data="back_to_locations")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    expiration_date = (datetime.now() + timedelta(days=30))
    persian_expiration_date = gregorian_to_persian(expiration_date.isoformat())

    await query.edit_message_text(
        f"📋 *جزئیات سرویس*\n\n"
        f"🌍 لوکیشن: {loc_data['flag']} {loc_data['name']}\n"
        f"💰 قیمت: {price} تومان\n"
        f"⏱ مدت اعتبار: 30 روز (تا {persian_expiration_date})\n\n"
        f"💰 موجودی فعلی شما: {user_info['balance']} تومان\n\n"
        f"آیا مایل به خرید این سرویس هستید؟\n"
        f"(آدرس‌ها پس از تایید خرید نمایش داده می‌شوند)",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    return CONFIRM_PURCHASE

async def confirm_direct_purchase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user_info = ensure_user_exists(user_id, query.from_user.username)
    location = context.user_data.get("selected_location")
    loc_data = server_data['locations'][location]
    ipv4_address = context.user_data.get("selected_ipv4")
    ipv6_address_0 = context.user_data.get("selected_ipv6_0")
    ipv6_address_1 = context.user_data.get("selected_ipv6_1")
    price = loc_data.get('price', server_data['prices']['dns_package']) # Price for the package

    if user_info['balance'] < price:
        await query.edit_message_text(
            "❌ موجودی کیف پول شما کافی نیست.\n"
            "لطفا ابتدا موجودی خود را افزایش دهید.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_main")]])
        )
        return MAIN_MENU

    # Process purchase
    user_info['balance'] -= price

    # Calculate expiration date (30 days from now)
    purchase_date = datetime.now()
    expiration_date = purchase_date + timedelta(days=30)
    persian_expiration_date = gregorian_to_persian(expiration_date.isoformat())

    # اضافه کردن سرویس‌ها به حساب کاربر
    if 'services' not in user_info:
        user_info['services'] = []

    # ایجاد یک سرویس ترکیبی برای تمامی آدرس‌ها
    service = {
        "location": location,
        "address": f"{ipv4_address}\n{ipv6_address_0}\n{ipv6_address_1}",
        "purchase_date": purchase_date.isoformat(),
        "expiration_date": expiration_date.isoformat()
    }

    # اضافه کردن سرویس به کاربر
    user_info['services'].append(service)
    save_data(USER_DATA_FILE, user_data)

    loc_data = server_data['locations'][location]
    expiration_date_str = persian_expiration_date

    await query.edit_message_text(
        f"✅ *خرید شما با موفقیت انجام شد!*\n\n"
        f"🌍 لوکیشن: {loc_data['flag']} {loc_data['name']}\n"
        f"⏱ مدت اعتبار: 30 روز (تا {expiration_date_str})\n\n"
        f"🔹 *آدرس IPv4:*\n`{ipv4_address}`\n\n"
        f"🔹 *آدرس‌های IPv6:*\n`{ipv6_address_0}`\n`{ipv6_address_1}`\n\n"
        f"💰 قیمت: {price} تومان\n"
        f"💰 موجودی جدید: {user_info['balance']} تومان",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data="back_to_main")]]),
        parse_mode='Markdown'
    )
    return MAIN_MENU

# Admin panel handlers
# تعریف حالت‌های جدید برای مدیریت کاربران
ADMIN_USER_ID_INPUT, ADMIN_AMOUNT_INPUT, ADMIN_GIFT_AMOUNT_INPUT = range(7, 10)

# Add state for broadcast message
ADMIN_BROADCAST_MESSAGE = 12

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if not is_admin(user_id):
        await query.edit_message_text(
            "❌ شما دسترسی به پنل مدیریت را ندارید.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_main")]])
        )
        return MAIN_MENU

    if query.data == "manage_users":
        keyboard = [
            [
                InlineKeyboardButton("➕ افزایش موجودی", callback_data="add_user_balance"),
                InlineKeyboardButton("👤 اطلاعات کاربر", callback_data="view_user_info")
            ],
            [
                InlineKeyboardButton("🎁 اعطای هدیه", callback_data="gift_all_users"),
                InlineKeyboardButton("📣 پیام همگانی", callback_data="broadcast_message")
            ],
            [
                InlineKeyboardButton("👛 درخواست‌های پرداخت", callback_data="payment_requests"),
                InlineKeyboardButton("🗑️ پاکسازی کاربران", callback_data="clean_inactive_users")
            ],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_admin")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "👥 مدیریت کاربران",
            reply_markup=reply_markup
        )
        return ADMIN_PANEL

    elif query.data == "add_user_balance":
        await query.edit_message_text(
            "لطفا شناسه (ID) کاربر مورد نظر را وارد کنید:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_admin")]])
        )
        return ADMIN_USER_ID_INPUT

    elif query.data == "gift_all_users":
        await query.edit_message_text(
            "لطفا مبلغ هدیه (به تومان) برای همه کاربران را وارد کنید:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_admin")]])
        )
        return ADMIN_GIFT_AMOUNT_INPUT

    elif query.data == "view_user_info":
        await query.edit_message_text(
            "لطفا شناسه (ID) کاربر مورد نظر را وارد کنید:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_admin")]])
        )
        return ADMIN_USER_ID_INPUT

    elif query.data == "manage_servers":
        keyboard = []

        for loc_code, loc_data in server_data['locations'].items():
            status = "✅" if loc_data['active'] else "❌"
            keyboard.append([
                InlineKeyboardButton(
                    f"{status} {loc_data['flag']} {loc_data['name']}", 
                    callback_data=f"toggle_location_{loc_code}"
                )
            ])

        keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_admin")])
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "🌐 مدیریت سرورها\n"
            "برای فعال/غیرفعال کردن یک لوکیشن، روی آن کلیک کنید:",
            reply_markup=reply_markup
        )
        return ADMIN_PANEL

    elif query.data == "bot_settings":
        status = "فعال ✅" if bot_config.get("is_active", True) else "غیرفعال ❌"
        keyboard = [
            [InlineKeyboardButton(f"وضعیت ربات: {status}", callback_data="toggle_bot_status")],
            [
                InlineKeyboardButton("➕ افزودن ادمین", callback_data="add_admin"),
                InlineKeyboardButton("➖ حذف ادمین", callback_data="remove_admin"),
                InlineKeyboardButton("🔄 بروزرسانی", callback_data="update_prices")
            ],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_admin")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "⚙️ تنظیمات ربات",
            reply_markup=reply_markup
        )
        return ADMIN_PANEL

    elif query.data.startswith("toggle_location_"):
        location = query.data.split("_")[2]
        server_data['locations'][location]['active'] = not server_data['locations'][location]['active']
        save_data(SERVER_DATA_FILE, server_data)

        # Refresh the server management menu
        keyboard = []
        for loc_code, loc_data in server_data['locations'].items():
            status = "✅" if loc_data['active'] else "❌"
            keyboard.append([
                InlineKeyboardButton(
                    f"{status} {loc_data['flag']} {loc_data['name']}", 
                    callback_data=f"toggle_location_{loc_code}"
                )
            ])

        keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_admin")])
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "🌐 مدیریت سرورها\n"
            "برای فعال/غیرفعال کردن یک لوکیشن، روی آن کلیک کنید:",
            reply_markup=reply_markup
        )
        return ADMIN_PANEL

    elif query.data == "toggle_bot_status":
        bot_config["is_active"] = not bot_config.get("is_active", True)
        save_data(BOT_CONFIG_FILE, bot_config)

        # Refresh the bot settings menu
        status = "فعال ✅" if bot_config.get("is_active", True) else "غیرفعال ❌"
        keyboard = [
            [InlineKeyboardButton(f"وضعیت ربات: {status}", callback_data="toggle_bot_status")],
            [InlineKeyboardButton("➕ افزودن ادمین", callback_data="add_admin")],
            [InlineKeyboardButton("➖ حذف ادمین", callback_data="remove_admin")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="back_toadmin")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "⚙️ تنظیمات ربات",
            reply_markup=reply_markup
        )
        return ADMIN_PANEL

    elif query.data == "stats":
        total_users = len(user_data)
        total_services = sum(len(u.get('services', [])) for u in user_data.values())
        total_balance = sum(u.get('balance', 0) for u in user_data.values())

        await query.edit_message_text(
            f"📊 آمار ربات:\n\n"
            f"👥 تعداد کاربران: {total_users}\n"
            f"🌐 تعداد سرویس‌های فروخته شده: {total_services}\n"
            f"💰 مجموع موجودی کاربران: {total_balance} تومان",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_admin")]])
        )
        return ADMIN_PANEL

    elif query.data.startswith("toggle_location_"):
        location = query.data.split("_")[2]
        server_data['locations'][location]['active'] = not server_data['locations'][location]['active']
        save_data(SERVER_DATA_FILE, server_data)

        # Refresh the server management menu
        keyboard = []
        for loc_code, loc_data in server_data['locations'].items():
            status = "✅" if loc_data['active'] else "❌"
            keyboard.append([
                InlineKeyboardButton(
                    f"{status} {loc_data['flag']} {loc_data['name']}", 
                    callback_data=f"toggle_location_{loc_code}"
                )
            ])

        keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_admin")])
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "🌐 مدیریت سرورها\n"
            "برای فعال/غیرفعال کردن یک لوکیشن، روی آن کلیک کنید:",
            reply_markup=reply_markup
        )
        return ADMIN_PANEL

    elif query.data == "toggle_bot_status":
        bot_config["is_active"] = not bot_config.get("is_active", True)
        save_data(BOT_CONFIG_FILE, bot_config)

        # Refresh the bot settings menu
        status = "فعال ✅" if bot_config.get("is_active", True) else "غیرفعال ❌"
        keyboard = [
            [InlineKeyboardButton(f"وضعیت ربات: {status}", callback_data="toggle_bot_status")],
            [InlineKeyboardButton("➕ افزودن ادمین", callback_data="add_admin")],
            [InlineKeyboardButton("➖ حذف ادمین", callback_data="remove_admin")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_admin")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "⚙️ تنظیمات ربات",
            reply_markup=reply_markup
        )
        return ADMIN_PANEL

    elif query.data == "broadcast_message":
        await query.edit_message_text(
            "📣 لطفا پیام خود را برای ارسال به تمامی کاربران وارد کنید:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 انصراف", callback_data="back_to_admin")]])
        )
        return ADMIN_BROADCAST_MESSAGE

    elif query.data == "payment_requests":
        # Get pending payment requests
        pending_payments = user_data.get("pending_payments", {})

        if not pending_payments:
            await query.edit_message_text(
                "📭 در حال حاضر هیچ درخواست پرداختی در انتظار تایید وجود ندارد.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_admin")]])
            )
            return ADMIN_PANEL

        # Count pending payments
        pending_count = sum(1 for p in pending_payments.values() if p.get("status") == "pending")

        await query.edit_message_text(
            f"👛 *درخواست‌های پرداخت*\n\n"
            f"تعداد درخواست‌های در انتظار: {pending_count}\n\n"
            f"برای مشاهده و مدیریت درخواست‌ها، از منوی زیر استفاده کنید:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("👁️ مشاهده درخواست‌ها", callback_data="view_pending_payments")],
                [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_admin")]
            ]),
            parse_mode='Markdown'
        )
        return ADMIN_PANEL

    elif query.data == "view_pending_payments":
        # Get pending payment requests
        pending_payments = user_data.get("pending_payments", {})

        # Filter only pending payments
        pending = {k: v for k, v in pending_payments.items() if v.get("status") == "pending"}

        if not pending:
            await query.edit_message_text(
                "📭 در حال حاضر هیچ درخواست پرداختی در انتظار تایید وجود ندارد.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="payment_requests")]])
            )
            return ADMIN_PANEL

        # Show the most recent pending payment
        payment_id, payment_info = next(iter(pending.items()))

        user_id = payment_info.get("user_id")
        username = payment_info.get("username", "بدون نام کاربری")
        amount = payment_info.get("amount", 0)
        timestamp = datetime.fromisoformat(payment_info.get("timestamp")).strftime('%Y-%m-%d %H:%M:%S')
        receipt_type = "تصویر" if payment_info.get("receipt_type") == "photo" else "شماره پیگیری"

        # Create keyboard with approve/reject buttons
        keyboard = [
            [
                InlineKeyboardButton("✅ تایید", callback_data=f"approve_payment_{payment_id}"),
                InlineKeyboardButton("❌ رد", callback_data=f"reject_payment_{payment_id}")
            ],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="payment_requests")]
        ]

        # If there are more pending payments, add next button
        if len(pending) > 1:
            keyboard.insert(1, [InlineKeyboardButton("⏩ بعدی", callback_data="next_pending_payment")])

        reply_markup = InlineKeyboardMarkup(keyboard)

        message = (
            f"🧾 *درخواست پرداخت #{payment_id[-6:]}*\n\n"
            f"👤 کاربر: @{username}\n"
            f"🆔 شناسه: `{user_id}`\n"
            f"💰 مبلغ: {amount:,} تومان\n"
            f"🕒 زمان: {timestamp}\n"
            f"📝 نوع رسید: {receipt_type}\n\n"
        )

        if payment_info.get("receipt_type") == "text":
            message += f"📄 متن رسید: `{payment_info.get('receipt_data')}`"

        await query.edit_message_text(
            message,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

        # If it's a photo receipt, send the photo
        if payment_info.get("receipt_type") == "photo":
            try:
                await context.bot.send_photo(
                    chat_id=query.message.chat_id,
                    photo=payment_info.get("receipt_data"),
                    caption=f"🧾 تصویر رسید پرداخت #{payment_id[-6:]}"
                )
            except Exception as e:
                logger.error(f"Error sending receipt photo: {e}")
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text="❌ خطا در نمایش تصویر رسید"
                )

        return ADMIN_PANEL

    elif query.data.startswith("approve_payment_") or query.data.startswith("reject_payment_"):
        is_approved = query.data.startswith("approve_payment_")
        payment_id = query.data.split("_")[2]

        # Get payment info
        pending_payments = user_data.get("pending_payments", {})
        if payment_id not in pending_payments:
            await query.edit_message_text(
                "❌ درخواست پرداخت یافت نشد یا قبلاً پردازش شده است.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="payment_requests")]])
            )
            return ADMIN_PANEL

        payment_info = pending_payments[payment_id]
        user_id = payment_info.get("user_id")
        amount = payment_info.get("amount", 0)

        # Update payment status
        payment_info["status"] = "approved" if is_approved else "rejected"
        payment_info["processed_by"] = str(query.from_user.id)
        payment_info["processed_at"] = datetime.now().isoformat()

        # If approved, add balance to user
        if is_approved and user_id in user_data:
            user_data[user_id]["balance"] += amount

        save_data(USER_DATA_FILE, user_data)

        # Notify user
        try:
            if is_approved:
                await context.bot.send_message(
                    chat_id=int(user_id),
                    text=f"✅ *افزایش موجودی تایید شد*\n\n"
                         f"درخواست افزایش موجودی شما به مبلغ {amount:,} تومان تایید و به کیف پول شما اضافه شد.\n"
                         f"موجودی فعلی: {user_data[user_id]['balance']:,} تومان",
                    parse_mode='Markdown'
                )
            else:
                await context.bot.send_message(
                    chat_id=int(user_id),
                    text=f"❌ *افزایش موجودی تایید نشد*\n\n"
                         f"متأسفانه درخواست افزایش موجودی شما به مبلغ {amount:,} تومان تایید نشد.\n"
                         f"لطفاً با پشتیبانی تماس بگیرید یا مجدداً تلاش کنید.",
                    parse_mode='Markdown'
                )
        except Exception as e:
            logger.error(f"Error notifying user {user_id}: {e}")

        # Return to payment requests menu
        result = "تایید" if is_approved else "رد"
        await query.edit_message_text(
            f"✅ درخواست پرداخت با موفقیت {result} شد.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="payment_requests")]])
        )
        return ADMIN_PANEL

    elif query.data == "clean_inactive_users":
        # Count users with no services
        inactive_count = sum(1 for u_id, u_data in user_data.items() 
                          if u_id not in bot_config.get("admins", []) and not u_data.get("services"))

        keyboard = [
            [
                InlineKeyboardButton("✅ تایید پاکسازی", callback_data="confirm_clean_users"),
                InlineKeyboardButton("❌ انصراف", callback_data="back_to_admin")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            f"🗑️ *پاکسازی کاربران غیرفعال*\n\n"
            f"تعداد کاربران بدون سرویس: {inactive_count}\n\n"
            f"آیا از پاکسازی کاربران بدون سرویس اطمینان دارید؟",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return ADMIN_PANEL

    elif query.data == "confirm_clean_users":
        # Remove users with no services
        before_count = len(user_data)
        admin_ids = bot_config.get("admins", [])

        # Create a new user_data dictionary without inactive users
        new_user_data = {u_id: u_data for u_id, u_data in user_data.items() 
                        if u_id in admin_ids or u_data.get("services")}

        removed_count = before_count - len(new_user_data)

        # Update user_data
        user_data.clear()
        user_data.update(new_user_data)
        save_data(USER_DATA_FILE, user_data)

        await query.edit_message_text(
            f"✅ پاکسازی با موفقیت انجام شد.\n\n"
            f"تعداد کاربران حذف شده: {removed_count}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_admin")]])
        )
        return ADMIN_PANEL

    elif query.data == "back_to_admin":
        keyboard = [
            [
                InlineKeyboardButton("👥 مدیریت کاربران", callback_data="manage_users"),
                InlineKeyboardButton("🌐 مدیریت سرورها", callback_data="manage_servers")
            ],
            [
                InlineKeyboardButton("⚙️ تنظیمات ربات", callback_data="bot_settings"),
                InlineKeyboardButton("📊 آمار", callback_data="stats")
            ],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "👑 پنل مدیریت",
            reply_markup=reply_markup
        )
        return ADMIN_PANEL

    return ADMIN_PANEL

# تابع‌های جدید برای مدیریت کاربران
async def admin_user_id_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_input = update.message.text
    context.user_data['admin_target_user_id'] = user_input

    # بررسی اینکه آیا این از طرف add_user_balance آمده یا view_user_info
    if 'admin_action' not in context.user_data:
        # اگر از منوی افزایش موجودی آمده باشد
        await update.message.reply_text(
            f"لطفا مبلغی که می‌خواهید به موجودی کاربر با شناسه {user_input} اضافه کنید را وارد کنید:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_admin")]])
        )
        context.user_data['admin_action'] = 'add_balance'
        return ADMIN_AMOUNT_INPUT
    elif context.user_data.get('admin_action') == 'view_info':
        # اگر از منوی مشاهده اطلاعات آمده باشد
        if user_input in user_data:
            user_info = user_data[user_input]
            join_date = datetime.fromisoformat(user_info['joined_at']).strftime('%Y-%m-%d')
            persian_date = gregorian_to_persian(user_info['joined_at'])
            services_count = len(user_info.get('services', []))

            await update.message.reply_text(
                f"👤 *اطلاعات کاربر*\n\n"
                f"🆔 شناسه کاربری: `{user_input}`\n"
                f"👤 نام کاربری: @{user_info['username'] or 'بدون نام کاربری'}\n"
                f"💰 موجودی: {user_info['balance']} تومان\n"
                f"📊 تعداد سرویس‌ها: {services_count}\n"
                f"📅 تاریخ عضویت: {persian_date}",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_admin")]]),
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                "❌ کاربری با این شناسه یافت نشد.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_admin")]])
            )
        return ADMIN_PANEL

async def admin_amount_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        amount = int(update.message.text)
        user_id = context.user_data.get('admin_target_user_id')

        if user_id in user_data:
            user_data[user_id]['balance'] += amount
            save_data(USER_DATA_FILE, user_data)

            # Notify admin
            await update.message.reply_text(
                f"✅ مبلغ {amount:,} تومان با موفقیت به موجودی کاربر با شناسه {user_id} اضافه شد.\n"
                f"موجودی جدید: {user_data[user_id]['balance']:,} تومان",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_admin")]])
            )

            # Try to notify user
            try:
                admin_name = update.effective_user.full_name or "مدیر سیستم"
                await context.bot.send_message(
                    chat_id=int(user_id),
                    text=f"💰 *افزایش موجودی*\n\n"
                         f"مبلغ {amount:,} تومان توسط {admin_name} به موجودی کیف پول شما اضافه شد.\n"
                         f"موجودی فعلی: {user_data[user_id]['balance']:,} تومان",
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"Error notifying user {user_id}: {e}")
                # Continue even if notification fails
        else:
            await update.message.reply_text(
                "❌ کاربری با این شناسه یافت نشد.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_admin")]])
            )
    except ValueError:
        await update.message.reply_text(
            "❌ لطفا یک عدد صحیح وارد کنید.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_admin")]])
        )

    return ADMIN_PANEL

async def admin_gift_amount_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        amount = int(update.message.text)
        count = 0

        for user_id in user_data:
            user_data[user_id]['balance'] += amount
            count += 1

        save_data(USER_DATA_FILE, user_data)

        await update.message.reply_text(
            f"✅ مبلغ {amount:,} تومان با موفقیت به موجودی {count} کاربر اضافه شد.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_admin")]])
        )
    except ValueError:
        await update.message.reply_text(
            "❌ لطفا یک عدد صحیح وارد کنید.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_admin")]])
        )

    return ADMIN_PANEL

async def admin_broadcast_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message_text = update.message.text
    sender = update.effective_user
    success_count = 0
    failed_count = 0

    # Show processing message
    processing_msg = await update.message.reply_text(
        "📣 در حال ارسال پیام به تمامی کاربران...\n"
        "لطفا صبر کنید..."
    )

    # Add sender info and timestamp to the message
    broadcast_text = (
        f"📢 *پیام از طرف مدیریت*\n\n"
        f"{message_text}\n\n"
        f"🕒 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )

    # Send to all users
    for user_id in user_data:
        try:
            await context.bot.send_message(
                chat_id=int(user_id),
                text=broadcast_text,
                parse_mode='Markdown'
            )
            success_count += 1
        except Exception as e:
            logger.error(f"Error sending broadcast to user {user_id}: {e}")
            failed_count += 1

    # Update processing message with results
    await processing_msg.edit_text(
        f"✅ *نتیجه ارسال پیام همگانی*\n\n"
        f"📨 پیام ارسال شده:\n"
        f"`{message_text[:50]}{'...' if len(message_text) > 50 else ''}`\n\n"
        f"✅ ارسال موفق: {success_count}\n"
        f"❌ ارسال ناموفق: {failed_count}\n",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_admin")]]),
        parse_mode='Markdown'
    )

    return ADMIN_PANEL

# Main function
def main() -> None:
    # Create the application and pass it your bot's token
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "7426668282:AAGomYDgN_lXAkpzABbwM7irPs_XT0SW11c")
    application = Application.builder().token(token).build()

    # Create conversation handler with states
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        per_message=False,  # Changed to False to allow mixed handler types
        states={
            MAIN_MENU: [
                CallbackQueryHandler(menu_callback, pattern="^(wallet|buy_dns|my_services|admin_panel|back_to_main|user_profile|add_balance)$"),
            ],
            WALLET: [
                CallbackQueryHandler(wallet_callback, pattern="^(add_balance|back_to_wallet|payment_[0-9]+)$"),
                CallbackQueryHandler(menu_callback, pattern="^back_to_main$"),
            ],
            PAYMENT_RECEIPT: [
                MessageHandler(filters.PHOTO | filters.TEXT & ~filters.COMMAND, payment_receipt_handler),
                CallbackQueryHandler(wallet_callback, pattern="^back_to_wallet$"),
            ],
            SELECT_LOCATION: [
                CallbackQueryHandler(location_callback, pattern="^direct_purchase_|^location_|^back_to_locations$"),
                CallbackQueryHandler(menu_callback, pattern="^back_to_main$"),
            ],
            SELECT_IP_TYPE: [
                CallbackQueryHandler(ip_type_callback, pattern="^ip_type_"),
                CallbackQueryHandler(location_callback, pattern="^back_to_locations$"),
            ],
            CONFIRM_PURCHASE: [
                CallbackQueryHandler(confirm_purchase_callback, pattern="^(confirm_purchase|backto_ip_type)$"),
                CallbackQueryHandler(confirm_direct_purchase, pattern="^confirm_direct_purchase$"),
                CallbackQueryHandler(location_callback, pattern="^back_to_locations$"),
            ],
            ADMIN_PANEL: [
                CallbackQueryHandler(admin_callback, pattern="^(manage_users|manage_servers|bot_settings|stats|toggle_location_|toggle_bot_status|back_to_admin|add_user_balance|gift_all_users|view_user_info|update_prices|broadcast_message|payment_requests|view_pending_payments|approve_payment_|reject_payment_|clean_inactive_users|confirm_clean_users)$"),
                CallbackQueryHandler(menu_callback, pattern="^back_to_main$"),
            ],
            ADMIN_USER_ID_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_user_id_handler),
                CallbackQueryHandler(admin_callback, pattern="^back_to_admin$"),
            ],
            ADMIN_AMOUNT_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_amount_handler),
                CallbackQueryHandler(admin_callback, pattern="^back_to_admin$"),
            ],
            ADMIN_GIFT_AMOUNT_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_gift_amount_handler),
                CallbackQueryHandler(admin_callback, pattern="^back_to_admin$"),
            ],
            ADMIN_BROADCAST_MESSAGE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_broadcast_handler),
                CallbackQueryHandler(admin_callback, pattern="^back_to_admin$"),
            ],
        },
        fallbacks=[CommandHandler("start", start)],
    )

    application.add_handler(conv_handler)

    # Display success message in logs
    print("Bot start sucesfuly✅")
    logger.info("Bot start sucesfuly✅")

    # Run the bot until the user presses Ctrl-C
    application.run_polling()

if __name__ == "__main__":
    main()

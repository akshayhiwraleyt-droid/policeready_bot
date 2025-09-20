import asyncio
import sqlite3
import json
import logging
import re
from datetime import datetime, date, timedelta
from typing import Dict, List, Tuple, Optional
import random

from telegram import (
    Update, 
    InlineKeyboardButton, 
    InlineKeyboardMarkup, 
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove
)
from telegram.ext import (
    Application, 
    CommandHandler, 
    ContextTypes, 
    ConversationHandler, 
    CallbackQueryHandler, 
    MessageHandler,
    filters,
    JobQueue
)
from telegram.constants import ParseMode

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Database setup
def init_database():
    conn = sqlite3.connect('maharashtra_police_bot.db')
    cursor = conn.cursor()
    
    # Create users table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        full_name TEXT,
        gender TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Create user progress table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS user_progress (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        subject TEXT,
        score INTEGER,
        total_questions INTEGER,
        exam_date DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (user_id)
    )
    ''')
    
    # Create reminders table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS reminders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        reminder_text TEXT,
        reminder_time DATETIME,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (user_id)
    )
    ''')
    
    conn.commit()
    conn.close()

# Initialize database
init_database()

# Define states for conversation
SELECTING_SUBJECT, EXAM_IN_PROGRESS, SETTING_REMINDER = range(3)

# Load questions from JSON file (you'll need to create this)
def load_questions():
    try:
        with open('questions.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        # Sample questions if file doesn't exist
        return {
            "मराठी": [
                {
                    "question": "मराठी भाषेतील पहिले कवी कोण?",
                    "options": ["संत ज्ञानेश्वर", "संत एकनाथ", "संत तुकाराम", "संत नामदेव"],
                    "correct_answer": 0
                }
            ],
            "सामान्य ज्ञान": [
                {
                    "question": "महाराष्ट्राची स्थापना कधी झाली?",
                    "options": ["१ मे १९६०", "१५ ऑगस्ट १९४७", "२६ जानेवारी १९५०", "१ नोव्हेंबर १९५६"],
                    "correct_answer": 0
                }
            ],
            "बुद्धिमत्ता चाचणी": [
                {
                    "question": "जर A = 1, B = 2, तर Z = ?",
                    "options": ["24", "25", "26", "27"],
                    "correct_answer": 2
                }
            ],
            "गणित": [
                {
                    "question": "२५ चे वर्गमूळ किती?",
                    "options": ["5", "6", "7", "8"],
                    "correct_answer": 0
                }
            ],
            "इतिहास/भूगोल/संविधान": [
                {
                    "question": "भारताचे राष्ट्रीय चिन्ह कोठून घेण्यात आले आहे?",
                    "options": ["मुघल साम्राज्य", "अशोक स्तंभ", "महाबळेश्वर", "हस्तलिखित संविधान"],
                    "correct_answer": 1
                }
            ],
            "चालू घडामोडी": [
                {
                    "question": "महाराष्ट्राचे सध्याचे मुख्यमंत्री कोण?",
                    "options": ["एकनाथ शिंदे", "देवेंद्र फडणवीस", "उद्धव ठाकरे", "अजित पवार"],
                    "correct_answer": 0
                }
            ]
        }

# Load questions
questions_data = load_questions()

# Load daily thoughts
daily_thoughts = [
    {
        "thought": "जिंकण्याची इच्छा असलेल्या माणसाला कोणीही पराभूत करू शकत नाही.",
        "author": "छत्रपती शिवाजी महाराज"
    },
    {
        "thought": "शिक्षण हे समाजाचे आधारस्तंभ आहेत आणि ते समाजातील प्रत्येक व्यक्तीपर्यंत पोहोचले पाहिजे.",
        "author": "डॉ. बाबासाहेब आंबेडकर"
    },
    {
        "thought": "स्वातंत्र्य हा आपला जन्मसिद्ध हक्क आहे आणि आपण तो मिळवणारच.",
        "author": "लोकमान्य टिळक"
    },
    {
        "thought": "कष्टाचे फळ गोड असते, ते मिळवण्यासाठी कष्ट करणे आवश्यक आहे.",
        "author": "लालबहादूर शास्त्री"
    }
]

# News updates (would typically come from an API)
news_updates = [
    "महाराष्ट्र पोलिस भरती २०२३: ५००० जागांसाठी अधिसूचना जारी",
    "पोलिस भरती परीक्षेच्या तयारीसाठी मार्गदर्शक कार्यशाळा आयोजित",
    "महाराष्ट्र सरकारमध्ये नवीन पोलिस भरती प्रक्रिया सुरू",
    "पोलिस भरतीसाठी ऑनलाइन अर्ज प्रक्रिया सुरू"
]

# Gender detection based on name endings (basic estimation for Marathi names)
def detect_gender(name):
    name = name.lower().strip()
    female_endings = ['ा', 'ी', 'ीत', 'िन', 'िया', 'ना', 'ता', 'ला', 'मा', 'वी']
    male_endings = ['े', 'य', 'क', 'र', 'स', 'त', 'न', 'प', 'ज', 'व']
    
    for ending in female_endings:
        if name.endswith(ending):
            return "स्त्री"
    
    for ending in male_endings:
        if name.endswith(ending):
            return "पुरुष"
    
    return "अन्य"

# Main menu keyboard
def main_menu_keyboard():
    keyboard = [
        ["📝 परीक्षा सुरू करा", "📘 विषय निवडा"],
        ["💡 दैनंदिन विचार", "📰 बातम्या"],
        ["⏰ रिमाइंडर सेट करा", "🕒 वेळ आणि तारीख"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# Subject selection keyboard
def subject_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("📘 मराठी", callback_data="subject_मराठी"),
            InlineKeyboardButton("📙 सामान्य ज्ञान", callback_data="subject_सामान्य ज्ञान")
        ],
        [
            InlineKeyboardButton("📗 बुद्धिमत्ता चाचणी", callback_data="subject_बुद्धिमत्ता चाचणी"),
            InlineKeyboardButton("📕 गणित", callback_data="subject_गणित")
        ],
        [
            InlineKeyboardButton("📚 इतिहास/भूगोल/संविधान", callback_data="subject_इतिहास/भूगोल/संविधान"),
            InlineKeyboardButton("📰 चालू घडामोडी", callback_data="subject_चालू घडामोडी")
        ],
        [
            InlineKeyboardButton("🔙 मुख्य मेनू", callback_data="main_menu")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# District selection keyboard (for future enhancement)
def district_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("जालना", callback_data="district_जालना"),
            InlineKeyboardButton("औरंगाबाद", callback_data="district_औरंगाबाद")
        ],
        [
            InlineKeyboardButton("मुंबई", callback_data="district_मुंबई"),
            InlineKeyboardButton("पुणे", callback_data="district_पुणे")
        ],
        [
            InlineKeyboardButton("🔙 मुख्य मेनू", callback_data="main_menu")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# Start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    context.user_data['user_id'] = user.id
    
    # Check if user exists in database
    conn = sqlite3.connect('maharashtra_police_bot.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user.id,))
    existing_user = cursor.fetchone()
    
    if not existing_user:
        # Ask for user's name
        await update.message.reply_text(
            "महाराष्ट्र पोलिस भरती बॉटमध्ये आपले स्वागत आहे! 👮‍♂️\n\n"
            "कृपया आपले नाव प्रविष्ट करा:",
            reply_markup=ReplyKeyboardRemove()
        )
        return 0
    else:
        await update.message.reply_text(
            f"पुन्हा भेटल्यावर आनंद झाला {existing_user[2]}! 😊\n\n"
            "मुख्य मेनू:",
            reply_markup=main_menu_keyboard()
        )
        return ConversationHandler.END

# Get user's name and detect gender
async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.message.text
    gender = detect_gender(user_name)
    
    # Store user data
    user = update.effective_user
    conn = sqlite3.connect('maharashtra_police_bot.db')
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO users (user_id, username, full_name, gender) VALUES (?, ?, ?, ?)",
        (user.id, user.username, user_name, gender)
    )
    conn.commit()
    conn.close()
    
    # Greet based on gender
    if gender == "स्त्री":
        greeting = f"सुस्वागतम {user_name}! तुमच्या महाराष्ट्र पोलिस भरती तयारीच्या सफरेत आम्ही तुमच्या सोबत आहोत! 👮‍♀️"
    elif gender == "पुरुष":
        greeting = f"सुस्वागतम {user_name}! तुमच्या महाराष्ट्र पोलिस भरती तयारीच्या सफरेत आम्ही तुमच्या सोबत आहोत! 👮‍♂️"
    else:
        greeting = f"सुस्वागतम {user_name}! तुमच्या महाराष्ट्र पोलिस भरती तयारीच्या सफरेत आम्ही तुमच्या सोबत आहोत! 👮"
    
    await update.message.reply_text(
        greeting + "\n\nमुख्य मेनू:",
        reply_markup=main_menu_keyboard()
    )
    return ConversationHandler.END

# Main menu handler
async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "मुख्य मेनू:",
        reply_markup=main_menu_keyboard()
    )

# Start exam
async def start_exam(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Check if user has selected a subject
    if 'current_subject' not in context.user_data:
        await update.message.reply_text(
            "कृपया प्रथम विषय निवडा:",
            reply_markup=subject_keyboard()
        )
        return SELECTING_SUBJECT
    
    # Start the exam
    subject = context.user_data['current_subject']
    context.user_data['current_question'] = 0
    context.user_data['score'] = 0
    context.user_data['correct_streak'] = 0
    
    # Load questions for the subject
    if subject in questions_data:
        context.user_data['questions'] = questions_data[subject]
        total_questions = len(context.user_data['questions'])
        context.user_data['total_questions'] = total_questions
        
        # Set exam timer (60 minutes for 100 questions)
        exam_duration = 3600  # 60 minutes in seconds
        context.user_data['exam_end_time'] = datetime.now() + timedelta(seconds=exam_duration)
        
        # Start the exam
        await display_question(update, context)
        
        # Schedule timer updates
        context.job_queue.run_repeating(
            update_exam_timer, 
            interval=10, 
            first=10, 
            chat_id=update.effective_chat.id, 
            name=str(update.effective_chat.id)
        )
        
        # Schedule 10-minute warning
        warning_time = exam_duration - 600  # 10 minutes before end
        if warning_time > 0:
            context.job_queue.run_once(
                warn_remaining_time, 
                warning_time, 
                chat_id=update.effective_chat.id, 
                name=f"warning_{update.effective_chat.id}"
            )
        
        return EXAM_IN_PROGRESS
    else:
        await update.message.reply_text(
            "क्षमस्व, या विषयासाठी प्रश्न उपलब्ध नाहीत. कृपया दुसरा विषय निवडा.",
            reply_markup=subject_keyboard()
        )
        return SELECTING_SUBJECT

# Display current question
async def display_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    question_index = context.user_data['current_question']
    questions = context.user_data['questions']
    
    if question_index < len(questions):
        question_data = questions[question_index]
        question_text = question_data['question']
        options = question_data['options']
        
        # Create inline keyboard for options
        keyboard = []
        for i, option in enumerate(options):
            keyboard.append([InlineKeyboardButton(f"{i+1}. {option}", callback_data=f"answer_{i}")])
        
        # Add exit button
        keyboard.append([InlineKeyboardButton("🚪 परीक्षा सोडा", callback_data="exit_exam")])
        
        # Display question with timer
        remaining_time = context.user_data['exam_end_time'] - datetime.now()
        minutes, seconds = divmod(int(remaining_time.total_seconds()), 60)
        
        message = (
            f"⏰ उर्वरित वेळ: {minutes:02d}:{seconds:02d}\n\n"
            f"प्रश्न {question_index + 1}/{len(questions)}:\n"
            f"{question_text}\n\n"
            "पर्याय:"
        )
        
        if update.callback_query:
            await update.callback_query.edit_message_text(
                message, 
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await update.message.reply_text(
                message, 
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
    else:
        # Exam finished
        await finish_exam(update, context)

# Update exam timer
async def update_exam_timer(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    chat_id = job.chat_id
    
    if 'exam_end_time' in context.user_data:
        remaining_time = context.user_data['exam_end_time'] - datetime.now()
        if remaining_time.total_seconds() <= 0:
            # Exam time is over
            await context.bot.send_message(
                chat_id=chat_id,
                text="⏰ परीक्षेचा वेळ संपला आहे!",
                reply_markup=main_menu_keyboard()
            )
            job.schedule_removal()
            return ConversationHandler.END
        
        minutes, seconds = divmod(int(remaining_time.total_seconds()), 60)
        
        # Update the message with remaining time
        try:
            await context.bot.edit_message_text(
                text=f"⏰ उर्वरित वेळ: {minutes:02d}:{seconds:02d}",
                chat_id=chat_id,
                message_id=context.user_data.get('timer_message_id')
            )
        except:
            # Message might not be accessible, ignore error
            pass

# Warn about remaining time
async def warn_remaining_time(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    chat_id = job.chat_id
    
    # Send warning message
    warning_msg = await context.bot.send_message(
        chat_id=chat_id,
        text="⚠️ सावधान! परीक्षेचा वेळ फक्त १० मिनिटे शिल्लक आहे! ⚠️",
        parse_mode=ParseMode.HTML
    )
    
    # Blink the warning message
    for _ in range(5):
        await asyncio.sleep(1)
        try:
            await context.bot.edit_message_text(
                text="<b>⚠️ सावधान! परीक्षेचा वेळ फक्त १० मिनिटे शिल्लक आहे! ⚠️</b>",
                chat_id=chat_id,
                message_id=warning_msg.message_id,
                parse_mode=ParseMode.HTML
            )
        except:
            pass
        
        await asyncio.sleep(1)
        try:
            await context.bot.edit_message_text(
                text="⚠️ सावधान! परीक्षेचा वेळ फक्त १० मिनिटे शिल्लक आहे! ⚠️",
                chat_id=chat_id,
                message_id=warning_msg.message_id,
                parse_mode=ParseMode.HTML
            )
        except:
            pass

# Handle answer selection
async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    answer_index = int(query.data.split('_')[1])
    question_index = context.user_data['current_question']
    questions = context.user_data['questions']
    question_data = questions[question_index]
    correct_index = question_data['correct_answer']
    
    # Check if answer is correct
    if answer_index == correct_index:
        context.user_data['score'] += 1
        context.user_data['correct_streak'] += 1
        
        # Celebration for every 10 correct answers
        if context.user_data['correct_streak'] % 10 == 0:
            celebration_messages = [
                "अभिनंदन! 🔥 तुमची कामगिरी अत्यंत उत्कृष्ट आहे!",
                "वाह! 🌟 तुम्ही अप्रतिम प्रगती करत आहात!",
                "अद्भुत! 💯 तुमच्या कष्टाचे फळ मिळत आहे!"
            ]
            await query.edit_message_text(
                text=f"✅ बरोबर उत्तर!\n\n{random.choice(celebration_messages)}"
            )
            await asyncio.sleep(2)
        else:
            # Show correct answer animation
            await query.edit_message_text(
                text="✅ बरोबर उत्तर! " + "🎉" * min(context.user_data['correct_streak'], 5)
            )
            await asyncio.sleep(1)
    else:
        context.user_data['correct_streak'] = 0
        correct_answer = question_data['options'][correct_index]
        
        # Show wrong answer animation
        await query.edit_message_text(
            text=f"❌ चुकीचे उत्तर!\n\nयोग्य उत्तर: {correct_answer}"
        )
        await asyncio.sleep(2)
    
    # Move to next question
    context.user_data['current_question'] += 1
    await display_question(update, context)

# Finish exam and show results
async def finish_exam(update: Update, context: ContextTypes.DEFAULT_TYPE):
    score = context.user_data['score']
    total_questions = context.user_data['total_questions']
    subject = context.user_data['current_subject']
    
    # Calculate percentage
    percentage = (score / total_questions) * 100
    
    # Store result in database
    user_id = context.user_data['user_id']
    conn = sqlite3.connect('maharashtra_police_bot.db')
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO user_progress (user_id, subject, score, total_questions) VALUES (?, ?, ?, ?)",
        (user_id, subject, score, total_questions)
    )
    conn.commit()
    conn.close()
    
    # Prepare result message
    result_message = (
        f"📊 तुमचे परीक्षा निकाल:\n\n"
        f"विषय: {subject}\n"
        f"एकूण प्रश्न: {total_questions}\n"
        f"बरोबर उत्तरे: {score}\n"
        f"टक्केवारी: {percentage:.2f}%\n\n"
    )
    
    # Add motivational message based on score
    if percentage < 50:
        result_message += (
            "💪 घाबरू नका! कष्ट सुरू ठेवा, कुटुंब आणि मित्रांच्या सहकार्याने तुम्ही नक्कीच यशस्वी व्हाल!\n\n"
            "📚 अधिक सराव करण्यासाठी पुन्हा प्रयत्न करा!"
        )
    else:
        result_message += (
            "🎖️ अभिनंदन! उत्तम कामगिरी!\n\n"
            "वर्दी तुझी वाट पाहत आहे! 👮‍♂️"
        )
    
    # Send result message
    if update.callback_query:
        await update.callback_query.edit_message_text(
            result_message,
            reply_markup=main_menu_keyboard()
        )
    else:
        await update.message.reply_text(
            result_message,
            reply_markup=main_menu_keyboard()
        )
    
    # Remove exam timer job
    if 'exam_timer_job' in context.user_data:
        context.user_data['exam_timer_job'].schedule_removal()
    
    return ConversationHandler.END

# Exit exam
async def exit_exam(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    # Confirm exit
    keyboard = [
        [InlineKeyboardButton("✅ होय", callback_data="confirm_exit")],
        [InlineKeyboardButton("❌ नाही", callback_data="cancel_exit")]
    ]
    
    await query.edit_message_text(
        "तुम्हाला परीक्षा सोडायची आहे का? सध्या केलेले प्रगती नष्ट होईल.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# Confirm exam exit
async def confirm_exit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "परीक्षा सोडली आहे. मुख्य मेनूमध्ये परत आलात.",
        reply_markup=main_menu_keyboard()
    )
    
    # Remove exam timer job
    if 'exam_timer_job' in context.user_data:
        context.user_data['exam_timer_job'].schedule_removal()
    
    return ConversationHandler.END

# Cancel exam exit
async def cancel_exit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    # Return to current question
    await display_question(update, context)
    return EXAM_IN_PROGRESS

# Select subject
async def select_subject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith("subject_"):
        subject = query.data.split("_")[1]
        context.user_data['current_subject'] = subject
        
        await query.edit_message_text(
            f"तुम्ही निवडलेला विषय: {subject}\n\n"
            "परीक्षा सुरू करण्यासाठी '📝 परीक्षा सुरू करा' वर क्लिक करा.",
            reply_markup=main_menu_keyboard()
        )
    elif query.data == "main_menu":
        await query.edit_message_text(
            "मुख्य मेनू:",
            reply_markup=main_menu_keyboard()
        )
    
    return ConversationHandler.END

# Show daily thought
async def daily_thought(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Get today's thought (based on day of year for consistency)
    day_of_year = datetime.now().timetuple().tm_yday
    thought_index = day_of_year % len(daily_thoughts)
    thought = daily_thoughts[thought_index]
    
    await update.message.reply_text(
        f"📅 दैनंदिन विचार:\n\n"
        f"{thought['thought']}\n\n"
        f"- {thought['author']}"
    )

# Show news updates
async def news_updates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Get today's news (in a real scenario, this would come from an API)
    today_news = news_updates[datetime.now().day % len(news_updates)]
    
    await update.message.reply_text(
        f"📰 अद्यतन बातम्या:\n\n"
        f"{today_news}\n\n"
        f"📅 {datetime.now().strftime('%d-%m-%Y')}"
    )

# Set reminder
async def set_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⏰ तुम्हाला रिमाइंडर सेट करायचा आहे का?\n\n"
        "कृपया रिमाइंडरचा संदेश आणि वेळ पाठवा (उदा: 'उद्या सकाळी ९ वाजता अभ्यास सुरू करा').",
        reply_markup=ReplyKeyboardRemove()
    )
    return SETTING_REMINDER

# Handle reminder input
async def handle_reminder_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reminder_text = update.message.text
    user_id = context.user_data['user_id']
    
    # Simple reminder parsing (in a real scenario, use a proper NLP library)
    if 'उद्या' in reminder_text:
        reminder_time = datetime.now() + timedelta(days=1)
    elif 'आज' in reminder_text:
        reminder_time = datetime.now()
    else:
        reminder_time = datetime.now() + timedelta(hours=1)
    
    # Set time to 9 AM if not specified
    reminder_time = reminder_time.replace(hour=9, minute=0, second=0, microsecond=0)
    
    # Store reminder in database
    conn = sqlite3.connect('maharashtra_police_bot.db')
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO reminders (user_id, reminder_text, reminder_time) VALUES (?, ?, ?)",
        (user_id, reminder_text, reminder_time)
    )
    conn.commit()
    conn.close()
    
    # Schedule reminder
    context.job_queue.run_once(
        send_reminder, 
        when=reminder_time, 
        chat_id=update.effective_chat.id, 
        data=reminder_text,
        name=f"reminder_{user_id}_{reminder_time}"
    )
    
    await update.message.reply_text(
        f"✅ रिमाइंडर सेट केला आहे!\n\n"
        f"संदेश: {reminder_text}\n"
        f"वेळ: {reminder_time.strftime('%d-%m-%Y %H:%M')}",
        reply_markup=main_menu_keyboard()
    )
    
    return ConversationHandler.END

# Send reminder
async def send_reminder(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    await context.bot.send_message(
        chat_id=job.chat_id,
        text=f"⏰ रिमाइंडर:\n\n{job.data}"
    )

# Show current time and date
async def show_time_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now()
    await update.message.reply_text(
        f"🕒 वेळ आणि तारीख:\n\n"
        f"तारीख: {now.strftime('%d-%m-%Y')}\n"
        f"वेळ: {now.strftime('%H:%M:%S')}\n"
        f"वार: {['सोमवार', 'मंगळवार', 'बुधवार', 'गुरुवार', 'शुक्रवार', 'शनिवार', 'रविवार'][now.weekday()]}"
    )

# Cancel conversation
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ऑपरेशन रद्द केले आहे.",
        reply_markup=main_menu_keyboard()
    )
    return ConversationHandler.END

# Error handler
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(msg="Exception while handling an update:", exc_info=context.error)
    
    # Send a message to the user
    await update.message.reply_text(
        "क्षमस्व, तांत्रिक समस्या आली आहे. कृपया नंतर पुन्हा प्रयत्न करा.",
        reply_markup=main_menu_keyboard()
    )

# Main function
def main():
    # Create Application
    application = Application.builder().token("8034142571:AAFEUhf8UEPz0lE6p60wPwcIHzAN09OPjuQ").build()
    
    # Add conversation handler for the start command
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            0: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    
    # Add handlers
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.Regex("^📝 परीक्षा सुरू करा$"), start_exam))
    application.add_handler(MessageHandler(filters.Regex("^📘 विषय निवडा$"), 
                                         lambda update, context: update.message.reply_text(
                                             "विषय निवडा:", reply_markup=subject_keyboard())))
    application.add_handler(MessageHandler(filters.Regex("^💡 दैनंदिन विचार$"), daily_thought))
    application.add_handler(MessageHandler(filters.Regex("^📰 बातम्या$"), news_updates))
    application.add_handler(MessageHandler(filters.Regex("^⏰ रिमाइंडर सेट करा$"), set_reminder))
    application.add_handler(MessageHandler(filters.Regex("^🕒 वेळ आणि तारीख$"), show_time_date))
    
    # Add callback query handlers
    application.add_handler(CallbackQueryHandler(select_subject, pattern="^subject_"))
    application.add_handler(CallbackQueryHandler(main_menu, pattern="^main_menu$"))
    application.add_handler(CallbackQueryHandler(handle_answer, pattern="^answer_"))
    application.add_handler(CallbackQueryHandler(exit_exam, pattern="^exit_exam$"))
    application.add_handler(CallbackQueryHandler(confirm_exit, pattern="^confirm_exit$"))
    application.add_handler(CallbackQueryHandler(cancel_exit, pattern="^cancel_exit$"))
    
    # Add conversation handler for setting reminders
    reminder_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^⏰ रिमाइंडर सेट करा$"), set_reminder)],
        states={
            SETTING_REMINDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_reminder_input)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    application.add_handler(reminder_handler)
    
    # Add error handler
    application.add_error_handler(error_handler)
    
    # Start the Bot
    application.run_polling()

if __name__ == "__main__":
    main()
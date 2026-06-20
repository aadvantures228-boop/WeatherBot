from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import CallbackContext
import storage

async def start(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    lang = storage.get_user_lang(context, user_id)
    
    if lang == "rus":
        keyboard = [["⚙️ Настройки", "⭐ Избранное"], ["🌅 Погода в моем регионе", "🔄 Обновления"]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text(
            "🌤️ Добро пожаловать в погодного бота!\n"
            "📌 Текущая версия: 1.0\n\n"
            "Я показываю погоду в любой точке земного шара!\n"
            "🏙️ Введите город, чтобы увидеть погоду в нём!\n"
            "📱 Используйте кнопки ниже или введите /settings для помощи.",
            reply_markup=reply_markup
        )
    else:
        keyboard = [["⚙️ Settings", "⭐ Favorites"], ["🌅 Weather in my region", "🔄 Updates"]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text(
            "🌤️ Welcome to the weather bot!\n"
            "📌 Current version: 1.0\n\n"
            "I show weather anywhere in the world!\n"
            "🏙️ Enter a city to see the weather there!\n"
            "📱 Use the buttons below or type /settings for help.",
            reply_markup=reply_markup
        )

async def settings(update: Update, context: CallbackContext):
    user_id = update.effective_user.id if update.message else update.callback_query.from_user.id
    lang = storage.get_user_lang(context, user_id)
    
    if lang == "rus":
        keyboard = [[InlineKeyboardButton("🌐 Язык", callback_data="Language")]]
        text = "⚙️ Настройки:"
    else:
        keyboard = [[InlineKeyboardButton("🌐 Language", callback_data="Language")]]
        text = "⚙️ Settings:"
        
    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.message: await update.message.reply_text(text, reply_markup=reply_markup)
    elif update.callback_query: await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
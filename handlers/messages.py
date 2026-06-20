from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import CallbackContext
import storage
import utils
from weather_api import get_weather, get_forecast, get_daily_forecast

async def handle_reply(update: Update, context: CallbackContext):
    text = update.message.text.strip()
    user_id = update.effective_user.id
    lang = storage.get_user_lang(context, user_id)
    current_region = storage.get_user_region(context, user_id)
    
    if context.user_data.get('awaiting_region_input'):
        weather_info, weather_text = get_weather(text, lang)
        if weather_info:
            city = weather_info['city']
            storage.set_user_region(context, user_id, city)
            if 'awaiting_region_input' in context.user_data:
                del context.user_data['awaiting_region_input']
            city_in_favorites = city in storage.get_user_favorites(context, user_id)
            keyboard = utils.create_weather_keyboard(city, city_in_favorites, city, lang, from_favorites=False)
            await update.message.reply_text(weather_text, reply_markup=keyboard)
        else:
            if 'awaiting_region_input' in context.user_data:
                del context.user_data['awaiting_region_input']
            await update.message.reply_text(weather_text)
        return

    if lang == "rus":
        if text == "⚙️ Настройки": return await __import__('handlers.commands').commands.settings(update, context)
        elif text == "⭐ Избранное": return await favorites(update, context)
        elif text == "🌅 Погода в моем регионе": return await get_weather_for_region(update, context)
        elif text == "🔄 Обновления": return await show_updates_menu(update, context)
    else:
        if text == "⚙️ Settings": return await __import__('handlers.commands').commands.settings(update, context)
        elif text == "⭐ Favorites": return await favorites(update, context)
        elif text == "🌅 Weather in my region": return await get_weather_for_region(update, context)
        elif text == "🔄 Updates": return await show_updates_menu(update, context)

    weather_info, weather_text = get_weather(text, lang)
    if weather_info:
        city = weather_info['city']
        city_in_favorites = city in storage.get_user_favorites(context, user_id)
        keyboard = utils.create_weather_keyboard(city, city_in_favorites, current_region, lang, from_favorites=False)
        await update.message.reply_text(weather_text, reply_markup=keyboard)
    else:
        await update.message.reply_text(weather_text)

async def get_weather_for_region(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    lang = storage.get_user_lang(context, user_id)
    region = storage.get_user_region(context, user_id)
    
    if region == 'Moscow':
        context.user_data['awaiting_region_input'] = True
        text = ("📍 Вы еще не выбрали свой регион!\n\n"
                "Введите название города прямо в чат, и он автоматически станет вашим регионом.") if lang == "rus" else \
               ("📍 You haven't selected your region yet!\n\n"
                "Enter the city name directly in the chat, and it will automatically become your region.")
        await update.message.reply_text(text)
        return

    weather_info, weather_text = get_weather(region, lang)
    if weather_info:
        city = weather_info['city']
        city_in_favorites = city in storage.get_user_favorites(context, user_id)
        keyboard = utils.create_weather_keyboard(city, city_in_favorites, region, lang, from_favorites=False)
        await update.message.reply_text(weather_text, reply_markup=keyboard)
    else:
        await update.message.reply_text(f"⚠️ Не удалось получить погоду для региона {region}" if lang == "rus" else f"⚠️ Failed to get weather for region {region}")

async def favorites(update: Update, context: CallbackContext):
    query = update.callback_query if hasattr(update, 'callback_query') else None
    user_id = update.effective_user.id if update.message else query.from_user.id
    lang = storage.get_user_lang(context, user_id)
    favorites_list = storage.get_user_favorites(context, user_id)
    
    if not favorites_list:
        text = "⭐ Ваш список избранных городов пуст." if lang == "rus" else "⭐ Your favorites list is empty."
        await (update.message if update.message else query.message).reply_text(text)
        return

    text = "⭐ Ваши избранные города:" if lang == "rus" else "⭐ Your favorite cities:"
    keyboard = []
    for city in favorites_list:
        weather_info, _ = get_weather(city, lang)
        temp = weather_info['temp'] if weather_info else "?"
        city_text = f"🏙️ {city} ({temp}°C)"
        keyboard.append([
            InlineKeyboardButton(city_text, callback_data=f"weather_fav_{city}"),
            InlineKeyboardButton("❌", callback_data=f"remove_favorite_{city}")
        ])
    if favorites_list:
        keyboard.append([InlineKeyboardButton("🗑️ Очистить весь список" if lang == "rus" else "🗑️ Clear all favorites", callback_data="clear_all_favorites")])
        
    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.message: await update.message.reply_text(text, reply_markup=reply_markup)
    elif query: await query.edit_message_text(text, reply_markup=reply_markup)

async def week_forecast(update: Update, context: CallbackContext, city_name: str = None, from_favorites: bool = False):
    query = update.callback_query if hasattr(update, 'callback_query') else None
    user_id = query.from_user.id if query else update.effective_user.id
    lang = storage.get_user_lang(context, user_id)
    
    if not city_name:
        city_name = storage.get_user_region(context, user_id)
        
    text = f"📅 Загружаю прогноз погоды для {city_name} на неделю..." if lang == "rus" else f"📅 Loading weather forecast for {city_name} for the week..."
    if query: await query.edit_message_text(text)
    else: await update.message.reply_text(text)
        
    city_name_api, forecast_list, error = get_forecast(city_name, lang)
    if error or not forecast_list:
        error_msg = "❌ Не удалось получить прогноз." if lang == "rus" else "❌ Failed to get forecast."
        if query: await query.message.reply_text(error_msg)
        else: await update.message.reply_text(error_msg)
        return
        
    context.user_data['forecast_data'] = {'city': city_name_api, 'forecast_list': forecast_list}
    text = f"🌤️ Прогноз погоды в {city_name_api}:\nВыберите день:" if lang == "rus" else f"🌤️ Weather forecast in {city_name_api}:\nChoose a day:"
    days_of_week = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"] if lang == "rus" else ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    
    now = datetime.now()
    keyboard = []
    
    # ИСПРАВЛЕНИЕ 1: Возвращено исходное поведение (6 дней, начиная с "Сегодня")
    for i in range(6):
        forecast_date = now + timedelta(days=i)
        day_num, month_num = forecast_date.day, forecast_date.month
        if lang == "rus":
            if i == 0: day_name = "Сегодня"
            elif i == 1: day_name = "Завтра"
            else: day_name = days_of_week[forecast_date.weekday()]
        else:
            if i == 0: day_name = "Today"
            elif i == 1: day_name = "Tomorrow"
            else: day_name = days_of_week[forecast_date.weekday()]
            
        button_text = f"{day_name} ({day_num}.{month_num})"
        
        # Безопасная группировка по 2 кнопки в строку
        if i % 2 == 0:
            keyboard.append([InlineKeyboardButton(button_text, callback_data=f"day_forecast_{city_name_api}_{i}")])
        else:
            keyboard[-1].append(InlineKeyboardButton(button_text, callback_data=f"day_forecast_{city_name_api}_{i}"))
            
    back_callback = f"weather_fav_{city_name_api}" if from_favorites else f"weather_{city_name_api}"
    keyboard.append([InlineKeyboardButton("🔙 Назад к погоде" if lang == "rus" else "🔙 Back to weather", callback_data=back_callback)])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    if query: await query.message.reply_text(text, reply_markup=reply_markup)
    else: await update.message.reply_text(text, reply_markup=reply_markup)

async def show_updates_menu(update: Update, context: CallbackContext):
    query = update.callback_query if hasattr(update, 'callback_query') else None
    lang = storage.get_user_lang(context, update.effective_user.id if update.message else query.from_user.id)

    if lang == "rus":
        text = "📌 *История обновлений*\nВыберите версию:"
        keyboard = [[InlineKeyboardButton("🧪 Beta 1.0", callback_data="changelog_beta"), InlineKeyboardButton("🚀 1.0", callback_data="changelog_1_0")]]
    else:
        text = "📌 *Update History*\nChoose version:"
        keyboard = [[InlineKeyboardButton("🧪 Beta 1.0", callback_data="changelog_beta"), InlineKeyboardButton("🚀 1.0", callback_data="changelog_1_0")]]

    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.message: await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")
    elif query: await query.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")

async def show_changelog(update: Update, context: CallbackContext, version: str):
    query = update.callback_query
    lang = storage.get_user_lang(context, query.from_user.id)

    if version == "1_0":
        text = ("🚀 *1.0 (Основной релиз)*\n\n"
                "• Кнопка «Сделать моим регионом» скрыта, если город уже является регионом.\n"
                "• При добавлении/удалении из избранного кнопка меняется мгновенно, без лишних сообщений.\n"
                "• Список избранного обновляется автоматически при удалении городов.\n"
                "• Удобное меню истории обновлений.") if lang == "rus" else \
               ("🚀 *1.0 (Main Release)*\n\n"
                "• 'Set as my region' hidden if already region.\n"
                "• Favorites button toggles instantly (Add <-> Remove) without spam messages.\n"
                "• Favorites list auto-refreshes upon deletion.\n"
                "• Convenient update history menu.")
    else:
        text = ("🧪 *Beta 1.0*\n\n"
                "• Базовый просмотр погоды.\n"
                "• Прогноз на неделю.\n"
                "• Список избранных городов.\n"
                "• Возможность сменить язык.") if lang == "rus" else \
               ("🧪 *Beta 1.0*\n\n"
                "• Basic weather viewing.\n"
                "• Weekly forecast.\n"
                "• Favorite cities list.\n"
                "• Ability to change language.")

    back_text = "🔙 К списку версий" if lang == "rus" else "🔙 Back to versions"
    keyboard = [[InlineKeyboardButton(back_text, callback_data="updates_menu")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
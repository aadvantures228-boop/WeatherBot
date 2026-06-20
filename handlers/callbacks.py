import logging
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import CallbackContext
import storage
import utils
from weather_api import get_weather, get_forecast, get_daily_forecast
from handlers import commands, messages

logger = logging.getLogger(__name__)

async def button_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer() # Ответ без текста (убирает загрузку)
    data = query.data
    user_id = query.from_user.id
    lang = storage.get_user_lang(context, user_id)
    current_region = storage.get_user_region(context, user_id)
    
    logger.info(f"User {user_id} pressed button with data: {data}")

    # Отслеживаем контекст: пришли ли мы из избранного?
    if data.startswith("weather_fav_"):
        context.user_data['viewing_fav_weather'] = data.split("_", 2)[2]
    elif data.startswith("weather_"):
        if 'viewing_fav_weather' in context.user_data:
            del context.user_data['viewing_fav_weather']

    if data == "Language":
        keyboard = [[InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru")], [InlineKeyboardButton("🇺🇸 English", callback_data="lang_en")], [InlineKeyboardButton("🔙 Назад", callback_data="settings_back")]]
        await query.edit_message_text("🌐 Выберите язык:" if lang == "rus" else "🌐 Choose language:", reply_markup=InlineKeyboardMarkup(keyboard))
    elif data == "lang_ru":
        storage.set_user_lang(context, user_id, "rus")
        keyboard = [["⚙️ Настройки", "⭐ Избранное"], ["🌅 Погода в моем регионе", "🔄 Обновления"]]
        await query.message.reply_text("✅ Язык изменен на Русский", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
    elif data == "lang_en":
        storage.set_user_lang(context, user_id, "eng")
        keyboard = [["⚙️ Settings", "⭐ Favorites"], ["🌅 Weather in my region", "🔄 Updates"]]
        await query.message.reply_text("✅ Language changed to English", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
    elif data == "settings_back":
        await commands.settings(update, context)
    elif data == "favorites":
        await messages.favorites(update, context)
        
    elif data.startswith("weather_fav_"):
        city = data.split("_", 2)[2]
        weather_info, weather_text = get_weather(city, lang)
        if weather_info:
            city_in_favorites = city in storage.get_user_favorites(context, user_id)
            await query.edit_message_text(weather_text, reply_markup=utils.create_weather_keyboard(city, city_in_favorites, current_region, lang, from_favorites=True))
        else:
            await query.edit_message_text(weather_text)

    elif data.startswith("weather_"):
        city = data.split("_", 1)[1]
        weather_info, weather_text = get_weather(city, lang)
        if weather_info:
            city_in_favorites = city in storage.get_user_favorites(context, user_id)
            await query.edit_message_text(weather_text, reply_markup=utils.create_weather_keyboard(city, city_in_favorites, current_region, lang, from_favorites=False))
        else:
            await query.edit_message_text(weather_text)
            
    elif data.startswith("set_region_"):
        city = data.split("_", 2)[2]
        storage.set_user_region(context, user_id, city)
        await query.answer()
        await query.message.reply_text(f"📍 Город {city} установлен как ваш регион" if lang == "rus" else f"📍 City {city} set as your region")
            
    # ИСПРАВЛЕНИЕ 2: Мгновенная смена кнопки "Добавить" на "Удалить" без сообщений
    elif data.startswith("add_favorite_"):
        city = data.split("_", 2)[2]
        is_fav_view = context.user_data.get('viewing_fav_weather') == city
        
        if storage.add_user_favorite(context, user_id, city):
            # Успешно добавлено -> меняем кнопку на "Удалить"
            new_kb = utils.create_weather_keyboard(city, True, current_region, lang, from_favorites=is_fav_view)
            await query.edit_message_reply_markup(reply_markup=new_kb)
        else:
            # Уже добавлено -> просто обновляем кнопку, чтобы она точно показывала "Удалить"
            new_kb = utils.create_weather_keyboard(city, True, current_region, lang, from_favorites=is_fav_view)
            await query.edit_message_reply_markup(reply_markup=new_kb)
            
    # ИСПРАВЛЕНИЕ 2: Мгновенная смена кнопки "Удалить" на "Добавить"
    elif data.startswith("remove_favorite_"):
        city = data.split("_", 2)[2]
        is_fav_view = context.user_data.get('viewing_fav_weather') == city
        
        # Проверяем, находимся ли мы в списке избранного (по тексту сообщения)
        is_in_list = "Ваши избранные города" in query.message.text or "favorite cities" in query.message.text

        if storage.remove_user_favorite(context, user_id, city):
            if is_in_list:
                # Если мы в списке, перерисовываем список (город исчезает)
                await messages.favorites(update, context)
            else:
                # Если мы в карточке погоды, меняем кнопку на "Добавить"
                new_kb = utils.create_weather_keyboard(city, False, current_region, lang, from_favorites=is_fav_view)
                await query.edit_message_reply_markup(reply_markup=new_kb)
        else:
            # Если города нет (ошибка), просто обновляем кнопку на "Добавить"
            if is_in_list:
                await messages.favorites(update, context)
            else:
                new_kb = utils.create_weather_keyboard(city, False, current_region, lang, from_favorites=is_fav_view)
                await query.edit_message_reply_markup(reply_markup=new_kb)
            
    elif data == "clear_all_favorites":
        keyboard = [[InlineKeyboardButton("✅ Да" if lang == "rus" else "✅ Yes", callback_data="confirm_clear_favorites")], [InlineKeyboardButton("❌ Нет" if lang == "rus" else "❌ No", callback_data="favorites")]]
        await query.edit_message_text("⚠️ Очистить весь список?" if lang == "rus" else "⚠️ Clear all favorites?", reply_markup=InlineKeyboardMarkup(keyboard))
    elif data == "confirm_clear_favorites":
        storage.clear_user_favorites(context, user_id)
        await query.answer()
        await query.edit_message_text("🗑️ Список очищен." if lang == "rus" else "🗑️ List cleared.")
            
    elif data.startswith("week_forecast_fav_"):
        city_name = data.split("_", 3)[3]
        await messages.week_forecast(update, context, city_name, from_favorites=True)
    elif data.startswith("week_forecast_"):
        city_name = data.split("_", 2)[2]
        await messages.week_forecast(update, context, city_name, from_favorites=False)
        
    elif data.startswith("day_forecast_"):
        parts = data.split("_")
        city_name, day_offset = parts[2], int(parts[3])
        forecast_data = context.user_data.get('forecast_data')
        if not forecast_data or forecast_data['city'] != city_name:
            city_name_api, forecast_list, error = get_forecast(city_name, lang)
            if error:
                await query.message.reply_text(error)
                return
            forecast_data = {'city': city_name_api, 'forecast_list': forecast_list}
            
        daily = get_daily_forecast(forecast_data['forecast_list'], day_offset)
        if daily:
            now = datetime.now()
            target_date = now + timedelta(days=day_offset)
            days_ru = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
            days_en = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
            months_ru = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"]
            months_en = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
            
            if lang == "rus":
                day_name = "сегодня" if day_offset == 0 else "завтра" if day_offset == 1 else days_ru[target_date.weekday()].lower()
                date_str = f"{target_date.day} {months_ru[target_date.month - 1]}"
                pressure_display = f"{round(daily['pressure'] * 0.750062)} мм рт. ст."
                forecast_text = (f"📅 Погода в {forecast_data['city']} на {day_name} ({date_str}):\n"
                                 f"📝 {daily['description'].capitalize()}\n🌡️ Температура: {daily['temp_day']}°C (ощущается {daily['feels_like']}°C)\n"
                                 f"📈 Диапазон: {daily['temp_min']}°C - {daily['temp_max']}°C\n💧 Влажность: {daily['humidity']}%\n"
                                 f"📊 Давление: {pressure_display}\n💨 Ветер: {daily['wind_speed']} м/с")
            else:
                day_name = "today" if day_offset == 0 else "tomorrow" if day_offset == 1 else days_en[target_date.weekday()].lower()
                date_str = f"{months_en[target_date.month - 1]} {target_date.day}"
                forecast_text = (f"📅 Weather in {forecast_data['city']} on {day_name} ({date_str}):\n"
                                 f"📝 {daily['description'].capitalize()}\n🌡️ Temperature: {daily['temp_day']}°C (feels like {daily['feels_like']}°C)\n"
                                 f"📈 Range: {daily['temp_min']}°C - {daily['temp_max']}°C\n💧 Humidity: {daily['humidity']}%\n"
                                 f"📊 Pressure: {daily['pressure']} hPa\n💨 Wind: {daily['wind_speed']} m/s")
            await query.message.reply_text(forecast_text)
        else:
            await query.message.reply_text("❌ Не удалось получить прогноз." if lang == "rus" else "❌ Failed to get forecast.")

    elif data == "updates_menu":
        await messages.show_updates_menu(update, context)
    elif data == "changelog_1_0":
        await messages.show_changelog(update, context, "1_0")
    elif data == "changelog_beta":
        await messages.show_changelog(update, context, "beta")
    else:
        await query.answer()
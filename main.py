import asyncio
import logging
import requests
import pytz
import uuid
from datetime import datetime, time, timedelta
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice
from telegram.ext import (
    Application, CommandHandler, CallbackContext,
    filters, MessageHandler, CallbackQueryHandler,
    ContextTypes, PreCheckoutQueryHandler
)

# ==================== НАСТРОЙКИ ====================

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Ключи API
weather_token = "e8677da6c554a5a738e4df8f0802c283"
BOT_TOKEN = "8507475399:AAFDXfVd9900GI1PDjlB8greQz5X4a-0RPE"
PROVIDER_TOKEN = "284685063:TEST:YTk5MjljN2FkNTQx"

# Премиум пакеты
PREMIUM_PACKAGES = {
    "month": {"stars": 10, "days": 30, "description": "Премиум на месяц"},
    "year": {"stars": 30, "days": 365, "description": "Премиум на год"},
    "forever": {"stars": 50, "days": 99999, "description": "Премиум навсегда"}
}

# Промокоды
PROMO_CODES = {
    "weather": {"days": 30, "max_uses": 100, "used_by": set()},
    "advanturesmade": {"days": 99999, "max_uses": 100, "used_by": set()}
}

# ==================== ФУНКЦИИ ХРАНЕНИЯ ДАННЫХ ====================

def get_user_lang(context: CallbackContext, user_id: int):
    if 'lang' not in context.bot_data:
        context.bot_data['lang'] = {}
    if user_id not in context.bot_data['lang']:
        context.bot_data['lang'][user_id] = 'rus'
    return context.bot_data['lang'][user_id]
def set_user_lang(context: CallbackContext, user_id: int, lang: str):
    if 'lang' not in context.bot_data:
        context.bot_data['lang'] = {}
    context.bot_data['lang'][user_id] = lang

def get_user_premium(context: CallbackContext, user_id: int):
    if 'premium' not in context.bot_data:
        context.bot_data['premium'] = {}
    if user_id not in context.bot_data['premium']:
        context.bot_data['premium'][user_id] = {
            'active': False,
            'until': None,
            'trial_used_callback': False,
            'features': {
                'geolocation': False,
                'forecast': False,
                'multiple_notifications': False,
                'extended_data': False,
                'cloudiness': False,
                'wind_direction': False,
                'wind_gust': False,
                'sunrise_sunset': False
            },
            'daily_usage': {
                'geolocation_used': False,
                'forecast_used': False,
                'weather_queries': 0  # Счетчик запросов погоды за день
            }
            # УДАЛЕНЫ ПОЛЯ СПЕЦИАЛЬНОГО ПРЕДЛОЖЕНИЯ
        }
    return context.bot_data['premium'][user_id]
def update_user_premium(context: CallbackContext, user_id: int, premium_data: dict):
    if 'premium' not in context.bot_data:
        context.bot_data['premium'] = {}
    context.bot_data['premium'][user_id] = premium_data
def activate_premium(context: CallbackContext, user_id: int, days: int, offer_type: str = None):
    try:
        premium = get_user_premium(context, user_id)
        now = datetime.now()

        if premium['until']:
            current_end = datetime.fromisoformat(premium['until'])
            if current_end > now:
                new_end = current_end + timedelta(days=days)
            else:
                new_end = now + timedelta(days=days)
        else:
            new_end = now + timedelta(days=days)

        premium['active'] = True
        premium['until'] = new_end.isoformat()

        # Включаем базовые функции премиума
        premium['features']['geolocation'] = True
        premium['features']['forecast'] = True
        premium['features']['multiple_notifications'] = True
        premium['features']['extended_data'] = True

        # ВКЛЮЧАЕМ ВСЕ ДОПОЛНИТЕЛЬНЫЕ ФУНКЦИИ ПО УМОЛЧАНИЮ
        premium['features']['cloudiness'] = True
        premium['features']['wind_direction'] = True
        premium['features']['wind_gust'] = True
        premium['features']['sunrise_sunset'] = True

        update_user_premium(context, user_id, premium)
        logger.info(f"Premium activated for user {user_id} for {days} days until {new_end}")
        logger.info(f"All premium features enabled for user {user_id}")
        return True
    except Exception as e:
        logger.error(f"Error activating premium for user {user_id}: {e}")
        return False
def deactivate_premium(context: CallbackContext, user_id: int):
    premium = get_user_premium(context, user_id)
    premium['active'] = False
    premium['until'] = None
    # Выключаем все функции премиума
    for feature in premium['features']:
        premium['features'][feature] = False

    # Отключаем все рассылки при отключении премиума
    disable_all_notifications(context, user_id)

    update_user_premium(context, user_id, premium)
    return True

def reset_daily_usage(context: CallbackContext, user_id: int):
    premium = get_user_premium(context, user_id)
    premium['daily_usage']['geolocation_used'] = False
    premium['daily_usage']['forecast_used'] = False
    update_user_premium(context, user_id, premium)
def can_use_geolocation(context: CallbackContext, user_id: int):
    premium = get_user_premium(context, user_id)

    # Логирование для отладки
    logger.info(
        f"Проверка геолокации для user {user_id}: active={premium['active']}, geolocation={premium['features']['geolocation']}, daily_used={premium['daily_usage']['geolocation_used']}")

    if premium['active'] and premium['features']['geolocation']:
        return True, ""
    elif not premium['daily_usage']['geolocation_used']:
        premium['daily_usage']['geolocation_used'] = True
        update_user_premium(context, user_id, premium)
        logger.info(f"Установлен флаг geolocation_used=True для user {user_id}")
        return True, ""
    else:
        lang = get_user_lang(context, user_id)
        if lang == "rus":
            return False, "🚫 Вы исчерпали дневной лимит бесплатного использования геолокации. Оформите премиум для неограниченного доступа."
        else:
            return False, "🚫 You have exhausted the daily limit for free geolocation usage. Get premium for unlimited access."
def can_use_forecast(context: CallbackContext, user_id: int):
    premium = get_user_premium(context, user_id)
    if premium['active'] and premium['features']['forecast']:
        return True, ""
    elif not premium['daily_usage']['forecast_used']:
        premium['daily_usage']['forecast_used'] = True
        update_user_premium(context, user_id, premium)
        return True, ""
    else:
        lang = get_user_lang(context, user_id)
        if lang == "rus":
            return False, "🚫 Вы исчерпали дневной лимит бесплатного прогноза погоды. Оформите премиум для неограниченного доступа."
        else:
            return False, "🚫 You have exhausted the daily limit for free weather forecast. Get premium for unlimited access."
def toggle_premium_feature(context: CallbackContext, user_id: int, feature: str):
    premium = get_user_premium(context, user_id)
    if feature in premium['features']:
        premium['features'][feature] = not premium['features'][feature]
        update_user_premium(context, user_id, premium)
        return True
    return False

# ==================== СИСТЕМА УВЕДОМЛЕНИЙ ====================

def get_user_notifications(context: CallbackContext, user_id: int):
    if 'notifications' not in context.bot_data:
        context.bot_data['notifications'] = {}
    if user_id not in context.bot_data['notifications']:
        context.bot_data['notifications'][user_id] = []
    return context.bot_data['notifications'][user_id]
def set_user_notifications(context: CallbackContext, user_id: int, notifications_list):
    if 'notifications' not in context.bot_data:
        context.bot_data['notifications'] = {}
    context.bot_data['notifications'][user_id] = notifications_list
    return True
def add_user_notification(context: CallbackContext, user_id: int, hour: int, minute: int, timezone_str: str):
    premium = get_user_premium(context, user_id)
    notifications = get_user_notifications(context, user_id)

    # Проверка лимита для бесплатных пользователей
    if not (premium['active'] and premium['features']['multiple_notifications']):
        if len(notifications) >= 1:
            return False, "limit_exceeded"

    for notification in notifications:
        if notification['hour'] == hour and notification['minute'] == minute and notification[
            'timezone'] == timezone_str:
            return False, "already_exists"

    new_notification = {
        'id': str(uuid.uuid4())[:8],
        'hour': hour,
        'minute': minute,
        'timezone': timezone_str,
        'region': get_user_region(context, user_id)
    }

    notifications.append(new_notification)
    set_user_notifications(context, user_id, notifications)

    # Проверяем, доступен ли job_queue
    if context.application and context.application.job_queue:
        create_notification_job(context, user_id, new_notification)
        return True, "success"
    else:
        logger.error("Job queue не доступен!")
        return False, "job_queue_unavailable"
def remove_user_notification(context: CallbackContext, user_id: int, notification_id: str):
    notifications = get_user_notifications(context, user_id)

    new_notifications = []
    removed = False

    for notification in notifications:
        if notification['id'] == notification_id:
            remove_notification_job(context, user_id, notification_id)
            removed = True
        else:
            new_notifications.append(notification)

    set_user_notifications(context, user_id, new_notifications)
    return removed
def disable_all_notifications(context: CallbackContext, user_id: int):
    notifications = get_user_notifications(context, user_id)

    for notification in notifications:
        remove_notification_job(context, user_id, notification['id'])

    context.bot_data['notifications'][user_id] = []

    return True
def create_notification_job(context: CallbackContext, user_id: int, notification):
    job_queue = context.application.job_queue

    if job_queue is not None:
        job_name = f"notif_{user_id}_{notification['id']}"
        timezone_str = notification['timezone']

        try:
            # Удаляем старую задачу если существует
            remove_notification_job(context, user_id, notification['id'])

            # Создаем время с правильным часовым поясом
            user_tz = pytz.timezone(timezone_str)
            notification_time = time(
                hour=notification['hour'],
                minute=notification['minute'],
                tzinfo=user_tz  # Ключевое отличие!
            )

            # Создаем новую задачу
            job_queue.run_daily(
                send_daily_notification,
                time=notification_time,
                days=(0, 1, 2, 3, 4, 5, 6),
                data={'notification_id': notification['id'], 'user_id': user_id},  # user_id в data!
                name=job_name
            )

            logger.info(
                f"Создано уведомление {job_name} на {notification['hour']:02d}:{notification['minute']:02d} в часовом поясе {timezone_str}")

        except Exception as e:
            logger.error(f"Ошибка создания уведомления: {e}")
def remove_notification_job(context: CallbackContext, user_id: int, notification_id: str):
    job_queue = context.application.job_queue

    if job_queue is not None:
        job_name = f"notif_{user_id}_{notification_id}"
        jobs = job_queue.jobs()
        jobs_to_remove = []

        for job in jobs:
            if job.name == job_name:
                jobs_to_remove.append(job)

        for job in jobs_to_remove:
            job.schedule_removal()
            logger.info(f"Удалена задача уведомления {job_name}")

        return len(jobs_to_remove) > 0

    return False
def get_jobs_by_name(job_queue, name):
    if job_queue is None:
        return []
    jobs = []
    for job in job_queue.jobs():
        if job.name == name:
            jobs.append(job)
    return jobs

# ==================== ПОГОДНЫЕ ФУНКЦИИ ====================

def get_weather(city: str, lang: str = "ru", premium_features: dict = None) -> tuple:
    try:
        url = 'https://api.openweathermap.org/data/2.5/weather'
        params = {
            'q': city,
            'appid': weather_token,
            'units': 'metric',
            'lang': 'ru' if lang == 'rus' else 'en'
        }
        response = requests.get(url, params=params, timeout=10)

        if response.status_code == 404:
            return None, f"🌍 Город {city} не найден" if lang == 'rus' else f"🌍 City {city} not found"
        elif response.status_code != 200:
            return None, f"⚠️ Ошибка: код {response.status_code}" if lang == 'rus' else f"⚠️ Error: code {response.status_code}"

        data = response.json()
        temp = data['main']['temp']
        feels_like = data['main']['feels_like']
        humidity = data['main']['humidity']
        pressure_hpa = data['main']['pressure']
        wind_speed = data['wind']['speed']
        desc = data['weather'][0]['description']
        city_name = data['name']

        if lang == 'rus':
            pressure_mmhg = round(pressure_hpa * 0.750062)
            pressure_display = f"{pressure_mmhg} мм рт. ст."
        else:
            pressure_display = f"{pressure_hpa} hPa"

        weather_info = {
            'city': city_name,
            'temp': temp,
            'feels_like': feels_like,
            'humidity': humidity,
            'pressure_hpa': pressure_hpa,
            'wind_speed': wind_speed,
            'desc': desc
        }

        if lang == 'rus':
            text = (f"🌤️ Погода в {city_name}:\n\n"
                    f"🌡️ Температура: {temp}°C (ощущается как {feels_like}°C)\n"
                    f"📝 Описание: {desc}\n"
                    f"💧 Влажность: {humidity}%\n"
                    f"📊 Давление: {pressure_display}\n"
                    f"💨 Ветер: {wind_speed} м/с")

            # Добавляем расширенные данные если включены соответствующие функции премиума
            if premium_features:
                extended_text = "\n\n💎 ДОПОЛНИТЕЛЬНЫЕ ДАННЫЕ:"

                if premium_features.get('cloudiness', False):
                    clouds = data['clouds'].get('all', 'Н/Д')
                    extended_text += f"\n☁️ Облачность: {clouds}%"

                if premium_features.get('wind_direction', False):
                    wind_deg = data['wind'].get('deg')
                    if wind_deg:
                        directions = ["⬆️ Северный", "↗️ Северо-восточный", "➡️ Восточный", "↘️ Юго-восточный",
                                      "⬇️ Южный", "↙️ Юго-западный", "⬅️ Западный", "↖️ Северо-западный"]
                        idx = round(wind_deg / 45) % 8
                        extended_text += f"\n💨 Направление: {directions[idx]}"

                if premium_features.get('wind_gust', False):
                    wind_gust = data['wind'].get('gust')
                    if wind_gust:
                        extended_text += f"\n💨 Порывы: {wind_gust} м/с"

                if premium_features.get('sunrise_sunset', False):
                    sunrise = datetime.fromtimestamp(data['sys']['sunrise']).strftime('%H:%M')
                    sunset = datetime.fromtimestamp(data['sys']['sunset']).strftime('%H:%M')
                    extended_text += f"\n🌅 Восход: {sunrise}\n🌇 Закат: {sunset}"

                if extended_text != "\n\n💎 ДОПОЛНИТЕЛЬНЫЕ ДАННЫЕ:":
                    text += extended_text
        else:
            text = (f"🌤️ Weather in {city_name}:\n\n"
                    f"🌡️ Temperature: {temp}°C (feels like {feels_like}°C)\n"
                    f"📝 Description: {desc}\n"
                    f"💧 Humidity: {humidity}%\n"
                    f"📊 Pressure: {pressure_display}\n"
                    f"💨 Wind: {wind_speed} m/s")

            # Добавляем расширенные данные если включены соответствующие функции премиума
            if premium_features:
                extended_text = "\n\n💎 EXTENDED DATA:"

                if premium_features.get('cloudiness', False):
                    clouds = data['clouds'].get('all', 'N/A')
                    extended_text += f"\n☁️ Cloudiness: {clouds}%"

                if premium_features.get('wind_direction', False):
                    wind_deg = data['wind'].get('deg')
                    if wind_deg:
                        directions = ["⬆️ North", "↗️ Northeast", "➡️ East", "↘️ Southeast",
                                      "⬇️ South", "↙️ Southwest", "⬅️ West", "↖️ Northwest"]
                        idx = round(wind_deg / 45) % 8
                        extended_text += f"\n💨 Direction: {directions[idx]}"

                if premium_features.get('wind_gust', False):
                    wind_gust = data['wind'].get('gust')
                    if wind_gust:
                        extended_text += f"\n💨 Gust: {wind_gust} m/s"

                if premium_features.get('sunrise_sunset', False):
                    sunrise = datetime.fromtimestamp(data['sys']['sunrise']).strftime('%H:%M')
                    sunset = datetime.fromtimestamp(data['sys']['sunset']).strftime('%H:%M')
                    extended_text += f"\n🌅 Sunrise: {sunrise}\n🌇 Sunset: {sunset}"

                if extended_text != "\n\n💎 EXTENDED DATA:":
                    text += extended_text

        return weather_info, text

    except Exception as e:
        return None, f'❌ Ошибка: {e}' if lang == 'rus' else f'❌ Error: {e}'

def get_forecast(city: str, lang: str = "ru"):
    try:
        url = 'https://api.openweathermap.org/data/2.5/forecast'
        params = {
            'q': city,
            'appid': weather_token,
            'units': 'metric',
            'lang': 'ru' if lang == 'rus' else 'en',
            'cnt': 40
        }
        response = requests.get(url, params=params, timeout=10)

        if response.status_code == 404:
            return None, None, f"Город {city} не найден" if lang == 'rus' else f"City {city} not found"
        elif response.status_code != 200:
            return None, None, f"Ошибка: код {response.status_code}" if lang == 'rus' else f"Error: code {response.status_code}"

        data = response.json()
        city_name = data['city']['name']
        forecast_list = data['list']

        return city_name, forecast_list, None

    except Exception as e:
        return None, None, f'Ошибка: {e}' if lang == 'rus' else f'Error: {e}'

def get_daily_forecast(forecast_list, day_offset: int = 0):
    if not forecast_list:
        return None

    target_date = (datetime.now() + timedelta(days=day_offset)).date()

    day_forecasts = []
    for forecast in forecast_list:
        forecast_dt = datetime.fromtimestamp(forecast['dt'])
        if forecast_dt.date() == target_date:
            day_forecasts.append(forecast)

    if not day_forecasts:
        return None

    temps = [f['main']['temp'] for f in day_forecasts]
    feels_like = [f['main']['feels_like'] for f in day_forecasts]
    humidities = [f['main']['humidity'] for f in day_forecasts]

    day_forecast = None
    for forecast in day_forecasts:
        hour = datetime.fromtimestamp(forecast['dt']).hour
        if 12 <= hour <= 15:
            day_forecast = forecast
            break

    if not day_forecast:
        day_forecast = day_forecasts[0]

    return {
        'date': target_date,
        'temp_min': min(temps),
        'temp_max': max(temps),
        'temp_day': day_forecast['main']['temp'],
        'feels_like': day_forecast['main']['feels_like'],
        'humidity': day_forecast['main']['humidity'],
        'pressure': day_forecast['main']['pressure'],
        'wind_speed': day_forecast['wind']['speed'],
        'description': day_forecast['weather'][0]['description'],
        'icon': day_forecast['weather'][0]['icon']
    }

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def get_user_region(context: CallbackContext, user_id: int):
    if 'region' not in context.bot_data:
        context.bot_data['region'] = {}
    if user_id not in context.bot_data['region']:
        context.bot_data['region'][user_id] = 'Moscow'
    return context.bot_data['region'][user_id]
def set_user_region(context: CallbackContext, user_id: int, region: str):
    if 'region' not in context.bot_data:
        context.bot_data['region'] = {}
    context.bot_data['region'][user_id] = region

    # Обновляем регион во всех уведомлениях пользователя
    if 'notifications' in context.bot_data and user_id in context.bot_data['notifications']:
        notifications = context.bot_data['notifications'][user_id]
        for notification in notifications:
            notification['region'] = region
        context.bot_data['notifications'][user_id] = notifications

        logger.info(f"Регион обновлен во всех {len(notifications)} уведомлениях пользователя {user_id}")

    return True

def get_user_timezone(context: CallbackContext, user_id: int):
    if 'timezone' not in context.bot_data:
        context.bot_data['timezone'] = {}
    if user_id not in context.bot_data['timezone']:
        context.bot_data['timezone'][user_id] = 'Europe/Moscow'
    return context.bot_data['timezone'][user_id]
def set_user_timezone(context: CallbackContext, user_id: int, timezone: str):
    if 'timezone' not in context.bot_data:
        context.bot_data['timezone'] = {}
    context.bot_data['timezone'][user_id] = timezone
    return True

def get_user_favorites(context: CallbackContext, user_id: int):
    if 'favorites' not in context.bot_data:
        context.bot_data['favorites'] = {}
    if user_id not in context.bot_data['favorites']:
        context.bot_data['favorites'][user_id] = []
    return context.bot_data['favorites'][user_id]
def add_user_favorite(context: CallbackContext, user_id: int, city: str):
    favorites = get_user_favorites(context, user_id)
    if city not in favorites:
        favorites.append(city)
        context.bot_data['favorites'][user_id] = favorites
        return True
    return False
def remove_user_favorite(context: CallbackContext, user_id: int, city: str):
    favorites = get_user_favorites(context, user_id)
    if city in favorites:
        favorites.remove(city)
        context.bot_data['favorites'][user_id] = favorites
        return True
    return False
def clear_user_favorites(context: CallbackContext, user_id: int):
    if 'favorites' not in context.bot_data:
        context.bot_data['favorites'] = {}
    context.bot_data['favorites'][user_id] = []
    return True

def get_timezone_by_city(city):
    try:
        city_lower = city.lower()

        known_cities = {
            'moscow': 'Europe/Moscow',
            'москва': 'Europe/Moscow',
            'москве': 'Europe/Moscow',
            'москву': 'Europe/Moscow',
            'санкт-петербург': 'Europe/Moscow',
            'saint petersburg': 'Europe/Moscow',
            'st petersburg': 'Europe/Moscow',
            'питер': 'Europe/Moscow',
            'омск': 'Asia/Omsk',
            'omsk': 'Asia/Omsk',
            'новосибирск': 'Asia/Novosibirsk',
            'novosibirsk': 'Asia/Novosibirsk',
            'екатеринбург': 'Asia/Yekaterinburg',
            'yekaterinburg': 'Asia/Yekaterinburg',
            'казань': 'Europe/Moscow',
            'kazan': 'Europe/Moscow',
            'нижний новгород': 'Europe/Moscow',
            'nizhny novgorod': 'Europe/Moscow',
            'самара': 'Europe/Samara',
            'samara': 'Europe/Samara',
            'красноярск': 'Asia/Krasnoyarsk',
            'krasnoyarsk': 'Asia/Krasnoyarsk',
            'иркутск': 'Asia/Irkutsk',
            'irkutsk': 'Asia/Irkutsk',
            'владивосток': 'Asia/Vladivostok',
            'vladivostok': 'Asia/Vladivostok',
            'якутск': 'Asia/Yakutsk',
            'yakutsk': 'Asia/Yakutsk',
            'london': 'Europe/London',
            'лондон': 'Europe/London',
            'new york': 'America/New_York',
            'нью-йорк': 'America/New_York',
            'нью йорк': 'America/New_York',
            'tokyo': 'Asia/Tokyo',
            'токио': 'Asia/Tokyo',
            'sydney': 'Australia/Sydney',
            'сидней': 'Australia/Sydney',
            'paris': 'Europe/Paris',
            'париж': 'Europe/Paris',
            'berlin': 'Europe/Berlin',
            'берлин': 'Europe/Berlin',
            'dubai': 'Asia/Dubai',
            'дубай': 'Asia/Dubai',
            'delhi': 'Asia/Kolkata',
            'дели': 'Asia/Kolkata',
        }

        if city_lower in known_cities:
            return known_cities[city_lower]

        for known_city, timezone in known_cities.items():
            if known_city in city_lower or city_lower in known_city:
                return timezone

        return 'Europe/Moscow'

    except Exception:
        return 'Europe/Moscow'
def get_utc_offset(timezone_str):
    try:
        tz = pytz.timezone(timezone_str)
        now = datetime.now(tz)
        offset = now.utcoffset()

        if offset:
            total_seconds = offset.total_seconds()
            hours = int(total_seconds // 3600)
            minutes = int((total_seconds % 3600) // 60)

            if hours >= 0:
                if minutes > 0:
                    return f"UTC+{hours}:{minutes:02d}"
                else:
                    return f"UTC+{hours}"
            else:
                if minutes > 0:
                    return f"UTC{hours}:{minutes:02d}"
                else:
                    return f"UTC{hours}"
        return "UTC"
    except:
        return "UTC"

def create_weather_keyboard(city_name: str, city_in_favorites: bool, lang: str = "rus", show_forecast: bool = True):
    """
    Создает клавиатуру для сообщения с погодой

    Args:
        city_name: Название города
        city_in_favorites: Находится ли город в избранном
        lang: Язык интерфейса ('rus' или 'eng')
        show_forecast: Показывать ли кнопку прогноза

    Returns:
        InlineKeyboardMarkup объект
    """
    keyboard = []

    # Первая строка: 2 кнопки рядом
    row = []

    # Кнопка "Сделать моим регионом"
    if lang == "rus":
        row.append(InlineKeyboardButton(
            "📍 Сделать моим регионом",
            callback_data=f"set_region_{city_name}"
        ))
    else:
        row.append(InlineKeyboardButton(
            "📍 Set as my region",
            callback_data=f"set_region_{city_name}"
        ))

    # Кнопка избранного
    if not city_in_favorites:
        if lang == "rus":
            row.append(InlineKeyboardButton(
                "⭐ Добавить в избранное",
                callback_data=f"add_favorite_{city_name}"
            ))
        else:
            row.append(InlineKeyboardButton(
                "⭐ Add to favorites",
                callback_data=f"add_favorite_{city_name}"
            ))
    else:
        if lang == "rus":
            row.append(InlineKeyboardButton(
                "❌ Удалить из избранного",
                callback_data=f"remove_favorite_{city_name}"
            ))
        else:
            row.append(InlineKeyboardButton(
                "❌ Remove from favorites",
                callback_data=f"remove_favorite_{city_name}"
            ))

    # Добавляем первую строку с двумя кнопками
    keyboard.append(row)

    # Вторая строка: Прогноз на неделю (если нужно показывать)
    if show_forecast:
        if lang == "rus":
            keyboard.append([InlineKeyboardButton(
                "📅 Прогноз на неделю",
                callback_data=f"week_forecast_{city_name}"
            )])
        else:
            keyboard.append([InlineKeyboardButton(
                "📅 Weekly forecast",
                callback_data=f"week_forecast_{city_name}"
            )])

    return InlineKeyboardMarkup(keyboard)

# ==================== ОСНОВНЫЕ ОБРАБОТЧИКИ ====================

async def start(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    lang = get_user_lang(context, user_id)

    # Сброс дневного использования при новом дне
    reset_daily_usage(context, user_id)

    # Восстановление уведомлений для всех пользователей
    notifications = get_user_notifications(context, user_id)
    for notification in notifications:
        create_notification_job(context, user_id, notification)

    if lang == "rus":
        keyboard = [
            ["⚙️ Настройки", "⭐ Избранное"],
            ["🌅 Погода в моем регионе", "🔔 Авто-рассылка"],
            ["📍 Погода в геолокации", "💎 Премиум"]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text(
            "🌤️ Привет, я показываю погоду в любой точке земного шара!\n\n"
            "🏙️ Введите город чтоб увидеть погоду в нём!\n\n"
            "📱 Введите /settings для помощи, или используйте кнопки ниже.\n"
            "🔔 Также в настройках можно настроить авторассылку погоды",
            reply_markup=reply_markup
        )
    else:
        keyboard = [
            ["⚙️ Settings", "⭐ Favorites"],
            ["🌅 Weather in my region", "🔔 Auto-notification"],
            ["📍 Weather in geolocation", "💎 Premium"]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text(
            "🌤️ Hello, I show weather anywhere in the world!\n\n"
            "🏙️ Enter a city to see the weather there!\n\n"
            "📱 Type /settings for help, or use the buttons below.\n"
            "🔔 You can also set up automatic weather notifications in the settings.",
            reply_markup=reply_markup
        )

async def send_daily_notification(context: CallbackContext):
    job = context.job
    notification_id = job.data.get('notification_id')
    user_id = job.data.get('user_id')  # Получаем user_id из data!

    if not notification_id or not user_id:
        logger.error(f"Нет данных в job: notification_id={notification_id}, user_id={user_id}")
        return

    # ПОЛУЧАЕМ ДАННЫЕ ПОЛЬЗОВАТЕЛЯ
    try:
        # Получаем язык пользователя
        lang = get_user_lang(context, user_id) or 'rus'

        # Получаем премиум статус и активные функции
        premium = get_user_premium(context, user_id)

        # Получаем только активные дополнительные функции
        active_features = {k: v for k, v in premium['features'].items()
                           if k in ['cloudiness', 'wind_direction', 'wind_gust', 'sunrise_sunset'] and v}

        logger.info(f"Уведомление для user {user_id}: active_features={active_features}")

    except Exception as e:
        logger.error(f"Ошибка получения данных пользователя {user_id}: {e}")
        lang = 'rus'
        active_features = None

    notifications = get_user_notifications(context, user_id)
    for notification in notifications:
        if notification['id'] == notification_id:
            region = notification['region']

            try:
                # ПЕРЕДАЕМ active_features в функцию get_weather
                weather_info, weather_text = get_weather(region, lang, active_features)
                if weather_info:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=f"🌅 Ежедневная рассылка погоды ({region}):\n\n{weather_text}"
                    )
                    logger.info(f"Отправлено уведомление пользователю {user_id} для региона {region}")
                else:
                    logger.error(f"Не удалось получить погоду для региона {region} пользователя {user_id}")
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления пользователю {user_id}: {e}")
            break

async def handle_reply(update: Update, context: CallbackContext):
    text = update.message.text
    user_id = update.effective_user.id
    lang = get_user_lang(context, user_id)
    premium = get_user_premium(context, user_id)

    # Проверка промокодов
    if text.lower() in ["weather", "advanturesmade"]:
        await handle_promo_code(update, context)
        return

    # Проверяем язык для правильного определения команд
    if lang == "rus":
        # Русские команды
        if text == "⚙️ Настройки":
            await settings(update, context)
        elif text == "⭐ Избранное":
            await favorites(update, context)
        elif text == "🌅 Погода в моем регионе":
            await get_weather_for_region(update, context)
        elif text == "🔔 Авто-рассылка":
            await notification_settings(update, context)
        elif text == "📍 Погода в геолокации":
            can_use, message = can_use_geolocation(context, user_id)
            if can_use:
                await get_user_location(update, context)
            else:
                keyboard = [[InlineKeyboardButton("💎 Подключить премиум", callback_data="premium_info")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(message, reply_markup=reply_markup)
        elif text == "💎 Премиум":
            await premium_menu(update, context)
        else:
            # Проверяем, находимся ли мы в режиме добавления уведомления вручную
            if context.user_data.get('action') == 'add_notification_time':
                # Обработка времени для уведомлений (формат ЧЧ:ММ)
                if ':' in text and len(text) <= 5:
                    try:
                        hour_str, minute_str = text.split(':')
                        hour = int(hour_str)
                        minute = int(minute_str)

                        if 0 <= hour <= 23 and 0 <= minute <= 59:
                            # Проверяем, есть ли временная зона в user_data
                            if 'temp_timezone' in context.user_data:
                                timezone_str = context.user_data['temp_timezone']
                                success, result = add_user_notification(context, user_id, hour, minute, timezone_str)

                                if success:
                                    region = get_user_region(context, user_id)
                                    utc_offset = get_utc_offset(timezone_str)

                                    # Очищаем временные данные
                                    if 'temp_timezone' in context.user_data:
                                        del context.user_data['temp_timezone']
                                    if 'adding_notification' in context.user_data:
                                        del context.user_data['adding_notification']
                                    if 'action' in context.user_data:
                                        del context.user_data['action']

                                    await update.message.reply_text(
                                        f"✅ Рассылка добавлена!\n\n"
                                        f"⏰ Время: {hour:02d}:{minute:02d}\n"
                                        f"📍 Регион: {region}\n"
                                        f"🕒 Часовой пояс: {utc_offset}\n\n"
                                        f"Вы будете получать ежедневную погоду в {hour:02d}:{minute:02d} по вашему времени."
                                    )

                                    # Показываем меню уведомлений
                                    await show_my_notifications(update, context)
                                    return
                                elif result == "limit_exceeded":
                                    await update.message.reply_text(
                                        "🚫 Вы можете добавить только 1 рассылку в бесплатной версии. "
                                        "Оформите премиум для неограниченного количества рассылок."
                                    )
                                    return
                                else:
                                    await update.message.reply_text("❌ Рассылка в это время уже существует")
                                    return
                            else:
                                await update.message.reply_text(
                                    "⚠️ Ошибка: часовой пояс не найден. Пожалуйста, начните сначала."
                                )
                                return
                        else:
                            await update.message.reply_text(
                                "⚠️ Неверный формат времени. Используйте ЧЧ:ММ (0-23 часов, 0-59 минут).")
                            return
                    except ValueError:
                        await update.message.reply_text(
                            "⚠️ Неверный формат. Используйте ЧЧ:ММ, например: 08:30 или 14:15")
                        return
                else:
                    await update.message.reply_text("⚠️ Неверный формат. Используйте ЧЧ:ММ, например: 08:30 или 14:15")
                    return

            # Обработка изменения времени существующего уведомления
            if ':' in text and len(text) <= 5 and context.user_data.get('action') == 'change_notification_time':
                try:
                    hour_str, minute_str = text.split(':')
                    hour = int(hour_str)
                    minute = int(minute_str)

                    if 0 <= hour <= 23 and 0 <= minute <= 59:
                        notification_id = context.user_data.get('editing_notification_id')
                        if notification_id:
                            notifications = get_user_notifications(context, user_id)
                            for notification in notifications:
                                if notification['id'] == notification_id:
                                    # Удаляем старую задачу
                                    remove_notification_job(context, user_id, notification_id)
                                    # Обновляем время
                                    notification['hour'] = hour
                                    notification['minute'] = minute
                                    # Создаем новую задачу
                                    create_notification_job(context, user_id, notification)
                                    set_user_notifications(context, user_id, notifications)

                                    # Очищаем временные данные
                                    if 'editing_notification_id' in context.user_data:
                                        del context.user_data['editing_notification_id']
                                    if 'action' in context.user_data:
                                        del context.user_data['action']

                                    await update.message.reply_text(
                                        f"✅ Время уведомления изменено на {hour:02d}:{minute:02d}")

                                    await show_my_notifications(update, context)
                                    return
                            await update.message.reply_text("❌ Уведомление не найдено")
                        else:
                            await update.message.reply_text("❌ Ошибка: не найден ID уведомления")
                    else:
                        await update.message.reply_text("⚠️ Неверный формат времени.")
                    return
                except ValueError:
                    pass

            # Обработка времени для уведомлений (формат ЧЧ:ММ) - старый вариант
            if ':' in text and len(text) <= 5:
                try:
                    hour_str, minute_str = text.split(':')
                    hour = int(hour_str)
                    minute = int(minute_str)

                    if 0 <= hour <= 23 and 0 <= minute <= 59:
                        # Проверяем, есть ли временная зона в user_data (из шага 1 добавления уведомления)
                        if 'temp_timezone' in context.user_data:
                            timezone_str = context.user_data['temp_timezone']
                            success, result = add_user_notification(context, user_id, hour, minute, timezone_str)

                            if success:
                                region = get_user_region(context, user_id)
                                utc_offset = get_utc_offset(timezone_str)
                                await update.message.reply_text(
                                    f"✅ Рассылка добавлена.\n\n"
                                    f"⏰ Время: {hour:02d}:{minute:02d}\n"
                                    f"📍 Регион: {region}\n"
                                    f"🕒 Часовой пояс: {utc_offset}")

                                # Удаляем временные данные
                                if 'temp_timezone' in context.user_data:
                                    del context.user_data['temp_timezone']
                            elif result == "limit_exceeded":
                                await update.message.reply_text(
                                    "🚫 Вы можете добавить только 1 рассылку в бесплатной версии. "
                                    "Оформите премиум для неограниченного количества рассылок.")
                            else:
                                await update.message.reply_text("❌ Рассылка в это время уже существует")
                            return
                        else:
                            await update.message.reply_text(
                                "⚠️ Сначала выберите часовой пояс для рассылки через меню авто-рассылки.")
                            return
                    else:
                        await update.message.reply_text("⚠️ Неверный формат времени.")
                        return
                except ValueError:
                    pass

            # Получение погоды по городу (если текст не команда)
            # Получаем только активные дополнительные функции
            active_features = {k: v for k, v in premium['features'].items()
                               if k in ['cloudiness', 'wind_direction', 'wind_gust', 'sunrise_sunset'] and v}

            weather_info, weather_text = get_weather(text, lang, active_features)

            if weather_info:
                city = weather_info['city']
                favorites_list = get_user_favorites(context, user_id)
                city_in_favorites = city in favorites_list

                keyboard = create_weather_keyboard(city, city_in_favorites, lang, show_forecast=True)

                await update.message.reply_text(weather_text, reply_markup=keyboard)
            else:
                await update.message.reply_text(weather_text)
    else:
        # Английские команды
        if text == "⚙️ Settings":
            await settings(update, context)
        elif text == "⭐ Favorites":
            await favorites(update, context)
        elif text == "🌅 Weather in my region":
            await get_weather_for_region(update, context)
        elif text == "🔔 Auto-notification":
            await notification_settings(update, context)
        elif text == "📍 Weather in geolocation":
            can_use, message = can_use_geolocation(context, user_id)
            if can_use:
                await get_user_location(update, context)
            else:
                keyboard = [[InlineKeyboardButton("💎 Get Premium", callback_data="premium_info")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(message, reply_markup=reply_markup)
        elif text == "💎 Premium":
            await premium_menu(update, context)
        else:
            # Проверяем, находимся ли мы в режиме добавления уведомления вручную
            if context.user_data.get('action') == 'add_notification_time':
                # Обработка времени для уведомлений
                if ':' in text and len(text) <= 5:
                    try:
                        hour_str, minute_str = text.split(':')
                        hour = int(hour_str)
                        minute = int(minute_str)

                        if 0 <= hour <= 23 and 0 <= minute <= 59:
                            if 'temp_timezone' in context.user_data:
                                timezone_str = context.user_data['temp_timezone']
                                success, result = add_user_notification(context, user_id, hour, minute, timezone_str)

                                if success:
                                    region = get_user_region(context, user_id)
                                    utc_offset = get_utc_offset(timezone_str)

                                    # Очищаем временные данные
                                    if 'temp_timezone' in context.user_data:
                                        del context.user_data['temp_timezone']
                                    if 'adding_notification' in context.user_data:
                                        del context.user_data['adding_notification']
                                    if 'action' in context.user_data:
                                        del context.user_data['action']

                                    await update.message.reply_text(
                                        f"✅ Notification added!\n\n"
                                        f"⏰ Time: {hour:02d}:{minute:02d}\n"
                                        f"📍 Region: {region}\n"
                                        f"🕒 Timezone: {utc_offset}\n\n"
                                        f"You will receive daily weather at {hour:02d}:{minute:02d} your time."
                                    )

                                    # Показываем меню уведомлений
                                    await show_my_notifications(update, context)
                                    return
                                elif result == "limit_exceeded":
                                    await update.message.reply_text(
                                        "🚫 You can only add 1 notification in free version. "
                                        "Get premium for unlimited notifications.")
                                    return
                                else:
                                    await update.message.reply_text("❌ Notification at this time already exists")
                                    return
                            else:
                                await update.message.reply_text(
                                    "⚠️ Error: timezone not found. Please start over.")
                                return
                        else:
                            await update.message.reply_text(
                                "⚠️ Invalid time format. Use HH:MM (0-23 hours, 0-59 minutes).")
                            return
                    except ValueError:
                        await update.message.reply_text("⚠️ Invalid format. Use HH:MM, for example: 08:30 or 14:15")
                        return
                else:
                    await update.message.reply_text("⚠️ Invalid format. Use HH:MM, for example: 08:30 or 14:15")
                    return

            # Обработка изменения времени существующего уведомления
            if ':' in text and len(text) <= 5 and context.user_data.get('action') == 'change_notification_time':
                try:
                    hour_str, minute_str = text.split(':')
                    hour = int(hour_str)
                    minute = int(minute_str)

                    if 0 <= hour <= 23 and 0 <= minute <= 59:
                        notification_id = context.user_data.get('editing_notification_id')
                        if notification_id:
                            notifications = get_user_notifications(context, user_id)
                            for notification in notifications:
                                if notification['id'] == notification_id:
                                    # Удаляем старую задачу
                                    remove_notification_job(context, user_id, notification_id)
                                    # Обновляем время
                                    notification['hour'] = hour
                                    notification['minute'] = minute
                                    # Создаем новую задачу
                                    create_notification_job(context, user_id, notification)
                                    set_user_notifications(context, user_id, notifications)

                                    # Очищаем временные данные
                                    if 'editing_notification_id' in context.user_data:
                                        del context.user_data['editing_notification_id']
                                    if 'action' in context.user_data:
                                        del context.user_data['action']

                                    await update.message.reply_text(
                                        f"✅ Notification time changed to {hour:02d}:{minute:02d}")

                                    await show_my_notifications(update, context)
                                    return
                            await update.message.reply_text("❌ Notification not found")
                        else:
                            await update.message.reply_text("❌ Error: notification ID not found")
                    else:
                        await update.message.reply_text("⚠️ Invalid time format.")
                    return
                except ValueError:
                    pass

            # Обработка времени для уведомлений - старый вариант
            if ':' in text and len(text) <= 5:
                try:
                    hour_str, minute_str = text.split(':')
                    hour = int(hour_str)
                    minute = int(minute_str)

                    if 0 <= hour <= 23 and 0 <= minute <= 59:
                        if 'temp_timezone' in context.user_data:
                            timezone_str = context.user_data['temp_timezone']
                            success, result = add_user_notification(context, user_id, hour, minute, timezone_str)

                            if success:
                                region = get_user_region(context, user_id)
                                utc_offset = get_utc_offset(timezone_str)
                                await update.message.reply_text(
                                    f"✅ Notification added.\n\n"
                                    f"⏰ Time: {hour:02d}:{minute:02d}\n"
                                    f"📍 Region: {region}\n"
                                    f"🕒 Timezone: {utc_offset}")

                                if 'temp_timezone' in context.user_data:
                                    del context.user_data['temp_timezone']
                            elif result == "limit_exceeded":
                                await update.message.reply_text(
                                    "🚫 You can only add 1 notification in free version. "
                                    "Get premium for unlimited notifications.")
                            else:
                                await update.message.reply_text("❌ Notification at this time already exists")
                            return
                        else:
                            await update.message.reply_text(
                                "⚠️ First choose timezone for notification through auto-notification menu.")
                            return
                    else:
                        await update.message.reply_text("⚠️ Invalid time format.")
                        return
                except ValueError:
                    pass

            # Получение погоды по городу (если текст не команда)
            # Получаем только активные дополнительные функции
            active_features = {k: v for k, v in premium['features'].items()
                               if k in ['cloudiness', 'wind_direction', 'wind_gust', 'sunrise_sunset'] and v}

            weather_info, weather_text = get_weather(text, lang, active_features)

            if weather_info:
                city = weather_info['city']
                favorites_list = get_user_favorites(context, user_id)
                city_in_favorites = city in favorites_list

                keyboard = create_weather_keyboard(city, city_in_favorites, lang, show_forecast=True)

                await update.message.reply_text(weather_text, reply_markup=keyboard)
            else:
                await update.message.reply_text(weather_text)

# =================== ПРЕМИУМ СИСТЕМА ====================

async def premium_menu(update: Update, context: CallbackContext):
    query = update.callback_query if hasattr(update, 'callback_query') else None
    user_id = update.effective_user.id if update.message else query.from_user.id
    lang = get_user_lang(context, user_id)
    premium = get_user_premium(context, user_id)

    if premium['active']:
        # Меню управления премиумом для активных пользователей
        if lang == "rus":
            text = "💎 ПРЕМИУМ АКТИВЕН\n\n"
            if premium['until']:
                until_date = datetime.fromisoformat(premium['until'])
                text += f"✅ Активен до: {until_date.strftime('%d.%m.%Y')}\n\n"
            else:
                text += "✅ Активен навсегда\n\n"
            text += "Вы можете настроить дополнительные функции или отключить премиум:"

            keyboard = [
                [InlineKeyboardButton("🔧 Дополнительные функции", callback_data="premium_features")],
                [InlineKeyboardButton("🚫 Отключить премиум", callback_data="deactivate_premium_confirm")]
            ]
        else:
            text = "💎 PREMIUM ACTIVE\n\n"
            if premium['until']:
                until_date = datetime.fromisoformat(premium['until'])
                text += f"✅ Active until: {until_date.strftime('%d.%m.%Y')}\n\n"
            else:
                text += "✅ Active forever\n\n"
            text += "You can configure additional features or deactivate premium:"

            keyboard = [
                [InlineKeyboardButton("🔧 Additional features", callback_data="premium_features")],
                [InlineKeyboardButton("🚫 Deactivate premium", callback_data="deactivate_premium_confirm")]
            ]
    else:
        # Меню покупки премиума для неактивных пользователей
        if lang == "rus":
            text = "💎 ПРЕМИУМ ПОДПИСКА\n\n"
            text += "Получите полный доступ ко всем функциям бота!"

            keyboard = [
                [InlineKeyboardButton("💰 Подключить премиум", callback_data="buy_premium_menu")],
                [InlineKeyboardButton("📋 О премиуме", callback_data="about_premium")]
            ]
        else:
            text = "💎 PREMIUM SUBSCRIPTION\n\n"
            text += "Get full access to all bot features!"

            keyboard = [
                [InlineKeyboardButton("💰 Get Premium", callback_data="buy_premium_menu")],
                [InlineKeyboardButton("📋 About Premium", callback_data="about_premium")]
            ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.message:
        await update.message.reply_text(text, reply_markup=reply_markup)
    elif query:
        await query.edit_message_text(text, reply_markup=reply_markup)

async def about_premium(update: Update, context: CallbackContext):
    query = update.callback_query if hasattr(update, 'callback_query') else None
    user_id = update.effective_user.id if update.message else query.from_user.id
    lang = get_user_lang(context, user_id)

    if lang == "rus":
        text = "📋 ЧТО ДАЕТ ПРЕМИУМ:\n\n"
        text += "✅ Прогноз погоды на неделю (без ограничений)\n"
        text += "✅ Погода по геолокации (без лимитов)\n"
        text += "✅ Несколько рассылок одновременно\n"
        text += "✅ Дополнительные данные о погоде:\n"
        text += "   • ☁️ Облачность\n"
        text += "   • 💨 Направление ветра\n"
        text += "   • 💨 Порывы ветра\n"
        text += "   • 🌅 Время восхода/заката\n\n"
        text += "💰 Стоимость:\n"
        text += "• Месяц - 10 звёзд\n"
        text += "• Год - 30 звёзд\n"
        text += "• Навсегда - 50 звёзд"

        keyboard = [
            [InlineKeyboardButton("💰 Подключить премиум", callback_data="buy_premium_menu")],
            [InlineKeyboardButton("🔙 Назад", callback_data="premium_info")]
        ]
    else:
        text = "📋 WHAT PREMIUM GIVES:\n\n"
        text += "✅ Weekly weather forecast (no limits)\n"
        text += "✅ Weather by geolocation (no limits)\n"
        text += "✅ Multiple notifications simultaneously\n"
        text += "✅ Additional weather data:\n"
        text += "   • ☁️ Cloudiness\n"
        text += "   • 💨 Wind direction\n"
        text += "   • 💨 Wind gusts\n"
        text += "   • 🌅 Sunrise/sunset time\n\n"
        text += "💰 Price:\n"
        text += "• Month - 10 stars\n"
        text += "• Year - 30 stars\n"
        text += "• Forever - 50 stars"

        keyboard = [
            [InlineKeyboardButton("💰 Get Premium", callback_data="buy_premium_menu")],
            [InlineKeyboardButton("🔙 Back", callback_data="premium_info")]
        ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.message:
        await update.message.reply_text(text, reply_markup=reply_markup)
    elif query:
        await query.edit_message_text(text, reply_markup=reply_markup)
async def premium_features(update: Update, context: CallbackContext):
    """Настройки дополнительных функций премиума"""
    query = update.callback_query if hasattr(update, 'callback_query') else None
    user_id = update.effective_user.id if update.message else query.from_user.id
    lang = get_user_lang(context, user_id)
    premium = get_user_premium(context, user_id)

    if lang == "rus":
        text = "🔧 ДОПОЛНИТЕЛЬНЫЕ ФУНКЦИИ\n\n"
        text += "Включите/выключите дополнительные данные о погоде:\n\n"

        features_status = {
            'cloudiness': ('☁️ Облачность', 'cloudiness'),
            'wind_direction': ('💨 Направление ветра', 'wind_direction'),
            'wind_gust': ('💨 Порывы ветра', 'wind_gust'),
            'sunrise_sunset': ('🌅 Восход/Закат', 'sunrise_sunset')
        }

        keyboard = []
        for feature, (name, callback_data) in features_status.items():
            status = "✅" if premium['features'][feature] else "❌"
            keyboard.append([
                InlineKeyboardButton(
                    f"{status} {name}",
                    callback_data=f"toggle_{callback_data}"
                )
            ])

        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="premium_info")])
    else:
        text = "🔧 ADDITIONAL FEATURES\n\n"
        text += "Enable/disable additional weather data:\n\n"

        features_status = {
            'cloudiness': ('☁️ Cloudiness', 'cloudiness'),
            'wind_direction': ('💨 Wind direction', 'wind_direction'),
            'wind_gust': ('💨 Wind gusts', 'wind_gust'),
            'sunrise_sunset': ('🌅 Sunrise/Sunset', 'sunrise_sunset')
        }

        keyboard = []
        for feature, (name, callback_data) in features_status.items():
            status = "✅" if premium['features'][feature] else "❌"
            keyboard.append([
                InlineKeyboardButton(
                    f"{status} {name}",
                    callback_data=f"toggle_{callback_data}"
                )
            ])

        keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="premium_info")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.message:
        await update.message.reply_text(text, reply_markup=reply_markup)
    elif query:
        await query.edit_message_text(text, reply_markup=reply_markup)
async def free_trial_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    lang = get_user_lang(context, user_id)

    # Получаем текущий статус премиума
    premium = get_user_premium(context, user_id)

    # Проверяем, использовал ли уже пользователь пробный период
    if premium.get('trial_used_callback', False):
        if lang == "rus":
            await query.message.reply_text("❌ Вы уже использовали пробный период!")
        else:
            await query.message.reply_text("❌ You have already used the free trial!")
        return

    # Активируем премиум на 29 дней через стандартную функцию
    success = activate_premium(context, user_id, 29)

    if not success:
        if lang == "rus":
            await query.message.reply_text("❌ Ошибка активации пробного периода")
        else:
            await query.message.reply_text("❌ Error activating free trial")
        return

    # Отмечаем, что пробный период использован
    premium = get_user_premium(context, user_id)  # Получаем обновленные данные
    premium['trial_used_callback'] = True
    update_user_premium(context, user_id, premium)

    # Получаем обновленную дату окончания
    premium = get_user_premium(context, user_id)
    if premium['until']:
        until_date = datetime.fromisoformat(premium['until'])
        now = datetime.now()
        days_left = (until_date - now).days

        if lang == "rus":
            await query.message.reply_text(
                f"✅ Пробный период активирован!\n"
                f"+29 дней бесплатного премиума\n"
                f"⏳ Активен до: {until_date.strftime('%d.%m.%Y')} (осталось {days_left} дней)\n\n"
                f"💎 Теперь вам доступны все премиум функции!"
            )
        else:
            await query.message.reply_text(
                f"✅ Free trial activated!\n"
                f"+29 days of free premium\n"
                f"⏳ Active until: {until_date.strftime('%d.%m.%Y')} ({days_left} days left)\n\n"
                f"💎 Now you have access to all premium features!"
            )
    else:
        if lang == "rus":
            await query.message.reply_text("❌ Ошибка активации пробного периода")
        else:
            await query.message.reply_text("❌ Error activating free trial")
async def buy_premium_menu(update: Update, context: CallbackContext):
    query = update.callback_query if hasattr(update, 'callback_query') else None
    user_id = update.effective_user.id if update.message else query.from_user.id
    lang = get_user_lang(context, user_id)

    # Проверяем, использовал ли уже пробный период
    premium = get_user_premium(context, user_id)
    trial_used = premium.get('trial_used_callback', False)

    if lang == "rus":
        text = "💰 ВЫБЕРИТЕ ПАКЕТ ПРЕМИУМ:\n\n"
        text += "1. 📅 Месяц - 10 звёзд\n"
        text += "2. 📆 Год - 30 звёзд\n"
        text += "3. ⭐ Навсегда - 50 звёзд\n\n"
        text += "💳 Оплата через Telegram Payments\n"

        keyboard = [
            [InlineKeyboardButton("📅 Месяц - 10 звёзд", callback_data="buy_month"),
             InlineKeyboardButton("📆 Год - 30 звёзд", callback_data="buy_year")],
            [InlineKeyboardButton("⭐ Навсегда - 50 звёзд", callback_data="buy_forever")],
            [InlineKeyboardButton("🎁 Активировать промокод", callback_data="activate_promo")],
            [InlineKeyboardButton("🔙 Назад", callback_data="premium_info")]
        ]

        # Добавляем кнопку пробного периода только если он не использован
        if not trial_used:
            keyboard.insert(0, [InlineKeyboardButton("🆓 Попробовать месяц бесплатно", callback_data="free_trial")])
    else:
        text = "💰 CHOOSE PREMIUM PACKAGE:\n\n"
        text += "1. 📅 Month - 10 stars\n"
        text += "2. 📆 Year - 30 stars\n"
        text += "3. ⭐ Forever - 50 stars\n\n"
        text += "💳 Payment via Telegram Payments\n"

        keyboard = [
            [InlineKeyboardButton("📅 Month - 10 stars", callback_data="buy_month"),
             InlineKeyboardButton("📆 Year - 30 stars", callback_data="buy_year")],
            [InlineKeyboardButton("⭐ Forever - 50 stars", callback_data="buy_forever")],
            [InlineKeyboardButton("🎁 Activate promo code", callback_data="activate_promo")],
            [InlineKeyboardButton("🔙 Back", callback_data="premium_info")]
        ]

        if not trial_used:
            keyboard.insert(0, [InlineKeyboardButton("🆓 Try free month", callback_data="free_trial")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.message:
        await update.message.reply_text(text, reply_markup=reply_markup)
    elif query:
        await query.edit_message_text(text, reply_markup=reply_markup)
async def send_invoice(update: Update, context: CallbackContext, package_type: str):
    query = update.callback_query
    user_id = query.from_user.id
    lang = get_user_lang(context, user_id)

    package = PREMIUM_PACKAGES[package_type]

    if lang == "rus":
        title = "Покупка премиум-подписки"
        description = package['description']
        payload = f"premium_{package_type}_{user_id}"
        currency = "XTR"
    else:
        title = "Premium subscription purchase"
        description = package['description']
        payload = f"premium_{package_type}_{user_id}"
        currency = "XTR"

    prices = [LabeledPrice(package['description'], package['stars'])]

    await context.bot.send_invoice(
        chat_id=query.message.chat_id,
        title=title,
        description=description,
        payload=payload,
        provider_token=PROVIDER_TOKEN,
        currency=currency,
        prices=prices,
        start_parameter="premium_purchase"
    )

async def pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    if query.invoice_payload.startswith("premium_"):
        await query.answer(ok=True)
    else:
        await query.answer(ok=False, error_message="Ошибка платежа")
async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    payment = update.message.successful_payment
    parts = payment.invoice_payload.split("_")

    if len(parts) >= 3:
        package_type = parts[1]
        user_id = int(parts[2])
        package = PREMIUM_PACKAGES.get(package_type)

        if package and user_id == update.message.from_user.id:
            # УДАЛЕН ПАРАМЕТР offer_type
            activate_premium(context, user_id, package['days'])
            lang = get_user_lang(context, user_id)

            if lang == "rus":
                await update.message.reply_text(
                    f"✅ Спасибо за покупку!\n"
                    f"{package['description']}\n\n"
                    f"💎 Теперь вам доступны все премиум функции!"
                )
            else:
                await update.message.reply_text(
                    f"✅ Thank you for your purchase!\n"
                    f"{package['description']}\n\n"
                    f"💎 Now you have access to all premium features!"
                )

# ==================== ИЗБРАННОЕ ====================

async def favorites(update: Update, context: CallbackContext):
    query = update.callback_query if hasattr(update, 'callback_query') else None
    user_id = update.effective_user.id if update.message else query.from_user.id
    lang = get_user_lang(context, user_id)
    favorites_list = get_user_favorites(context, user_id)

    if not favorites_list:
        if lang == "rus":
            text = "⭐ Ваш список избранных городов пуст."
        else:
            text = "⭐ Your favorites list is empty."

        await (update.message if update.message else query.message).reply_text(text)
        return

    if lang == "rus":
        text = "⭐ Ваши избранные города:"
    else:
        text = "⭐ Your favorite cities:"

    keyboard = []

    # Строго по одному городу в строке (город + крестик)
    for city in favorites_list:
        weather_info, _ = get_weather(city, lang)
        if weather_info:
            temp = weather_info['temp']
            if lang == "rus":
                city_text = f"🏙️ {city} ({temp}°C)"
            else:
                city_text = f"🏙️ {city} ({temp}°C)"

            # Город и крестик в одной строке
            keyboard.append([
                InlineKeyboardButton(city_text, callback_data=f"weather_{city}"),
                InlineKeyboardButton("❌", callback_data=f"remove_favorite_{city}")
            ])

    # Добавляем кнопку очистки всего списка
    if favorites_list:
        if lang == "rus":
            keyboard.append([InlineKeyboardButton("🗑️ Очистить весь список", callback_data="clear_all_favorites")])
        else:
            keyboard.append([InlineKeyboardButton("🗑️ Clear all favorites", callback_data="clear_all_favorites")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.message:
        await update.message.reply_text(text, reply_markup=reply_markup)
    elif query:
        await query.edit_message_text(text, reply_markup=reply_markup)

# ==================== РАССЫЛКИ ====================

async def show_my_notifications(update: Update, context: CallbackContext):
    query = update.callback_query if hasattr(update, 'callback_query') else None
    user_id = update.effective_user.id if update.message else query.from_user.id
    lang = get_user_lang(context, user_id)
    notifications = get_user_notifications(context, user_id)

    if not notifications:
        if lang == "rus":
            text = "⏰ У вас нет настроенных рассылок."
            add_text = "➕ Добавить рассылку"
        else:
            text = "⏰ You have no notifications set up."
            add_text = "➕ Add notification"

        keyboard = [
            [InlineKeyboardButton(add_text, callback_data="add_notification_step1")]
        ]
    else:
        # Сортировка по времени
        sorted_notifications = sorted(notifications, key=lambda x: (x['hour'], x['minute']))

        if lang == "rus":
            text = "⏰ Ваши рассылки:"
        else:
            text = "⏰ Your notifications:"

        keyboard = []

        for notification in sorted_notifications:
            utc_offset = get_utc_offset(notification['timezone'])
            time_str = f"{notification['hour']:02d}:{notification['minute']:02d}"
            region = notification['region']

            # Обрезаем слишком длинные названия городов
            if len(region) > 10:
                region_display = region[:10] + "..."
            else:
                region_display = region

            if lang == "rus":
                button_text = f"⏰ {time_str} 📍{region_display}"
            else:
                button_text = f"⏰ {time_str} 📍{region_display}"

            # Изменяем callback_data для открытия меню редактирования
            keyboard.append([
                InlineKeyboardButton(button_text, callback_data=f"edit_notification_{notification['id']}"),
                InlineKeyboardButton("❌", callback_data=f"disable_notification_{notification['id']}")
            ])

        if lang == "rus":
            keyboard.append([InlineKeyboardButton("➕ Добавить рассылку", callback_data="add_notification_step1")])
            keyboard.append([InlineKeyboardButton("🔕 Отключить все", callback_data="disable_all_notifications")])
        else:
            keyboard.append([InlineKeyboardButton("➕ Add notification", callback_data="add_notification_step1")])
            keyboard.append([InlineKeyboardButton("🔕 Disable all", callback_data="disable_all_notifications")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.message:
        await update.message.reply_text(text, reply_markup=reply_markup)
    elif query:
        await query.edit_message_text(text, reply_markup=reply_markup)

async def edit_notification(update: Update, context: CallbackContext, notification_id: str):
    query = update.callback_query if hasattr(update, 'callback_query') else None
    user_id = update.effective_user.id if update.message else query.from_user.id
    lang = get_user_lang(context, user_id)

    notifications = get_user_notifications(context, user_id)
    notification = None

    for n in notifications:
        if n['id'] == notification_id:
            notification = n
            break

    if not notification:
        if lang == "rus":
            await query.answer("❌ Рассылка не найдена")
        else:
            await query.answer("❌ Notification not found")
        return

    time_str = f"{notification['hour']:02d}:{notification['minute']:02d}"
    utc_offset = get_utc_offset(notification['timezone'])

    if lang == "rus":
        text = f"✏️ Редактирование рассылки:\n\n"
        text += f"⏰ Время: {time_str}\n"
        text += f"📍 Регион: {notification['region']}\n"
        text += f"🕒 Часовой пояс: {utc_offset}\n\n"
        text += "Выберите действие:"

        keyboard = [
            [InlineKeyboardButton("🕐 Изменить время", callback_data=f"change_notif_time_{notification_id}")],
            [InlineKeyboardButton("🌍 Изменить часовой пояс", callback_data=f"change_notif_tz_{notification_id}")],
            [InlineKeyboardButton("🗑️ Удалить", callback_data=f"disable_notification_{notification_id}")],
            [InlineKeyboardButton("🔙 Назад", callback_data="my_notifications")]
        ]
    else:
        text = f"✏️ Edit notification:\n\n"
        text += f"⏰ Time: {time_str}\n"
        text += f"📍 Region: {notification['region']}\n"
        text += f"🕒 Timezone: {utc_offset}\n\n"
        text += "Choose action:"

        keyboard = [
            [InlineKeyboardButton("🕐 Change time", callback_data=f"change_notif_time_{notification_id}")],
            [InlineKeyboardButton("🌍 Change timezone", callback_data=f"change_notif_tz_{notification_id}")],
            [InlineKeyboardButton("🗑️ Delete", callback_data=f"disable_notification_{notification_id}")],
            [InlineKeyboardButton("🔙 Back", callback_data="my_notifications")]
        ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    if query:
        await query.edit_message_text(text, reply_markup=reply_markup)

async def change_notification_time(update: Update, context: CallbackContext, notification_id: str):
    query = update.callback_query if hasattr(update, 'callback_query') else None
    user_id = update.effective_user.id if update.message else query.from_user.id
    lang = get_user_lang(context, user_id)

    # Сохраняем notification_id в user_data для дальнейшей обработки
    context.user_data['editing_notification_id'] = notification_id
    context.user_data['action'] = 'change_notification_time'

    notifications = get_user_notifications(context, user_id)
    notification = None

    for n in notifications:
        if n['id'] == notification_id:
            notification = n
            break

    if not notification:
        if lang == "rus":
            await query.answer("❌ Рассылка не найдена")
        else:
            await query.answer("❌ Notification not found")
        return

    if lang == "rus":
        text = f"🕐 Изменение времени рассылки:\n\n"
        text += f"Текущее время: {notification['hour']:02d}:{notification['minute']:02d}\n\n"
        text += "Выберите новое время:"

        keyboard = [
            [InlineKeyboardButton("🕘 09:00", callback_data=f"new_time_{notification_id}_9_0"),
             InlineKeyboardButton("🕛 12:00", callback_data=f"new_time_{notification_id}_12_0")],
            [InlineKeyboardButton("🕕 18:00", callback_data=f"new_time_{notification_id}_18_0")],
            [InlineKeyboardButton("✏️ Настроить вручную", callback_data=f"new_time_manual_{notification_id}")],
            [InlineKeyboardButton("🔙 Назад", callback_data=f"edit_notification_{notification_id}")]
        ]
    else:
        text = f"🕐 Change notification time:\n\n"
        text += f"Current time: {notification['hour']:02d}:{notification['minute']:02d}\n\n"
        text += "Choose new time:"

        keyboard = [
            [InlineKeyboardButton("🕘 09:00", callback_data=f"new_time_{notification_id}_9_0"),
             InlineKeyboardButton("🕛 12:00", callback_data=f"new_time_{notification_id}_12_0")],
            [InlineKeyboardButton("🕕 18:00", callback_data=f"new_time_{notification_id}_18_0")],
            [InlineKeyboardButton("✏️ Set manually", callback_data=f"new_time_manual_{notification_id}")],
            [InlineKeyboardButton("🔙 Back", callback_data=f"edit_notification_{notification_id}")]
        ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    if query:
        await query.edit_message_text(text, reply_markup=reply_markup)

async def add_notification_step1(update: Update, context: CallbackContext):
    """Первый шаг: выбор часового пояса"""
    query = update.callback_query if hasattr(update, 'callback_query') else None
    user_id = update.effective_user.id if update.message else query.from_user.id
    lang = get_user_lang(context, user_id)

    if lang == "rus":
        text = "🌍 Сначала выберите часовой пояс для рассылки:"

        keyboard = [
            [InlineKeyboardButton("📍 Определить автоматически", callback_data="auto_detect_timezone")],
            [InlineKeyboardButton("Москва 🇷🇺 (UTC+3)", callback_data="tz_add_mos")],
            [InlineKeyboardButton("Лондон 🇬🇧 (UTC+0)", callback_data="tz_add_lon")],
            [InlineKeyboardButton("Нью-Йорк 🇺🇸 (UTC-5)", callback_data="tz_add_ny")],
            [InlineKeyboardButton("Токио 🇯🇵 (UTC+9)", callback_data="tz_add_tok")],
            [InlineKeyboardButton("Сидней 🇦🇺 (UTC+10)", callback_data="tz_add_sid")],
            [InlineKeyboardButton("Дубай 🇦🇪 (UTC+4)", callback_data="tz_add_dub")],
            [InlineKeyboardButton("🔙 Назад", callback_data="my_notifications")]
        ]
    else:
        text = "🌍 First, choose timezone for notification:"

        keyboard = [
            [InlineKeyboardButton("📍 Detect automatically", callback_data="auto_detect_timezone")],
            [InlineKeyboardButton("Moscow 🇷🇺 (UTC+3)", callback_data="tz_add_mos")],
            [InlineKeyboardButton("London 🇬🇧 (UTC+0)", callback_data="tz_add_lon")],
            [InlineKeyboardButton("New York 🇺🇸 (UTC-5)", callback_data="tz_add_ny")],
            [InlineKeyboardButton("Tokyo 🇯🇵 (UTC+9)", callback_data="tz_add_tok")],
            [InlineKeyboardButton("Sydney 🇦🇺 (UTC+10)", callback_data="tz_add_sid")],
            [InlineKeyboardButton("Dubai 🇦🇪 (UTC+4)", callback_data="tz_add_dub")],
            [InlineKeyboardButton("🔙 Back", callback_data="my_notifications")]
        ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.message:
        await update.message.reply_text(text, reply_markup=reply_markup)
    elif query:
        await query.edit_message_text(text, reply_markup=reply_markup)
async def add_notification_step2(update: Update, context: CallbackContext, timezone_str: str):
    """Второй шаг: выбор времени"""
    query = update.callback_query if hasattr(update, 'callback_query') else None
    user_id = update.effective_user.id if update.message else query.from_user.id
    lang = get_user_lang(context, user_id)

    # Сохраняем временную зону в user_data
    context.user_data['temp_timezone'] = timezone_str
    utc_offset = get_utc_offset(timezone_str)

    if lang == "rus":
        text = f"🌍 Часовой пояс: {utc_offset}\n\n⏰ Теперь выберите время для рассылки:"

        keyboard = [
            [InlineKeyboardButton("🕘 09:00", callback_data="time_add_9_0"),
             InlineKeyboardButton("🕛 12:00", callback_data="time_add_12_0")],
            [InlineKeyboardButton("🕕 18:00", callback_data="time_add_18_0")],
            [InlineKeyboardButton("✏️ Настроить вручную", callback_data="time_add_manual")],
            [InlineKeyboardButton("🔙 К выбору часового пояса", callback_data="add_notification_step1")]
        ]
    else:
        text = f"🌍 Timezone: {utc_offset}\n\n⏰ Now choose time for notification:"

        keyboard = [
            [InlineKeyboardButton("🕘 09:00", callback_data="time_add_9_0"),
             InlineKeyboardButton("🕛 12:00", callback_data="time_add_12_0")],
            [InlineKeyboardButton("🕕 18:00", callback_data="time_add_18_0")],
            [InlineKeyboardButton("✏️ Set manually", callback_data="time_add_manual")],
            [InlineKeyboardButton("🔙 Back to timezone", callback_data="add_notification_step1")]
        ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.message:
        await update.message.reply_text(text, reply_markup=reply_markup)
    elif query:
        await query.edit_message_text(text, reply_markup=reply_markup)

async def auto_detect_timezone(update: Update, context: CallbackContext):
    """Автоматическое определение часового пояса"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    lang = get_user_lang(context, user_id)

    try:
        if lang == "rus":
            await query.edit_message_text("📍 Определяем ваш часовой пояс...")
        else:
            await query.edit_message_text("📍 Determining your timezone...")

        response = requests.get('http://ip-api.com/json/', timeout=5)
        data = response.json()

        if data['status'] == 'success':
            city = data.get('city', '')
            if city:
                timezone_str = get_timezone_by_city(city)
                if timezone_str:
                    set_user_timezone(context, user_id, timezone_str)
                    await add_notification_step2(update, context, timezone_str)
                    return

        # Если не удалось определить, используем Москву
        timezone_str = 'Europe/Moscow'
        set_user_timezone(context, user_id, timezone_str)
        await add_notification_step2(update, context, timezone_str)

    except Exception as e:
        # В случае ошибки используем Москву
        timezone_str = 'Europe/Moscow'
        set_user_timezone(context, user_id, timezone_str)
        await add_notification_step2(update, context, timezone_str)

def get_jobs_by_name(job_queue, name):
    """Получить все jobs по имени"""
    jobs = []
    for job in job_queue.jobs():
        if job.name == name:
            jobs.append(job)
    return jobs

# ==================== ПРОГНОЗ НА НЕДЕЛЮ ====================

async def week_forecast(update: Update, context: CallbackContext, city_name: str = None):
    query = update.callback_query if hasattr(update, 'callback_query') else None
    user_id = query.from_user.id if query else update.effective_user.id
    lang = get_user_lang(context, user_id)

    can_use, message = can_use_forecast(context, user_id)

    if not can_use:
        keyboard = [[InlineKeyboardButton(
            "💎 Подключить премиум" if lang == "rus" else "💎 Get Premium",
            callback_data="premium_info"
        )]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        if query:
            await query.answer(message, show_alert=True)
            await query.message.reply_text(message, reply_markup=reply_markup)
        else:
            await update.message.reply_text(message, reply_markup=reply_markup)
        return

    if not city_name:
        region = get_user_region(context, user_id)
        city_name = region

    if lang == "rus":
        text = f"📅 Загружаю прогноз погоды для {city_name} на неделю..."
    else:
        text = f"📅 Loading weather forecast for {city_name} for the week..."

    if query:
        await query.edit_message_text(text)
    else:
        await update.message.reply_text(text)

    city_name_api, forecast_list, error = get_forecast(city_name, lang)

    if error:
        if query:
            await query.message.reply_text(error)
        else:
            await update.message.reply_text(error)
        return

    if not forecast_list:
        error_msg = "❌ Не удалось получить прогноз." if lang == "rus" else "❌ Failed to get forecast."
        if query:
            await query.message.reply_text(error_msg)
        else:
            await update.message.reply_text(error_msg)
        return

    context.user_data['forecast_data'] = {
        'city': city_name_api,
        'forecast_list': forecast_list
    }

    if lang == "rus":
        text = f"🌤️ Прогноз погоды в {city_name_api}:\n\nВыберите день:"
        days_of_week = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    else:
        text = f"🌤️ Weather forecast in {city_name_api}:\n\nChoose a day:"
        days_of_week = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    now = datetime.now()
    keyboard = []

    # Только 6 дней (исключаем последний день)
    for i in range(6):
        forecast_date = now + timedelta(days=i)
        day_num = forecast_date.day
        month_num = forecast_date.month

        if lang == "rus":
            if i == 0:
                day_name = "Сегодня"
            elif i == 1:
                day_name = "Завтра"
            else:
                day_name = days_of_week[forecast_date.weekday()]
        else:
            if i == 0:
                day_name = "Today"
            elif i == 1:
                day_name = "Tomorrow"
            else:
                day_name = days_of_week[forecast_date.weekday()]

        button_text = f"{day_name} ({day_num}.{month_num})"

        if i % 2 == 0:
            keyboard.append([InlineKeyboardButton(
                button_text,
                callback_data=f"day_forecast_{city_name_api}_{i}"
            )])
        else:
            keyboard[-1].append(InlineKeyboardButton(
                button_text,
                callback_data=f"day_forecast_{city_name_api}_{i}"
            ))

    # Кнопка "Назад" возвращает на погоду в этом городе
    keyboard.append([InlineKeyboardButton(
        "🔙 Назад к погоде" if lang == "rus" else "🔙 Back to weather",
        callback_data=f"weather_{city_name_api}"
    )])

    reply_markup = InlineKeyboardMarkup(keyboard)

    if query:
        await query.message.reply_text(text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, reply_markup=reply_markup)

# ==================== ОСТАЛЬНЫЕ ФУНКЦИИ ====================

async def settings(update: Update, context: CallbackContext):
    user_id = update.effective_user.id if update.message else update.callback_query.from_user.id
    lang = get_user_lang(context, user_id)
    region = get_user_region(context, user_id)

    if lang == "rus":
        keyboard = [
            [InlineKeyboardButton(f"🌐 Язык", callback_data="Language")],
            [InlineKeyboardButton(f"📚 Инструкция", callback_data="Instruction")],
            [InlineKeyboardButton(f"📍 Изменить регион ({region})", callback_data="change_region")],
            [InlineKeyboardButton(f"🤝 Партнеры", callback_data="partners")]
        ]
        text = "⚙️ Настройки:"
    else:
        keyboard = [
            [InlineKeyboardButton(f"🌐 Language", callback_data="Language")],
            [InlineKeyboardButton(f"📚 Instructions", callback_data="Instruction")],
            [InlineKeyboardButton(f"📍 Change region ({region})", callback_data="change_region")],
            [InlineKeyboardButton(f"🤝 Partners", callback_data="partners")]
        ]
        text = "⚙️ Settings:"

    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.message:
        await update.message.reply_text(text, reply_markup=reply_markup)
    elif update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
async def notification_settings(update: Update, context: CallbackContext):
    user_id = update.effective_user.id if update.message else update.callback_query.from_user.id
    lang = get_user_lang(context, user_id)
    region = get_user_region(context, user_id)
    notifications = get_user_notifications(context, user_id)

    has_notifications = len(notifications) > 0

    if has_notifications:
        if lang == "rus":
            text = f"🔔 Настройки авто-рассылки:\n\n"
            text += f"✅ Рассылка включена\n"
            text += f"📍 Регион: {region}\n"
            text += f"📅 Активных рассылок: {len(notifications)}\n"
            text += f"\n🌤️ Вы будете получать ежедневную погоду по расписанию."

            keyboard = [
                [InlineKeyboardButton("⏰ Мои рассылки", callback_data="my_notifications"),
                 InlineKeyboardButton("➕ Добавить рассылку", callback_data="add_notification_step1")],
                [InlineKeyboardButton("🔕 Отключить все рассылки", callback_data="disable_all_notifications")]
            ]
        else:
            text = f"🔔 Auto-notification settings:\n\n"
            text += f"✅ Notifications enabled\n"
            text += f"📍 Region: {region}\n"
            text += f"📅 Active notifications: {len(notifications)}\n"
            text += f"\n🌤️ You will receive daily weather on schedule."

            keyboard = [
                [InlineKeyboardButton("⏰ My notifications", callback_data="my_notifications"),
                 InlineKeyboardButton("➕ Add notification", callback_data="add_notification_step1")],
                [InlineKeyboardButton("🔕 Disable all notifications", callback_data="disable_all_notifications")]
            ]
    else:
        if lang == "rus":
            text = f"🔔 Настройки авто-рассылки:\n\n"
            text += f"🔕 Рассылка отключена\n"
            text += f"📍 Регион: {region}\n"
            text += f"\n🌤️ Включите ежедневную рассылку погоды для вашего региона."

            keyboard = [
                [InlineKeyboardButton("➕ Добавить рассылку", callback_data="add_notification_step1")]
            ]
        else:
            text = f"🔔 Auto-notification settings:\n\n"
            text += f"🔕 Notifications disabled\n"
            text += f"📍 Region: {region}\n"
            text += f"\n🌤️ Enable daily weather notifications for your region."

            keyboard = [
                [InlineKeyboardButton("➕ Add notification", callback_data="add_notification_step1")]
            ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.message:
        await update.message.reply_text(text, reply_markup=reply_markup)
    elif update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup)

async def get_user_location(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    lang = get_user_lang(context, user_id)

    try:
        if lang == "rus":
            await update.message.reply_text("📍 Определяем ваше местоположение...")
        else:
            await update.message.reply_text("📍 Determining your location...")

        response = requests.get('http://ip-api.com/json/', timeout=5)
        data = response.json()

        if data['status'] == 'success':
            city = data.get('city', 'Unknown')

            if lang == "rus":
                result = f"📍 Ваше местоположение:\n\n🏙️ Город: {city}"
            else:
                result = f"📍 Your location:\n\n🏙️ City: {city}"

            premium = get_user_premium(context, user_id)
            # Получаем только активные дополнительные функции
            active_features = {k: v for k, v in premium['features'].items()
                               if k in ['cloudiness', 'wind_direction', 'wind_gust', 'sunrise_sunset'] and v}

            weather_info, weather_text = get_weather(city, lang, active_features)
            if weather_info:
                city_name = weather_info['city']
                favorites_list = get_user_favorites(context, user_id)
                city_in_favorites = city_name in favorites_list

                keyboard = create_weather_keyboard(city_name, city_in_favorites, lang, show_forecast=True)

                await update.message.reply_text(result)
                await update.message.reply_text(weather_text, reply_markup=keyboard)
            else:
                await update.message.reply_text(result)
                if lang == "rus":
                    await update.message.reply_text(f"🌤️ Не удалось получить погоду для города {city}")
                else:
                    await update.message.reply_text(f"🌤️ Failed to get weather for city {city}")
        else:
            if lang == "rus":
                await update.message.reply_text("❌ Не удалось определить местоположение")
            else:
                await update.message.reply_text("❌ Failed to determine location")

    except Exception as e:
        if lang == "rus":
            await update.message.reply_text(f"❌ Ошибка: {e}")
        else:
            await update.message.reply_text(f"❌ Error: {e}")

async def get_weather_for_region(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    lang = get_user_lang(context, user_id)
    region = get_user_region(context, user_id)

    # Проверяем, установлен ли регион (по умолчанию 'Moscow')
    if region == 'Moscow':
        if lang == "rus":
            text = "📍 Вы еще не выбрали свой регион!\n\n"
            text += "Введите название города в чат, и после получения погоды нажмите кнопку '📍 Сделать моим регионом'.\n\n"
            text += "Или определите регион автоматически:"

            keyboard = [
                [InlineKeyboardButton("📍 Определить мой регион по геолокации", callback_data="auto_detect_region")]
            ]
        else:
            text = "📍 You haven't selected your region yet!\n\n"
            text += "Enter city name in chat, and after getting weather click '📍 Set as my region' button.\n\n"
            text += "Or detect region automatically:"

            keyboard = [
                [InlineKeyboardButton("📍 Detect my region by geolocation", callback_data="auto_detect_region")]
            ]

        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(text, reply_markup=reply_markup)
        return

    premium = get_user_premium(context, user_id)

    # Получаем только активные дополнительные функции
    active_features = {k: v for k, v in premium['features'].items()
                       if k in ['cloudiness', 'wind_direction', 'wind_gust', 'sunrise_sunset'] and v}

    weather_info, weather_text = get_weather(region, lang, active_features)
    if weather_info:
        city = weather_info['city']
        favorites_list = get_user_favorites(context, user_id)
        city_in_favorites = city in favorites_list

        keyboard = create_weather_keyboard(city, city_in_favorites, lang, show_forecast=True)

        await update.message.reply_text(weather_text, reply_markup=keyboard)
    else:
        if lang == "rus":
            await update.message.reply_text(f"⚠️ Не удалось получить погоду для региона {region}")
        else:
            await update.message.reply_text(f"⚠️ Failed to get weather for region {region}")

# ==================== ОБРАБОТЧИК CALLBACK ====================

async def button_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id
    lang = get_user_lang(context, user_id)

    # Добавляем логирование для отладки
    logger.info(f"User {user_id} pressed button with data: {data}")

    if data == "Language":
        await language(update, context)

    elif data.startswith("lang_"):
        if data == "lang_ru":
            set_user_lang(context, user_id, "rus")
            keyboard = [
                ["⚙️ Настройки", "⭐ Избранное"],
                ["🌅 Погода в моем регионе", "🔔 Авто-рассылка"],
                ["📍 Погода в геолокации", "💎 Премиум"]
            ]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            await query.message.reply_text("✅ Язык изменен на Русский", reply_markup=reply_markup)
        elif data == "lang_en":
            set_user_lang(context, user_id, "eng")
            keyboard = [
                ["⚙️ Settings", "⭐ Favorites"],
                ["🌅 Weather in my region", "🔔 Auto-notification"],
                ["📍 Weather in geolocation", "💎 Premium"]
            ]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            await query.message.reply_text("✅ Language changed to English", reply_markup=reply_markup)

    elif data == "settings_back":
        await settings(update, context)

    elif data == "auto_detect_region":
        # Используем ту же логику, что и для геолокации
        if lang == "rus":
            await query.edit_message_text("📍 Определяем ваше местоположение...")
        else:
            await query.edit_message_text("📍 Determining your location...")

        try:
            response = requests.get('http://ip-api.com/json/', timeout=5)
            data_response = response.json()

            if data_response['status'] == 'success':
                city = data_response.get('city', 'Unknown')
                if city:
                    # Устанавливаем регион
                    set_user_region(context, user_id, city)
                    if lang == "rus":
                        await query.edit_message_text(f"✅ Ваш регион установлен: {city}")
                        # Теперь показываем погоду для этого региона
                        premium = get_user_premium(context, user_id)
                        active_features = {k: v for k, v in premium['features'].items()
                                           if
                                           k in ['cloudiness', 'wind_direction', 'wind_gust', 'sunrise_sunset'] and v}
                        weather_info, weather_text = get_weather(city, lang, active_features)
                        if weather_info:
                            city_name = weather_info['city']
                            favorites_list = get_user_favorites(context, user_id)
                            city_in_favorites = city_name in favorites_list
                            keyboard = create_weather_keyboard(city_name, city_in_favorites, lang, show_forecast=True)
                            await query.message.reply_text(weather_text, reply_markup=keyboard)
                    else:
                        await query.edit_message_text(f"✅ Your region set to: {city}")
                else:
                    if lang == "rus":
                        await query.edit_message_text("❌ Не удалось определить ваш город")
                    else:
                        await query.edit_message_text("❌ Failed to determine your city")
            else:
                if lang == "rus":
                    await query.edit_message_text("❌ Не удалось определить местоположение")
                else:
                    await query.edit_message_text("❌ Failed to determine location")
        except Exception as e:
            if lang == "rus":
                await query.edit_message_text(f"❌ Ошибка: {e}")
            else:
                await query.edit_message_text(f"❌ Error: {e}")


    elif data.startswith("set_region_"):

        city = data.split("_", 2)[2]

        # Проверяем, есть ли у пользователя рассылки

        notifications = get_user_notifications(context, user_id)

        if notifications:

            if lang == "rus":

                # Создаем клавиатуру с вариантами

                keyboard = [

                    [InlineKeyboardButton("✅ Да, изменить регион во всех рассылках",

                                          callback_data=f"confirm_set_region_{city}")],

                    [InlineKeyboardButton("❌ Нет, только установить как основной",

                                          callback_data=f"set_default_region_{city}")],

                    [InlineKeyboardButton("🔙 Отмена", callback_data=f"weather_{city}")]

                ]

                await query.edit_message_text(

                    f"⚠️ У вас есть {len(notifications)} активных рассылок.\n\n"

                    f"Хотите изменить регион во всех рассылках на '{city}'?\n\n"

                    f"✅ 'Да' - изменит регион во всех рассылках\n"

                    f"❌ 'Нет' - установит только как основной регион для новых рассылок",

                    reply_markup=InlineKeyboardMarkup(keyboard)

                )

                return

            else:

                # Английская версия

                keyboard = [

                    [InlineKeyboardButton("✅ Yes, change in all notifications",

                                          callback_data=f"confirm_set_region_{city}")],

                    [InlineKeyboardButton("❌ No, set only as default",

                                          callback_data=f"set_default_region_{city}")],

                    [InlineKeyboardButton("🔙 Cancel", callback_data=f"weather_{city}")]

                ]

                await query.edit_message_text(

                    f"⚠️ You have {len(notifications)} active notifications.\n\n"

                    f"Do you want to change region in all notifications to '{city}'?\n\n"

                    f"✅ 'Yes' - change region in all notifications\n"

                    f"❌ 'No' - set only as default region for new notifications",

                    reply_markup=InlineKeyboardMarkup(keyboard)

                )

                return

        else:

            # Если нет рассылок, просто устанавливаем регион

            set_user_region(context, user_id, city)

            if lang == "rus":

                await query.answer(f"✅ {city} установлен как ваш регион")

                await query.message.reply_text(f"📍 Город {city} установлен как ваш регион")

            else:

                await query.answer(f"✅ {city} set as your region")

                await query.message.reply_text(f"📍 City {city} set as your region")
    elif data.startswith("add_favorite_"):
        try:
            city = data.split("_", 2)[2]
            logger.info(f"Добавление в избранное: {city}")

            if add_user_favorite(context, user_id, city):
                if lang == "rus":
                    await query.answer(f"✅ {city} добавлен в избранное")
                    await query.message.reply_text(f"⭐ Город '{city}' добавлен в избранное!")
                else:
                    await query.answer(f"✅ {city} added to favorites")
                    await query.message.reply_text(f"⭐ City '{city}' added to favorites!")
            else:
                if lang == "rus":
                    await query.answer(f"⚠️ {city} уже в избранном")
                else:
                    await query.answer(f"⚠️ {city} already in favorites")
        except Exception as e:
            logger.error(f"Ошибка при добавлении в избранное: {e}")
            if lang == "rus":
                await query.answer("❌ Ошибка при добавлении в избранное")
            else:
                await query.answer("❌ Error adding to favorites")


    elif data.startswith("remove_favorite_"):

        try:

            city = data.split("_", 2)[2]

            logger.info(f"Удаление из избранного: {city}")

            if remove_user_favorite(context, user_id, city):

                if lang == "rus":

                    await query.answer(f"✅ {city} удален из избранного")

                else:

                    await query.answer(f"✅ {city} removed from favorites")

                # ОБНОВЛЯЕМ список избранного после удаления

                await favorites(update, context)

            else:

                if lang == "rus":

                    await query.answer(f"⚠️ {city} не найден в избранном")

                else:

                    await query.answer(f"⚠️ {city} not found in favorites")

        except Exception as e:

            logger.error(f"Ошибка при удалении из избранного: {e}")

            if lang == "rus":

                await query.answer("❌ Ошибка при удалении из избранного")

            else:

                await query.answer("❌ Error removing from favorites")

    elif data.startswith("confirm_set_region_"):
        city = data.split("_", 3)[3]
        # Изменяем регион во всех рассылках
        set_user_region(context, user_id, city)

        if lang == "rus":
            await query.answer(f"✅ Регион изменен во всех рассылках на {city}")
            await query.edit_message_text(
                f"✅ Регион успешно изменен во всех рассылках на '{city}'"
            )
        else:
            await query.answer(f"✅ Region changed in all notifications to {city}")
            await query.edit_message_text(
                f"✅ Region successfully changed in all notifications to '{city}'"
            )

    elif data.startswith("set_default_region_"):
        city = data.split("_", 3)[3]
        # Устанавливаем только как регион по умолчанию, не трогая рассылки
        if 'region' not in context.bot_data:
            context.bot_data['region'] = {}
        context.bot_data['region'][user_id] = city

        if lang == "rus":
            await query.answer(f"✅ {city} установлен как основной регион")
            await query.edit_message_text(
                f"✅ '{city}' установлен как ваш основной регион.\n\n"
                f"⚠️ Существующие рассылки остались без изменений.\n"
                f"📝 Новые рассылки будут использовать этот регион."
            )
        else:
            await query.answer(f"✅ {city} set as default region")
            await query.edit_message_text(
                f"✅ '{city}' set as your default region.\n\n"
                f"⚠️ Existing notifications remain unchanged.\n"
                f"📝 New notifications will use this region."
            )

    elif data == "clear_all_favorites":
        if lang == "rus":
            keyboard = [
                [InlineKeyboardButton("✅ Да, очистить", callback_data="confirm_clear_favorites")],
                [InlineKeyboardButton("❌ Нет, отмена", callback_data="favorites")]
            ]
            text = "⚠️ Вы уверены, что хотите очистить весь список избранных городов?"
        else:
            keyboard = [
                [InlineKeyboardButton("✅ Yes, clear", callback_data="confirm_clear_favorites")],
                [InlineKeyboardButton("❌ No, cancel", callback_data="favorites")]
            ]
            text = "⚠️ Are you sure you want to clear all favorite cities?"

        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, reply_markup=reply_markup)

    elif data == "confirm_clear_favorites":
        clear_user_favorites(context, user_id)
        if lang == "rus":
            await query.answer("✅ Список очищен", show_alert=True)
            text = "🗑️ Весь список избранных городов очищен."
        else:
            await query.answer("✅ List cleared", show_alert=True)
            text = "🗑️ All favorite cities cleared."
        await query.edit_message_text(text)

    elif data.startswith("weather_"):
        city = data.split("_", 1)[1]
        premium = get_user_premium(context, user_id)
        # Получаем только активные дополнительные функции
        active_features = {k: v for k, v in premium['features'].items()
                           if k in ['cloudiness', 'wind_direction', 'wind_gust', 'sunrise_sunset'] and v}

        weather_info, weather_text = get_weather(city, lang, active_features)
        if weather_info:
            city_name = weather_info['city']
            favorites_list = get_user_favorites(context, user_id)
            city_in_favorites = city_name in favorites_list
            keyboard = create_weather_keyboard(city_name, city_in_favorites, lang, show_forecast=True)
            await query.edit_message_text(weather_text, reply_markup=keyboard)
        else:
            await query.edit_message_text(weather_text)

    elif data.startswith("week_forecast_"):
        city_name = data.split("_", 2)[2]
        await week_forecast(update, context, city_name)

    elif data == "premium_info":
        await premium_menu(update, context)

    elif data == "premium_features":
        await premium_features(update, context)

    elif data.startswith("toggle_"):
        feature = data.split("_", 1)[1]
        if toggle_premium_feature(context, user_id, feature):
            await query.answer("✅ Настройка изменена" if lang == "rus" else "✅ Setting changed")
            await premium_features(update, context)

    elif data == "free_trial":
        await free_trial_callback(update, context)

    elif data == "about_premium":
        await about_premium(update, context)

    elif data == "buy_premium_menu":
        await buy_premium_menu(update, context)

    elif data.startswith("buy_"):
        package_type = data.split("_")[1]
        await send_invoice(update, context, package_type)

    elif data == "deactivate_premium_confirm":
        if lang == "rus":
            text = "⚠️ Вы уверены, что хотите отключить премиум?\n\nВсе рассылки будут остановлены."
            keyboard = [
                [InlineKeyboardButton("✅ Да, отключить", callback_data="deactivate_premium")],
                [InlineKeyboardButton("❌ Нет, отмена", callback_data="premium_info")]
            ]
        else:
            text = "⚠️ Are you sure you want to deactivate premium?\n\nAll notifications will be stopped."
            keyboard = [
                [InlineKeyboardButton("✅ Yes, deactivate", callback_data="deactivate_premium")],
                [InlineKeyboardButton("❌ No, cancel", callback_data="premium_info")]
            ]

        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, reply_markup=reply_markup)

    elif data == "deactivate_premium":
        # Отключаем премиум
        deactivate_premium(context, user_id)

        if lang == "rus":
            # Показываем уведомление
            await query.answer("✅ Премиум отключен", show_alert=True)
            # Обновляем сообщение
            await query.edit_message_text(
                "🚫 Премиум подписка отключена. Все рассылки остановлены.\n\n"
                "Для повторной активации нажмите /premium",
                reply_markup=None  # Убираем клавиатуру
            )
        else:
            await query.answer("✅ Premium deactivated", show_alert=True)
            await query.edit_message_text(
                "🚫 Premium subscription deactivated. All notifications stopped.\n\n"
                "To reactivate press /premium",
                reply_markup=None
            )

    elif data.startswith("day_forecast_"):
        parts = data.split("_")
        city_name = parts[2]
        day_offset = int(parts[3])

        forecast_data = context.user_data.get('forecast_data')

        if not forecast_data or forecast_data['city'] != city_name:
            city_name_api, forecast_list, error = get_forecast(city_name, lang)
            if error:
                await query.message.reply_text(error)
                return
            forecast_data = {
                'city': city_name_api,
                'forecast_list': forecast_list
            }

        daily_forecast = get_daily_forecast(forecast_data['forecast_list'], day_offset)

        if not daily_forecast:
            error_msg = "❌ Не удалось получить прогноз на этот день." if lang == "rus" else "❌ Failed to get forecast for this day."
            await query.message.reply_text(error_msg)
            return

        now = datetime.now()
        target_date = now + timedelta(days=day_offset)

        if lang == "rus":
            days_of_week = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
            months = ["января", "февраля", "марта", "апреля", "мая", "июня",
                      "июля", "августа", "сентября", "октября", "ноября", "декабря"]

            if day_offset == 0:
                day_name = "сегодня"
            elif day_offset == 1:
                day_name = "завтра"
            else:
                day_name = f"{days_of_week[target_date.weekday()].lower()}"
        else:
            days_of_week = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
            months = ["January", "February", "March", "April", "May", "June",
                      "July", "August", "September", "October", "November", "December"]

            if day_offset == 0:
                day_name = "today"
            elif day_offset == 1:
                day_name = "tomorrow"
            else:
                day_name = f"{days_of_week[target_date.weekday()].lower()}"

        date_str = f"{target_date.day} {months[target_date.month - 1]}"

        pressure_mmhg = round(daily_forecast['pressure'] * 0.750062)

        if lang == "rus":
            forecast_text = (
                f"📅 Погода в {forecast_data['city']} на {day_name} ({date_str}):\n\n"
                f"📝 {daily_forecast['description'].capitalize()}\n"
                f"🌡️ Температура: {daily_forecast['temp_day']}°C\n"
                f"   (ощущается как {daily_forecast['feels_like']}°C)\n"
                f"📈 Диапазон: {daily_forecast['temp_min']}°C - {daily_forecast['temp_max']}°C\n"
                f"💧 Влажность: {daily_forecast['humidity']}%\n"
                f"📊 Давление: {pressure_mmhg} мм рт. ст.\n"
                f"💨 Ветер: {daily_forecast['wind_speed']} м/с"
            )
        else:
            forecast_text = (
                f"📅 Weather in {forecast_data['city']} on {day_name} ({date_str}):\n\n"
                f"📝 {daily_forecast['description'].capitalize()}\n"
                f"🌡️ Temperature: {daily_forecast['temp_day']}°C\n"
                f"   (feels like {daily_forecast['feels_like']}°C)\n"
                f"📈 Range: {daily_forecast['temp_min']}°C - {daily_forecast['temp_max']}°C\n"
                f"💧 Humidity: {daily_forecast['humidity']}%\n"
                f"📊 Pressure: {pressure_mmhg} mmHg\n"
                f"💨 Wind: {daily_forecast['wind_speed']} m/s"
            )

        await query.message.reply_text(forecast_text)

    elif data == "my_notifications":
        await show_my_notifications(update, context)

    elif data == "add_notification_step1":
        await add_notification_step1(update, context)

    elif data.startswith("tz_add_"):
        timezone_code = data.split("_", 2)[2]

        timezone_map = {
            'mos': 'Europe/Moscow',
            'lon': 'Europe/London',
            'ny': 'America/New_York',
            'tok': 'Asia/Tokyo',
            'sid': 'Australia/Sydney',
            'dub': 'Asia/Dubai'
        }

        timezone_str = timezone_map.get(timezone_code, 'Europe/Moscow')
        await add_notification_step2(update, context, timezone_str)

    elif data == "auto_detect_timezone":
        await auto_detect_timezone(update, context)

    elif data.startswith("time_add_"):
        if data == "time_add_manual":
            # Устанавливаем флаг для ручного ввода времени
            context.user_data['adding_notification'] = True
            context.user_data['action'] = 'add_notification_time'

            if lang == "rus":
                await query.message.reply_text(
                    "⏰ Введите время в формате ЧЧ:ММ (например, 08:30 или 14:15).\n\n"
                    "⚠️ Убедитесь, что время указано в вашем часовом поясе."
                )

                # Обновляем предыдущее сообщение
                await query.edit_message_text(
                    query.message.text + "\n\n⌛ Ожидаю ввода времени в формате ЧЧ:ММ..."
                )
            else:
                await query.message.reply_text(
                    "⏰ Enter time in format HH:MM (e.g., 08:30 or 14:15).\n\n"
                    "⚠️ Make sure the time is in your timezone."
                )

                await query.edit_message_text(
                    query.message.text + "\n\n⌛ Waiting for time input in HH:MM format..."
                )
            return

        parts = data.split("_")
        hour = int(parts[2])
        minute = int(parts[3])

        timezone_str = context.user_data.get('temp_timezone', get_user_timezone(context, user_id))

        success, result = add_user_notification(context, user_id, hour, minute, timezone_str)

        if success:
            region = get_user_region(context, user_id)
            utc_offset = get_utc_offset(timezone_str)

            if lang == "rus":
                await query.answer(f"✅ Рассылка добавлена на {hour:02d}:{minute:02d}")
                text = f"✅ Рассылка успешно добавлена!\n\n"
                text += f"⏰ Время: {hour:02d}:{minute:02d}\n"
                text += f"📍 Регион: {region}\n"
                text += f"🕒 Часовой пояс: {utc_offset}\n\n"
                text += f"Вы будете получать ежедневную погоду в {hour:02d}:{minute:02d} по вашему времени."
            else:
                await query.answer(f"✅ Notification added for {hour:02d}:{minute:02d}")
                text = f"✅ Notification successfully added!\n\n"
                text += f"⏰ Time: {hour:02d}:{minute:02d}\n"
                text += f"📍 Region: {region}\n"
                text += f"🕒 Timezone: {utc_offset}\n\n"
                text += f"You will receive daily weather at {hour:02d}:{minute:02d} your time."

            if 'temp_timezone' in context.user_data:
                del context.user_data['temp_timezone']

            keyboard = [
                [InlineKeyboardButton(
                    "⏰ Мои рассылки" if lang == "rus" else "⏰ My notifications",
                    callback_data="my_notifications"
                )],
                [InlineKeyboardButton(
                    "➕ Добавить еще" if lang == "rus" else "➕ Add another",
                    callback_data="add_notification_step1"
                )]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, reply_markup=reply_markup)
        else:
            if result == "limit_exceeded":
                if lang == "rus":
                    await query.answer("🚫 Лимит рассылок", show_alert=True)
                    keyboard = [[InlineKeyboardButton("💎 Подключить премиум", callback_data="premium_info")]]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    await query.message.reply_text(
                        "🚫 Вы можете добавить только 1 рассылку в бесплатной версии. "
                        "Оформите премиум для неограниченного количества рассылок.",
                        reply_markup=reply_markup
                    )
                else:
                    await query.answer("🚫 Notification limit", show_alert=True)
                    keyboard = [[InlineKeyboardButton("💎 Get Premium", callback_data="premium_info")]]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    await query.message.reply_text(
                        "🚫 You can only add 1 notification in free version. "
                        "Get premium for unlimited notifications.",
                        reply_markup=reply_markup
                    )
            else:
                if lang == "rus":
                    await query.answer("❌ Рассылка в это время уже существует")
                else:
                    await query.answer("❌ Notification at this time already exists")

    elif data.startswith("disable_notification_"):
        notification_id = data.split("_", 2)[2]
        if remove_user_notification(context, user_id, notification_id):
            await query.answer("✅ Рассылка отключена" if lang == "rus" else "✅ Notification disabled")
        else:
            await query.answer("❌ Ошибка" if lang == "rus" else "❌ Error")
        await show_my_notifications(update, context)

    elif data == "disable_all_notifications":
        disable_all_notifications(context, user_id)
        await query.answer("✅ Все рассылки отключены" if lang == "rus" else "✅ All notifications disabled")
        await notification_settings(update, context)

    elif data.startswith("edit_notification_"):
        notification_id = data.split("_", 2)[2]
        await edit_notification(update, context, notification_id)

    elif data.startswith("change_notif_time_"):
        notification_id = data.split("_", 3)[3]
        await change_notification_time(update, context, notification_id)

    elif data.startswith("change_notif_tz_"):
        notification_id = data.split("_", 3)[3]
        # Сохраняем notification_id для шага изменения часового пояса
        context.user_data['editing_notification_id'] = notification_id
        context.user_data['action'] = 'change_timezone'
        await add_notification_step1(update, context)

    elif data.startswith("new_time_"):
        parts = data.split("_")
        notification_id = parts[2]
        hour = int(parts[3])
        minute = int(parts[4])

        notifications = get_user_notifications(context, user_id)
        for notification in notifications:
            if notification['id'] == notification_id:
                # Удаляем старую задачу
                remove_notification_job(context, user_id, notification_id)
                # Обновляем время
                notification['hour'] = hour
                notification['minute'] = minute
                # Создаем новую задачу
                create_notification_job(context, user_id, notification)
                set_user_notifications(context, user_id, notifications)

                if lang == "rus":
                    await query.answer(f"✅ Время изменено на {hour:02d}:{minute:02d}", show_alert=True)
                else:
                    await query.answer(f"✅ Time changed to {hour:02d}:{minute:02d}", show_alert=True)

                await show_my_notifications(update, context)
                break

    elif data.startswith("new_time_manual_"):
        notification_id = data.split("_", 3)[3]

        # Сохраняем информацию для ручного ввода
        context.user_data['editing_notification_id'] = notification_id
        context.user_data['action'] = 'change_notification_time'

        if lang == "rus":
            await query.message.reply_text(
                f"⏰ Введите новое время в формате ЧЧ:ММ для уведомления:\n\n"
                f"Например: 08:30 или 14:15"
            )
            # Обновляем предыдущее сообщение
            await query.edit_message_text(
                query.message.text + "\n\n⌛ Ожидаю ввода нового времени..."
            )
        else:
            await query.message.reply_text(
                f"⏰ Enter new time in format HH:MM for notification:\n\n"
                f"For example: 08:30 or 14:15"
            )
            await query.edit_message_text(
                query.message.text + "\n\n⌛ Waiting for new time input..."
            )

    elif data == "activate_promo":
        if lang == "rus":
            await query.message.reply_text("🎁 Введите промокод:")
        else:
            await query.message.reply_text("🎁 Enter promo code:")

    elif data == "change_region":
        region = get_user_region(context, user_id)
        if lang == "rus":
            text = f"📍 Ваш текущий регион: {region}\n\n"
            text += "Чтобы изменить регион, введите название города в чат и нажмите кнопку '📍 Сделать моим регионом' под сообщением с погодой."

            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="settings_back")]]
        else:
            text = f"📍 Your current region: {region}\n\n"
            text += "To change region, enter city name in chat and press '📍 Set as my region' button under weather message."

            keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="settings_back")]]

        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, reply_markup=reply_markup)

    elif data == "Instruction":
        if lang == "rus":
            text = "📚 Инструкция по использованию бота:\n\n"
            text += "1️⃣ Введите название города для получения погоды\n"
            text += "2️⃣ Используйте кнопки для быстрого доступа\n"
            text += "3️⃣ Настройки: /settings\n"
            text += "4️⃣ Выбор языка: нажмите 'Язык' в настройках\n"
            text += "5️⃣ Премиум: расширенные функции за подписку"

            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="settings_back")]]
        else:
            text = "📚 Bot Instructions:\n\n"
            text += "1️⃣ Enter city name to get weather\n"
            text += "2️⃣ Use buttons for quick access\n"
            text += "3️⃣ Settings: /settings\n"
            text += "4️⃣ Language selection: click 'Language' in settings\n"
            text += "5️⃣ Premium: extended features with subscription"

            keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="settings_back")]]

        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, reply_markup=reply_markup)

    elif data == "partners":
        if lang == "rus":
            text = "🤝 Наши партнеры:\n\n"
            text += "🎁 Secret Santa Gift Joy - https://secret-santa-gift-joy.lovable.app/\n"
            text += "🎄 Отличный сервис для организации тайного Санты!"

            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="settings_back")]]
        else:
            text = "🤝 Our partners:\n\n"
            text += "🎁 Secret Santa Gift Joy - https://secret-santa-gift-joy.lovable.app/\n"
            text += "🎄 Great service for organizing Secret Santa!"

            keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="settings_back")]]

        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, reply_markup=reply_markup)

    else:
        # Если callback_data не распознан
        logger.warning(f"Unknown callback data: {data}")
        if lang == "rus":
            await query.answer("⚠️ Неизвестная команда")
        else:
            await query.answer("⚠️ Unknown command")

async def language(update: Update, context: CallbackContext):
    query = update.callback_query if hasattr(update, 'callback_query') else None
    user_id = update.effective_user.id if update.message else query.from_user.id
    lang = get_user_lang(context, user_id)

    if lang == "rus":
        keyboard = [
            [InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru")],
            [InlineKeyboardButton("🇺🇸 English", callback_data="lang_en")],
            [InlineKeyboardButton("🔙 Назад", callback_data="settings_back")]
        ]
        text = "🌐 Выберите язык:"
    else:
        keyboard = [
            [InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru")],
            [InlineKeyboardButton("🇺🇸 English", callback_data="lang_en")],
            [InlineKeyboardButton("🔙 Back", callback_data="settings_back")]
        ]
        text = "🌐 Choose language:"

    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.message:
        await update.message.reply_text(text, reply_markup=reply_markup)
    elif update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup)

async def handle_promo_code(update: Update, context: CallbackContext):
    promo_code = update.message.text.strip().lower()
    user_id = update.message.from_user.id
    lang = get_user_lang(context, user_id)

    if promo_code in PROMO_CODES:
        promo = PROMO_CODES[promo_code]

        if user_id in promo['used_by']:
            if lang == "rus":
                await update.message.reply_text("❌ Вы уже использовали этот промокод!")
            else:
                await update.message.reply_text("❌ You have already used this promo code!")
            return

        if len(promo['used_by']) >= promo['max_uses']:
            if lang == "rus":
                await update.message.reply_text("❌ Промокод закончился!")
            else:
                await update.message.reply_text("❌ Promo code has expired!")
            return

        activate_premium(context, user_id, promo['days'])
        promo['used_by'].add(user_id)

        if lang == "rus":
            if promo['days'] == 99999:
                await update.message.reply_text(
                    f"✅ Промокод активирован! Вечный премиум!\n\n"
                    f"💎 Теперь вам доступны все премиум функции!"
                )
            else:
                await update.message.reply_text(
                    f"✅ Промокод активирован! Премиум на {promo['days']} дней.\n\n"
                    f"💎 Теперь вам доступны все премиум функции!"
                )
        else:
            if promo['days'] == 99999:
                await update.message.reply_text(
                    f"✅ Promo code activated! Forever premium!\n\n"
                    f"💎 Now you have access to all premium features!"
                )
            else:
                await update.message.reply_text(
                    f"✅ Promo code activated! Premium for {promo['days']} days.\n\n"
                    f"💎 Now you have access to all premium features!"
                )
    else:
        if lang == "rus":
            await update.message.reply_text("❌ Неверный промокод")
        else:
            await update.message.reply_text("❌ Invalid promo code")

# ==================== ёОСНОВНАЯ ФУНКЦИЯ ====================

async def restore_notifications(application: Application):
    """Восстановление всех уведомлений при запуске бота"""
    try:
        context = application.bot_data
        if 'notifications' in context:
            for user_id, notifications in context['notifications'].items():
                for notification in notifications:
                    # Создаем job для каждого уведомления
                    job_queue = application.job_queue
                    if job_queue:
                        # Используем CallbackContext для создания job
                        callback_context = CallbackContext.from_update(application, None)
                        callback_context.application = application
                        create_notification_job(callback_context, user_id, notification)
                        logger.info(f"Восстановлено уведомление для пользователя {user_id}")
    except Exception as e:
        logger.error(f"Ошибка восстановления уведомлений: {e}")


def main():
    try:
        logger.info("Запуск бота погоды...")
        application = Application.builder().token(BOT_TOKEN).build()
        logger.info(f"Application создан, job_queue доступен: {application.job_queue is not None}")

        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("settings", settings))
        application.add_handler(CommandHandler("premium", premium_menu))
        application.add_handler(CallbackQueryHandler(button_callback))
        application.add_handler(PreCheckoutQueryHandler(pre_checkout))
        application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_reply))
        logger.info("Обработчики добавлены, запускаю polling...")
        application.run_polling()

    except Exception as e:
        logger.error(f"Критическая ошибка при запуске бота: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()

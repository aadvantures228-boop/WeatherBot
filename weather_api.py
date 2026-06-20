import requests
from datetime import datetime, timedelta
import config

def get_weather(city: str, lang: str = "ru") -> tuple:
    try:
        city_query = config.AMBIGUOUS_CITIES.get(city.lower(), city)
        url = 'https://api.openweathermap.org/data/2.5/weather'
        params = {'q': city_query, 'appid': config.WEATHER_TOKEN, 'units': 'metric', 'lang': 'ru' if lang == 'rus' else 'en'}
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
            pressure_display = f"{round(pressure_hpa * 0.750062)} мм рт. ст."
            text = (f"🌤️ Погода в {city_name}:\n🌡️ Температура: {temp}°C (ощущается как {feels_like}°C)\n"
                    f"📝 Описание: {desc}\n💧 Влажность: {humidity}%\n📊 Давление: {pressure_display}\n💨 Ветер: {wind_speed} м/с")
            extended_text = "\n\n📊 ДОПОЛНИТЕЛЬНЫЕ ДАННЫЕ:"
        else:
            pressure_display = f"{pressure_hpa} hPa"
            text = (f"🌤️ Weather in {city_name}:\n🌡️ Temperature: {temp}°C (feels like {feels_like}°C)\n"
                    f"📝 Description: {desc}\n💧 Humidity: {humidity}%\n📊 Pressure: {pressure_display}\n💨 Wind: {wind_speed} m/s")
            extended_text = "\n\n📊 EXTENDED DATA:"

        added = False
        clouds = data['clouds'].get('all', 'Н/Д' if lang == 'rus' else 'N/A')
        extended_text += f"\n☁️ {'Облачность' if lang=='rus' else 'Cloudiness'}: {clouds}%"
        added = True
        
        wind_deg = data['wind'].get('deg')
        if wind_deg:
            dirs_ru = ["⬆️ Северный", "↗️ Северо-восточный", "➡️ Восточный", "↘️ Юго-восточный", "⬇️ Южный", "↙️ Юго-западный", "⬅️ Западный", "↖️ Северо-западный"]
            dirs_en = ["⬆️ North", "↗️ Northeast", "➡️ East", "↘️ Southeast", "⬇️ South", "↙️ Southwest", "⬅️ West", "↖️ Northwest"]
            dirs = dirs_ru if lang == 'rus' else dirs_en
            extended_text += f"\n💨 {'Направление' if lang=='rus' else 'Direction'}: {dirs[round(wind_deg / 45) % 8]}"
            added = True
            
        wind_gust = data['wind'].get('gust')
        if wind_gust:
            extended_text += f"\n💨 {'Порывы' if lang=='rus' else 'Gust'}: {wind_gust} {'м/с' if lang=='rus' else 'm/s'}"
            added = True
            
        sunrise = datetime.fromtimestamp(data['sys']['sunrise']).strftime('%H:%M')
        sunset = datetime.fromtimestamp(data['sys']['sunset']).strftime('%H:%M')
        extended_text += f"\n🌅 {'Восход' if lang=='rus' else 'Sunrise'}: {sunrise}\n🌇 {'Закат' if lang=='rus' else 'Sunset'}: {sunset}"
        added = True
        
        if added: text += extended_text
        return {'city': city_name, 'temp': temp}, text
    except Exception as e:
        return None, f'❌ Ошибка: {e}' if lang == 'rus' else f'❌ Error: {e}'

def get_forecast(city: str, lang: str = "ru"):
    try:
        city_query = config.AMBIGUOUS_CITIES.get(city.lower(), city)
        url = 'https://api.openweathermap.org/data/2.5/forecast'
        # ИСПРАВЛЕНИЕ 1: Увеличиваем cnt до 48, чтобы хватило данных на 6 дней вперед
        params = {'q': city_query, 'appid': config.WEATHER_TOKEN, 'units': 'metric', 'lang': 'ru' if lang == 'rus' else 'en', 'cnt': 48}
        response = requests.get(url, params=params, timeout=10)
        if response.status_code != 200:
            return None, None, f"Ошибка: код {response.status_code}" if lang == 'rus' else f"Error: code {response.status_code}"
        data = response.json()
        return data['city']['name'], data['list'], None
    except Exception as e:
        return None, None, f'Ошибка: {e}' if lang == 'rus' else f'Error: {e}'

def get_daily_forecast(forecast_list, day_offset: int = 0):
    if not forecast_list: return None
    target_date = (datetime.now() + timedelta(days=day_offset)).date()
    day_forecasts = [f for f in forecast_list if datetime.fromtimestamp(f['dt']).date() == target_date]
    if not day_forecasts: return None
    
    temps = [f['main']['temp'] for f in day_forecasts]
    day_forecast = next((f for f in day_forecasts if 12 <= datetime.fromtimestamp(f['dt']).hour <= 15), day_forecasts[0])
    
    return {
        'date': target_date, 'temp_min': min(temps), 'temp_max': max(temps),
        'temp_day': day_forecast['main']['temp'], 'feels_like': day_forecast['main']['feels_like'],
        'humidity': day_forecast['main']['humidity'], 'pressure': day_forecast['main']['pressure'],
        'wind_speed': day_forecast['wind']['speed'], 'description': day_forecast['weather'][0]['description']
    }
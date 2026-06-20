from telegram import InlineKeyboardMarkup, InlineKeyboardButton

def create_weather_keyboard(city_name: str, city_in_favorites: bool, current_region: str, lang: str = "rus", from_favorites: bool = False):
    keyboard = []
    is_current_region = city_name.lower() == current_region.lower()
    
    if from_favorites:
        # Если пришли из избранного: показываем ТОЛЬКО прогноз и кнопку назад
        keyboard.append([
            InlineKeyboardButton(
                "📅 Прогноз на неделю" if lang == "rus" else "📅 Weekly forecast",
                callback_data=f"week_forecast_fav_{city_name}"
            )
        ])
        keyboard.append([
            InlineKeyboardButton(
                "🔙 Назад в избранное" if lang == "rus" else "🔙 Back to favorites",
                callback_data="favorites"
            )
        ])
    else:
        # Обычный поиск города
        row = []
        if not is_current_region:
            row.append(InlineKeyboardButton(
                "📍 Сделать моим регионом" if lang == "rus" else "📍 Set as my region",
                callback_data=f"set_region_{city_name}"
            ))
        
        if city_in_favorites:
            row.append(InlineKeyboardButton(
                "❌ Удалить из избранного" if lang == "rus" else "❌ Remove from favorites",
                callback_data=f"remove_favorite_{city_name}"
            ))
        else:
            row.append(InlineKeyboardButton(
                "⭐ Добавить в избранное" if lang == "rus" else "⭐ Add to favorites",
                callback_data=f"add_favorite_{city_name}"
            ))
        keyboard.append(row)
        
        keyboard.append([
            InlineKeyboardButton(
                "📅 Прогноз на неделю" if lang == "rus" else "📅 Weekly forecast",
                callback_data=f"week_forecast_{city_name}"
            )
        ])
        
    return InlineKeyboardMarkup(keyboard)
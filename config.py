import logging

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = "8507475399:AAFDXfVd9900GI1PDjlB8greQz5X4a-0RPE"
WEATHER_TOKEN = "e8677da6c554a5a738e4df8f0802c283"

# ИСПРАВЛЕНИЕ №4: Принудительное указание страны для неоднозначных городов
AMBIGUOUS_CITIES = {
    "истра": "Istra, RU",
    "истре": "Istra, RU",
    "истру": "Istra, RU",
    "истрой": "Istra, RU"
}
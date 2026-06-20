def get_user_lang(context, user_id: int):
    if 'lang' not in context.bot_data: context.bot_data['lang'] = {}
    if user_id not in context.bot_data['lang']: context.bot_data['lang'][user_id] = 'rus'
    return context.bot_data['lang'][user_id]

def set_user_lang(context, user_id: int, lang: str):
    if 'lang' not in context.bot_data: context.bot_data['lang'] = {}
    context.bot_data['lang'][user_id] = lang

def get_user_region(context, user_id: int):
    if 'region' not in context.bot_data: context.bot_data['region'] = {}
    if user_id not in context.bot_data['region']: context.bot_data['region'][user_id] = 'Moscow'
    return context.bot_data['region'][user_id]

def set_user_region(context, user_id: int, region: str):
    if 'region' not in context.bot_data: context.bot_data['region'] = {}
    context.bot_data['region'][user_id] = region

def get_user_favorites(context, user_id: int):
    if 'favorites' not in context.bot_data: context.bot_data['favorites'] = {}
    if user_id not in context.bot_data['favorites']: context.bot_data['favorites'][user_id] = []
    return context.bot_data['favorites'][user_id]

def add_user_favorite(context, user_id: int, city: str):
    favorites = get_user_favorites(context, user_id)
    if city not in favorites:
        favorites.append(city)
        context.bot_data['favorites'][user_id] = favorites
        return True
    return False

def remove_user_favorite(context, user_id: int, city: str):
    favorites = get_user_favorites(context, user_id)
    if city in favorites:
        favorites.remove(city)
        context.bot_data['favorites'][user_id] = favorites
        return True
    return False

def clear_user_favorites(context, user_id: int):
    if 'favorites' not in context.bot_data: context.bot_data['favorites'] = {}
    context.bot_data['favorites'][user_id] = []
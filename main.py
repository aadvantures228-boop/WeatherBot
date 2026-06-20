import logging
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
import config
from handlers import commands, messages, callbacks

logger = logging.getLogger(__name__)

def main():
    try:
        logger.info("Запуск бота погоды (Версия 1.0)...")
        application = Application.builder().token(config.BOT_TOKEN).build()
        
        application.add_handler(CommandHandler("start", commands.start))
        application.add_handler(CommandHandler("settings", commands.settings))
        application.add_handler(CallbackQueryHandler(callbacks.button_callback))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, messages.handle_reply))
        
        logger.info("Обработчики добавлены, запускаю polling...")
        application.run_polling(allowed_updates=["message", "callback_query"])
    except Exception as e:
        logger.error(f"Критическая ошибка при запуске бота: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()
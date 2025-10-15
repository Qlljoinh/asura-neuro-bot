import asyncio
import logging
import sys
import os
import io
from typing import List, Dict, Optional
import re
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from telegram.error import InvalidToken, NetworkError
from config import Config
from gigachat_api import GigaChatAPI
from deepseek_api import DeepSeekAPI
from models_manager import ModelsManager
from rate_limiter import RateLimiter, RateLimitExceeded
from dialog_manager import DialogManager
from utils import TelegramFormatter
from image_service import image_service

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('bot.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

class GigaChatBot:
    def __init__(self):
        try:
            Config.validate()
            Config.print_config_summary()
            
            # Инициализация API
            self.gigachat = GigaChatAPI(
                auth_key=Config.GIGACHAT_AUTH_KEY,
                scope=Config.GIGACHAT_SCOPE,
                ignore_ssl=Config.IGNORE_SSL_ERRORS
            )
            
            self.deepseek = DeepSeekAPI(
                api_key=Config.DEEPSEEK_API_KEY,
                base_url=Config.DEEPSEEK_BASE_URL
            )
            
            self.models_manager = ModelsManager(self.gigachat)
            self.rate_limiter = RateLimiter(Config.REDIS_URL)
            self.user_prompts = {}
            self.dialog_manager = DialogManager()
            
            self.app = Application.builder().token(Config.TELEGRAM_TOKEN).build()
            self._register_handlers()
            
            logger.info("✅ Bot initialized successfully with GigaChat + DeepSeek")
            
        except ValueError as e:
            logger.error(f"❌ Configuration error: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ Failed to initialize bot: {e}")
            raise
            
    
    async def model_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать выбор модели"""
        keyboard = [
            [InlineKeyboardButton("🤖 GigaChat", callback_data="model_gigachat")],
            [InlineKeyboardButton("🧠 DeepSeek", callback_data="model_deepseek")],
            [InlineKeyboardButton("🔄 Текущая модель", callback_data="model_current")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        current_model = self.dialog_manager.get_active_model(update.effective_user.id)
        
        await update.message.reply_text(
            f"🎛️ Выбор модели AI\n\n"
            f"Текущая модель: {current_model}\n\n"
            "GigaChat - официальная модель от Сбера\n"
            "DeepSeek - мощная альтернативная модель\n\n"
            "Выберите модель для общения:",
            reply_markup=reply_markup
        )


    async def model_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка выбора модели"""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        model_type = query.data.replace("model_", "")
        
        if model_type == "gigachat":
            success = self.dialog_manager.switch_model(user_id, "GigaChat")
            if success:
                await query.edit_message_text(
                    "✅ Переключено на GigaChat\n\n"
                    "Теперь я буду использовать модель GigaChat для ответов.\n"
                    "🎯 Надежная модель от Сбера"
                )
                
        elif model_type == "deepseek":
            success = self.dialog_manager.switch_model(user_id, "DeepSeek")
            if success:
                await query.edit_message_text(
                    "✅ Переключено на DeepSeek\n\n"
                    "Теперь я буду использовать модель DeepSeek для ответов.\n"
                    "⚠️ Внимание: Может быть недоступна из-за ограничений API\n"
                    "При ошибках автоматически переключится на GigaChat"
                )
        
    async def send_to_model(self, message: str, user_id: int, system_prompt: str, history: List[Dict]) -> tuple[str, str]:
        """Отправка сообщения в выбранную модель с автоматическим fallback"""
        current_model = self.dialog_manager.get_active_model(user_id)
        
        logger.info(f"Sending message to {current_model} for user {user_id}")
        
        # Если выбрана DeepSeek, пробуем отправить, но с fallback на GigaChat
        if current_model == "DeepSeek":
            try:
                response = await self.deepseek.send_message(
                    message=message,
                    model="deepseek-chat",
                    temperature=Config.DEFAULT_TEMPERATURE,
                    system_prompt=system_prompt,
                    conversation_history=history
                )
                model_used = "DeepSeek"
                logger.info(f"DeepSeek response received successfully")
                
            except Exception as e:
                logger.error(f"DeepSeek error: {e}")
                
                # Автоматически переключаем на GigaChat при ошибках DeepSeek
                self.dialog_manager.switch_model(user_id, "GigaChat")
                logger.warning(f"Auto-switched to GigaChat due to DeepSeek error")
                
                # Используем GigaChat как fallback
                response = await self.gigachat.send_message(
                    message=message,
                    model=Config.DEFAULT_MODEL,
                    temperature=Config.DEFAULT_TEMPERATURE,
                    system_prompt=system_prompt,
                    conversation_history=history
                )
                model_used = "GigaChat (авто-переключение)"
                
        else:
            # Используем GigaChat
            response = await self.gigachat.send_message(
                message=message,
                model=Config.DEFAULT_MODEL,
                temperature=Config.DEFAULT_TEMPERATURE,
                system_prompt=system_prompt,
                conversation_history=history
            )
            model_used = "GigaChat"
        
        return response, model_used
    def _register_handlers(self):
        """Register all command handlers"""
        handlers = [
            CommandHandler("start", self.start_command),
            CommandHandler("help", self.help_command),
            CommandHandler("model", self.model_command),
            CommandHandler("models", self.models_command),
            CommandHandler("modelinfo", self.model_info_command),
            CommandHandler("modelstats", self.model_stats_command),
            CommandHandler("refreshmodels", self.refresh_models_command),
            CommandHandler("prompt", self.prompt_command),
            CommandHandler("myprompt", self.myprompt_command),
            CommandHandler("prompts", self.prompts_list_command),
            CommandHandler("resetprompt", self.reset_prompt_command),
            CommandHandler("coding", lambda u, c: self.set_prompt_type(u, c, "coding")),
            CommandHandler("creative", lambda u, c: self.set_prompt_type(u, c, "creative")),
            CommandHandler("science", lambda u, c: self.set_prompt_type(u, c, "science")),
            CommandHandler("psychology", lambda u, c: self.set_prompt_type(u, c, "psychology")),
            CommandHandler("business", lambda u, c: self.set_prompt_type(u, c, "business")),
            CommandHandler("teacher", lambda u, c: self.set_prompt_type(u, c, "teacher")),
            CommandHandler("default", lambda u, c: self.set_prompt_type(u, c, "default")),
            CommandHandler("newdialog", self.new_dialog_command),
            CommandHandler("mydialogs", self.my_dialogs_command),
            CommandHandler("exportdialog", self.export_dialog_command),
            CommandHandler("cleardialog", self.clear_dialog_command),
            CommandHandler("draw", self.draw_command),
            CommandHandler("image", self.image_command),
            CommandHandler("deepseekstatus", self.deepseek_status_command),
            CallbackQueryHandler(self.model_callback, pattern="^model_"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message),
        ]
        
        for handler in handlers:
            self.app.add_handler(handler)
        
        self.app.add_error_handler(self.error_handler)
    
    def _is_draw_request(self, message_text: str) -> bool:
        """Определяет, является ли сообщение запросом на рисование"""
        draw_keywords = [
            'нарисуй', 'нарисуйте', 'рисунок', 'изображение',
            'draw', 'paint', 'image', 'picture',
            'создай картинку', 'сгенерируй изображение',
            'хочу картинку', 'сделай рисунок'
        ]
        
        message_lower = message_text.lower()
        return any(keyword in message_lower for keyword in draw_keywords)
    
    def _extract_draw_prompt(self, message_text: str) -> str:
        """Извлекает промпт для рисования из сообщения"""
        patterns = [
            r'нарисуй\s+(.+)',
            r'нарисуйте\s+(.+)', 
            r'рисунок\s+(.+)',
            r'изображение\s+(.+)',
            r'draw\s+(.+)',
            r'paint\s+(.+)',
            r'image\s+(.+)',
            r'picture\s+(.+)',
            r'создай картинку\s+(.+)',
            r'сгенерируй изображение\s+(.+)',
            r'хочу картинку\s+(.+)',
            r'сделай рисунок\s+(.+)'
        ]
        
        message_lower = message_text.lower()
        
        for pattern in patterns:
            match = re.search(pattern, message_lower)
            if match:
                return match.group(1).strip()
        
        return message_text.strip()
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        welcome_text = """
🤖 Добро пожаловать в AI Assistant Bot!

🎛️ Доступные модели:
• 🤖 GigaChat - официальная модель от Сбера
• 🧠 DeepSeek - мощная альтернативная модель

✨ Возможности:
💬 Общение с сохранением контекста
🎨 Генерация изображений по описанию
📝 Стили общения (программист, креатив и др.)
🔄 Смена моделей на лету

🚀 Команды:
/model - выбор модели
/help - помощь
/newdialog - новый диалог
/draw - нарисовать изображение

Начните общение или выберите модель! 😊
"""
        await update.message.reply_text(welcome_text)
        
        # Показываем кнопки выбора модели
        keyboard = [
            [InlineKeyboardButton("🤖 Начать с GigaChat", callback_data="model_gigachat")],
            [InlineKeyboardButton("🧠 Начать с DeepSeek", callback_data="model_deepseek")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "🎛️ Выберите модель для начала общения:",
            reply_markup=reply_markup
        )
    async def deepseek_status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Проверка статуса DeepSeek"""
        try:
            # Пробуем отправить тестовый запрос
            test_response = await self.deepseek.send_message(
                message="Hello",
                model="deepseek-chat",
                temperature=0.7,
                system_prompt="You are a helpful assistant",
                conversation_history=[]
            )
            
            status = "✅ Доступен"
            message = "DeepSeek работает нормально"
            
        except Exception as e:
            status = "❌ Недоступен" 
            message = f"Ошибка: {str(e)}"

        await update.message.reply_text(
            f"🧠 Статус DeepSeek:\n\n"
            f"{status}\n"
            f"{message}\n\n"
            f"Текущий API ключ: {Config.DEEPSEEK_API_KEY[:10]}...\n"
            f"При ошибках автоматически переключается на GigaChat"
        )
    async def image_status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Информация о статусе генерации изображений"""
        try:
            status = await self.image_generator.get_status()
            
            message = (
                "🖼️ Статус генерации изображений:\n\n"
                f"• Используется: {'✅ Основной API' if status['uses_same_api'] else '❌ Отдельный API'}\n"
                f"• Access token: {'✅ Динамический'}\n"
                f"• Действие токена: 30 минут\n"
                f"• Автообновление: {'✅ Включено'}\n\n"
                "🔧 Технические детали:\n"
                "• Токен получается через OAuth\n"
                "• Используется для всех запросов\n"
                "• Автоматически обновляется\n\n"
                "🎯 Команды:\n"
                "• /draw <описание> - генерация\n"
                "• /imagestatus - этот статус"
            )
            
            await update.message.reply_text(message)
            
        except Exception as e:
            logger.error(f"Error checking image status: {e}")
            await update.message.reply_text("❌ Ошибка при проверке статуса.")
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        help_text = """
    🤖 Помощь по использованию бота:

    💬 Общение с контекстом:
    • Просто напишите сообщение - бот запомнит историю
    • /newdialog - начать новый диалог
    • /mydialogs - список ваших диалогов  

    🎨 Генерация изображений:
    • /draw <описание> - нарисовать изображение
    • /imagestatus - проверить доступность
    • "нарисуй..." - текстовый запрос

    ⚠️ Генерация изображений может быть временно недоступна
    Используйте /imagestatus для проверки

    🎭 Стили общения:
    • /prompts - список стилей
    • /coding - режим программирования
    • /creative - креативный режим

    📊 Информация:
    • /models - список моделей
    • /modelstats - статистика моделей
    """
        await update.message.reply_text(help_text)
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        message_text = update.message.text
        
        if message_text.startswith('/'):
            return
        
        if self._is_draw_request(message_text):
            await self.handle_draw_request(update, message_text)
            return
        
        try:
            async with self.rate_limiter.limit_context(user_id):
                current_model = self.dialog_manager.get_active_model(user_id)
                self.dialog_manager.add_message(user_id, "user", message_text, current_model)
                
                history = self.dialog_manager.get_conversation_history_for_api(user_id, max_messages=5)
                history_for_api = history[:-1] if len(history) > 1 else []
                
                from prompts import SystemPrompts
                system_prompt = self.user_prompts.get(user_id, SystemPrompts.DEFAULT)
                
                await update.message.chat.send_action(action="typing")
                
                response, model_used = await self.send_to_model(
                    message_text, user_id, system_prompt, history_for_api
                )
                
                self.dialog_manager.add_message(user_id, "assistant", response, model_used)
                
                # Форматируем ответ для Telegram
                formatted_response = TelegramFormatter.format_to_telegram(response)
                
                # Добавляем информацию о модели
                model_info = f"\n\n🤖 Ответ от {model_used}"
                
                # Если было авто-переключение, добавляем предупреждение
                if "авто-переключение" in model_used:
                    warning = "\n⚠️ DeepSeek временно недоступен, использован GigaChat"
                    model_info = warning + model_info
                
                if len(formatted_response + model_info) <= 4096:
                    formatted_response += model_info
                
                await update.message.reply_text(
                    formatted_response,
                    parse_mode='HTML',
                    disable_web_page_preview=True
                )
                
        except RateLimitExceeded:
            await update.message.reply_text("⚠️ Слишком много запросов. Подождите немного.")
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            await update.message.reply_text("❌ Произошла ошибка. Попробуйте позже.")
    
    
# В методе generate_and_send_image добавьте:
    async def generate_and_send_image(self, update: Update, prompt: str):
        """Генерация и отправка изображения через внешние API"""
        user_id = update.effective_user.id
        
        if len(prompt) > 1000:
            await update.message.reply_text("❌ Слишком длинное описание. Максимум 1000 символов.")
            return
        
        try:
            async with self.rate_limiter.limit_context(user_id):
                await update.message.chat.send_action(action="upload_photo")
                
                # Генерируем изображение через внешние API
                image_data, error = await image_service.generate_image(prompt)
                
                if not image_data:
                    await self._handle_failed_image_generation(update, prompt, error)
                    return
                
                # Проверяем размер файла
                if len(image_data) > 10 * 1024 * 1024:  # 10MB limit
                    await update.message.reply_text("❌ Изображение слишком большое для отправки в Telegram.")
                    return
                
                # Отправляем изображение пользователю
                await update.message.reply_photo(
                    photo=image_data,
                    caption=f"🎨 Сгенерировано по запросу: \"{prompt}\""
                )
                logger.info(f"Image sent to user {user_id}")
                
        except RateLimitExceeded:
            await update.message.reply_text("⚠️ Слишком много запросов. Подождите перед следующей генерацией.")
        except Exception as e:
            logger.error(f"Error generating image: {e}")
            await self._handle_image_generation_error(update, prompt, str(e))

    def _is_valid_image(self, image_data: bytes) -> bool:
        """Проверяет, являются ли данные валидным изображением"""
        try:
            from PIL import Image
            import io
            
            # Пытаемся открыть изображение
            image = Image.open(io.BytesIO(image_data))
            image.verify()  # Проверяем целостность
            return True
        except Exception as e:
            logger.error(f"Invalid image data: {e}")
            return False
        
    async def _handle_telegram_image_error(self, update: Update, prompt: str):
        """Обработка специфичных ошибок изображения в Telegram"""
        response_text = (
            "❌ Не удалось отправить изображение\n\n"
            f"Запрос: \"{prompt}\"\n\n"
            "Возможные причины:\n"
            "• Некорректный формат изображения\n"
            "• Слишком большой размер файла\n"
            "• Временные проблемы с сервером\n\n"
            "Попробуйте:\n"
            "• Другой запрос\n"
            "• Более простое описание\n"
            "• Повторить позже"
        )
        
        await update.message.reply_text(response_text)
    async def _handle_unavailable_image_generation(self, update: Update, prompt: str):
        """Обработка когда генерация изображений недоступна"""
        alternatives = await self.image_generator.get_alternative_suggestions(prompt)
        
        response_text = (
            "❌ Генерация изображений временно недоступна\n\n"
            f"Ваш запрос: \"{prompt}\"\n\n"
            "🎯 Альтернативы:\n"
            f"• {alternatives['text_description']}\n\n"
            "⏰ Совет: {alternatives['wait_suggestion']}\n\n"
            "💡 Можно также:\n"
            "• Использовать текстовое описание\n"
            "• Попробовать другой запрос\n"
            "• Написать администратору"
        )
        
        await update.message.reply_text(response_text)

    async def _handle_failed_image_generation(self, update: Update, prompt: str, error: str = None):
        """Обработка когда генерация не удалась"""
        error_msg = f"\nОшибка: {error}" if error else ""
        
        response_text = (
            "❌ Не удалось сгенерировать изображение\n\n"
            f"Запрос: \"{prompt}\"{error_msg}\n\n"
            "Возможные причины:\n"
            "• Внешние сервисы генерации временно недоступны\n"
            "• Слишком сложный или абстрактный запрос\n"
            "• Ограничения бесплатных API\n\n"
            "Попробуйте:\n"
            "• Более конкретный запрос\n"
            "• Описать простыми словами\n"
            "• Попробовать позже\n\n"
            "💡 Совет: используйте английские промпты для лучших результатов"
        )
        
        await update.message.reply_text(response_text)
        await update.message.reply_text(response_text)
    async def describe_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Создать подробное текстовое описание изображения"""
        if not context.args:
            await update.message.reply_text(
                "📝 Создание текстового описания изображения\n\n"
                "Использование: /describe <что описать>\n\n"
                "Примеры:\n"
                "• /describe кот в космосе\n"
                "• /describe фантастический пейзаж\n"
                "• /describe портрет робота будущего"
            )
            return
        
        prompt = " ".join(context.args)
        user_id = update.effective_user.id
        
        try:
            async with self.rate_limiter.limit_context(user_id):
                await update.message.chat.send_action(action="typing")
                
                # Создаем промпт для подробного описания
                description_prompt = f"""
    Создай максимально подробное и красочное текстовое описание изображения на основе запроса: "{prompt}"

    Опиши в деталях:
    1. КОМПОЗИЦИЯ - расположение основных элементов, перспектива, баланс
    2. ЦВЕТА - цветовая гамма, сочетания, освещение, тени
    3. СТИЛЬ - художественный стиль, техника исполнения
    4. АТМОСФЕРА - настроение, эмоции, ощущения
    5. ДЕТАЛИ - мелкие особенности, текстуры, элементы

    Сделай описание настолько vivid и детализированным, чтобы можно было ясно представить изображение.
    """
                
                response = await self.gigachat.send_message(
                    description_prompt,
                    Config.DEFAULT_MODEL,
                    Config.DEFAULT_TEMPERATURE,
                    max_tokens=800
                )
                
                # Форматируем ответ
                formatted_response = TelegramFormatter.format_to_telegram(response)
                
                await update.message.reply_text(
                    f"📝 Детальное описание для \"{prompt}\":\n\n{formatted_response}",
                    parse_mode='HTML',
                    disable_web_page_preview=True
                )
                
        except Exception as e:
            logger.error(f"Error creating description: {e}")
            await update.message.reply_text(
                "❌ Не удалось создать описание. Попробуйте другой запрос или повторите позже."
            )
    async def _handle_image_generation_error(self, update: Update, prompt: str, error: str):
        """Обработка ошибок генерации"""
        response_text = (
            "⚠️ Произошла ошибка при генерации\n\n"
            f"Запрос: \"{prompt}\"\n\n"
            "Техническая информация:\n"
            f"Ошибка: {error[:100]}...\n\n"
            "Что делать:\n"
            "• Попробуйте другой запрос\n"
            "• Используйте /describe для текстового описания\n"
            "• Повторите попытку позже"
        )
        
        await update.message.reply_text(response_text)
    async def handle_draw_request(self, update: Update, message_text: str):
        """Обработка запросов на рисование с улучшенным UX"""
        prompt = self._extract_draw_prompt(message_text)
        
        if not prompt:
            # Показываем примеры если запрос пустой
            examples = [
                "нарисуй кота в космосе",
                "нарисуй фантастический пейзаж", 
                "нарисуй робота будущего",
                "нарисуй волшебный замок"
            ]
            
            example_text = "\n".join([f"• {ex}" for ex in examples[:3]])
            
            await update.message.reply_text(
                "🎨 Укажите что нарисовать!\n\n"
                "Примеры запросов:\n"
                f"{example_text}\n\n"
                "⚠️ Внимание: генерация изображений может быть недоступна\n"
                "Используйте /imagestatus для проверки"
            )
            return
        
        # Показываем что запрос принят
        await update.message.reply_text(
            f"🖌️ Принял запрос: \"{prompt}\"\n"
            "Пытаюсь сгенерировать изображение..."
        )
        
        await self.generate_and_send_image(update, prompt) 
    
    async def models_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать список доступных моделей"""
        try:
            async with self.rate_limiter.limit_context(update.effective_user.id):
                models = await self.models_manager.get_recommended_models()
                
                if not models:
                    await update.message.reply_text("❌ Не удалось получить список моделей.")
                    return
                
                models_list = "\n".join([f"• {model.id}" for model in models[:10]])
                message_text = f"📊 Доступные модели:\n{models_list}"
                
                if len(models) > 10:
                    message_text += f"\n\n... и еще {len(models) - 10} моделей."
                
                await update.message.reply_text(message_text)
                
        except RateLimitExceeded:
            await update.message.reply_text("⚠️ Слишком много запросов. Попробуйте позже.")
        except Exception as e:
            logger.error(f"Error getting models: {e}")
            await update.message.reply_text("❌ Ошибка при получении списка моделей.")

    async def model_info_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Информация о конкретной модели"""
        if not context.args:
            await update.message.reply_text("❌ Укажите название модели. Например: /model GigaChat:latest")
            return
        
        model_name = " ".join(context.args)
        
        try:
            async with self.rate_limiter.limit_context(update.effective_user.id):
                model = await self.models_manager.get_model_by_id(model_name)
                
                if not model:
                    await update.message.reply_text(f"❌ Модель '{model_name}' не найдена.")
                    return
                
                info_text = (
                    f"📋 Информация о модели:\n\n"
                    f"🏷️ Название: {model.id}\n"
                    f"📁 Тип: {model.object}\n"
                    f"👥 Владелец: {model.owned_by}\n"
                    f"📝 Описание: {model.description}"
                )
                
                await update.message.reply_text(info_text)
                
        except RateLimitExceeded:
            await update.message.reply_text("⚠️ Слишком много запросов. Попробуйте позже.")
        except Exception as e:
            logger.error(f"Error getting model info: {e}")
            await update.message.reply_text("❌ Ошибка при получении информации о модели.")

    async def model_stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Статистика по моделям"""
        try:
            async with self.rate_limiter.limit_context(update.effective_user.id):
                stats = await self.models_manager.get_models_stats()
                
                stats_text = (
                    f"📊 Статистика моделей:\n\n"
                    f"📈 Всего моделей: {stats['total_models']}\n"
                )
                
                if stats['model_types']:
                    stats_text += f"🔧 Типы моделей:\n"
                    for model_type, count in stats['model_types'].items():
                        stats_text += f"   • {model_type}: {count}\n"
                
                await update.message.reply_text(stats_text)
                
        except RateLimitExceeded:
            await update.message.reply_text("⚠️ Слишком много запросов. Попробуйте позже.")
        except Exception as e:
            logger.error(f"Error getting model stats: {e}")
            await update.message.reply_text("❌ Ошибка при получении статистики моделей.")

    async def refresh_models_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обновить список моделей"""
        try:
            async with self.rate_limiter.limit_context(update.effective_user.id):
                await self.models_manager.clear_cache()
                models = await self.models_manager.get_all_models(force_refresh=True)
                
                await update.message.reply_text(
                    f"✅ Список моделей обновлен!\n"
                    f"Загружено {len(models)} моделей."
                )
                
        except RateLimitExceeded:
            await update.message.reply_text("⚠️ Слишком много запросов. Попробуйте позже.")
        except Exception as e:
            logger.error(f"Error refreshing models: {e}")
            await update.message.reply_text("❌ Ошибка при обновлении списка моделей.")

    async def prompt_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Установить системный промпт"""
        if not context.args:
            await update.message.reply_text(
                "❌ Укажите тип промпта. Доступные варианты:\n"
                "/prompt coding - помощник по программированию\n"
                "/prompt creative - креативный писатель\n" 
                "/prompt science - научный помощник\n"
                "/prompt psychology - психолог\n"
                "/prompt business - бизнес-консультант\n"
                "/prompt teacher - учитель\n"
                "/prompt default - стандартный помощник"
            )
            return
        
        prompt_type = " ".join(context.args).lower()
        user_id = update.effective_user.id
        
        try:
            from prompts import SystemPrompts
            prompt_text = SystemPrompts.get_prompt(prompt_type)
            
            self.user_prompts[user_id] = prompt_text
            await update.message.reply_text(
                f"✅ Системный промпт установлен: {prompt_type}\n"
                f"Теперь я буду отвечать в этом стиле."
            )
            
        except Exception as e:
            logger.error(f"Error setting prompt: {e}")
            await update.message.reply_text("❌ Ошибка при установке промпта.")

    async def myprompt_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать текущий промпт"""
        user_id = update.effective_user.id
        current_prompt = self.user_prompts.get(user_id)
        
        if current_prompt:
            await update.message.reply_text(
                f"📝 Ваш текущий промпт:\n{current_prompt[:200]}..."
            )
        else:
            from prompts import SystemPrompts
            await update.message.reply_text(
                f"📝 Используется стандартный промпт:\n{SystemPrompts.DEFAULT[:200]}..."
            )

    async def prompts_list_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать список доступных промптов"""
        from prompts import SystemPrompts
        
        prompts_list = """🎭 Доступные стили ответов:

    /coding - Помощник по программированию
    /creative - Креативный писатель и поэт  
    /science - Научный помощник
    /psychology - Психолог-помощник
    /business - Бизнес-консультант
    /teacher - Учитель-помощник
    /default - Стандартный AI ассистент

    Используйте /prompt <тип> чтобы изменить стиль"""
        
        await update.message.reply_text(prompts_list)

    async def reset_prompt_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Сбросить промпт к стандартному"""
        user_id = update.effective_user.id
        if user_id in self.user_prompts:
            del self.user_prompts[user_id]
        
        await update.message.reply_text("✅ Промпт сброшен к стандартному.")

    async def set_prompt_type(self, update: Update, context: ContextTypes.DEFAULT_TYPE, prompt_type: str):
        """Быстрая установка промпта по типу"""
        user_id = update.effective_user.id
        
        try:
            from prompts import SystemPrompts
            prompt_text = SystemPrompts.get_prompt(prompt_type)
            
            self.user_prompts[user_id] = prompt_text
            
            type_names = {
                "coding": "помощник по программированию",
                "creative": "креативный писатель",
                "science": "научный помощник", 
                "psychology": "психолог",
                "business": "бизнес-консультант",
                "teacher": "учитель",
                "default": "стандартный помощник"
            }
            
            await update.message.reply_text(
                f"✅ Режим установлен: {type_names[prompt_type]}\n"
                f"Теперь я буду отвечать в этом стиле."
            )
            
        except Exception as e:
            logger.error(f"Error setting prompt type: {e}")
            await update.message.reply_text("❌ Ошибка при установке режима.")
    
    async def new_dialog_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        self.dialog_manager.create_dialog(user_id)
        await update.message.reply_text("🆕 Создан новый диалог! История очищена.")
    
    async def my_dialogs_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        dialogs = self.dialog_manager.get_user_dialogs(user_id)
        
        if not dialogs:
            await update.message.reply_text("📝 У вас пока нет сохраненных диалогов.")
            return
        
        response = "📚 Ваши диалоги:\n\n"
        for i, dialog in enumerate(dialogs, 1):
            time_str = datetime.fromtimestamp(dialog.created_at).strftime("%d.%m %H:%M")
            response += f"{i}. Диалог #{dialog.dialog_hash[:8]}...\n"
            response += f"   📅 {time_str}, сообщений: {len(dialog.messages)}\n\n"
        
        response += "Используйте /exportdialog <хеш> для экспорта"
        await update.message.reply_text(response)
    
    async def export_dialog_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        
        if not context.args:
            await update.message.reply_text("❌ Укажите хеш диалога. Например: /exportdialog abc123")
            return
        
        dialog_hash = context.args[0]
        export_text = self.dialog_manager.export_dialog(user_id, dialog_hash)
        
        if not export_text:
            await update.message.reply_text("❌ Диалог не найден.")
            return
        
        if len(export_text) > 4000:
            await update.message.reply_document(
                document=io.BytesIO(export_text.encode()),
                filename=f"dialog_{dialog_hash}.txt",
                caption=f"📄 Экспорт диалога #{dialog_hash}"
            )
        else:
            await update.message.reply_text(f"📄 Диалог #{dialog_hash}:\n\n{export_text}")
    
    async def clear_dialog_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if self.dialog_manager.clear_dialog(user_id):
            await update.message.reply_text("🧹 Текущий диалог очищен.")
        else:
            await update.message.reply_text("❌ Нет активного диалога для очистки.")
    
    async def draw_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            await update.message.reply_text("❌ Укажите описание изображения. Например: /draw кот в космосе")
            return
        
        prompt = " ".join(context.args)
        await self.generate_and_send_image(update, prompt)
    
    async def image_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            await update.message.reply_text("❌ Укажите описание изображения. Например: /image закат над морем")
            return
        
        prompt = " ".join(context.args)
        await self.generate_and_send_image(update, prompt)
    
    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        logger.error(f"Exception while handling an update: {context.error}")
    
    async def run(self):
        try:
            await self.app.initialize()
            await self.app.start()
            await self.app.updater.start_polling()
            
            logger.info("✅ Bot started successfully!")
            
            # Preload models on startup
            try:
                await self.models_manager.get_all_models()
                logger.info("✅ Models preloaded successfully")
            except Exception as e:
                logger.warning(f"⚠️ Failed to preload models: {e}")
            
            # Check image generation status on startup
            try:
                image_status = await self.image_generator.is_image_generation_available()
                status_msg = "AVAILABLE" if image_status else "NOT AVAILABLE"
                logger.info(f"🖼️ Image generation status: {status_msg}")
            except Exception as e:
                logger.warning(f"⚠️ Failed to check image generation status: {e}")
            
            # Keep the application running
            await asyncio.Event().wait()
            
        except InvalidToken as e:
            logger.error(f"❌ Invalid Telegram token: {e}")
            raise
        except NetworkError as e:
            logger.error(f"❌ Network error: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ Failed to start bot: {e}")
            raise
    
    async def shutdown(self):
        try:
            if hasattr(self, 'app'):
                await self.app.stop()
                await self.app.shutdown()
            if hasattr(self, 'gigachat'):
                await self.gigachat.close()
            if hasattr(self, 'deepseek'):
                await self.deepseek.close()
            await image_service.close()
            logger.info("✅ Bot shutdown successfully")
        except Exception as e:
            logger.error(f"❌ Error during shutdown: {e}")

async def main():
    try:
        bot = GigaChatBot()
        await bot.run()
    except (InvalidToken, ValueError) as e:
        print(f"\n❌ Critical error: {e}")
        print("💡 Please check your .env file and make sure:")
        print("   - TELEGRAM_TOKEN is correct (from @BotFather)")
        print("   - GIGACHAT_AUTH_KEY is correct (from GigaChat)")
        print("   - All required variables are set")
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped by user")
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
    finally:
        if 'bot' in locals():
            await bot.shutdown()

if __name__ == "__main__":
    if not os.path.exists('.env'):
        print("❌ .env file not found!")
        print("💡 Please create .env file from .env.example")
        sys.exit(1)
    
    asyncio.run(main())
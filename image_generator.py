from aiogram import Router, F
from aiogram.types import Message, BufferedInputFile
from aiogram.filters import Command
from aiogram.enums import ParseMode

from image_service import image_service
from rate_limiter import rate_limit

router = Router()

@router.message(Command("image", "img", "generate"))
@rate_limit(limit=5, interval=60)
async def handle_image_generation(message: Message):
    """
    Обработчик генерации изображений через Perchance.
    Поддерживает команды: /image, /img, /generate
    """
    # Извлекаем текст команды
    command_text = message.text.split(maxsplit=1)
    if len(command_text) < 2:
        await show_help(message)
        return

    await message.answer_chat_action("upload_photo")
    
    # Парсим команду для определения стиля
    parts = command_text[1].split(maxsplit=2)
    style = "realistic"
    user_prompt = command_text[1]
    
    # Проверяем, указан ли стиль как первый параметр
    if len(parts) >= 2 and parts[0].startswith("style:"):
        style_name = parts[0].replace("style:", "").strip().lower()
        if style_name in image_service.get_available_styles():
            style = style_name
            user_prompt = parts[1] if len(parts) > 1 else ""
        else:
            await message.answer(
                f"❌ Неизвестный стиль: {style_name}\n\n"
                f"Доступные стили: {', '.join(image_service.get_available_styles())}"
            )
            return
    elif len(parts) >= 3 and parts[1].startswith("style:"):
        # Стиль указан как второй параметр
        style_name = parts[1].replace("style:", "").strip().lower()
        if style_name in image_service.get_available_styles():
            style = style_name
            user_prompt = f"{parts[0]} {parts[2]}" if len(parts) > 2 else parts[0]
        else:
            await message.answer(
                f"❌ Неизвестный стиль: {style_name}\n\n"
                f"Доступные стили: {', '.join(image_service.get_available_styles())}"
            )
            return

    if not user_prompt.strip():
        await message.answer("❌ Пожалуйста, укажите описание для генерации изображения.")
        return

    # Генерируем изображение
    image_data, error = await image_service.generate_image(
        prompt=user_prompt,
        style=style
    )
    
    if image_data:
        # Отправляем изображение
        photo = BufferedInputFile(image_data, filename="generated_image.png")
        caption = (
            f"🎨 Сгенерировано через Perchance\n\n"
            f"📝 Запрос: {user_prompt}\n"
            f"🎭 Стиль: {style}\n"
            f"⚡️ Нейросеть: Perchance AI"
        )
        
        await message.answer_photo(photo, caption=caption, parse_mode=ParseMode.HTML)
    else:
        await message.answer(f"❌ {error}")

@router.message(Command("styles", "presets"))
async def handle_list_styles(message: Message):
    """Показывает доступные стили генерации."""
    styles = image_service.get_available_styles()
    styles_list = "\n".join([f"• {style}" for style in styles])
    
    help_text = (
        "🎨 <b>Доступные стили генерации:</b>\n\n"
        f"{styles_list}\n\n"
        "<b>Примеры использования:</b>\n"
        "<code>/image кот в шляпе</code> - реалистичный стиль\n"
        "<code>/image style:anime девушка-воин</code> - аниме стиль\n"
        "<code>/img портрет кота style:art</code> - арт стиль\n\n"
        "Можно использовать команды: /image, /img, /generate"
    )
    
    await message.answer(help_text, parse_mode=ParseMode.HTML)

async def show_help(message: Message):
    """Показывает справку по генерации изображений."""
    help_text = (
        "🎨 <b>Генерация изображений через Perchance AI</b>\n\n"
        "<b>Команды:</b>\n"
        "<code>/image описание</code> - генерация изображения\n"
        "<code>/img описание</code> - сокращенная команда\n"
        "<code>/generate описание</code> - альтернативная команда\n"
        "<code>/styles</code> - список доступных стилей\n\n"
        "<b>Указание стиля:</b>\n"
        "<code>/image style:anime девушка-воин</code>\n"
        "<code>/img портрет style:realistic</code>\n\n"
        "Используйте <code>/styles</code> чтобы увидеть все доступные стили!"
    )
    
    await message.answer(help_text, parse_mode=ParseMode.HTML)

# Обработчик для любых сообщений, которые могут быть промптами
@router.message(F.text & ~F.command)
async def handle_possible_prompt(message: Message):
    """
    Предлагает генерацию изображения если сообщение похоже на промпт.
    """
    text = message.text.strip()
    if len(text.split()) >= 3 and len(text) > 10:  # Если сообщение достаточно длинное
        await message.answer(
            f"🎨 Хотите сгенерировать изображение по этому описанию?\n\n"
            f"<code>/image {text}</code>\n\n"
            "Или укажите стиль: <code>/image style:anime {text}</code>",
            parse_mode=ParseMode.HTML
        )
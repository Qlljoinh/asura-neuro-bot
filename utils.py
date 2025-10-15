import html
import re
from typing import Optional

class TelegramFormatter:
    @staticmethod
    def escape_html(text: str) -> str:
        """Экранирование HTML символов для Telegram"""
        return html.escape(text)
    
    @staticmethod
    def format_to_telegram(text: str) -> str:
        """
        Конвертирует Markdown-like форматирование в Telegram HTML
        Поддерживает: *жирный*, _курсив_, `код`, ```блок кода```
        """
        if not text:
            return ""
        
        # Экранируем HTML символы
        text = TelegramFormatter.escape_html(text)
        
        # Заменяем форматирование
        text = TelegramFormatter._replace_formatting(text)
        
        return text
    
    @staticmethod
    def _replace_formatting(text: str) -> str:
        """Замена форматирования на Telegram HTML"""
        # Жирный текст: **text** или __text__ -> <b>text</b>
        text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
        text = re.sub(r'__(.+?)__', r'<b>\1</b>', text)
        
        # Курсив: *text* или _text_ -> <i>text</i>
        text = re.sub(r'\*(.+?)\*', r'<i>\1</i>', text)
        text = re.sub(r'_(.+?)_', r'<i>\1</i>', text)
        
        # Моноширинный/код: `code` -> <code>code</code>
        text = re.sub(r'`([^`]+?)`', r'<code>\1</code>', text)
        
        # Блоки кода: ```language\ncode\n``` -> <pre><code class="language">code</code></pre>
        text = re.sub(r'```(\w+)?\n(.+?)\n```', r'<pre><code class="\1">\2</code></pre>', text, flags=re.DOTALL)
        text = re.sub(r'```(.+?)```', r'<pre>\1</pre>', text, flags=re.DOTALL)
        
        # Ссылки: [текст](url) -> <a href="url">текст</a>
        text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', text)
        
        # Убираем экранирование для HTML тегов
        text = text.replace('&lt;', '<').replace('&gt;', '>')
        text = text.replace('&amp;', '&')
        
        return text
    
    @staticmethod
    def truncate_text(text: str, max_length: int = 4096) -> str:
        """Обрезает текст до максимальной длины"""
        if len(text) <= max_length:
            return text
        
        # Находим последний пробел перед лимитом
        truncated = text[:max_length]
        last_space = truncated.rfind(' ')
        
        if last_space > max_length - 100:  # Если есть нормальное место для обрезания
            return truncated[:last_space] + "..."
        else:
            return truncated + "..."
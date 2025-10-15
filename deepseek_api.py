import aiohttp
import logging
from typing import List, Dict, Optional
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)
api_key = "sk-0b0b6296377d4aa6b48b356da32ec37d"
class DeepSeekAPI:
    def __init__(self, api_key: str, base_url: str = "https://api.deepseek.com"):
        self.api_key = api_key
        self.base_url = base_url
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        logger.info("DeepSeekAPI initialized")
    def switch_model(self, user_id: int, model: str) -> bool:
        """Переключение модели в активном диалоге"""
        dialog = self.get_active_dialog(user_id)
        if dialog:
            dialog.current_model = model
            logger.info(f"Switched to model {model} for user {user_id}")
            return True
        return False

    def get_active_model(self, user_id: int) -> str:
        """Получение активной модели"""
        dialog = self.get_active_dialog(user_id)
        return dialog.current_model if dialog else "GigaChat"
    async def send_message(self, message: str, model: str = "deepseek-chat", 
                         temperature: float = 0.7, system_prompt: str = None,
                         conversation_history: List[Dict] = None) -> str:
        """Отправка сообщения в DeepSeek с поддержкой истории диалога"""
        try:
            # Создаем messages массив
            messages = []
            
            # Добавляем системный промпт если указан
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            
            # Добавляем историю диалога если есть
            if conversation_history:
                messages.extend(conversation_history)
            
            # Добавляем текущее сообщение пользователя
            messages.append({"role": "user", "content": message})
            
            logger.debug(f"Sending message to DeepSeek with {len(messages)} messages")
            
            response = await self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                stream=False
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"Error sending message to DeepSeek: {e}")
            raise

    async def close(self):
        """Закрытие клиента"""
        try:
            await self.client.close()
        except:
            pass
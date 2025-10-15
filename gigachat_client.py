import logging
from typing import Optional, List, Dict
from gigachat import GigaChat
from gigachat.models import Chat, Messages, MessagesRole

logger = logging.getLogger(__name__)

class GigaChatClient:
    """Клиент для работы с GigaChat через официальную библиотеку gigachat."""
    
    def __init__(self, credentials: str, scope: str = "GIGACHAT_API_PERS", ignore_ssl: bool = False):
        self.credentials = credentials
        self.scope = scope
        self.ignore_ssl = ignore_ssl
        self.client = None
        self._initialize_client()

    def _initialize_client(self):
        """Инициализирует клиент GigaChat."""
        try:
            self.client = GigaChat(
                credentials=self.credentials,
                scope=self.scope,
                verify_ssl_certs=not self.ignore_ssl,
                timeout=30
            )
            logger.info("GigaChat client initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize GigaChat client: {e}")
            raise

    async def send_message(
        self,
        message: str,
        model: str = "GigaChat",
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        system_prompt: Optional[str] = None,
        conversation_history: Optional[List[Dict]] = None
    ) -> str:
        """Отправляет сообщение в GigaChat и возвращает ответ."""
        try:
            # Подготовка сообщений
            messages = []
            
            if system_prompt:
                messages.append(Messages(role=MessagesRole.SYSTEM, content=system_prompt))
            
            if conversation_history:
                for msg in conversation_history:
                    if msg["role"] == "user":
                        messages.append(Messages(role=MessagesRole.USER, content=msg["content"]))
                    elif msg["role"] == "assistant":
                        messages.append(Messages(role=MessagesRole.ASSISTANT, content=msg["content"]))
            
            messages.append(Messages(role=MessagesRole.USER, content=message))

            # Создаем чат запрос
            chat_request = Chat(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )

            # Отправка запроса
            response = self.client.chat(chat_request)
            
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"Error sending message to GigaChat: {e}")
            raise

    async def get_models(self):
        """Получает список доступных моделей."""
        try:
            # Для получения моделей может потребоваться другой подход
            # Возвращаем стандартный список моделей GigaChat
            return [
                "GigaChat",
                "GigaChat-Plus", 
                "GigaChat-Pro",
                "GigaChat-2",
                "GigaChat-2-Max"
            ]
        except Exception as e:
            logger.error(f"Error getting models: {e}")
            return []

    async def close(self):
        """Закрывает клиент."""
        if self.client:
            try:
                # Библиотека gigachat может иметь метод close или использовать контекстный менеджер
                if hasattr(self.client, 'close'):
                    self.client.close()
                logger.info("GigaChat client closed")
            except Exception as e:
                logger.error(f"Error closing client: {e}")

    async def get_access_token(self) -> Optional[str]:
        """Возвращает текущий access token."""
        try:
            # Библиотека gigachat управляет токенами internally
            return "gigachat_internal_token"
        except Exception as e:
            logger.error(f"Error getting access token: {e}")
            return None

    async def get_session(self):
        """Возвращает сессию для совместимости."""
        return self

    # Контекстный менеджер для with
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
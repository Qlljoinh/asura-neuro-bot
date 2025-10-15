from gigachat import GigaChat
from gigachat.models import Chat, Messages, MessagesRole
import os
from config import Config

class GigaChainClient:
    def __init__(self):
        # Авторизация через credentials
        self.client = GigaChat(
            credentials=Config.GIGACHAT_CLIENT_SECRET,  # или base64 encoded client_id:client_secret
            scope=Config.GIGACHAT_SCOPE,
            verify_ssl_certs=not Config.IGNORE_SSL_ERRORS
        )
    
    async def send_message(self, message: str, model: str = "GigaChat:latest") -> str:
        try:
            payload = Chat(
                model=model,
                messages=[Messages(role=MessagesRole.USER, content=message)],
                temperature=Config.DEFAULT_TEMPERATURE
            )
            
            response = await self.client.achat(payload)
            return response.choices[0].message.content
            
        except Exception as e:
            raise Exception(f"GigaChain error: {e}")
    
    async def close(self):
        await self.client.aclose()
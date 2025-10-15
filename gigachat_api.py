import aiohttp
import json
import uuid
import time
import ssl
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)

@dataclass
class Token:
    access_token: str
    expires_at: float

class GigaChatAPI:
    def __init__(self, auth_key: str, scope: str = "GIGACHAT_API_PERS", ignore_ssl: bool = True):
        self.auth_key = auth_key
        self.scope = scope
        self.ignore_ssl = ignore_ssl
        self.token: Optional[Token] = None
        self.session: Optional[aiohttp.ClientSession] = None
        self.ssl_context: Optional[ssl.SSLContext] = None
        
        if self.ignore_ssl:
            self._create_ssl_context()
        
        logger.info(f"GigaChatAPI initialized with scope: {scope}")
    
    def _create_ssl_context(self):
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.check_hostname = False
        self.ssl_context.verify_mode = ssl.CERT_NONE
    
    async def get_session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            connector = aiohttp.TCPConnector(ssl=self.ssl_context if self.ignore_ssl else None)
            self.session = aiohttp.ClientSession(connector=connector)
        return self.session
    
    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()
    
    async def get_access_token(self) -> str:
        if self.token and self.token.expires_at > time.time() + 60:
            return self.token.access_token
        
        logger.info("Requesting new access token via OAuth...")
        url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
        
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': 'application/json',
            'Authorization': f'Basic {self.auth_key}',
            'RqUID': str(uuid.uuid4())
        }
        
        data = {'scope': self.scope}
        
        try:
            session = await self.get_session()
            
            async with session.post(
                url, 
                headers=headers, 
                data=data, 
                ssl=False if self.ignore_ssl else None
            ) as response:
                
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"OAuth request failed: {response.status} - {error_text}")
                
                result = await response.json()
                
                if 'access_token' not in result:
                    raise Exception("Invalid OAuth response: access_token not found")
                
                self.token = Token(
                    access_token=result['access_token'],
                    expires_at=time.time() + 1800
                )
                logger.info("New access token obtained successfully")
                return self.token.access_token
                
        except Exception as e:
            logger.error(f"Error getting access token: {e}")
            raise
    
    async def send_message(self, message: str, model: str = "GigaChat:latest", 
                         temperature: float = 0.87, system_prompt: str = None,
                         conversation_history: List[Dict] = None) -> str:
        """Отправка сообщения с поддержкой истории диалога"""
        token = await self.get_access_token()
        url = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"
        
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Authorization': f'Bearer {token}'
        }
        
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
        
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": 1024
        }
        
        logger.debug(f"Sending message with {len(conversation_history or [])} history messages")
        
        try:
            session = await self.get_session()
            
            async with session.post(
                url, 
                headers=headers, 
                json=payload, 
                ssl=False if self.ignore_ssl else None
            ) as response:
                
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Chat request failed: {response.status} - {error_text}")
                
                result = await response.json()
                
                if 'choices' not in result or not result['choices']:
                    raise Exception("Invalid chat response: no choices found")
                
                return result['choices'][0]['message']['content']
                
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            raise

    async def get_models_raw(self) -> List[Dict[str, Any]]:
        """Получить сырые данные моделей из API"""
        token = await self.get_access_token()
        url = "https://gigachat.devices.sberbank.ru/api/v1/models"
        
        headers = {
            'Accept': 'application/json',
            'Authorization': f'Bearer {token}'
        }
        
        try:
            session = await self.get_session()
            
            async with session.get(
                url, 
                headers=headers, 
                ssl=False if self.ignore_ssl else None
            ) as response:
                
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Models request failed: {response.status} - {error_text}")
                
                result = await response.json()
                
                if 'data' not in result:
                    raise Exception("Invalid models response: data not found")
                
                return result.get('data', [])
                
        except Exception as e:
            logger.error(f"Error getting models: {e}")
            raise
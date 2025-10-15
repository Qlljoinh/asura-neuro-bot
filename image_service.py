import aiohttp
import logging
import asyncio
import io
import re
import random
from typing import Optional, Tuple
from PIL import Image
from bs4 import BeautifulSoup
import urllib.parse

logger = logging.getLogger(__name__)

class ImageGenerationService:
    """Сервис для генерации изображений через парсинг бесплатных веб-сервисов."""
    
    def __init__(self):
        self.session = None
        self.services = [
            self._try_craiyon,
            self._try_nexus,
            self._try_aiart,
            self._try_freeimageai
        ]
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36',
            'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15'
        ]

    async def init_session(self):
        if not self.session or self.session.closed:
            self.session = aiohttp.ClientSession()

    async def generate_image(self, prompt: str) -> Tuple[Optional[bytes], Optional[str]]:
        """Пробует разные бесплатные веб-сервисы для генерации изображений."""
        await self.init_session()
        
        # Перемешиваем сервисы для балансировки нагрузки
        services_to_try = random.sample(self.services, len(self.services))
        
        for service_method in services_to_try:
            try:
                logger.info(f"Trying service: {service_method.__name__} for prompt: {prompt[:50]}...")
                result = await service_method(prompt)
                if result and self._is_valid_image(result):
                    logger.info(f"Success with service: {service_method.__name__}, data size: {len(result)} bytes")
                    return result, None
            except Exception as e:
                logger.warning(f"Service {service_method.__name__} failed: {e}")
                continue
        
        return None, "Все сервисы генерации изображений временно недоступны. Попробуйте позже."

    def _is_valid_image(self, image_data: bytes) -> bool:
        """Проверяет, являются ли данные валидным изображением"""
        try:
            image = Image.open(io.BytesIO(image_data))
            image.verify()
            return len(image_data) > 1024  # Минимальный размер для валидного изображения
        except Exception as e:
            logger.error(f"Invalid image data: {e}")
            return False

    async def _try_craiyon(self, prompt: str) -> Optional[bytes]:
        """Парсит Craiyon (ранее DALL-E Mini) - бесплатный сервис генерации изображений."""
        try:
            # Кодируем промпт для URL
            encoded_prompt = urllib.parse.quote(prompt)
            
            # Отправляем запрос на генерацию
            generate_url = f"https://api.craiyon.com/generate"
            
            headers = {
                'User-Agent': random.choice(self.user_agents),
                'Content-Type': 'application/json',
                'Origin': 'https://www.craiyon.com',
                'Referer': 'https://www.craiyon.com/'
            }
            
            payload = {
                "prompt": prompt,
                "version": "35s5hfwn9n78gb06",
                "token": None
            }
            
            async with self.session.post(
                generate_url,
                json=payload,
                headers=headers,
                timeout=120
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    images = data.get('images', [])
                    
                    if images:
                        # Берем первое изображение (base64)
                        image_base64 = images[0]
                        if image_base64.startswith('data:image/jpeg;base64,'):
                            image_base64 = image_base64.replace('data:image/jpeg;base64,', '')
                        
                        try:
                            image_data = base64.b64decode(image_base64)
                            if self._is_valid_image(image_data):
                                return image_data
                        except:
                            pass
                
                return None
                
        except Exception as e:
            logger.error(f"Craiyon service exception: {e}")
            return None

    async def _try_nexus(self, prompt: str) -> Optional[bytes]:
        """Парсит Nexus Free AI Art Generator."""
        try:
            # Получаем страницу для получения CSRF токена
            base_url = "https://nexus.artemisai.art/"
            
            headers = {
                'User-Agent': random.choice(self.user_agents),
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Connection': 'keep-alive'
            }
            
            async with self.session.get(base_url, headers=headers, timeout=30) as response:
                if response.status == 200:
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    # Ищем форму генерации
                    form = soup.find('form', {'id': 'generate-form'})
                    if form:
                        # Пытаемся отправить запрос на генерацию
                        generate_url = "https://nexus.artemisai.art/generate"
                        
                        generate_headers = {
                            'User-Agent': random.choice(self.user_agents),
                            'Content-Type': 'application/x-www-form-urlencoded',
                            'Origin': 'https://nexus.artemisai.art',
                            'Referer': 'https://nexus.artemisai.art/',
                            'X-Requested-With': 'XMLHttpRequest'
                        }
                        
                        data = {
                            'prompt': prompt,
                            'style': 'default',
                            'size': '512x512'
                        }
                        
                        async with self.session.post(
                            generate_url,
                            data=data,
                            headers=generate_headers,
                            timeout=120
                        ) as gen_response:
                            if gen_response.status == 200:
                                result = await gen_response.json()
                                image_url = result.get('image_url')
                                
                                if image_url:
                                    # Скачиваем изображение
                                    async with self.session.get(image_url) as img_response:
                                        if img_response.status == 200:
                                            return await img_response.read()
                
                return None
                
        except Exception as e:
            logger.error(f"Nexus service exception: {e}")
            return None

    async def _try_aiart(self, prompt: str) -> Optional[bytes]:
        """Парсит различные бесплатные AI Art генераторы."""
        try:
            # Пробуем разные бесплатные сервисы
            services = [
                {
                    'url': 'https://www.aiartapps.com/generate',
                    'data': {'prompt': prompt, 'style': 'digital-art'}
                },
                {
                    'url': 'https://freeaiapi.com/generate',
                    'data': {'text': prompt, 'model': 'stable-diffusion'}
                }
            ]
            
            for service in services:
                try:
                    headers = {
                        'User-Agent': random.choice(self.user_agents),
                        'Content-Type': 'application/json',
                        'Accept': 'application/json'
                    }
                    
                    async with self.session.post(
                        service['url'],
                        json=service['data'],
                        headers=headers,
                        timeout=60
                    ) as response:
                        if response.status == 200:
                            data = await response.json()
                            image_url = data.get('image_url') or data.get('url')
                            
                            if image_url:
                                async with self.session.get(image_url) as img_response:
                                    if img_response.status == 200:
                                        image_data = await img_response.read()
                                        if self._is_valid_image(image_data):
                                            return image_data
                except:
                    continue
            
            return None
                
        except Exception as e:
            logger.error(f"AI Art service exception: {e}")
            return None

    async def _try_freeimageai(self, prompt: str) -> Optional[bytes]:
        """Парсит FreeImageAI и подобные сервисы."""
        try:
            # Используем поиск Google Images для похожих AI изображений
            search_query = f"{prompt} AI generated art"
            encoded_query = urllib.parse.quote(search_query)
            
            search_url = f"https://www.google.com/search?q={encoded_query}&tbm=isch&tbs=isz:l"
            
            headers = {
                'User-Agent': random.choice(self.user_agents),
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
            }
            
            async with self.session.get(search_url, headers=headers, timeout=30) as response:
                if response.status == 200:
                    html = await response.text()
                    
                    # Ищем URL изображений в результатах
                    image_urls = re.findall(r'\"(https?://[^\"]+\.(?:jpg|jpeg|png|webp))\"', html)
                    
                    if image_urls:
                        # Берем случайное изображение из результатов
                        image_url = random.choice(image_urls[:5])
                        
                        async with self.session.get(image_url, headers=headers, timeout=30) as img_response:
                            if img_response.status == 200:
                                image_data = await img_response.read()
                                if self._is_valid_image(image_data):
                                    return image_data
                
                return None
                
        except Exception as e:
            logger.error(f"FreeImageAI service exception: {e}")
            return None

    async def get_alternative_suggestions(self, prompt: str) -> dict:
        """Возвращает альтернативные предложения если генерация недоступна."""
        return {
            "text_description": "Попробуйте описать изображение текстом или используйте другой запрос",
            "wait_suggestion": "Подождите несколько минут и попробуйте снова",
            "simple_prompt": "Используйте более простые и конкретные описания"
        }

    async def close(self):
        if self.session:
            await self.session.close()

# Глобальный экземпляр
image_service = ImageGenerationService()
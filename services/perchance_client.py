import aiohttp
import asyncio
import random
from loguru import logger
from typing import Optional, Tuple

class PerchanceService:
    """Сервис для генерации изображений через Perchance API."""
    
    def __init__(self):
        self.base_url = "https://perchance.org/api/generate"
        self.session: Optional[aiohttp.ClientSession] = None

    async def init_session(self):
        """Инициализирует сессию."""
        if not self.session:
            self.session = aiohttp.ClientSession()

    async def generate_image(self, prompt: str) -> Tuple[Optional[bytes], Optional[str]]:
        """
        Генерирует изображение через Perchance API.
        
        Returns:
            Tuple[image_data, error_message]
        """
        if not self.session:
            await self.init_session()

        payload = {
            "prompt": f"{prompt}, high quality, detailed",
            "width": 1024,
            "height": 1024,
            "quality": "high",
            "generate": "image",
            "seed": random.randint(1, 1000000)
        }

        try:
            async with self.session.post(
                self.base_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=120)
            ) as response:
                
                if response.status == 200:
                    content_type = response.headers.get('Content-Type', '')
                    
                    if 'image' in content_type:
                        image_data = await response.read()
                        logger.success(f"Image generated successfully")
                        return image_data, None
                    else:
                        error_data = await response.text()
                        logger.error(f"Perchance API error: {error_data}")
                        return None, "Ошибка генерации изображения"
                        
                else:
                    error_text = await response.text()
                    logger.error(f"HTTP Error {response.status}: {error_text}")
                    return None, "Сервер перегружен, попробуйте позже"
                    
        except aiohttp.ClientError as e:
            logger.error(f"Network error: {e}")
            return None, "Ошибка сети"
        except asyncio.TimeoutError:
            logger.error("Timeout while generating image")
            return None, "Таймаут при генерации"
        except Exception as e:
            logger.exception(f"Unexpected error: {e}")
            return None, "Неизвестная ошибка"

    async def close(self):
        """Закрывает сессию."""
        if self.session:
            await self.session.close()
            self.session = None

# Глобальный экземпляр
perchance_service = PerchanceService()
import aiohttp
import logging
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from gigachat_api import GigaChatAPI

logger = logging.getLogger(__name__)

@dataclass
class ModelInfo:
    id: str
    object: str
    owned_by: str
    description: str = ""
    capabilities: List[str] = None

    def __post_init__(self):
        if self.capabilities is None:
            self.capabilities = []

class ModelsManager:
    def __init__(self, gigachat_api: GigaChatAPI):
        self.api = gigachat_api
        self._models_cache: Optional[List[ModelInfo]] = None
        self._last_update: float = 0
        self.cache_timeout = 3600  # 1 hour cache
    
    async def get_all_models(self, force_refresh: bool = False) -> List[ModelInfo]:
        """Получить все доступные модели с кэшированием"""
        current_time = self._get_current_time()
        
        if (not force_refresh and 
            self._models_cache and 
            current_time - self._last_update < self.cache_timeout):
            return self._models_cache
        
        try:
            raw_models = await self._fetch_models_from_api()
            self._models_cache = self._parse_models(raw_models)
            self._last_update = current_time
            return self._models_cache
            
        except Exception as e:
            logger.error(f"Error fetching models: {e}")
            # Return cached models if available, even if expired
            if self._models_cache:
                return self._models_cache
            raise
    
    async def get_model_by_id(self, model_id: str) -> Optional[ModelInfo]:
        """Найти модель по ID"""
        models = await self.get_all_models()
        for model in models:
            if model.id == model_id:
                return model
        return None
    
    async def search_models(self, search_term: str) -> List[ModelInfo]:
        """Поиск моделей по названию"""
        models = await self.get_all_models()
        search_term = search_term.lower()
        
        return [
            model for model in models
            if search_term in model.id.lower() or search_term in model.description.lower()
        ]
    
    async def get_recommended_models(self) -> List[ModelInfo]:
        """Получить рекомендуемые модели"""
        models = await self.get_all_models()
        
        # Сортируем по приоритету: сначала основные, потом остальные
        priority_models = []
        other_models = []
        
        for model in models:
            if any(keyword in model.id.lower() for keyword in ['gigachat', 'latest', 'pro', 'max']):
                priority_models.append(model)
            else:
                other_models.append(model)
        
        return priority_models + other_models
    
    async def validate_model(self, model_id: str) -> bool:
        """Проверить, существует ли модель"""
        models = await self.get_all_models()
        return any(model.id == model_id for model in models)
    
    async def get_models_stats(self) -> Dict[str, Any]:
        """Получить статистику по моделям"""
        models = await self.get_all_models()
        
        return {
            "total_models": len(models),
            "model_types": self._count_model_types(models),
            "owned_by": self._count_owned_by(models),
            "latest_models": [model.id for model in models if 'latest' in model.id.lower()][:5]
        }
    
    def _get_current_time(self) -> float:
        """Вспомогательный метод для получения времени"""
        import time
        return time.time()
    
    async def _fetch_models_from_api(self) -> List[Dict[str, Any]]:
        """Получить модели из API"""
        token = await self.api.get_access_token()
        url = "https://gigachat.devices.sberbank.ru/api/v1/models"
        
        headers = {
            'Accept': 'application/json',
            'Authorization': f'Bearer {token}'
        }
        
        session = await self.api.get_session()
        async with session.get(url, headers=headers) as response:
            response.raise_for_status()
            result = await response.json()
            return result.get('data', [])
    
    def _parse_models(self, raw_models: List[Dict[str, Any]]) -> List[ModelInfo]:
        """Парсинг сырых данных моделей"""
        models = []
        
        for model_data in raw_models:
            try:
                model = ModelInfo(
                    id=model_data.get('id', ''),
                    object=model_data.get('object', ''),
                    owned_by=model_data.get('owned_by', ''),
                    description=self._generate_description(model_data)
                )
                models.append(model)
            except Exception as e:
                logger.warning(f"Failed to parse model data: {model_data}, error: {e}")
        
        return models
    
    def _generate_description(self, model_data: Dict[str, Any]) -> str:
        """Генерация описания модели на основе её данных"""
        model_id = model_data.get('id', '').lower()
        
        descriptions = {
            'gigachat': "Основная модель GigaChat для общего использования",
            'pro': "Продвинутая версия с улучшенными возможностями",
            'max': "Максимальная версия с наибольшим контекстом",
            'latest': "Самая последняя версия модели",
            'embedding': "Модель для создания векторных представлений",
            'multimodal': "Мультимодальная модель для работы с текстом и изображениями"
        }
        
        description_parts = []
        for keyword, desc in descriptions.items():
            if keyword in model_id:
                description_parts.append(desc)
        
        return ". ".join(description_parts) if description_parts else "Модель искусственного интеллекта"
    
    def _count_model_types(self, models: List[ModelInfo]) -> Dict[str, int]:
        """Подсчет типов моделей"""
        types_count = {}
        for model in models:
            model_type = self._detect_model_type(model.id)
            types_count[model_type] = types_count.get(model_type, 0) + 1
        return types_count
    
    def _count_owned_by(self, models: List[ModelInfo]) -> Dict[str, int]:
        """Подсчет владельцев моделей"""
        owned_count = {}
        for model in models:
            owner = model.owned_by or 'unknown'
            owned_count[owner] = owned_count.get(owner, 0) + 1
        return owned_count
    
    def _detect_model_type(self, model_id: str) -> str:
        """Определить тип модели по ID"""
        model_id = model_id.lower()
        
        if 'embedding' in model_id:
            return 'embedding'
        elif 'multimodal' in model_id or 'vision' in model_id:
            return 'multimodal'
        elif 'pro' in model_id:
            return 'pro'
        elif 'max' in model_id:
            return 'max'
        elif 'latest' in model_id:
            return 'latest'
        elif 'gigachat' in model_id:
            return 'standard'
        else:
            return 'other'
    
    async def clear_cache(self):
        """Очистить кэш моделей"""
        self._models_cache = None
        self._last_update = 0
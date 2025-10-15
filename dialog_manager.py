import hashlib
import json
import time
import logging
import random
import string
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
import os
from datetime import datetime

logger = logging.getLogger(__name__)

@dataclass
class Message:
    role: str  # "user" или "assistant"
    content: str
    timestamp: float
    model: str = "unknown"  # Добавляем информацию о модели

@dataclass
class Dialog:
    user_id: int
    dialog_hash: str
    messages: List[Message]
    created_at: float
    last_activity: float
    current_model: str = "GigaChat"  # Модель по умолчанию

class DialogManager:
    def __init__(self, max_messages_per_dialog: int = 20, max_dialogs_per_user: int = 10):
        self.max_messages = max_messages_per_dialog
        self.max_dialogs = max_dialogs_per_user
        self.dialogs: Dict[int, List[Dialog]] = {}
        self.active_dialogs: Dict[int, str] = {}
        self.used_hashes: set = set()  # Для отслеживания использованных хешей
        
        os.makedirs("dialog_logs", exist_ok=True)
    
    def _generate_unique_dialog_hash(self) -> str:
        """Генерация уникального 6-символьного хеша"""
        while True:
            # Генерируем 6 случайных символов (буквы + цифры)
            hash_chars = random.choices(string.ascii_lowercase + string.digits, k=6)
            dialog_hash = ''.join(hash_chars)
            
            # Проверяем уникальность
            if dialog_hash not in self.used_hashes:
                self.used_hashes.add(dialog_hash)
                return dialog_hash
    
    def get_active_dialog(self, user_id: int) -> Optional[Dialog]:
        """Получение активного диалога"""
        if user_id not in self.active_dialogs:
            return None
        
        dialog_hash = self.active_dialogs[user_id]
        return self.get_dialog(user_id, dialog_hash)
    
    def create_dialog(self, user_id: int, model: str = "GigaChat") -> Dialog:
        """Создание нового диалога"""
        dialog_hash = self._generate_unique_dialog_hash()
        dialog = Dialog(
            user_id=user_id,
            dialog_hash=dialog_hash,
            messages=[],
            created_at=time.time(),
            last_activity=time.time(),
            current_model=model
        )
        
        if user_id not in self.dialogs:
            self.dialogs[user_id] = []
        
        if len(self.dialogs[user_id]) >= self.max_dialogs:
            # Удаляем самый старый диалог
            removed_dialog = self.dialogs[user_id].pop(0)
            # Освобождаем хеш
            self.used_hashes.discard(removed_dialog.dialog_hash)
        
        self.dialogs[user_id].append(dialog)
        self.active_dialogs[user_id] = dialog_hash
        
        logger.info(f"Created new dialog {dialog_hash} for user {user_id} with model {model}")
        return dialog
    
    def get_dialog(self, user_id: int, dialog_hash: str) -> Optional[Dialog]:
        """Получение диалога по хешу"""
        if user_id not in self.dialogs:
            return None
        
        for dialog in self.dialogs[user_id]:
            if dialog.dialog_hash == dialog_hash:
                return dialog
        return None
    
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
    
    def add_message(self, user_id: int, role: str, content: str, model: str = None) -> Optional[Dialog]:
        """Добавление сообщения в диалог"""
        dialog = self.get_active_dialog(user_id)
        if not dialog:
            # При создании нового диалога используем текущую модель
            current_model = self.get_active_model(user_id)
            dialog = self.create_dialog(user_id, current_model)
        
        # Если модель не указана, используем модель диалога
        if model is None:
            model = dialog.current_model
        
        message = Message(role=role, content=content, timestamp=time.time(), model=model)
        dialog.messages.append(message)
        dialog.last_activity = time.time()
        
        if len(dialog.messages) > self.max_messages:
            dialog.messages = dialog.messages[-self.max_messages:]
        
        self._log_message(user_id, dialog.dialog_hash, message)
        
        return dialog
    def get_conversation_history(self, user_id: int, max_messages: int = 10) -> List[Message]:
        """Получение истории сообщений для контекста"""
        dialog = self.get_active_dialog(user_id)
        if not dialog or not dialog.messages:
            return []
        
        return dialog.messages[-max_messages:]
    
    def get_conversation_history_for_api(self, user_id: int, max_messages: int = 10) -> List[Dict]:
        """Получение истории в формате для API"""
        history = self.get_conversation_history(user_id, max_messages)
        return [
            {"role": msg.role, "content": msg.content}
            for msg in history
        ]
    
    def clear_dialog(self, user_id: int) -> bool:
        """Очистка активного диалога"""
        if user_id in self.active_dialogs:
            del self.active_dialogs[user_id]
            logger.info(f"Cleared active dialog for user {user_id}")
            return True
        return False
    
    def switch_model(self, user_id: int, model: str) -> bool:
        """Переключение модели в активном диалоге"""
        dialog = self.get_active_dialog(user_id)
        
        if not dialog:
            # Если нет активного диалога - создаем новый с выбранной моделью
            self.create_dialog(user_id, model)
            logger.info(f"Created new dialog with model {model} for user {user_id}")
            return True
        
        old_model = dialog.current_model
        dialog.current_model = model
        logger.info(f"Switched from {old_model} to {model} for user {user_id}")
        
        # Отладочная информация
        logger.info(f"Dialog hash: {dialog.dialog_hash}")
        logger.info(f"Total messages: {len(dialog.messages)}")
        return True
    
    def get_user_dialogs(self, user_id: int) -> List[Dialog]:
        """Получение всех диалогов пользователя"""
        return self.dialogs.get(user_id, [])
    
    def _log_message(self, user_id: int, dialog_hash: str, message: Message):
        """Логирование сообщения в файл"""
        try:
            log_entry = {
                "user_id": user_id,
                "dialog_hash": dialog_hash,
                "timestamp": datetime.fromtimestamp(message.timestamp).isoformat(),
                "role": message.role,
                "model": message.model,
                "content": message.content[:500]
            }
            
            with open(f"dialog_logs/dialogs.log", "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
            
            user_log_dir = f"dialog_logs/user_{user_id}"
            os.makedirs(user_log_dir, exist_ok=True)
            
            with open(f"{user_log_dir}/{dialog_hash}.log", "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
                
        except Exception as e:
            logger.error(f"Error logging message: {e}")
    
    def export_dialog(self, user_id: int, dialog_hash: str) -> Optional[str]:
        """Экспорт диалога в читаемый формат"""
        dialog = self.get_dialog(user_id, dialog_hash)
        if not dialog:
            return None
        
        export_text = f"Диалог #{dialog_hash}\n"
        export_text += f"Создан: {datetime.fromtimestamp(dialog.created_at)}\n"
        export_text += f"Модель: {dialog.current_model}\n"
        export_text += f"Сообщений: {len(dialog.messages)}\n\n"
        
        for msg in dialog.messages:
            role = "👤 Вы" if msg.role == "user" else "🤖 Бот"
            time_str = datetime.fromtimestamp(msg.timestamp).strftime("%H:%M")
            model_info = f" ({msg.model})" if msg.model != "unknown" else ""
            export_text += f"{role}{model_info} ({time_str}):\n{msg.content}\n\n"
        
        return export_text
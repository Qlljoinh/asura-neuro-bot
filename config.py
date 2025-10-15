import os
import re
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Telegram Bot Token
    TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
    
    # GigaChat API
    GIGACHAT_AUTH_KEY = os.getenv('credentials')
    GIGACHAT_SCOPE = os.getenv('GIGACHAT_SCOPE', 'GIGACHAT_API_PERS')
    
    # DeepSeek API
    DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY', 'sk-0b0b6296377d4aa6b48b356da32ec37d')
    DEEPSEEK_BASE_URL = os.getenv('DEEPSEEK_BASE_URL', 'https://api.deepseek.com')
    
    # SSL settings
    IGNORE_SSL_ERRORS = os.getenv('IGNORE_SSL_ERRORS', 'true').lower() == 'true'
    
    # Redis для rate limiting
    REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
    
    # Rate limiting settings
    MAX_REQUESTS_PER_MINUTE = int(os.getenv('MAX_REQUESTS_PER_MINUTE', '10'))
    MAX_REQUESTS_PER_USER = int(os.getenv('MAX_REQUESTS_PER_USER', '60'))
    
    # Model settings
    DEFAULT_MODEL = os.getenv('DEFAULT_MODEL', 'GigaChat:latest')
    DEFAULT_TEMPERATURE = float(os.getenv('DEFAULT_TEMPERATURE', '0.87'))
    
    # Image generation settings
    DEFAULT_IMAGE_MODEL = "GigaChat:latest"
    IMAGE_SIZE = "1024x1024"
    IMAGE_QUALITY = "standard"
    
    @classmethod
    def validate(cls):
        errors = []
        
        # Validate Telegram token
        if not cls.TELEGRAM_TOKEN:
            errors.append("TELEGRAM_TOKEN is required")
        elif cls.TELEGRAM_TOKEN == 'your_telegram_bot_token_here':
            errors.append("TELEGRAM_TOKEN must be replaced with actual token from @BotFather")
        elif not cls._is_valid_telegram_token(cls.TELEGRAM_TOKEN):
            errors.append("TELEGRAM_TOKEN format is invalid")
        
        # Validate GigaChat credentials
        if not cls.GIGACHAT_AUTH_KEY:
            errors.append("credentials is required")
        elif cls.GIGACHAT_AUTH_KEY == 'your_base64_auth_key_here':
            errors.append("credentials must be replaced with actual Base64 auth key")
        
        if errors:
            error_message = "\n".join([f"❌ {error}" for error in errors])
            raise ValueError(f"Configuration errors:\n{error_message}")
    
    @staticmethod
    def _is_valid_telegram_token(token: str) -> bool:
        pattern = r'^\d{9,10}:[a-zA-Z0-9_-]{35}$'
        return re.match(pattern, token) is not None
    
    @classmethod
    def print_config_summary(cls):
        print("🔧 Configuration Summary:")
        print(f"   Telegram Token: {'✅ Set' if cls.TELEGRAM_TOKEN and cls.TELEGRAM_TOKEN != 'your_telegram_bot_token_here' else '❌ Not set'}")
        print(f"   GigaChat Auth Key: {'✅ Set' if cls.GIGACHAT_AUTH_KEY and cls.GIGACHAT_AUTH_KEY != 'your_base64_auth_key_here' else '❌ Not set'}")
        print(f"   DeepSeek API Key: {'✅ Set' if cls.DEEPSEEK_API_KEY else '❌ Not set'}")
        print(f"   Scope: {cls.GIGACHAT_SCOPE}")
        print(f"   SSL Ignore: {'✅ Enabled' if cls.IGNORE_SSL_ERRORS else '❌ Disabled'}")
        print(f"   Default Model: {cls.DEFAULT_MODEL}")
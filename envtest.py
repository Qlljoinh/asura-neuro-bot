import os
from dotenv import load_dotenv

def check_env_file():
    print("🔍 Checking .env file...")
    
    if not os.path.exists('.env'):
        print("❌ .env file not found!")
        print("💡 Creating .env.example for you...")
        
        with open('.env.example', 'w', encoding='utf-8') as f:
            f.write("""# Telegram Bot Token from @BotFather
TELEGRAM_TOKEN=your_telegram_bot_token_here

# GigaChat API credentials
GIGACHAT_CLIENT_ID=your_client_id_here
GIGACHAT_AUTH_TOKEN=your_auth_token_here
GIGACHAT_SCOPE=GIGACHAT_API_PERS

# SSL settings
IGNORE_SSL_ERRORS=true

# Redis
REDIS_URL=redis://localhost:6379/0

# Rate limiting
MAX_REQUESTS_PER_MINUTE=60
MAX_REQUESTS_PER_USER=10

# Model settings
DEFAULT_MODEL=GigaChat:latest
DEFAULT_TEMPERATURE=0.87
""")
        print("✅ .env.example created. Please copy it to .env and fill in your credentials")
        return False
    
    # Загружаем .env
    load_dotenv()
    
    # Проверяем обязательные переменные
    required_vars = [
        'TELEGRAM_TOKEN',
        'GIGACHAT_CLIENT_ID', 
        'GIGACHAT_AUTH_TOKEN'
    ]
    
    missing_vars = []
    for var in required_vars:
        value = os.getenv(var)
        if not value or value == f'your_{var.lower()}_here':
            missing_vars.append(var)
    
    if missing_vars:
        print("❌ Missing or invalid variables in .env:")
        for var in missing_vars:
            print(f"   - {var}")
        print("\n💡 Please fill in all required variables in .env file")
        return False
    
    print("✅ .env file is properly configured!")
    print(f"   TELEGRAM_TOKEN: {os.getenv('TELEGRAM_TOKEN')[:15]}...")
    print(f"   GIGACHAT_CLIENT_ID: {os.getenv('GIGACHAT_CLIENT_ID')}")
    print(f"   GIGACHAT_AUTH_TOKEN: {os.getenv('GIGACHAT_AUTH_TOKEN')[:15]}...")
    
    return True

if __name__ == "__main__":
    check_env_file()
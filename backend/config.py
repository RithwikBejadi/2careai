from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str
    REDIS_URL: str

    GOOGLE_API_KEY: str = ""
    GEMINI_API_KEY: str = ""

    OPENAI_API_KEY: str = ""
    DEEPGRAM_API_KEY: str
    ELEVENLABS_API_KEY: str

    TWILIO_ACCOUNT_SID: str
    TWILIO_AUTH_TOKEN: str
    TWILIO_PHONE_NUMBER: str

    LANGCHAIN_TRACING_V2: str = "true"
    LANGCHAIN_API_KEY: str = ""

    VOICE_EN: str = "21m00Tcm4TlvDq8ikWAM"
    VOICE_HI: str = "AZnzlk1XvdvUeBnXmlld"
    VOICE_TA: str = "EXAVITQu4vr4xnSDxMaL"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()


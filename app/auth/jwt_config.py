from dotenv import load_dotenv

from app.utils.env import get_required_env


load_dotenv()

SECRET_KEY = get_required_env("SECRET_KEY")
ALGORITHM = get_required_env("ALGORITHM")

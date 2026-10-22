# Load the private .env (repo root) before any module reads os.environ.
from dotenv import load_dotenv

load_dotenv()

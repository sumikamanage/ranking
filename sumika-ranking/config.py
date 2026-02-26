
import os




# --- DB_PATH をこのファイルと同じディレクトリに固定 ---
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DB_PATH = os.path.join(BASE_DIR, "messages.db")

TOKEN = os.getenv("TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID"))
APP_ID = int(os.getenv("APPLICATION_ID"))

LOG_CHANNEL_ID = 1276087091280871546

FOOTER = os.getenv("footer")

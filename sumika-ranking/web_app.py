from flask import Flask, send_file
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Flaskサーバー
app = Flask(
    __name__,
    static_folder=os.path.join(BASE_DIR, "static"),
    static_url_path="/static",
)

# 自分で適当に作ったキー
app.secret_key = os.getenv("FLASK_SECRET_KEY")

# これがHPに出てくる
@app.route('/')
def home():
    return "Go",200



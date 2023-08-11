from pymongo import MongoClient
from langchain.embeddings import OpenAIEmbeddings
from dotenv import load_dotenv
from langchain.vectorstores import Chroma
import os
import requests
import uuid
import json
import shutil
import customUtil as cu

load_dotenv()

db_name = os.environ["DB_NAME"]
persist_directory = os.environ["PERSIST_DIRECTORY"]
source_directory = os.environ["SOURCE_DIRECTORY"]

client = MongoClient('localhost', 27017)

db = client[db_name]

USER_ID = "h1"
USER_PWD = "123"
USER_KEY = os.environ["OPENAI_API_KEY"]
INITIAL_DIR = "./DummyData"
DATA_FILES = os.listdir(INITIAL_DIR)

JSON_FILES = [file for file in DATA_FILES if file.endswith(".json")]
ALL_DATA = []

def initialize():
    #############################################################################################################################################
    # 제거 
    client.drop_database(db_name)
    db.userInfo.insert_one({"user_id": USER_ID, "user_pwd": USER_PWD, "openai_key": USER_KEY, "occupied_channel_id": None}) # 추후 수정
    if os.path.exists(f"./{USER_ID}/db"):
        shutil.rmtree(f"./{USER_ID}/db")
    if os.path.exists(f"./DummyData/db"):
        shutil.copytree(f"./DummyData/db", f"./{USER_ID}/db")
    #############################################################################################################################################


    #############################################################################################################################################
    # 채워넣기
    for json_file in JSON_FILES:
        with open(os.path.join(INITIAL_DIR, json_file), "r", encoding = "utf-8") as file:
            json_data = file.read()
            dict_data = json.loads(json_data)
            ALL_DATA.append(json.loads(json_data))

    for data in ALL_DATA:
        channelInfo = data["channelInfo"]
        channelHistory = data["channelHistory"]
        idInfo = data["idInfo"]
        db.channelInfo.insert_one(channelInfo)
        db.chatHistory.insert_many(channelHistory)
        db.idInfo.insert_many(idInfo)
    #############################################################################################################################################

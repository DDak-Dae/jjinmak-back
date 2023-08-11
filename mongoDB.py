from pymongo import MongoClient
from langchain.embeddings import OpenAIEmbeddings
from dotenv import load_dotenv
from langchain.vectorstores import Chroma
import os
import requests
import uuid
import json
import customUtil as cu
import shutil

load_dotenv()

db_name = os.environ["DB_NAME"]
persist_directory = os.environ["PERSIST_DIRECTORY"]
source_directory = os.environ["SOURCE_DIRECTORY"]

client = MongoClient('localhost', 27017)
db = client[db_name]

embeddings = OpenAIEmbeddings()

#######################################################################
#                            Login Page                               #
#######################################################################
def insertUser(userId, password, openaiKey):
  # print("---------- insertUser 실행 !! ----------")
  #중복되는 아이디 있는지 확인
  if db.userInfo.find_one({'user_id': userId}):
    return "fail", "이미 존재하는 아이디입니다"
  
  url = "https://api.openai.com/v1/engines/davinci"

  #유효한 api key인지 확인
  headers = {
    "Authorization": f"Bearer {openaiKey}",
  }
  response = requests.get(url = url, headers = headers)

  if response.status_code != 200:
    return "fail", "API키가 유효하지 않습니다"
  
  #db에 삽입
  db.userInfo.insert_one({"user_id": userId, "user_pwd": password, "openai_key": openaiKey, "occupied_channel_id": None}) # 추후 수정

  return "success", "회원가입 성공!"

def checkIdPassword(userId, password):
  # print("---------- checkIdPassword 실행 !! ----------")
  result = db.userInfo.find_one({"user_id" : userId, "user_pwd" : password})

  if result == None :
    return "fail", "로그인 실패, 아이디와 비밀번호를 확인해주세요" , None
  
  return "success" , "로그인 성공", result["openai_key"]

#######################################################################
#                            Workspace Page                           #
#######################################################################
def checkChannelId(userId, channelId, imgPath, description = "채널 description입니다."):
  # print("---------- checkChannelId 실행 !! ----------")
  if db.channelInfo.find_one({"user_id": userId, "channel_id": channelId}):
    return "fail", "중복된 이름입니다"

  collectionName = cu.channelId2CollectionName(channelId)
  dummyRootId = db.chatHistory.insert_one({"_id": str(uuid.uuid1()), "user_id": userId, "channel_id": channelId, "child_ids": [], "parent_id": None, "question": channelId, "answer": description, "sources": []}).inserted_id
  result = db.channelInfo.insert_one({"user_id": userId, "channel_id": channelId, "collection_name": collectionName, "description": description, "prev_msg_id": dummyRootId, "word_cloud": [], "img_path": imgPath})
  
  if result == None:
    return "fail", "채널 생성 실패"
  
  return "success", "채널 생성 성공"

def getChannelList(userId):
  result = db.channelInfo.find({'user_id': userId})

  channelInfoList=[]
  for doc in result:
    totalSize = cu.getChannelSize(userId, doc["channel_id"])
    imgDto = cu.getImgDto(doc["img_path"])
    channelInfoList.append({"channelId": doc["channel_id"], "description": doc["description"], "totalSize": totalSize, "wordCloud": doc["word_cloud"], "imgPath": imgDto})

  return "success", channelInfoList

#######################################################################
#                             Vector DB                               #
#######################################################################
def insertFileIdElemId(userId, channelId, data):
  # print("---------- insertFileIdElemId 실행 !! ----------")
  
  for i in range(len(data["file_ids"])):
    db.idInfo.insert_one({"user_id": userId, "channel_id": channelId, "file_id": data["file_ids"][i], "elem_id": []})
    for j in range(len(data["elem_ids"][i])):
      db.idInfo.update_one({"user_id": userId, "channel_id": channelId, "file_id": data["file_ids"][i]}, {"$push": {"elem_id": data["elem_ids"][i][j]}})

  return "sucess", "파일이 디렉토리와 벡터 DB에 저장되었습니다"

def getOccupiedChannelId(userId):
  # print("---------- getOccupiedChannelId 실행 !! ----------")
  result = db.userInfo.find_one({"user_id": userId})
  return result["occupied_channel_id"]

def getPrevMsgId(userId, channelId):
  # print("---------- getPrevMsgId 실행 !! ----------")
  result = db.channelInfo.find_one({"user_id": userId, "channel_id": channelId})
  return result["prev_msg_id"]

def getCollectionName(userId, channelId):
  # print("---------- getCollectionName 실행 !! ----------")
  result = db.channelInfo.find_one({"user_id": userId, "channel_id": channelId})
  return result["collection_name"]

def updatePrevMsgId(userId, channelId, newMsgId):
  # print("---------- updatePrevMsgId 실행 !! ----------")
  db.channelInfo.update_one({"user_id": userId, "channel_id": channelId}, {"$set": {"prev_msg_id": newMsgId}})

def updateWordCloud(userId, channelId, wordCloud):
  # print("---------- updateWordCloud 실행 !! ----------")
  for word in wordCloud:
    db.channelInfo.update_one({"user_id": userId, "channel_id": channelId}, {"$addToSet": {"word_cloud": word}})

def updateOccupiedChannel(userId, channelId):
  # print("---------- updateOccupiedChannel 실행 !! ----------")
  db.userInfo.update_one({"user_id": userId}, {"$set": {"occupied_channel_id": channelId}})

def giveMsgId(userId, question, answer, curMsgId, modifyId = None, sources = None):
  # print("---------- giveMsgId 실행 !! ----------")
  channelId = getOccupiedChannelId(userId)
  prevMsgId = getPrevMsgId(userId, channelId)

  # 기존 context에 채팅을 이어갈 때
  if modifyId is None:
    db.chatHistory.insert_one({"_id": curMsgId, "user_id": userId, "channel_id": channelId, "child_ids": [], "parent_id": prevMsgId, "question": question, "answer": answer, "sources": sources})
    # 현재 메시지ID를 이전 메시지의 자식으로 추가
    db.chatHistory.update_one({"_id": prevMsgId, "user_id": userId, "channel_id": channelId}, {"$push": {"child_ids": curMsgId}})

    updatePrevMsgId(userId, channelId, curMsgId)
  else:
    # curMsgId의 부모를 찾고, 새로 생성될 메시지의 부모로 지정 해줌
    parentMsgId = db.chatHistory.find_one({"_id": curMsgId, "user_id": userId, "channel_id": channelId})["parent_id"]
    # 새로 생성된 메시지의 ID를 받아옴
    db.chatHistory.insert_one({"_id": modifyId, "user_id": userId, "channel_id": channelId, "child_ids": [], "parent_id": parentMsgId, "question": question, "answer": answer, "sources": sources})
    # 부모 메시지의 자식으로 추가
    db.chatHistory.update_one({"_id": parentMsgId, "user_id": userId, "channel_id": channelId}, {"$push": {"child_ids": modifyId}})

    updatePrevMsgId(userId, channelId, modifyId)

def giveAllMsg(userId, channelId):
  # parent_id가 null인걸 찾음 -> 최상위
  channelId = db.userInfo.find_one({"user_id": userId})["occupied_channel_id"]
  rootResult = db.chatHistory.find_one({"user_id": userId, "channel_id": channelId, "parent_id": None})

  # 전위 순회
  if rootResult:
    dto = {}
    rootMsgId = rootResult["_id"]
    preorderMakeDto(userId, channelId, rootMsgId, dto)
    jsonData = json.dumps(dto, ensure_ascii = False, indent = 4)
    
    # with open('계층구조.json', 'w', encoding = 'utf-8') as json_file:
    #   json.dump(dto, json_file, ensure_ascii = False, indent = 6)
    
    # # print(jsonData)

  return jsonData

# 프론트에 전해줄 계층구조 json data를 만드는 함수. giveAllMsg 함수에 종속되어 있음.
def preorderMakeDto(userId, channelId, curMsgId, msgDto):
  curRow = db.chatHistory.find_one({"_id": curMsgId, "user_id": userId, "channel_id": channelId})

  if not curRow:
    return

  msgDto["id"] = curRow["_id"]
  msgDto["question"] = curRow["question"]
  msgDto["answer"] = curRow["answer"]
  msgDto["childs"] = []

  for child_id in curRow["child_ids"]:
    child_dto = {}
    preorderMakeDto(userId, channelId, child_id, child_dto)
    msgDto["childs"].append(child_dto)

def getMsgContext(userId, channelId, msgId = None):
  chatContext = []

  if msgId is None:
    msgId = getPrevMsgId(userId, channelId)
  else:
    updatePrevMsgId(userId, channelId, msgId)
  result = db.chatHistory.find_one({"user_id": userId, "channel_id": channelId, "_id": msgId})


  while result["parent_id"]:
    imgPaths = result["sources"]
    imgDtos = cu.getImgDtos(imgPaths)
    sourceList = cu.getImgTuple(imgDtos, imgPaths)

    chatContext.append({"role": "gpt", "message": result["answer"], "id": result["_id"], "sourceList": sourceList})
    chatContext.append({"role": "user", "message": result["question"], "id": result["_id"]})
    result = db.chatHistory.find_one({"user_id": userId, "channel_id": channelId, "_id": result["parent_id"]})

  return list(reversed(chatContext))

def addBookmark(userId, imgPath, bookmarkName, chatList):
  channelId = getOccupiedChannelId(userId)

  db.bookmark.insert_one({"user_id": userId, "channel_id": channelId, "img_path": cu.getImgDto(imgPath), "bookmark_name": bookmarkName, "chat_list": chatList})

def getBookmark(userId):
  channelId = getOccupiedChannelId(userId)

  bookmarkList = []
  results = db.bookmark.find({"user_id": userId, "channel_id": channelId})

  for result in results:
    bookmark = {
      "bookmarkName": result["bookmark_name"],
      "imgPath": result["img_path"],
      "chatList": result["chat_list"]
    }
    bookmarkList.append(bookmark)

  return bookmarkList

def initialize():
  USER_ID = "h1"
  USER_PWD = "123"
  USER_KEY = os.environ["OPENAI_API_KEY"]
  INITIAL_DIR = "./DummyData"
  DATA_FILES = os.listdir(INITIAL_DIR)

  JSON_FILES = [file for file in DATA_FILES if file.endswith(".json")]
  ALL_DATA = []
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






def delFileIdElemId(fileId, userId, channelId):
  # print("---------- delFileIdElemId 실행 !! ----------")

  dbPath = f"./{userId}/db"
  vdb = Chroma(
    persist_directory = dbPath, 
    embedding_function = embeddings, 
    collection_name = getCollectionName(userId, channelId),
  )

  cursor = db.idInfo.find({"file_id": fileId})
  
  if cursor == None :
    # print("No file")
    return
  
  for doc in cursor:
    vdb.delete(doc["elem_id"])
    db.idInfo.delete_one({"_id": doc["_id"]})
    # print(doc['elem_id'])
    # print(doc)

  # print("Delete! sucess")
  vdb.persist()
from flask import Flask, request, jsonify, send_file, make_response
from werkzeug.utils import secure_filename
from ingest import Ingest
import os
from flask_cors import CORS
import mongoDB
from pathlib import Path
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity, get_jwt
from datetime import timedelta
from ingest import Ingest
import gpt
import customUtil as cu
import init

source_dir = os.environ.get('SOURCE_DIRECTORY')

#Flask 객체 인스턴스 생성
app = Flask(__name__)
app.config['DEBUG'] = True
app.config["JWT_SECRET_KEY"] = "TYcR0KGj-PcBvILq"  # JWT 비밀키 설정
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(seconds = 60 * 600) # 600분
CORS(app)
jwt = JWTManager(app)

#######################################################################
#                           Check token                               # 
#######################################################################
@app.route("/api/token", methods=["GET"])
@jwt_required()  # 토큰의 유효성 검사
def token():
  print("---------- token 실행 !! ----------")
  current_user = get_jwt_identity()
  return jsonify({"result": "success", "message": f"안녕하세요, {current_user}님!"}), 200

#######################################################################
#                            Login Page                               # 
#######################################################################
@app.route('/api/login', methods=['POST'])
def login():
  print("---------- login 실행 !! ----------")
  data = request.json

  userId = data['userId']
  password = data['password']
  result, message, openaiKey = mongoDB.checkIdPassword(userId, password)
  
  if result == "fail":
    return jsonify({"result": result, "message": message, "token": None})

  access_token = create_access_token(identity = userId, additional_claims = {"openaiKey": openaiKey, "userId": userId})

  return jsonify({"result": result, "message": message, "token": access_token})

#######################################################################
#                            Join Page                               # 
#######################################################################
@app.route('/api/join', methods=['POST'])
def join():
  print("---------- join 실행 !! ----------")
  data = request.json

  userId = data['userId']
  password = data['password']
  openaiKey = data['openaiKey']
  
  result, message = mongoDB.insertUser(userId, password, openaiKey)

  if result == "success":
    path = f"./{userId}"
    cu.makeDirectory(path)

  return jsonify({"result": result, "message": message})

#######################################################################
#                          Workspace Page                             #
#######################################################################
@app.route('/api/getWorkspaceData', methods=['GET']) # 접속하는 url
@jwt_required() 
def getWorkspaceData():
  print("---------- getWorkspaceData 실행 !! ----------")
  data = get_jwt()

  userId = data["userId"]
  result, channelInfoList= mongoDB.getChannelList(userId)
  
  return jsonify({"result": result, "channelInfoList": channelInfoList })

@app.route('/api/createChannel', methods=['POST']) # 접속하는 url
@jwt_required() 
def createChannel():
  print("---------- createChannel 실행 !! ----------")

  userId = get_jwt()["userId"]
  channelId = request.form["channelId"]
  description = request.form["description"]
  image = request.files["imgFile"]

  fileName = secure_filename(image.filename)
  imgDir = f"./{userId}/ChannelImg"
  imgPath = f"{imgDir}/{fileName}"
  cu.makeDirectory(imgDir)
  image.save(imgPath)

  imgUrl = cu.getImgDto(imgPath)
  result, message = mongoDB.checkChannelId(userId, channelId, imgPath, description)

  if result == "success":
    path = Path(f"./{userId}/{channelId}")
    path.mkdir(parents = True, exist_ok = True)

  # 성공일시 프론트에서 workspaceId 기억.
  return jsonify({"result": result, "message": message, "imgUrl": imgUrl})

#######################################################################
#                           Channel Page                           #
#######################################################################
@app.route('/api/getChannelData', methods=['POST']) # 접속하는 url
@jwt_required() 
def getChannelData():
  print("---------- getChannelData 실행 !! ----------")
  data = request.json

  userId = get_jwt()["userId"]
  channelId = data["channelId"]
  mongoDB.updateOccupiedChannel(userId, channelId)
  msgId = data.get("msgId")
  channelPath = f"./{userId}/{channelId}"
  
  all_files_and_dirs = os.listdir(channelPath)
  fileList = []
  for file in all_files_and_dirs:
    fileList.append({"fileName": f"{channelId}/{file}"})

  print("@@@@@@@@@@@", msgId)
  messageList = mongoDB.getMsgContext(userId, channelId, msgId)

  return jsonify({"result": "success", "fileList": fileList, "messageList": messageList})

@app.route('/api/chat', methods=['POST']) # 접속하는 url
@jwt_required() 
def chat():
  print("---------- chat 실행 !! ----------")
  data = request.json

  userId = get_jwt()["userId"]
  query = data["message"]
  id = data["id"]

  result, answer, source_list = gpt.GPT(userId, query, id) ####### 추후 수정

  return jsonify({"result": result, "answer": answer, "sourceList": source_list})

@app.route('/api/modify', methods=['POST'])
@jwt_required() 
def modify():
  print("---------- modify 실행 !! ----------")
  data = request.json

  userId = get_jwt()["userId"]
  prevMsgId = data["preMsgId"]
  postMsgId = data["postMsgId"]
  query = data["message"]

  result, answer, source_list = gpt.GPT(userId, query, prevMsgId, postMsgId)

  return jsonify({"result": result, "answer": answer, "sourceList": source_list})

@app.route('/api/upload', methods=['POST'])
@jwt_required() 
def upload():
  print("---------- upload 실행 !! ----------")

  userId = get_jwt()["userId"]
  channelId = request.form.get('channelId')
  files = request.files.getlist('files[]')
  channelPath = f"./{userId}/{channelId}"

  cu.makeDirectory(channelPath)

  for file in files:
    file.save(f"{channelPath}/{secure_filename(file.filename)}")

  result, message, data, sendData = Ingest(userId, channelPath, channelId)
  
  if result == "success" and data:
    result, message = mongoDB.insertFileIdElemId(userId, channelId, data)
  
  return jsonify({'result': result, "message": message, "fileList": sendData})

@app.route('/api/downloadRef', methods=['POST'])
@jwt_required() 
def downloadRef():
  print("downloadRef 실행 !!")
  data = request.json
  
  userId = get_jwt()["userId"]
  channelId = mongoDB.getOccupiedChannelId(userId)
  imgPaths = data["imagePath"]

  pdfName, pdfPath = cu.img2Pdf(userId, imgPaths)

  response = make_response(send_file(pdfPath, mimetype = 'application/pdf'))
  response.headers['Content-Disposition'] = f"attachment; filename = {pdfName}"

  return response

@app.route('/api/tree', methods=['POST'])
@jwt_required() 
def tree():
  print("tree 실행 !!")
  # data = request.json

  userId = get_jwt()["userId"]
  channelId = mongoDB.getOccupiedChannelId(userId)

  jsonData = mongoDB.giveAllMsg(userId, "notion")
  print(jsonData)

  return jsonData

@app.route('/api/selectContext', methods=['POST'])
@jwt_required() 
def selectContext():
  print("selectContext 실행 !!")
  userId = get_jwt()["userId"]

  return jsonify({"result": "success", "channelId": mongoDB.getOccupiedChannelId(userId)})

@app.route('/api/addBookmark', methods=['POST'])
@jwt_required() 
def addBookmark():
  print("---------- addBookmark 실행 !! ----------")
  userId = get_jwt()["userId"]

  image = request.files["bookMarkPhoto"]
  bookmarkName = request.form.get("bookMarkName")
  chatList = request.form.get("bookMarkChatData")

  imgDir = f"./{userId}/bookMarkImg"
  fileName = secure_filename(image.filename)
  imgPath = f"{imgDir}/{fileName}"

  if not os.path.exists(imgDir):
    os.mkdir(path = imgDir)

  image.save(imgPath)
  mongoDB.addBookmark(userId, imgPath, bookmarkName, chatList)

  return jsonify({"result": "success"})

@app.route('/api/getBookmark', methods=['POST'])
@jwt_required() 
def getBookmark():
  print("---------- getBookmark 실행 !! ----------")
  userId = get_jwt()["userId"]

  bookmarkList = mongoDB.getBookmark(userId)

  return jsonify({"result": "success", "bookmarkList": bookmarkList})

@app.route('/api/initialize', methods=['GET'])
def initialize():
  # init.initialize()
  mongoDB.initialize()
  return "초기화 완료"

# @app.route('/api/delete', methods=['POST'])
# @jwt_required()
# def delete():
#     print("delete 실행 !!")
    
#     # 데이터 받기
#     data = request.json  # 전달된 JSON 데이터를 파싱
#     userId = get_jwt()["userId"]
#     channelId = data["channelId"]  # channelId 추출

#     deletedFileName = data["deletedFileName"]  # deletedFile 추출
#     deletedFileId = data["deletedFileId"]  # deletedFile 추출
    
#     os.unlink(f"./{userId}/{deletedFileName}")
    
#     # MongoDB 작업 수행
#     mongoDB.delFileIdElemId(deletedFileId, userId, channelId)
    
#     return jsonify({'result': 'success'})

if __name__=="__main__":
  app.run(host = "localhost", port = "5002", debug = True)
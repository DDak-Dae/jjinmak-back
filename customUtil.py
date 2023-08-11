import base64
import fitz
import uuid
import os
from PIL import Image
import re
from chromadb.config import Settings

def pdfPage2Image(userId, sources: list) -> list:
    imgDtos = []
    imgPaths = []
    
    if not os.path.exists(f"./{userId}/refDocuments"):
        os.mkdir(path = f"./{userId}/refDocuments")

    for source, page in sources:
        imgName = f"{os.path.basename(source).split('.')[0]}#{page + 1}.png"
        imgPath = os.path.join(f"./{userId}/refDocuments", imgName)
        imgPaths.append(imgPath)

        if os.path.exists(imgPath):
            imgPathDto = getImgDto(imgPath)
            imgDtos.append(imgPathDto)
            continue

        pdfDocument = fitz.open(source)
        page = pdfDocument.load_page(page)

        img = page.get_pixmap(dpi = 300)
        img.save(imgPath)

        pdfDocument.close()

        imgPathDto = getImgDto(imgPath)
        imgDtos.append(imgPathDto)

    return imgDtos, imgPaths

# 이미지를 pdf로 만들기
def img2Pdf(userId, sources):

    pdfName = "refDocument#" + str(uuid.uuid1()) + ".pdf"
    pdfPath = "./" + userId + "/" + "refDocuments/" + pdfName

    img_main = Image.open(sources[0])
    img_main_rgb = img_main.convert("RGB")
    if len(sources) == 1:
        img_main_rgb.save(pdfPath, dpi = (300, 300))
    else:
        img_list = []
        for source in sources[1:]:
            img = Image.open(source)
            img_rgb = img.convert("RGB")
            img_list.append(img_rgb)

        img_main_rgb.save(pdfPath, save_all = True, dpi = (300, 300), append_images = img_list)

    return pdfName, pdfPath

def getChannelSize(userId, channelId):
    totalSize = 0

    channelPath = f"./{userId}/{channelId}"

    for dirpath, dirnames, filenames in os.walk(channelPath):
        for filename in filenames:
            filePath = os.path.join(dirpath, filename)
            totalSize += os.path.getsize(filePath)
            
    return totalSize

def channelId2CollectionName(channelId):
    pattern = r'[^a-zA-Z0-9]'
    serialNum = re.sub(pattern, '', str(uuid.uuid1()))
    channelId = channelId.replace(" ", "")

    sum = 0
    for ch in channelId:
        sum += ord(ch)

    collectionName = f"{sum}" + serialNum
    
    return collectionName

def getImgDto(imgPath):
    with open(imgPath, 'rb') as f:
        imageData = f.read()
        imageBase64 = base64.b64encode(imageData).decode('utf-8')

    imgPathDto = "data:image/jpeg;base64," + imageBase64
    
    return imgPathDto

def getImgDtos(imgPaths):
    imgDtos = []

    for imgPath in imgPaths:
        with open(imgPath, 'rb') as f:
            imageData = f.read()
            imageBase64 = base64.b64encode(imageData).decode('utf-8')

        imgPathDto = "data:image/jpeg;base64," + imageBase64
        imgDtos.append(imgPathDto)
    
    return imgDtos

def getImgTuple(imgDtos, imgPaths):
    sourceList = []
    
    for dto, path in zip(imgDtos, imgPaths):
        sourceList.append((dto, path))

    return sourceList

def makeDirectory(path):
    if not os.path.exists(path):
        os.mkdir(path = path)

def getChromaSettings(userId):
    chroma_settings = Settings(
        chroma_db_impl = 'duckdb + parquet',
        persist_directory = f'./{userId}/db',
        anonymized_telemetry = False
    )

    return chroma_settings
#!/usr/bin/env python3
import os
import glob
from typing import List
from dotenv import load_dotenv
from multiprocessing import Pool
from tqdm import tqdm
from langchain.embeddings import OpenAIEmbeddings
import uuid
from langchain.document_loaders import (
    CSVLoader,
    EverNoteLoader,
    PyMuPDFLoader,
    TextLoader,
    UnstructuredEmailLoader,
    UnstructuredEPubLoader,
    UnstructuredHTMLLoader,
    UnstructuredMarkdownLoader,
    UnstructuredODTLoader,
    UnstructuredPowerPointLoader,
    UnstructuredWordDocumentLoader,
)
from langchain.text_splitter import RecursiveCharacterTextSplitter, CharacterTextSplitter
from langchain.vectorstores import Chroma
from langchain.embeddings import HuggingFaceEmbeddings
from langchain.docstore.document import Document

import gpt
import mongoDB as mg
import customUtil as cu

load_dotenv()

chunk_size = 500
chunk_overlap = 100

LOADER_MAPPING = {
    ".csv": (CSVLoader, {}),
    ".doc": (UnstructuredWordDocumentLoader, {}),
    ".docx": (UnstructuredWordDocumentLoader, {}),
    ".enex": (EverNoteLoader, {}),
    ".epub": (UnstructuredEPubLoader, {}),
    ".html": (UnstructuredHTMLLoader, {}),
    ".md": (UnstructuredMarkdownLoader, {"encoding": "utf-8"}),
    ".odt": (UnstructuredODTLoader, {}),
    ".pdf": (PyMuPDFLoader, {}),
    ".ppt": (UnstructuredPowerPointLoader, {}),
    ".pptx": (UnstructuredPowerPointLoader, {}),
    ".txt": (TextLoader, {"encoding": "utf-8"}),
}

def load_single_document(file_path: str) -> List[Document]:
    ext = "." + file_path.rsplit(".", 1)[-1]
    if ext in LOADER_MAPPING:
        loader_class, loader_args = LOADER_MAPPING[ext]
        loader = loader_class(file_path, **loader_args)
        return loader.load()

    raise ValueError(f"Unsupported file extension '{ext}'")

def load_documents(source_dir: str, ignored_files: List[str] = []) -> List[Document]:
    all_files = []
    for ext in LOADER_MAPPING:
        all_files.extend(
            glob.glob(os.path.join(source_dir, f"**/*{ext}"), recursive=True)
        )
    filtered_files = [file_path for file_path in all_files if file_path not in ignored_files]

    with Pool(processes=os.cpu_count()) as pool:
        results = []
        with tqdm(total=len(filtered_files), desc='Loading new documents', ncols=80) as pbar:
            for i, docs in enumerate(pool.imap_unordered(load_single_document, filtered_files)):
                results.extend(docs)
                pbar.update()
    
    return results

def process_documents(userId, channelId, source_directory, ignored_files: List[str] = []) -> List[Document]:
    # print(f"Loading documents from {source_directory}")
    documents = load_documents(source_directory, ignored_files)
    if not documents:
        # print("No new documents to load")
        return None
    # print(f"Loaded {len(documents)} new documents from {source_directory}")
    # text_splitter = CharacterTextSplitter.from_tiktoken_encoder(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    text_splitter = RecursiveCharacterTextSplitter(chunk_size = chunk_size, chunk_overlap = chunk_overlap)
    texts = text_splitter.split_documents(documents)

    #####################################################################
    wordCloud = gpt.getWordCloud(texts) # 비동기 처리로 전환해야함.
    mg.updateWordCloud(userId, channelId, wordCloud)
    #####################################################################

    # print(f"Split into {len(texts)} chunks of text (max. {chunk_size} tokens each)")
    return texts

def does_vectorstore_exist(persist_directory: str) -> bool:
    if not os.path.exists(persist_directory):
        return False

    if os.path.exists(os.path.join(persist_directory, 'index')):
        if os.path.exists(os.path.join(persist_directory, 'chroma-collections.parquet')) and os.path.exists(os.path.join(persist_directory, 'chroma-embeddings.parquet')):
            list_index_files = glob.glob(os.path.join(persist_directory, 'index/*.bin'))
            list_index_files += glob.glob(os.path.join(persist_directory, 'index/*.pkl'))
            # At least 3 documents are needed in a working vectorstore
            if len(list_index_files) > 3:
                return True
    return False

def make_id(texts):
    # db_data는 mongoDB에 insert하기 위해 필효
    db_data = {
        "file_ids": [],
        "elem_ids": [],
    }
    
    # response_data는 Front에게 정보를 전달하기 위해 필요
    response_data = {
        "file_names" : [],
        "file_ids" : []
    }
    
    ids = []
    before_name = texts[0].metadata['source']
    
    db_data["file_ids"].append(str(uuid.uuid1()))
    
    #Front에 response로 담을 내용 추가
    response_data["file_names"].append(before_name) 
    response_data["file_ids"].append(db_data["file_ids"][-1])
    
    
    id = str(uuid.uuid1())
    temp_ids = [id]
    ids.append(id)

    for i in range(1,len(texts)) :
        cur_name = texts[i].metadata['source']
        id = str(uuid.uuid1())
        if cur_name != before_name:
            db_data["elem_ids"].append(temp_ids)
            
            db_data["file_ids"].append(str(uuid.uuid1()))
            #Front에 response로 담을 내용 추가
            response_data["file_names"].append(cur_name)
            response_data["file_ids"].append(db_data["file_ids"][-1])
            
            temp_ids = [id]
            # print("file name : ", cur_name)
            # print("file id ",db_data["file_ids"][-1])
            
        else : temp_ids.append(id)
        
        ids.append(id)
        before_name = cur_name
        
    db_data["elem_ids"].append(temp_ids)
    
    return response_data, db_data, ids

# def main():
def Ingest(userId, channelPath, channelId):
    embeddings = OpenAIEmbeddings()
    dbPath = f"./{userId}/db"

    if does_vectorstore_exist(dbPath):
        # print(f"Appending to existing vectorstore at {dbPath}")
        db = Chroma(
            persist_directory = dbPath, 
            embedding_function = embeddings, 
            collection_name = mg.getCollectionName(userId, channelId),
        )
        collection = db.get()
        texts = process_documents(
            userId = userId, 
            channelId = channelId, 
            source_directory = channelPath, 
            ignored_files = [metadata['source'] for metadata in collection['metadatas']],
        )
        if texts == None :
            return "success", "이미 저장된 파일입니다.", None, []

        # print(f"Creating embeddings. May take some minutes...")
        response_data, db_data, ids = make_id(texts)
        db.add_documents(texts, ids = ids)
    else:
        # print("Creating new vectorstore")
        texts = process_documents(
            userId = userId, 
            channelId = channelId, 
            source_directory = channelPath
        )

        if texts == None :
            return "success", "이미 저장된 파일입니다.", None, []
        
        # print(f"Creating embeddings. May take some minutes...")
        response_data, db_data, ids = make_id(texts)
        db = Chroma.from_documents(
            documents = texts, 
            embedding = embeddings, 
            persist_directory = dbPath,
            ids = ids,
            collection_name = mg.getCollectionName(userId, channelId),
        )
        
    db.persist()
    db = None

    # print(f"Ingestion complete! You can now run privateGPT.py to query your documents")
    
    sendData = []
    for i in range(len(response_data["file_names"])):
        # print(response_data["file_names"][i], response_data["file_ids"][i])
        temp = {"fileName" : response_data["file_names"][i].split('/')[-1], "fileId" : response_data["file_ids"][i]}
        sendData.append(temp)

    return "success", "벡터 DB에 저장 완료!", db_data, sendData

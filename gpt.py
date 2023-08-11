#!/usr/bin/env python3
from dotenv import load_dotenv
from langchain.chains import RetrievalQA, ConversationalRetrievalChain, AnalyzeDocumentChain, RetrievalQAWithSourcesChain
from langchain.vectorstores import Chroma
from langchain.llms import GPT4All, LlamaCpp
from langchain.schema import HumanMessage, SystemMessage
from langchain.embeddings import OpenAIEmbeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.llms import OpenAI
from langchain.chat_models import ChatOpenAI
from langchain.prompts import PromptTemplate
from langchain.chains.question_answering import load_qa_chain
from langchain.memory import ConversationBufferMemory, VectorStoreRetrieverMemory
from collections import Counter
from langchain.chains import LLMChain, ConversationChain
from langchain.chains.conversational_retrieval.prompts import CONDENSE_QUESTION_PROMPT
from langchain.chains.qa_with_sources import load_qa_with_sources_chain
import re
from langchain.prompts import PromptTemplate, ChatPromptTemplate, SystemMessagePromptTemplate, HumanMessagePromptTemplate
import mongoDB as mg
import customUtil as cu

def GPT(userId, query, prevMsgId, postMsgId = None):
    channelId = mg.getOccupiedChannelId(userId)
    embeddings = OpenAIEmbeddings()
    dbPath=f'./{userId}/db'
    llm = ChatOpenAI(model = "gpt-3.5-turbo", temperature = 0)
    # llm = ChatOpenAI(model = "gpt-4", temperature = 0.6)
    promptTemplate = """The following is a friendly conversation between a human and an AI. The AI is talkative and provides lots of specific details from its context. If the AI does not know the answer to a question, it truthfully says it does not know. AI should respond within 10 seconds.
    
    Current conversation:
    {history}
    Human: {input}
    AI Assistant:"""
    print(mg.getCollectionName(userId, channelId))
    prompt = PromptTemplate(
        template = promptTemplate, 
        input_variables = ["history", "input"],
    )
    db = Chroma(
        persist_directory = dbPath, 
        embedding_function = embeddings, 
        collection_name = mg.getCollectionName(userId, channelId),
    )
    retriever = db.as_retriever(
        search_type = "similarity_score_threshold", 
        search_kwargs = {"k": 6, "score_threshold": 0.7},
    )
    memory = VectorStoreRetrieverMemory(
        retriever = retriever, 
        return_docs = True,
    )
    chain = ConversationChain(
        prompt = prompt,
        llm = llm,
        memory = memory,
        verbose = True,
    )
    chainInput = {
        "input": query,
    }
    docScoreList = db.similarity_search_with_relevance_scores(
        query = query,
        k = 4,
        score_threshold = 0.7
    )
    dto = []
    for doc, score in docScoreList:
        if doc.metadata:
            dto.append((doc.metadata["source"], doc.metadata["page"]))

    result = chain(chainInput)
    answer = result["response"]
    imgDtos, imgPaths = cu.pdfPage2Image(userId, dto)
    sourceList = cu.getImgTuple(imgDtos, imgPaths)

    # 추가 채팅
    if postMsgId is None:
        mg.giveMsgId(userId = userId, question = query, answer = answer, curMsgId = prevMsgId, sources = imgPaths)
    # 수정 채팅
    else:
        mg.giveMsgId(userId = userId, question = query, answer = answer, curMsgId = prevMsgId, modifyId = postMsgId, sources = imgPaths)
    
    return "success", answer, sourceList

def getWordCloud(documents):
    sys = SystemMessage(content = "You are a helpful assisstant that extracts 10 meaningful keywords separated by ',' in order of importance from a list of keywords extracted in order of frequency from documents.")
    chat = ChatOpenAI(model_name = "gpt-3.5-turbo", temperature = 0)

    text = ""
    for doc in documents:
        text += doc.page_content
    words = re.findall(r'\b\w+\b', text.lower())
    wordFrequency = Counter(words)

    dto = ""
    for i, word in enumerate(wordFrequency):
        if i == 100:
            break
        dto += f"{word}, "
    
    wordCloud = chat([sys, HumanMessage(content = dto)]).content.split(", ")

    return wordCloud

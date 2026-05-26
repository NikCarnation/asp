import os
from langchain_text_splitters import RecursiveCharacterTextSplitter, MarkdownHeaderTextSplitter
from langchain_huggingface.embeddings import HuggingFaceEmbeddings
from langchain_core.documents import Document
from langchain_chroma import Chroma
from langchain_ollama import ChatOllama
from langchain_qwq import ChatQwen
from langchain_core.prompts import ChatPromptTemplate
import ollama 
from dotenv import load_dotenv
import json
import numpy as np

load_dotenv()


model = ChatOllama(
    model="ministral-3:8b",
    base_url="http://localhost:11434",
    temperature=0.0,
    num_predict=2048  
)

# model = ChatQwen(model="qwen/qwen3-vl-30b-a3b-thinking", api_key=os.getenv('OPENROUTER_API_KEY'), base_url='https://openrouter.ai/api/v1/', temperature=0.0)

database_path = os.getenv("knowbase_path")
vector_store_dir = os.getenv("database_path")

# emb = ollama.embed(model="qwen3-embedding:0.6b")
embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-mpnet-base-v2")

vector_store = Chroma(
    collection_name="cybersec_knowledge_base",
    embedding_function=embeddings,
    persist_directory=vector_store_dir
)

k = 4
DOCS_IN_RETRIEVER = 10
RELEVANCE_THRESHOLD_PROMPT = 0.5
RELEVANCE_THRESHOLD_DOCS = 0.5


def get_all_docs():
    docs = []
    for file in os.listdir(database_path):
        file_path = os.path.join(database_path, file)
        if not os.path.isfile(file_path):
            continue
        
        with open(file_path, 'r', encoding='utf-8') as fl:
            docs.append({
                "name": file,
                "content": fl.read(), 
                "path": file_path
            })
    return docs



def build_header_context(metadata: dict) -> str:
    parts = []
    for level in ["h1", "h2", "h3", "h4", "h5", "h6"]:
        if level in metadata:
            prefix = "#" * int(level[1])
            parts.append(f"{prefix} {metadata[level]}")
    return "\n".join(parts)
        
    
def text_spliter(documents: list[dict]) -> list[Document]:
    headers = [
        ("# ", "h1"),
        ("## ", "h2"),
        ("### ", "h3"),
        ("#### ", "h4"),
        ("##### ", "h5"),
        ("###### ", "h6")
    ]
    
    md_spliter = MarkdownHeaderTextSplitter(headers_to_split_on=headers, strip_headers=False)
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=3000, chunk_overlap=300, separators=["\n\n", "\n", ". ", " ", ""])

    all_chunks = []
    
    for doc in documents:
        md_chunks = md_spliter.split_text(doc["content"])
        for chunk in md_chunks:
            header_chain = build_header_context(chunk.metadata)
            
            enriched_text = f"{header_chain}\n\n{chunk.page_content}" \
                if header_chain else chunk.page_content
            
            if len(enriched_text) > 2000:
                sub_chunks = text_splitter.split_text(enriched_text)
                for j, sub in enumerate(sub_chunks):
                    all_chunks.append(Document(
                        page_content=sub,
                        metadata={
                            **chunk.metadata,
                            "source": doc["name"],
                            "sub_chunk": j,
                            "header_context": header_chain
                        }
                    ))
            else:
                all_chunks.append(Document(
                    page_content=enriched_text,
                    metadata={
                        **chunk.metadata,
                        "source": doc["name"],
                        "header_context": header_chain
                    }
                ))
    
    return all_chunks



def indexing():
    try: 
        documents = get_all_docs()
        chunks = text_spliter(documents)
        vector_store.add_documents(chunks)
        return "indexing complete"
    except Exception as e:
        return f"Ошибка {str(e)}"


def preprocessing_user_prompt(user_prompt:str):
    instruction = (
       "Your task is to refine the user prompt below, preserving its meaning.\n"
       "Steps to follow:\n"
       "1. Identify the main question or request.\n"
       "2. If there are multiple tasks, list them.\n"
       "3. Keep the text concise and clear.\n\n"
       f"User prompt:\n{user_prompt}\n\n"
       "-----\n"
       "Now, provide the improved prompt below:\n")    
    
    resp = model.invoke(instruction)
    improved_prompt = resp.content.strip()
    return improved_prompt


def retrive_docs(vector_store, user_query: str):
    if not vector_store:
        print("Векторное хранилище не загружено. Требуется повторная попытка.")
        return []
    
    try: 
        docs_score = vector_store.similarity_search(user_query, k=DOCS_IN_RETRIEVER)
        return docs_score
    except Exception as er:
        print(f"Ошибка: {er}")
        return []
    
    
def comp_emb_similarity(embeddings, prompt: str, docs: list):
    emb_from_prompt = np.array(embeddings.embed_query(prompt))
    relevance_score = []
    
    try:
        for doc in docs:
            doc_embedding = np.array(embeddings.embed_query(doc.page_content))
            if emb_from_prompt.size == 0 or doc_embedding.size == 0:
                print(f"Ошибка:: {doc.metadata.get('source', 'Unknown')}")
                similarity = 0.0
            else:
                dot_product = np.dot(emb_from_prompt, doc_embedding)
                norm_prompt = np.linalg.norm(emb_from_prompt)
                norm_doc = np.linalg.norm(doc_embedding)
                
                if norm_prompt > 1e-9 and norm_doc > 1e-9:
                    similarity = dot_product / (norm_prompt * norm_doc)
                else:
                    similarity = 0.0
                
                similarity = float(np.clip(similarity, -1.0, 1.0))

            relevance_score.append((doc, similarity))
        return relevance_score

    except Exception as e:
        print(f"Exception in compute_embeddings_similarity: {str(e)}")
        return [(doc, 0.0) for doc in docs]

    except Exception as e:
       print(f"Exception in compute_embeddings_similarity: {str(e)}")
       return [(doc, 0.0) for doc in docs]
        
    
    
def compare_prompt_for_docs(relevance_score, threshold=RELEVANCE_THRESHOLD_PROMPT):
    max_similarity = max((sim for _, sim in relevance_score), default=0.0)
    return max_similarity >= threshold

    
def generate_response(user_prompt: str):

    improve_user_promt = preprocessing_user_prompt(user_prompt)
    retrieve_documents = retrive_docs(vector_store, improve_user_promt)
    relevance_score = comp_emb_similarity(embeddings, improve_user_promt, retrieve_documents)
    
    rel_docs = [doc for (doc, similarity) in relevance_score 
                if similarity >= RELEVANCE_THRESHOLD_DOCS]
    
    
    prompt = ChatPromptTemplate.from_template(
        """На основе следующих документов, дай краткий и точный ответ на вопрос: {query}
           Контекст (документы): {context}. 
           В конце ответа укажи источники информации из которых взяты данные, в формате: Источник: <название источника>. 
           Если на вопрос не нашлось документов - отвечай так: 'Простите, не могу ответить на данный вопрос. Уточните пожалуйста, что вы имели ввиду'
           Ответ:
        """
    )
    
    context_str = ''
    for doc in rel_docs:
       source = doc.metadata.get('source', 'Unknown')
       content = doc.page_content or 'N/A'
       context_str += f"Source: {source},\nContent:\n{content}\n---\n"
    
    finall_prompt = prompt.invoke({"query": improve_user_promt, "context": context_str})   
    llm_ans = model.invoke(finall_prompt)
    
    return llm_ans.content




# print(generate_response("Дай информацию по защите Active Directory"))
# print(indexing())
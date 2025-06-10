# ======================================================================================
# --- PARCHE PARA SQLITE3 EN STREAMLIT CLOUD ---
# Este bloque de código DEBE SER LO PRIMERO en todo el script.
# Fuerza a la aplicación a usar una versión más nueva de sqlite3.
try:
    __import__('pysqlite3')
    import sys
    sys.modules['sqlite3'] = sys.modules.pop('pysqlite3')
except ImportError:
    pass # Si pysqlite3-binary no está instalado, simplemente continúa.
# ======================================================================================

import streamlit as st
import os
import sqlite3 # Importamos para verificar la versión
from dotenv import load_dotenv

# --- LIBRERÍAS REQUERIDAS ---
from google.cloud import texttospeech
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from langchain_community.document_loaders import PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain.chains import create_retrieval_chain
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain_core.prompts import ChatPromptTemplate

# ======================================================================================
# --- CONFIGURACIÓN FÁCIL ---
# ======================================================================================

CONFIG = {
    "PAGE_TITLE": "Asistente CSD",
    "PAGE_ICON": "🎓",
    "HEADER_IMAGE": "header_banner.png",
    "APP_TITLE": "🎓 Asistente Virtual del Colegio Santo Domingo",
    "APP_SUBHEADER": "¡Hola! Estoy aquí para responder tus preguntas basándome en el documento oficial.",
    "WELCOME_MESSAGE": "¡Hola! Soy el asistente virtual del CSD. ¿En qué puedo ayudarte?",
    "SPINNER_MESSAGE": "Buscando y preparando tu respuesta...",
    "PDF_DOCUMENT_PATH": "documento.pdf",
    "OFFICIAL_WEBSITE_URL": "https://colegiosantodomingo.edu.co/",
    "WEBSITE_LINK_TEXT": "Visita la Página Web Oficial del Colegio",
    "TTS_VOICE_NAME": "es-US-Standard-B",
    "CSS_FILE_PATH": "styles.css"
}

# ======================================================================================
# --- LÓGICA DE LA APLICACIÓN ---
# ======================================================================================

# --- FUNCIÓN para Cargar CSS Externo ---
def load_local_css(file_name):
    if os.path.exists(file_name):
        with open(file_name, "r", encoding="utf-8") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

# --- Configuración de la Página y Carga de CSS ---
st.set_page_config(page_title=CONFIG["PAGE_TITLE"], page_icon=CONFIG["PAGE_ICON"], layout="wide")
load_local_css(CONFIG["CSS_FILE_PATH"])


# --- DIAGNÓSTICO DE SQLITE3 ---
# Esta línea nos dirá qué versión se está usando realmente.
st.sidebar.info(f"Versión de SQLite3 en uso: **{sqlite3.sqlite_version}**")


# --- Header, Título y Subtítulo ---
with st.container():
    st.markdown('<div class="header-container">', unsafe_allow_html=True)
    if os.path.exists(CONFIG["HEADER_IMAGE"]):
        st.image(CONFIG["HEADER_IMAGE"], use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)
st.title(CONFIG["APP_TITLE"])
st.write(CONFIG["APP_SUBHEADER"])


# --- Resto del código (funciones de TTS y RAG) sin cambios... ---

@st.cache_resource
def load_rag_chain():
    # Código de la función load_rag_chain...
    load_dotenv()
    api_key = st.secrets.get("GOOGLE_API_KEY", os.getenv("GOOGLE_API_KEY"))
    if not api_key:
        st.error("Error: GOOGLE_API_KEY no está configurada.")
        st.stop()
    
    loader = PyPDFLoader(CONFIG["PDF_DOCUMENT_PATH"])
    docs = loader.load()
    # CORRECCIÓN: El argumento se llama 'chunk_overlap', no 'overlap'.
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150)
    chunks = text_splitter.split_documents(docs)
    embeddings = GoogleGenerativeAIEmbeddings(model="models/embedding-001", google_api_key=api_key)
    vectorstore = Chroma.from_documents(documents=chunks, embedding=embeddings)
    retriever = vectorstore.as_retriever()
    llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash", google_api_key=api_key)
    prompt_template = "Contexto: <context>{context}</context>\nPregunta: {input}\nRespuesta:"
    prompt = ChatPromptTemplate.from_template(prompt_template)
    rag_chain = create_retrieval_chain(retriever, create_stuff_documents_chain(llm, prompt))
    return rag_chain

def text_to_speech(text, voice_name):
    # Código de la función text_to_speech...
    try:
        # Intenta usar las credenciales de Streamlit Secrets
        if 'gcp_service_account' in st.secrets:
            creds_dict = dict(st.secrets['gcp_service_account'])
            from google.oauth2 import service_account
            client = texttospeech.TextToSpeechClient(credentials=service_account.Credentials.from_service_account_info(creds_dict))
        else: # Usa credenciales por defecto para desarrollo local
            client = texttospeech.TextToSpeechClient()
        
        synthesis_input = texttospeech.SynthesisInput(text=text)
        voice = texttospeech.VoiceSelectionParams(language_code="es-US", name=voice_name)
        audio_config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3)
        response = client.synthesize_speech(input=synthesis_input, voice=voice, audio_config=audio_config)
        return response.audio_content
    except Exception as e:
        st.error(f"Error al generar el audio: {e}")
        return None

try:
    rag_chain = load_rag_chain()
except Exception as e:
    # Si el error es de sqlite, el mensaje de arriba será más específico.
    st.error(f"Ocurrió un error crítico al inicializar la IA: {e}")
    st.stop()

# --- Lógica del Chat ---
if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": CONFIG["WELCOME_MESSAGE"]}]

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("Escribe tu pregunta aquí..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner(CONFIG["SPINNER_MESSAGE"]):
            response = rag_chain.invoke({"input": prompt})
            respuesta_ia = response["answer"]
            st.markdown(respuesta_ia)
            
            audio_content = text_to_speech(respuesta_ia, CONFIG["TTS_VOICE_NAME"])
            if audio_content:
                st.audio(audio_content, autoplay=True)
            
            st.session_state.messages.append({"role": "assistant", "content": respuesta_ia})

# --- Enlace al Sitio Web Oficial ---
st.divider()
st.markdown(
    f"<div class='footer-link'><a href='{CONFIG['OFFICIAL_WEBSITE_URL']}' target='_blank'>{CONFIG['WEBSITE_LINK_TEXT']}</a></div>",
    unsafe_allow_html=True
)


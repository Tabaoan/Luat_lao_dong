# ===================== IMPORTS =====================
import os, re, io
from typing import Dict, Any, List
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(override=True)

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_core.runnables import RunnableLambda
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_core.documents import Document
from langchain_pinecone import Pinecone 
from pinecone import Pinecone as PineconeClient
from langchain_core.messages import SystemMessage, HumanMessage, BaseMessage, AIMessage 


# ===================== ENV =====================
OPENAI__API_KEY = os.getenv("OPENAI__API_KEY")
OPENAI__EMBEDDING_MODEL = os.getenv("OPENAI__EMBEDDING_MODEL")
OPENAI__MODEL_NAME = os.getenv("OPENAI__MODEL_NAME")
OPENAI__TEMPERATURE = os.getenv("OPENAI__TEMPERATURE")

# ⬅️ THÊM BIẾN MÔI TRƯỜNG PINECONE
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_ENVIRONMENT = os.getenv("PINECONE_ENVIRONMENT")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME")
EMBEDDING_DIM = 3072 

llm = ChatOpenAI(
    api_key=OPENAI__API_KEY,
    model_name=OPENAI__MODEL_NAME,
    temperature=float(OPENAI__TEMPERATURE) if OPENAI__TEMPERATURE else 0
)

# Khởi tạo Pinecone Client
if PINECONE_API_KEY:
    pc = PineconeClient(api_key=PINECONE_API_KEY)
else:
    pc = None
    print("❌ Lỗi: Không tìm thấy PINECONE_API_KEY. Pinecone sẽ không hoạt động.")

emb = OpenAIEmbeddings(api_key=OPENAI__API_KEY, model=OPENAI__EMBEDDING_MODEL)

vectordb = None
retriever = None


# ===================== SYSTEM PROMPT =====================
PDF_READER_SYS = (
    "Bạn là một trợ lý AI pháp lý chuyên đọc hiểu và tra cứu các tài liệu được cung cấp "
    "(bao gồm: Luật, Nghị định, Quyết định, Thông tư, Văn bản hợp nhất, Quy hoạch, Danh mục khu công nghiệp, v.v.). "
    "Nhiệm vụ của bạn là trích xuất và trả lời chính xác các thông tin có trong tài liệu, "
    "đặc biệt liên quan đến Lao động, Dân sự và các Khu công nghiệp, Cụm công nghiệp tại Việt Nam.\n\n"

    
    "⚙️ QUY TẮC ĐẶC BIỆT:\n"
    "- Nếu người dùng chỉ chào hỏi hoặc đặt câu hỏi chung chung (ví dụ: 'xin chào', 'bạn làm được gì', 'giúp tôi với' ...), "
    "hãy trả lời nguyên văn như sau:\n"
    "'Xin chào! Mình là Chatbot Cổng việc làm Việt Nam. Mình có thể giúp anh/chị tra cứu và giải thích các quy định pháp luật "
    "(luật, nghị định, thông tư...) liên quan đến lao động, việc làm, dân sự và các lĩnh vực pháp lý khác. "
    "Gõ câu hỏi cụ thể hoặc mô tả tình huống nhé — mình sẽ trả lời ngắn gọn, có dẫn nguồn.'\n\n"

    "📘 NGUYÊN TẮC CHUNG KHI TRẢ LỜI:\n"
    "1) Phạm vi: Chỉ dựa vào nội dung trong các tài liệu đã được cung cấp; tuyệt đối không sử dụng hoặc suy diễn kiến thức bên ngoài.\n"
    "2) Nguồn trích dẫn: Khi có thể, chỉ ghi rõ nguồn theo quy định (ví dụ: Theo Điều X, Nghị định số Y/NĐ-CP...), "
    "nhưng không được ghi theo dạng liệt kê tài liệu như [1], [2], [3]... Không được phép sử dụng hoặc nhắc đến cụm từ như:'tài liệu PDF', 'trích từ tài liệu PDF', 'dưới đây là thông tin từ tài liệu PDF', hoặc các cụm tương tự."
    "Thay vào đó, chỉ nêu trực tiếp nội dung pháp luật, ví dụ: 'Thông tin liên quan đến Luật Việc làm quy định rằng...'.\n"
    "3) Ngôn ngữ: Sử dụng văn phong pháp lý, trung lập, rõ ràng và tôn trọng ngữ điệu hành chính.\n"
    "4) Trình bày: Ưu tiên trình bày dưới dạng danh sách (số thứ tự hoặc gạch đầu dòng) để dễ theo dõi; "
    "tuyệt đối không được sử dụng ký hiệu in đậm (** hoặc __) trong bất kỳ phần trả lời nào.\n"
    "5) Nếu thông tin không có: Trả lời rõ ràng: 'Thông tin này không có trong tài liệu được cung cấp.'\n"
    "6) Nếu câu hỏi mơ hồ: Yêu cầu người dùng làm rõ hoặc bổ sung chi tiết để trả lời chính xác hơn.\n"
 
    
    "Không được phép sử dụng hoặc nhắc đến cụm từ như: " "'tài liệu PDF', 'trích từ tài liệu PDF', 'dưới đây là thông tin từ tài liệu PDF', hoặc các cụm tương tự. " 
    "Thay vào đó, chỉ nêu trực tiếp nội dung pháp luật, ví dụ: 'Thông tin liên quan đến Luật Việc làm quy định rằng...'.\n"

    "🏭 QUY ĐỊNH RIÊNG ĐỐI VỚI CÁC KHU CÔNG NGHIỆP / CỤM CÔNG NGHIỆP:\n"
    "1) Nếu người dùng hỏi 'Tỉnh/thành phố nào có bao nhiêu khu hoặc cụm công nghiệp', "
    "hãy trả lời theo định dạng sau:\n"
    "   - Số lượng khu/cụm công nghiệp trong tỉnh hoặc thành phố đó.\n"
    "   - Danh sách tên của tất cả các khu/cụm.\n\n"
    "   Ví dụ:\n"
    "   'Tỉnh Bình Dương có 29 khu công nghiệp. Bao gồm:\n"
    "   - Khu công nghiệp Sóng Thần 1\n"
    "   - Khu công nghiệp VSIP 1\n"
    "   - Khu công nghiệp Mỹ Phước 3\n"
    "   ...'\n\n"

    "2) Nếu người dùng hỏi chi tiết về một khu/cụm công nghiệp cụ thể (lần đầu tiên), hãy trình bày đầy đủ thông tin (nếu có trong tài liệu), gồm:\n"
    "   - Tên khu công nghiệp / cụm công nghiệp\n"
    "   - Địa điểm (tỉnh/thành phố, huyện/thị xã)\n"
    "   - Diện tích (ha hoặc m²)\n"
    "   - Cơ quan quản lý / chủ đầu tư\n"
    "   - Quyết định thành lập hoặc phê duyệt quy hoạch\n"
    "   - Ngành nghề hoạt động chính\n"
    "   - Tình trạng hoạt động (đang hoạt động / đang quy hoạch / đang xây dựng)\n"
    "   - Các thông tin khác liên quan (nếu có)\n\n"

    "3) Nếu người dùng tiếp tục hỏi chi tiết về các cụm hoặc khu công nghiệp (từ lần thứ hai trở đi), "
    "hãy không liệt kê lại thông tin chi tiết, mà trả lời cố định như sau:\n"
    "'Nếu bạn muốn biết thêm thông tin chi tiết về các cụm, hãy truy cập vào website https://iipmap.com/.'\n\n"

    "4) Nếu người dùng chỉ hỏi thống kê (ví dụ: 'Tỉnh Bắc Ninh có bao nhiêu cụm công nghiệp?'), "
    "hãy luôn trả lời số lượng và liệt kê tên cụm/khu theo quy định tại mục (1) ở trên.\n\n"

    "5) Nếu người dùng hỏi câu ngoài phạm vi pháp luật hoặc khu/cụm công nghiệp "
    "(ví dụ: hỏi về tuyển dụng, giá đất, đầu tư cá nhân, v.v.), "
    "hãy trả lời nguyên văn như sau:\n"
    "'Anh/chị vui lòng để lại tên và số điện thoại, chuyên gia của IIP sẽ liên hệ và giải đáp các yêu cầu của anh/chị ạ.'\n\n"
)

# ===================== VECTORDB UTILS (Pinecone) =====================
def build_context_from_hits(hits, max_chars: int = 6000) -> str:
    """Xây dựng context từ kết quả tìm kiếm"""
    ctx = []
    total = 0
    for idx, h in enumerate(hits, start=1):
        source = h.metadata.get('source', 'unknown')
        seg = f"[Nguồn: {source}, Trang: {h.metadata.get('page', '?')}]\n{h.page_content.strip()}"
        if total + len(seg) > max_chars:
            break
        ctx.append(seg)
        total += len(seg)
    return "\n\n".join(ctx)

def get_existing_sources() -> set:
    """Lấy danh sách file đã có trong VectorDB (Pinecone - không hiệu quả, trả về rỗng)"""
    # Pinecone không có API dễ dàng để lấy tất cả sources từ metadata
    # Trả về thông báo chung
    return set()

def check_vectordb_exists() -> bool:
    """Kiểm tra xem Pinecone Index có tồn tại và có vectors không"""
    global pc, vectordb, retriever
    
    if pc is None or not PINECONE_INDEX_NAME:
        return False

    try:
        if PINECONE_INDEX_NAME not in pc.list_indexes().names():
            return False
            
        index = pc.Index(PINECONE_INDEX_NAME)
        stats = index.describe_index_stats()
        total_vectors = stats['total_vector_count']
        
        if total_vectors > 0:
            if vectordb is None:
                vectordb = Pinecone(
                    index=index, 
                    embedding=emb, 
                    text_key="text"
                )
                retriever = vectordb.as_retriever(search_kwargs={"k": 50})
            return True
            
        return False
        
    except Exception as e:
        return False

def get_vectordb_stats() -> Dict[str, Any]:
    """Lấy thông tin thống kê về VectorDB (Pinecone)"""
    global pc
    
    if pc is None or not PINECONE_INDEX_NAME or PINECONE_INDEX_NAME not in pc.list_indexes().names():
        return {"total_documents": 0, "name": PINECONE_INDEX_NAME, "exists": False, "sources": []}
    
    try:
        index = pc.Index(PINECONE_INDEX_NAME)
        stats = index.describe_index_stats()
        
        count = stats['total_vector_count']
        sources = ["Thông tin nguồn cần được quản lý riêng"]
        
        return {
            "total_documents": count,
            "name": PINECONE_INDEX_NAME,
            "exists": count > 0,
            "sources": sources,
            "dimension": stats.get('dimension', EMBEDDING_DIM)
        }
    except Exception as e:
        return {
            "total_documents": 0,
            "name": PINECONE_INDEX_NAME,
            "exists": False,
            "error": str(e),
            "sources": []
        }

def load_vectordb():
    """Load VectorDB từ Pinecone Index (Chỉ Đọc)"""
    global vectordb, retriever, pc

    if pc is None:
        print("❌ Lỗi: Pinecone Client chưa được khởi tạo. Vui lòng kiểm tra PINECONE_API_KEY.")
        return None

    try:
        # Kiểm tra Index có tồn tại không
        if PINECONE_INDEX_NAME not in pc.list_indexes().names():
            print(f"❌ Index '{PINECONE_INDEX_NAME}' không tồn tại trên Pinecone.")
            return None
            
        # Kết nối đến Index
        index = pc.Index(PINECONE_INDEX_NAME)
        stats = index.describe_index_stats()
        
        # Kiểm tra có document không
        if stats['total_vector_count'] == 0:
            print(f"❌ Index '{PINECONE_INDEX_NAME}' không có document nào.")
            return None
        
        # Kiểm tra dimension
        current_dim = stats.get('dimension', 0)
        if current_dim != EMBEDDING_DIM:
            print(f"⚠️ CẢNH BÁO: Dimension không khớp!")
            print(f"   Index: {current_dim} | Model: {EMBEDDING_DIM}")
            print(f"   Điều này có thể gây lỗi khi query.")
            
        # Khởi tạo vectordb và retriever
        vectordb = Pinecone(
            index=index, 
            embedding=emb, 
            text_key="text"
        )
        retriever = vectordb.as_retriever(search_kwargs={"k": 50})
        
        return vectordb
        
    except Exception as e:
        print(f"❌ Lỗi khi load Pinecone Index: {e}")
        vectordb = None
        retriever = None
        return None

# ===================== CLEANING & RETRIEVAL =====================
_URL_RE = re.compile(r"https?://[^\s]+", re.IGNORECASE)

def clean_question_remove_uris(text: str) -> str:
    """Làm sạch câu hỏi, loại bỏ URL và tên file PDF"""
    txt = _URL_RE.sub(" ", text or "")
    toks = re.split(r"\s+", txt)
    toks = [t for t in toks if not t.lower().endswith(".pdf")]
    return " ".join(toks).strip()

FIXED_RESPONSE_Q3 = 'Nếu bạn muốn biết thêm thông tin chi tiết về các cụm, hãy truy cập vào website https://iipmap.com/.'

def is_detail_query(text: str) -> bool:
    """Kiểm tra xem câu hỏi có phải là câu hỏi chi tiết về khu/cụm công nghiệp hay không"""
    text_lower = text.lower()
    keywords = ["nêu chi tiết", "chi tiết về", "thông tin chi tiết", "cụm công nghiệp", "khu công nghiệp"]
    if any(k in text_lower for k in keywords):
        if "có bao nhiêu" in text_lower or "thống kê" in text_lower:
            return False
        return True
    return False

def count_previous_detail_queries(history: List[BaseMessage]) -> int:
    """Đếm số lần hỏi chi tiết về KCN/CCN đã được trả lời trước đó"""
    count = 0
    for i in range(len(history)):
        current_message = history[i]
        if isinstance(current_message, HumanMessage):
            is_q = is_detail_query(current_message.content)
            if is_q and i + 1 < len(history) and isinstance(history[i+1], AIMessage):
                bot_response = history[i+1].content
                if FIXED_RESPONSE_Q3 not in bot_response:
                    count += 1
    return count

def process_pdf_question(i: Dict[str, Any]) -> str:
    """Xử lý câu hỏi từ người dùng"""
    global retriever
    
    message = i["message"]
    history: List[BaseMessage] = i.get("history", [])

    clean_question = clean_question_remove_uris(message)
    
    # Logic Quy tắc 3
    if is_detail_query(clean_question):
        count_detail_queries = count_previous_detail_queries(history)
        if count_detail_queries >= 1: 
            return FIXED_RESPONSE_Q3
        
    # Kiểm tra retriever
    if retriever is None:
        return "❌ VectorDB chưa được load hoặc không có dữ liệu. Vui lòng kiểm tra lại Pinecone Index."
    
    try:
        # Tìm kiếm trong VectorDB
        hits = retriever.invoke(clean_question)
        
        if not hits:
            return "Xin lỗi, tôi không tìm thấy thông tin liên quan trong dữ liệu hiện có."

        # Xây dựng context
        context = build_context_from_hits(hits, max_chars=6000)
        
        # Tạo messages
        messages = [SystemMessage(content=PDF_READER_SYS)]
        if history:
            messages.extend(history[-10:]) 

        user_message = f"""Câu hỏi: {clean_question}

Nội dung liên quan từ tài liệu:
{context}

Hãy trả lời dựa trên các nội dung trên."""
        
        messages.append(HumanMessage(content=user_message))
        
        # Gọi LLM
        response = llm.invoke(messages).content
        return response

    except Exception as e:
        print(f"❌ Lỗi: {e}")
        return f"Xin lỗi, tôi gặp lỗi khi xử lý câu hỏi: {str(e)}"

# ===================== MAIN CHATBOT =====================
pdf_chain = RunnableLambda(process_pdf_question)
store: Dict[str, ChatMessageHistory] = {}

def get_history(session_id: str):
    """Lấy hoặc tạo lịch sử chat cho session"""
    if session_id not in store:
        store[session_id] = ChatMessageHistory()
    return store[session_id]

chatbot = RunnableWithMessageHistory(
    pdf_chain,
    get_history,
    input_messages_key="message",
    history_messages_key="history"
)

def print_help():
    """In hướng dẫn sử dụng"""
    print("\n" + "="*60)
    print("📚 CÁC LỆNH CÓ SẴN:")
    print("="*60)
    print(" - exit / quit  : Thoát chương trình")
    print(" - clear        : Xóa lịch sử hội thoại")
    print(" - status       : Kiểm tra trạng thái Pinecone Index")
    print(" - help         : Hiển thị hướng dẫn này")
    print("="*60 + "\n")

def handle_command(command: str, session: str) -> bool:
    """Xử lý các lệnh đặc biệt"""
    cmd = command.lower().strip()

    if cmd in {"exit", "quit"}:
        print("\n👋 Tạm biệt! Hẹn gặp lại!")
        return False
    
    elif cmd == "clear":
        if session in store:
            store[session].clear()
            print("🧹 Đã xóa lịch sử hội thoại.\n")
        return True
    
    elif cmd == "status":
        stats = get_vectordb_stats()
        print("\n" + "="*60)
        print("📊 TRẠNG THÁI PINECONE INDEX (CHẾ ĐỘ CHỈ ĐỌC)")
        print("="*60)
        if stats["exists"]:
            print(f"✅ Trạng thái: Sẵn sàng")
            print(f"📚 Tên Index: {stats['name']}")
            print(f"📊 Tổng documents: {stats['total_documents']}")
            print(f"📏 Dimension: {stats['dimension']}")
        else:
            print("❌ Trạng thái: Chưa sẵn sàng")
            print(f"💡 Index '{PINECONE_INDEX_NAME}' không tồn tại hoặc không có documents.")
        print("="*60 + "\n")
        return True
    
    elif cmd == "help":
        print_help()
        return True
    
    else:
        return True

# ===================== AUTO LOAD WHEN IMPORTED =====================
# Khi module này được import (ví dụ từ FastAPI), sẽ tự load Pinecone nếu có key
if __name__ != "__main__":
    print("📦 Tự động load Pinecone khi import app.py...")
    load_vectordb()

# ===================== CLI =====================
if __name__ == "__main__":
    session = "pdf_reader_session"

    # Kiểm tra môi trường
    if not all([PINECONE_API_KEY, PINECONE_INDEX_NAME]):
        print("❌ LỖI: Thiếu PINECONE_API_KEY hoặc PINECONE_INDEX_NAME trong .env")
        exit(1)

    print("\n" + "="*60)
    print("🤖 CHATBOT CỔNG VIỆC LÀM VIỆT NAM (PINECONE - CHỈ ĐỌC)")
    print("="*60)
    print(f"☁️ Pinecone Index: {PINECONE_INDEX_NAME}")
    print(f"📏 Embedding dimension: {EMBEDDING_DIM}")
    print("🔍 Tôi hỗ trợ: Luật Lao động & Luật Dân sự Việt Nam")
    print_help()

    # Load VectorDB từ Pinecone
    print("📥 Đang kết nối đến Pinecone Index...")
    result = load_vectordb()
    
    if result is None:
        print("❌ KHÔNG THỂ LOAD PINECONE INDEX. Vui lòng kiểm tra:")
        print("   1. Index đã được tạo và có dữ liệu chưa?")
        print("   2. PINECONE_API_KEY và PINECONE_INDEX_NAME đúng chưa?")
        print("   3. Dimension của Index khớp với model embedding chưa?")
        exit(1)

    # In thống kê
    stats = get_vectordb_stats()
    print(f"✅ Pinecone Index sẵn sàng với {stats['total_documents']} documents\n")
    
    print("💬 Sẵn sàng trả lời câu hỏi! (Gõ 'help' để xem hướng dẫn)\n")

    # Main loop
    while True:
        try:
            message = input("👤 Bạn: ").strip()
            
            if not message:
                continue
            
            # Xử lý lệnh
            if not handle_command(message, session):
                break
            
            # Bỏ qua nếu là lệnh
            if message.lower() in ["clear", "status", "help"]: 
                continue
            
            # Xử lý câu hỏi thường
            print("🔎 Đang tìm kiếm trong Pinecone Index...")
            response = chatbot.invoke(
                {"message": message},
                config={"configurable": {"session_id": session}}
            )
            print(f"\n🤖 Bot: {response}\n")
            print("-" * 60 + "\n")
            
        except KeyboardInterrupt:
            print("\n\n👋 Tạm biệt!")
            break
        except Exception as e:
            print(f"\n❌ Lỗi: {e}\n")
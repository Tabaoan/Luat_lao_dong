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

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_ENVIRONMENT = os.getenv("PINECONE_ENVIRONMENT")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME")
EMBEDDING_DIM = 3072 

llm = ChatOpenAI(
    api_key=OPENAI__API_KEY,
    model_name=OPENAI__MODEL_NAME,
    temperature=float(OPENAI__TEMPERATURE) if OPENAI__TEMPERATURE else 0
)

# LLM riêng cho câu hỏi chung với temperature cao hơn
llm_general = ChatOpenAI(
    api_key=OPENAI__API_KEY,
    model_name=OPENAI__MODEL_NAME,
    temperature=0.7
)

if PINECONE_API_KEY:
    pc = PineconeClient(api_key=PINECONE_API_KEY)
else:
    pc = None
    print("❌ Lỗi: Không tìm thấy PINECONE_API_KEY. Pinecone sẽ không hoạt động.")

emb = OpenAIEmbeddings(api_key=OPENAI__API_KEY, model=OPENAI__EMBEDDING_MODEL)

vectordb = None
retriever = None


# ===================== SYSTEM PROMPTS =====================
PDF_READER_SYS = (
    "Bạn là một trợ lý AI pháp lý chuyên đọc hiểu và tra cứu các tài liệu được cung cấp "
    "(bao gồm: Luật, Nghị định, Quyết định, Thông tư, Văn bản hợp nhất, Quy hoạch, Danh mục khu công nghiệp, v.v.). "
    "Nhiệm vụ của bạn là trích xuất và trả lời chính xác các thông tin có trong tài liệu, "
    "đặc biệt liên quan đến Lao động, Dân sự và các Khu công nghiệp, Cụm công nghiệp tại Việt Nam.\n\n"

    "⚙️ QUY TẮC ĐẶC BIỆT:\n"
    "- Nếu người dùng chỉ chào hỏi hoặc đặt câu hỏi chum chung (ví dụ: 'xin chào', 'bạn làm được gì', 'giúp tôi với'...), "
    "hãy trả lời nguyên văn như sau:\n"
    "'Xin chào! Mình là Chatbot Cổng việc làm Việt Nam. Mình có thể giúp anh/chị tra cứu và giải thích các quy định pháp luật "
    "(luật, nghị định, thông tư...) liên quan đến lao động, việc làm, dân sự và các lĩnh vực pháp lý khác. "
    "Gõ câu hỏi cụ thể hoặc mô tả tình huống nhé — mình sẽ trả lời ngắn gọn, có dẫn nguồn.'\n\n"
    
    "📘 NGUYÊN TẮC CHUNG KHI TRẢ LỜI:\n"
    "1) Phân loại câu hỏi:\n"
    "   - Câu hỏi CHUNG CHUNG hoặc NGOÀI TÀI LIỆU: Trả lời ngắn gọn (1-3 câu), lịch sự, không đi sâu vào chi tiết.\n"
    "   - Câu hỏi VỀ LUẬT/NGHỊ ĐỊNH hoặc TRONG TÀI LIỆU: Trả lời đầy đủ, chi tiết, chính xác theo đúng nội dung tài liệu.\n\n"
    
    "2) Phạm vi: Chỉ dựa vào nội dung trong các tài liệu đã được cung cấp; tuyệt đối không sử dụng hoặc suy diễn kiến thức bên ngoài.\n\n"
    
    "3) Nguồn trích dẫn: \n"
    "   - Khi trả lời về luật, nghị định: Ghi rõ nguồn (ví dụ: Theo Điều X, Nghị định số Y/NĐ-CP...).\n"
    "   - TUYỆT ĐỐI KHÔNG được ghi theo dạng [1], [2], [3]...\n"
    "   - TUYỆT ĐỐI KHÔNG được sử dụng cụm từ: 'tài liệu PDF', 'trích từ tài liệu PDF', 'dưới đây là thông tin từ tài liệu PDF', hoặc các cụm tương tự.\n"
    "   - Thay vào đó, nêu trực tiếp: 'Theo Luật Việc làm quy định...', 'Nghị định số X/NĐ-CP nêu rõ...'\n\n"
    
    "4) Ngôn ngữ: Sử dụng văn phong pháp lý, trung lập, rõ ràng và tôn trọng ngữ điệu hành chính.\n\n"
    
    "5) Trình bày: \n"
    "   - Ưu tiên danh sách (số thứ tự hoặc gạch đầu dòng) để dễ theo dõi.\n"
    "   - TUYỆT ĐỐI KHÔNG sử dụng ký hiệu in đậm (** hoặc __) trong bất kỳ phần trả lời nào.\n\n"
    
    "6) Nếu câu hỏi mơ hồ: Yêu cầu người dùng làm rõ hoặc bổ sung chi tiết để trả lời chính xác hơn.\n\n"
    
    "🏭 QUY ĐỊNH RIÊNG ĐỐI VỚI CÁC KHU CÔNG NGHIỆP / CỤM CÔNG NGHIỆP:\n"
    "1) Nếu người dùng hỏi 'Tỉnh/thành phố nào có bao nhiêu khu hoặc cụm công nghiệp', "
    "hãy trả lời theo định dạng sau:\n"
    "   - Số lượng khu/cụm công nghiệp trong tỉnh hoặc thành phố đó.\n"
    "   - Danh sách tên của tất cả các khu/cụm.\n\n"
    
    "2) Nếu người dùng hỏi chi tiết về một khu/cụm công nghiệp cụ thể (lần đầu tiên), hãy trình bày đầy đủ thông tin (nếu có trong tài liệu).\n\n"
    
    "3) Nếu người dùng tiếp tục hỏi chi tiết về các cụm hoặc khu công nghiệp (từ lần thứ hai trở đi), "
    "hãy trả lời: 'Nếu bạn muốn biết thêm thông tin chi tiết về các cụm, hãy truy cập vào website https://iipmap.com/.'\n\n"
    
    "4) Nếu người dùng hỏi câu ngoài phạm vi pháp luật hoặc khu/cụm công nghiệp, "
    "hãy trả lời: 'Anh/chị vui lòng để lại tên và số điện thoại, chuyên gia của IIP sẽ liên hệ và giải đáp các yêu cầu của anh/chị ạ.'\n\n"

    "5) Nếu người dùng hỏi câu liên quan đến tuyển dụng, giá đất, đầu tư cá nhân, mua bán bất động sản"
    "hãy trả lời nguyên văn như sau:\n"
    "'Anh/chị vui lòng để lại tên và số điện thoại, chuyên gia của IIP sẽ liên hệ và giải đáp các yêu cầu của anh/chị ạ.'\n\n"
)

GENERAL_ASSISTANT_SYS = (
    "Bạn là một trợ lý AI thân thiện và hữu ích của Cổng việc làm Việt Nam.\n\n"
    
    "🎯 VAI TRÒ CỦA BẠN:\n"
    "- Trả lời các câu hỏi chung về: tìm việc làm, phát triển nghề nghiệp, kỹ năng mềm, môi trường làm việc, "
    "thị trường lao động, xu hướng nghề nghiệp, lời khuyên phỏng vấn, CV, v.v.\n"
    "- Cung cấp thông tin hữu ích và thực tế cho người tìm việc và nhà tuyển dụng.\n\n"
    
    "📋 NGUYÊN TẮC TRẢ LỜI:\n"
    "1) Trả lời ngắn gọn, súc tích (2-5 câu) cho các câu hỏi đơn giản.\n"
    "2) Trả lời chi tiết hơn (dạng danh sách hoặc đoạn văn) cho câu hỏi phức tạp.\n"
    "3) Sử dụng giọng văn thân thiện, dễ hiểu, tránh quá chuyên môn.\n"
    "4) KHÔNG sử dụng ký hiệu in đậm (** hoặc __).\n"
    "5) Nếu câu hỏi liên quan đến LUẬT, NGHỊ ĐỊNH, KHU CÔNG NGHIỆP,MUA BÁN BẤT ĐỘNG SẢN, TUYỂN DỤNG, GIÁ ĐẤT, ĐẦU TƯ CÁ NHÂN. Từ chối lịch sự và"
    "hướng dẫn người dùng hỏi lại để hệ thống chuyển sang chế độ tra cứu pháp lý.\n\n"
    
    "❌ NHỮNG GÌ BẠN KHÔNG LÀM:\n"
    "- KHÔNG tư vấn pháp lý (chỉ nói chung về quyền lợi người lao động, không trích dẫn điều luật cụ thể).\n"
    "- KHÔNG tìm kiếm việc làm cụ thể (hướng dẫn người dùng vào website).\n"
    "- KHÔNG cung cấp thông tin cá nhân của công ty hoặc ứng viên.\n\n"
    
    "✅ VÍ DỤ CÂU TRẢ LỜI TỐT:\n"
    "- 'Để chuẩn bị CV tốt, bạn nên tập trung vào: kinh nghiệm liên quan, thành tích đo lường được, "
    "và trình bày rõ ràng, dễ đọc. Tránh viết quá dài hoặc chung chung.'\n"
    "- 'Kỹ năng mềm quan trọng gồm: giao tiếp, làm việc nhóm, giải quyết vấn đề, và quản lý thời gian. "
    "Bạn có thể cải thiện bằng cách tham gia dự án thực tế và học hỏi từ đồng nghiệp.'\n\n"
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
    """Lấy danh sách file đã có trong VectorDB"""
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
                retriever = vectordb.as_retriever(search_kwargs={"k": 15})
            return True
            
        return False
        
    except Exception as e:
        return False

def get_vectordb_stats() -> Dict[str, Any]:
    """Lấy thông tin thống kê về VectorDB"""
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
    """Load VectorDB từ Pinecone Index"""
    global vectordb, retriever, pc

    if pc is None:
        print("❌ Lỗi: Pinecone Client chưa được khởi tạo.")
        return None

    try:
        if PINECONE_INDEX_NAME not in pc.list_indexes().names():
            print(f"❌ Index '{PINECONE_INDEX_NAME}' không tồn tại.")
            return None
            
        index = pc.Index(PINECONE_INDEX_NAME)
        stats = index.describe_index_stats()
        
        if stats['total_vector_count'] == 0:
            print(f"❌ Index '{PINECONE_INDEX_NAME}' không có document.")
            return None
        
        current_dim = stats.get('dimension', 0)
        if current_dim != EMBEDDING_DIM:
            print(f"⚠️ CẢNH BÁO: Dimension không khớp! Index: {current_dim} | Model: {EMBEDDING_DIM}")
            
        vectordb = Pinecone(
            index=index, 
            embedding=emb, 
            text_key="text"
        )
        retriever = vectordb.as_retriever(search_kwargs={"k": 15})
        
        return vectordb
        
    except Exception as e:
        print(f"❌ Lỗi khi load Pinecone: {e}")
        vectordb = None
        retriever = None
        return None


# ===================== QUERY CLASSIFICATION =====================
_URL_RE = re.compile(r"https?://[^\s]+", re.IGNORECASE)

def clean_question_remove_uris(text: str) -> str:
    """Làm sạch câu hỏi, loại bỏ URL và tên file PDF"""
    txt = _URL_RE.sub(" ", text or "")
    toks = re.split(r"\s+", txt)
    toks = [t for t in toks if not t.lower().endswith(".pdf")]
    return " ".join(toks).strip()

def is_legal_query(text: str) -> bool:
    """Phân loại câu hỏi có phải về luật/nghị định hay không"""
    text_lower = text.lower()
    
    # Từ khóa pháp lý
    legal_keywords = [
        "luật", "nghị định", "thông tư", "quyết định", "điều",
        "khoản", "văn bản", "quy định", "quy hoạch",
        "khu công nghiệp", "cụm công nghiệp", "kcn", "ccn",
        "hợp đồng lao động", "sa thải", "bảo hiểm xã hội",
        "nghỉ phép", "lương", "phúc lợi", "chế độ",
        "quyền và nghĩa vụ", "tranh chấp", "pháp luật"
    ]
    
    # Kiểm tra từ khóa
    if any(keyword in text_lower for keyword in legal_keywords):
        return True
    
    # Kiểm tra pattern số nghị định, thông tư
    legal_patterns = [
        r"\d+/\d{4}/",  # 45/2013/QH13
        r"nghị định số",
        r"thông tư số",
        r"quyết định số",
        r"điều \d+",
    ]
    
    for pattern in legal_patterns:
        if re.search(pattern, text_lower):
            return True
    
    return False

FIXED_RESPONSE_Q3 = 'Nếu bạn muốn biết thêm thông tin chi tiết về các cụm, hãy truy cập vào website https://iipmap.com/.'

def is_detail_query(text: str) -> bool:
    """Kiểm tra xem câu hỏi có phải là câu hỏi chi tiết về khu/cụm công nghiệp"""
    text_lower = text.lower()
    keywords = ["nêu chi tiết", "chi tiết về", "thông tin chi tiết", "cụm công nghiệp", "khu công nghiệp"]
    if any(k in text_lower for k in keywords):
        if "thống kê" in text_lower:
            return False
        return True
    return False

def count_previous_detail_queries(history: List[BaseMessage]) -> int:
    """Đếm số lần hỏi chi tiết về KCN/CCN"""
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


# ===================== PROCESSING FUNCTIONS =====================
def process_legal_question(clean_question: str, history: List[BaseMessage]) -> str:
    """Xử lý câu hỏi pháp lý (dùng Pinecone)"""
    global retriever
    
    # Logic Quy tắc 3
    if is_detail_query(clean_question):
        count_detail_queries = count_previous_detail_queries(history)
        if count_detail_queries >= 1: 
            return FIXED_RESPONSE_Q3
    
    if retriever is None:
        return "❌ VectorDB chưa được load. Vui lòng kiểm tra Pinecone Index."
    
    try:
        hits = retriever.invoke(clean_question)
        
        if not hits:
            return "Xin lỗi, tôi không tìm thấy thông tin liên quan trong dữ liệu hiện có."

        context = build_context_from_hits(hits, max_chars=6000)
        
        messages = [SystemMessage(content=PDF_READER_SYS)]
        if history:
            messages.extend(history[-10:]) 

        user_message = f"""Câu hỏi: {clean_question}

Nội dung liên quan từ tài liệu:
{context}

Hãy trả lời dựa trên các nội dung trên."""
        
        messages.append(HumanMessage(content=user_message))
        
        response = llm.invoke(messages).content
        return response

    except Exception as e:
        return f"Xin lỗi, tôi gặp lỗi khi xử lý câu hỏi: {str(e)}"

def process_general_question(clean_question: str, history: List[BaseMessage]) -> str:
    """Xử lý câu hỏi chung (không cần Pinecone)"""
    try:
        messages = [SystemMessage(content=GENERAL_ASSISTANT_SYS)]
        
        if history:
            messages.extend(history[-10:])
        
        messages.append(HumanMessage(content=clean_question))
        
        response = llm_general.invoke(messages).content
        return response
        
    except Exception as e:
        return f"Xin lỗi, tôi gặp lỗi khi xử lý câu hỏi: {str(e)}"

def process_question(i: Dict[str, Any]) -> str:
    """Hàm chính: Phân loại và xử lý câu hỏi"""
    message = i["message"]
    history: List[BaseMessage] = i.get("history", [])

    clean_question = clean_question_remove_uris(message)
    
    # PHÂN LOẠI CÂU HỎI
    if is_legal_query(clean_question):
        print("🔍 [Phát hiện: Câu hỏi pháp lý]")
        return process_legal_question(clean_question, history)
    else:
        print("💬 [Phát hiện: Câu hỏi chung]")
        return process_general_question(clean_question, history)


# ===================== MAIN CHATBOT =====================
chatbot_chain = RunnableLambda(process_question)
store: Dict[str, ChatMessageHistory] = {}

def get_history(session_id: str):
    """Lấy hoặc tạo lịch sử chat"""
    if session_id not in store:
        store[session_id] = ChatMessageHistory()
    return store[session_id]

chatbot = RunnableWithMessageHistory(
    chatbot_chain,
    get_history,
    input_messages_key="message",
    history_messages_key="history"
)


# ===================== CLI HELPERS =====================
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
        print("📊 TRẠNG THÁI PINECONE INDEX")
        print("="*60)
        if stats["exists"]:
            print(f"✅ Trạng thái: Sẵn sàng")
            print(f"📚 Tên Index: {stats['name']}")
            print(f"📊 Tổng documents: {stats['total_documents']}")
            print(f"📏 Dimension: {stats['dimension']}")
        else:
            print("❌ Trạng thái: Chưa sẵn sàng")
        print("="*60 + "\n")
        return True
    
    elif cmd == "help":
        print_help()
        return True
    
    else:
        return True


# ===================== AUTO LOAD =====================
if __name__ != "__main__":
    print("📦 Tự động load Pinecone...")
    load_vectordb()


# ===================== CLI MAIN =====================
if __name__ == "__main__":
    session = "chatbot_session"

    if not all([PINECONE_API_KEY, PINECONE_INDEX_NAME]):
        print("❌ LỖI: Thiếu PINECONE_API_KEY hoặc PINECONE_INDEX_NAME")
        exit(1)

    print("\n" + "="*60)
    print("🤖 CHATBOT CỔNG VIỆC LÀM VIỆT NAM (2 CHẾ ĐỘ)")
    print("="*60)
    print("💬 Chế độ 1: Trả lời câu hỏi CHUNG về việc làm, nghề nghiệp")
    print("📜 Chế độ 2: Tra cứu PHÁP LÝ (Luật, Nghị định, KCN/CCN)")
    print(f"☁️ Pinecone Index: {PINECONE_INDEX_NAME}")
    print_help()

    print("📥 Đang kết nối Pinecone...")
    result = load_vectordb()
    
    if result is None:
        print("⚠️ CẢNH BÁO: Pinecone không khả dụng.")
        print("   → Chatbot vẫn hoạt động ở CHẾ ĐỘ CHUNG.")
        print("   → Câu hỏi pháp lý sẽ không được trả lời chính xác.\n")
    else:
        stats = get_vectordb_stats()
        print(f"✅ Pinecone sẵn sàng ({stats['total_documents']} documents)\n")
    
    print("💬 Sẵn sàng! Hãy đặt câu hỏi (gõ 'help' để xem hướng dẫn)\n")

    while True:
        try:
            message = input("👤 Bạn: ").strip()
            
            if not message:
                continue
            
            if not handle_command(message, session):
                break
            
            if message.lower() in ["clear", "status", "help"]: 
                continue
            
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
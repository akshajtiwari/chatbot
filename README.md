
---

# 🎓 Campus Chatbot

A multilingual campus chatbot that ingests notices, parses them into structured text, processes them with NLP, and answers student queries across Web, Mobile, and WhatsApp.

---

## 📂 Repository Structure

```
campus-chatbot/
│
├── ingestion/        # Data ingestion scripts
├── parsing/          # Parsing & extraction (PDF, DOCX, HTML, OCR)
├── nlp/              # Multilingual NLP and entity extraction
├── backend/          # API layer and retrieval system
├── frontend/         # Web, Mobile, WhatsApp UI
├── devops/           # Docker, CI/CD, monitoring
├── tests/            # Unit + integration tests
└── docs/             # Documentation and API contracts
```

---

## ⚙️ Setup

### Clone the repo

```bash
git clone https://github.com/your-org/campus-chatbot.git
cd campus-chatbot
```

### Install dependencies

```bash
pip install -r requirements.txt
```

### Run backend locally

```bash
cd backend
uvicorn main:app --reload
```

### Run full system with Docker Compose

```bash
docker-compose up --build
```

---

## 🧑‍💻 Team Roles

* **Ingestion** → Fetch raw data from portals/notice boards
* **Parsing** → Clean and structure files (PDF, DOCX, HTML, OCR)
* **NLP** → Entity extraction, multilingual handling
* **Backend** → APIs + retrieval system
* **Frontend** → Chatbot UI (web, mobile, WhatsApp)
* **DevOps** → Deployment, monitoring, testing

---

## 🔄 Workflow

1. Ingestion fetches raw files.
2. Parsing converts them into clean JSON.
3. NLP extracts facts and translates.
4. Backend retrieves info (SQL + vector search).
5. Frontend shows answers with source + timestamp.

---

## 🤝 Contributing

1. Fork the repo
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Commit changes (`git commit -m "Added feature"`)
4. Push branch (`git push origin feature/my-feature`)
5. Open a Pull Request

---

## 📜 License

MIT License

---

👉 This is short, clean, and straight to the point — just enough to get developers started.

Do you want me to also add a **simple architecture diagram (frontend ↔ backend ↔ DB)** in the README, or keep it pure text?


## 📝 Archita’s Contribution

I worked on the **Backend & Retrieval System** part of the chatbot.  
Here’s what I contributed:

- 🔹 Setup of **FastAPI backend endpoints** for chatbot queries  
- 🔹 Integrated **SentenceTransformer (all-MiniLM-L6-v2)** for embeddings  
- 🔹 Added **vector store (in-memory FAISS / alternative)** for efficient retrieval  
- 🔹 Configured optional **Redis caching** (backend works even if Redis is not running)  
- 🔹 Tested and verified project setup on **macOS (MPS)** and **Windows (CPU/GPU)**  
- 🔹 Improved documentation with step-by-step **setup instructions**  

### ⚡ How My Part Works

1. User sends a query → goes to **FastAPI backend**.  
2. Backend encodes the query using **SentenceTransformer**.  
3. Vector search runs on **FAISS / in-memory store** to find relevant results.  
4. If Redis is enabled, results are cached for faster responses.  
5. Answer is sent back to frontend → shown to the student.  

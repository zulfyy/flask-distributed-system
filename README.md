![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-000000?style=for-the-badge&logo=flask&logoColor=white)
![K3s](https://img.shields.io/badge/K3s-FFC61C?style=for-the-badge&logo=k3s&logoColor=black)
![CloudNativePG](https://img.shields.io/badge/CloudNativePG-4169E1?style=for-the-badge&logo=postgresql&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?style=for-the-badge&logo=postgresql&logoColor=white)
# 📋 TODO — Parallel and Distributed Computing
> Informatics Engineering Semester 4 · LILIS ANGGRAINI, S.Kom., M.Kom

---

## 🗓️ Course Timeline

| Session | Agenda | Status |
|---------|--------|--------|
| Session 1 | Introduction + project idea | ✅ |
| Session 2 | System architecture design | ✅ |
| Session 3 | **Midterm (UTS)** — Proposal presentation | ⬜ |
| Session 4 | **Final (UAS)** — System demo | ⬜ |

---

## ✅ TODO per Session

### Session 1 — Introduction ✅
- [x] Understand parallel vs serial computing concepts
- [x] Understand distributed system concepts
- [x] Choose project idea
- [x] Form group members (2–3 people)

### Session 2 — System Design ✅
- [x] Create system architecture diagram
- [x] Decide on tech stack
- [x] Identify system components (client, server, database)
- [x] Ensure communication between components

### Session 3 — Midterm / UTS (Proposal)
- [ ] Prepare proposal document with structure:
  - [ ] Project title
  - [ ] Background
  - [ ] System goals
  - [ ] Architecture diagram
  - [ ] Technologies used
- [ ] Practice presentation (5–7 minutes)
- [ ] Ready to explain system architecture

### Session 4 — Final / UAS (Demo)
- [ ] System fully implemented and running
- [ ] Ready for live demo
- [ ] Ready to explain architecture & tech stack

---

## 💡 Project

> **Distributed File Upload**
> A distributed system where users can upload files, handled by a Flask backend deployed on K3s.

### Architecture
 ![Architecture System](https://github.com/zulfyy/flask-distributed-system/blob/main/ss/Architecture.png)
```
Client (Browser)
      |
Load Balancer (Traefik)
      |
Flask App (Python) (K3s Cluster) 3x Replica
      |
Database / Storage (K3s Cluster) 1 Main, 2 Slave with CloudNativePG
      |
Blob Storage Cloud (Still Thinking)
```

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|------------|
| Language | Python |
| Framework | Flask |
| Orchestration | K3s (Kubernetes) |
| Cloud | _(planned later)_ |

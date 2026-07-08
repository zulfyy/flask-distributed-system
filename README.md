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
| Session 3 | **Midterm (UTS)** — Proposal presentation | ✅ |
| Session 4 | **Final (UAS)** — System demo | ⬜ (Video Record) |

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
- [-] Prepare proposal document with structure:
  - [-] Project title
  - [-] Background
  - [-] System goals
  - [-] Architecture diagram
  - [-] Technologies used
- [-] Practice presentation (5–7 minutes)
- [-] Ready to explain system architecture

### Session 4 — Final / UAS (Demo)
- [✔] System fully implemented and running
- [✔] Ready for live demo
- [✔] Ready to explain architecture & tech stack

---

## 💡 Project

> **Distributed RemBG, Metadata-extract, Simple OCR**
> A distributed system with HA, handled by a Flask backend deployed on K3s.

### Architecture
 ![Architecture System](https://raw.githubusercontent.com/zulfyy/flask-distributed-system/refs/heads/main/ss/Architecture.jpg)
```
Client (Browser)
      |
Load Balancer (Traefik) (K3s Server) 
      |
Flask App (Python) (K3s Cluster) 2 Worker (For HA)
      |
DragonFly (Cache)  (K3s Cluster) 1 Main | 1 (Optional)
      |
Database / Storage (K3s Cluster) 1 Main, 1 Standby with CloudNativePG
      |
Blob Storage Cloud (Skip cause deadline)
```

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|------------|
| Language | Python |
| Framework | Flask |
| Orchestration | K3s (Kubernetes) |
| Cloud | Azure |


---

## 🚀 How to Deploy

> Order matters: Terraform → Ansible (inventory) → K3s Deploy Script.

### 1️⃣ Provision Infrastructure — `terraform/`
```bash
cd terraform/
terraform init
terraform plan
terraform apply
```
- After `apply` finishes, grab the output IPs (Control Plane, Workers, etc.):
```bash
  terraform output
```

### 2️⃣ Configure Ansible — `ansible/`
> ⚠️ **IMPORTANT:** update `inventory.ini` with the IPs from Terraform above before running the playbook.

```ini
[control_plane]
control-1 ansible_host=<CONTROL_PLANE_PUBLIC_IP>

[workers]
worker-1 ansible_host=<WORKER_1_PUBLIC_IP>
worker-2 ansible_host=<WORKER_2_PUBLIC_IP>
```

Then run the playbook:
```bash
cd ansible/
ansible-playbook -i inventory.ini playbook.yml
```

### 3️⃣ Deploy Manifests to K3s — `k3s-k8s-scripts/`
> This runs **directly on the Control Plane server** (not from your local machine), using the `001-full-deploy.sh` script.

> ⚠️ **Note:** make sure the private key `~/.ssh/id_rsa_azure` already exists on your machine before continuing.

```bash
eval $(ssh-agent)
ssh-add ~/.ssh/id_rsa_azure

ssh <user>@<CONTROL_PLANE_PUBLIC_IP>
cd k3s-k8s-scripts/
sudo DOPPLER_TOKEN='<your-doppler-token>' ./001-full-deploy.sh
```
- Secrets are injected via **Doppler** using `DOPPLER_TOKEN` — no `.env` file needed on the server.
- Since the script runs directly on the Control Plane, `kubeconfig` (`/etc/rancher/k3s/k3s.yaml`) is already available locally on the server — **no need** to manually copy it to `~/.kube/config`.
- The Load Balancer (Traefik) uses **Round Robin** by default to distribute traffic across the 2 Flask Workers.

#### 🔐 Required Doppler Secrets

Project **`<your_doppler_project_name>`** uses branched configs: `prd` (base) → `prd_azure` (branch, inherits from `prd`).

**Config `prd`** (base credentials)

| Secret | Type | Description |
|--------|------|--------------|
| `USERNAME` | String | Base auth username |
| `PASSWORD` | String | Base auth password |

**Config `prd_azure`** (branched from `prd`)

| Secret | Type | Description |
|--------|------|--------------|
| `ADMIN_DEFAULT_PASSWORD` | String | Default admin login password |
| `ADMIN_USERNAME` | String | Default admin login username |
| `APP_MODE` | String | App environment mode (e.g. `production`) |
| `APP_SECRET_KEY` | String | Flask secret key (session/CSRF signing) |
| `COOKIE_DOMAIN` | String | Domain scope for cookies |
| `DB_HOST` | String | PostgreSQL host (CloudNativePG) |
| `DB_NAME` | String | Database name |
| `DB_PASSWORD` | String | Database password |
| `DB_PORT` | String | Database port |
| `DB_USER` | String | Database user |
| `REDIS_HOST` | String | DragonFly (cache) host |
| `SHOW_DEBUG_INFO` | String | Toggle debug info on/off |

> Use `DOPPLER_TOKEN` scoped to config **`prd_azure`** when running the deploy script — branched configs automatically inherit secrets from `prd`.

### 4️⃣ (Optional) Domain / DNS Setup
If using a custom domain, point the following **DNS A Records** to the **Control Plane's public IP**:

| Type | Name | Value |
|------|------|-------|
| A | `@` | `<CONTROL_PLANE_PUBLIC_IP>` |
| A | `www` | `<CONTROL_PLANE_PUBLIC_IP>` |

> Traefik (Load Balancer) runs on the Control Plane and forwards traffic to the Flask App on the worker nodes.

---
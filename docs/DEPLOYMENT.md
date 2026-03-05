# SkillSight Deployment Guide (Week 24)

## 📋 Deployment Checklist

### Pre-Deployment Requirements

- [ ] Docker Desktop installed and running
- [ ] Python 3.11+ installed
- [ ] Node.js 18+ installed
- [ ] PostgreSQL client tools (optional, for debugging)
- [ ] Domain name configured (for production)
- [ ] SSL certificates ready (for production)

---

## 🚀 Deployment Options

### Option A: Local Docker Compose (Recommended for Pilot)

```bash
# 1. Clone repository
git clone https://github.com/your-org/skillsight.git
cd skillsight

# 2. Start infrastructure
docker compose up -d

# 3. Verify containers
docker compose ps
# Expected: skillsight_db (postgres), skillsight_redis

# 4. Set up Python environment
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 5. Configure environment
cp .env.example .env
# Edit .env with your settings:
# DATABASE_URL=postgresql://skillsight:skillsight@localhost:55432/skillsight
# REDIS_URL=redis://localhost:56379
# QDRANT_HOST=localhost
# QDRANT_PORT=6333

# 6. Run database migrations
alembic upgrade head

# 7. Import seed data
python scripts/import_seeds.py

# 8. Start Qdrant (vector database)
docker run -d -p 6333:6333 -p 6334:6334 \
  -v $(pwd)/qdrant_storage:/qdrant/storage \
  qdrant/qdrant

# 9. Start backend API
PYTHONPATH=. uvicorn backend.app.main:app --host 0.0.0.0 --port 8000

# 10. Start frontend (new terminal)
cd web
npm install
npm run build
npm start

# 11. Start background worker (new terminal)
cd backend
python worker.py
```

### Option B: Cloud Deployment (AWS/GCP)

#### AWS Architecture
```
┌─────────────────────────────────────────────────────────────┐
│                        AWS Cloud                             │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐       │
│  │   Route 53  │───│ CloudFront  │───│    ALB      │       │
│  │   (DNS)     │   │   (CDN)     │   │             │       │
│  └─────────────┘   └─────────────┘   └──────┬──────┘       │
│                                              │               │
│  ┌───────────────────────────────────────────┼─────────────┐│
│  │                    ECS Cluster            │             ││
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐     ││
│  │  │  Frontend   │  │   Backend   │  │   Worker    │     ││
│  │  │  (Next.js)  │  │  (FastAPI)  │  │   (RQ)      │     ││
│  │  └─────────────┘  └─────────────┘  └─────────────┘     ││
│  └─────────────────────────────────────────────────────────┘│
│                                                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │    RDS      │  │ ElastiCache │  │     S3      │         │
│  │ (Postgres)  │  │  (Redis)    │  │  (Storage)  │         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
└─────────────────────────────────────────────────────────────┘
```

#### Terraform Configuration (example)
```hcl
# main.tf
provider "aws" {
  region = "ap-east-1"  # Hong Kong
}

module "skillsight" {
  source = "./modules/skillsight"
  
  environment     = "production"
  domain_name     = "skillsight.hku.hk"
  db_instance     = "db.t3.medium"
  redis_instance  = "cache.t3.micro"
}
```

---

## 🔧 Configuration Reference

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | Yes | - | PostgreSQL connection string |
| `REDIS_URL` | Yes | - | Redis connection string |
| `QDRANT_HOST` | Yes | localhost | Qdrant server host |
| `QDRANT_PORT` | Yes | 6333 | Qdrant server port |
| `SECRET_KEY` | Yes | - | JWT signing key |
| `OLLAMA_HOST` | No | localhost | Ollama LLM host |
| `OLLAMA_MODEL` | No | llama2 | Default LLM model |
| `STORAGE_PATH` | No | ./uploads | File storage path |
| `LOG_LEVEL` | No | INFO | Logging level |

### Port Mapping

| Service | Internal | External | Protocol |
|---------|----------|----------|----------|
| Frontend | 3000 | 80/443 | HTTP/HTTPS |
| Backend API | 8000 | 8000 | HTTP |
| PostgreSQL | 5432 | 55432 | TCP |
| Redis | 6379 | 56379 | TCP |
| Qdrant | 6333 | 6333 | HTTP |

---

## 📊 Health Checks

### API Health
```bash
curl http://localhost:8000/health
# Expected: {"status": "ok", "ok": true}
```

### Database Connection
```bash
curl http://localhost:8000/stats
# Expected: {"status": "ok", "public_tables": [...], "public_table_count": N}
```

### Redis Connection
```bash
curl http://localhost:8000/jobs/queue/status
# Expected: {"connected": true, "queue_name": "skillsight", ...}
```

---

## 🔒 Security Checklist

### Production Security
- [ ] Change all default passwords
- [ ] Enable HTTPS only
- [ ] Configure CORS for production domain
- [ ] Set up rate limiting
- [ ] Enable database SSL
- [ ] Configure firewall rules
- [ ] Set up log aggregation
- [ ] Enable audit logging
- [ ] Configure backup schedule

### Data Privacy (PDPO Compliance)
- [ ] Consent collection implemented
- [ ] Data deletion workflow tested
- [ ] Audit logs enabled
- [ ] Data retention policy configured
- [ ] Access controls verified

---

## 📈 Monitoring & Logging

### Log Locations
```
/var/log/skillsight/
├── api.log          # Backend API logs
├── worker.log       # Background job logs
├── access.log       # HTTP access logs
└── audit.log        # Audit trail
```

### Metrics to Monitor
- API response time (p50, p95, p99)
- Request rate per endpoint
- Error rate by type
- Database query latency
- Queue depth and processing time
- Storage usage
- Memory/CPU utilization

### Alerting Thresholds
| Metric | Warning | Critical |
|--------|---------|----------|
| API latency p95 | > 500ms | > 2000ms |
| Error rate | > 1% | > 5% |
| Queue depth | > 100 | > 500 |
| Disk usage | > 70% | > 90% |

---

## 🔄 Backup & Recovery

### Database Backup
```bash
# Daily backup script
pg_dump -h localhost -p 55432 -U skillsight -Fc skillsight > backup_$(date +%Y%m%d).dump

# Restore from backup
pg_restore -h localhost -p 55432 -U skillsight -d skillsight backup_20260121.dump
```

### File Storage Backup
```bash
# Sync uploads to S3
aws s3 sync ./uploads s3://skillsight-backups/uploads/

# Restore from S3
aws s3 sync s3://skillsight-backups/uploads/ ./uploads/
```

### Disaster Recovery Plan
1. **RTO (Recovery Time Objective)**: 4 hours
2. **RPO (Recovery Point Objective)**: 24 hours
3. **Backup Frequency**: Daily full + hourly incremental
4. **Retention**: 30 days

---

## 🚨 Troubleshooting

### Common Issues

#### 1. Database Connection Failed
```bash
# Check PostgreSQL container
docker logs skillsight_db

# Verify connection
psql -h localhost -p 55432 -U skillsight -d skillsight
```

#### 2. Embedding Generation Slow
```bash
# Check if GPU is available
python -c "import torch; print(torch.cuda.is_available())"

# Use smaller model for faster processing
export EMBEDDING_MODEL=all-MiniLM-L6-v2
```

#### 3. File Upload Failed
```bash
# Check storage permissions
ls -la ./uploads/

# Verify disk space
df -h
```

#### 4. Worker Not Processing Jobs
```bash
# Check Redis connection
redis-cli -p 56379 ping

# View queue status
redis-cli -p 56379 LLEN skillsight
```

---

## 📞 Support Contacts

| Role | Contact | Responsibility |
|------|---------|----------------|
| System Admin | admin@hku.hk | Infrastructure |
| Developer | dev@hku.hk | Application bugs |
| Data Officer | dpo@hku.hk | Privacy concerns |

---

## 📝 Change Log

| Version | Date | Changes |
|---------|------|---------|
| v0.1.0 | 2026-01-21 | Initial MVP release |
| v0.2.0 | 2026-01-21 | Added multimodal + interactive assessments |

---

## ✅ Go-Live Checklist

### Pre-Launch (1 week before)
- [ ] Load testing completed (100 concurrent users)
- [ ] Security audit passed
- [ ] UAT sign-off from stakeholders
- [ ] Documentation reviewed
- [ ] Support team trained

### Launch Day
- [ ] Backup taken
- [ ] Monitoring dashboards ready
- [ ] Support channels open
- [ ] Rollback plan documented
- [ ] DNS TTL lowered

### Post-Launch (1 week after)
- [ ] Performance baseline established
- [ ] User feedback collected
- [ ] Bug backlog prioritized
- [ ] Monitoring alerts tuned

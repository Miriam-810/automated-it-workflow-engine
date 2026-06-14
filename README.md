# Automated IT Workflow Engine

An enterprise-grade infrastructure provisioning and governance RESTful service built with **Python**, **FastAPI**, and **SQLAlchemy ORM**. This system is engineered to automate enterprise IT resource lifecycles, evaluating request risks through a custom rule-based policy gate to deliver instantaneous auto-approvals while ensuring strict transactional integrity.

## 🚀 Core Architectural Features

- **Asynchronous RESTful Architecture**: Built on top of FastAPI for high-concurrency request handling and self-documenting OpenAPI endpoints.
- **Automated Governance Rule Engine**: Evaluates metadata (such as estimated cost thresholds and risk parameters) to dynamically route requests between instant auto-approval (`approved`) and manager evaluation (`pending`).
- **Data Persistence Tier**: Leverages SQLAlchemy ORM with a decoupled relational database schema (SQLite) ensuring ACID compliance and resilient audit logging.
- **Enterprise Security Compliance**: Implements robust transaction workflows designed to eliminate manual tracking overhead and align with strict corporate governance audits.

## 🛠️ Technology Stack

- **Framework**: FastAPI (Python 3.13)
- **ORM / Database**: SQLAlchemy / SQLite 3
- **ASGI Server**: Uvicorn
- **Dependency Management**: Pydantic v2 (Data Validation), Pip

## 📂 Repository Structure

- `main.py` - Core API routing, middleware integration, and rule engine logic.
- `database.py` - Database engine instantiation, session manufacturing, and dependency injection lifecycle.
- `models.py` - Declarative relational database schemas and object mappings for audit tracking.
- `requirements.txt` - Locked production dependencies.

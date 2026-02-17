# ===============================================
# SERVIDOR CENTRAL FHIR-LITE PARA TALLER HCD v3.0
# ===============================================

from fastapi import FastAPI, HTTPException, Header, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, validator
from typing import List, Optional
import json
import os
import uuid
from datetime import datetime, date

# -----------------------------------------------
# CONFIGURACIÓN GENERAL
# -----------------------------------------------

app = FastAPI(
    title="Servidor Central FHIR-Lite",
    version="3.0",  # >>> MODIFICADO
    description="Nodo de interoperabilidad académica con auditoría clínica"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATABASE_FILE = "database_hcd.json"
API_KEY = "seguridad_clinica_2024_xyz"

# -----------------------------------------------
# SEGURIDAD
# -----------------------------------------------

def verify_api_key(x_api_key: str = Header(...)):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="No autorizado")

# -----------------------------------------------
# UTILIDADES DE BASE DE DATOS
# -----------------------------------------------

# >>> NUEVO: Inicializa DB si no existe
def initialize_db():
    if not os.path.exists(DATABASE_FILE):
        data = {
            "patients": {},
            "observations": [],
            "logs": []  # >>> NUEVO
        }
        save_db(data)

def load_db():
    initialize_db()
    with open(DATABASE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_db(data):
    with open(DATABASE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

# -----------------------------------------------
# LOGS CLÍNICOS (AUDITORÍA)
# -----------------------------------------------

# >>> NUEVO
def log_event(action, resource, resource_id):
    db = load_db()

    log_entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "action": action,
        "resource": resource,
        "resource_id": resource_id
    }

    db["logs"].append(log_entry)
    save_db(db)

# -----------------------------------------------
# MODELOS
# -----------------------------------------------

class Patient(BaseModel):
    id: str
    family_name: str
    given_name: str
    gender: str
    birthDate: str
    medical_summary: str

    # >>> NUEVO: Validación clínica
    @validator("gender")
    def validate_gender(cls, v):
        if v not in ["male", "female", "other"]:
            raise ValueError("Género inválido")
        return v

    @validator("birthDate")
    def validate_birthdate(cls, v):
        if datetime.fromisoformat(v).date() > date.today():
            raise ValueError("Fecha de nacimiento futura no permitida")
        return v

# >>> NUEVO: Modelo para PATCH parcial
class PatientUpdate(BaseModel):
    family_name: Optional[str] = None
    given_name: Optional[str] = None
    gender: Optional[str] = None
    birthDate: Optional[str] = None
    medical_summary: Optional[str] = None

class Observation(BaseModel):
    patient_id: str
    category: str
    code: str
    display: str
    value: float
    unit: str
    date: str

# ===============================================
# ENDPOINTS FHIR
# ===============================================

# -----------------------------------------------
# LISTAR PACIENTES CON PAGINACIÓN
# -----------------------------------------------

# >>> MODIFICADO: ahora incluye paginación
@app.get("/fhir/Patient", dependencies=[Depends(verify_api_key)])
def get_patients(page: int = 1, size: int = 10):

    db = load_db()
    patients = list(db["patients"].values())

    start = (page - 1) * size
    end = start + size

    return {
        "total": len(patients),
        "page": page,
        "size": size,
        "data": patients[start:end]
    }

# -----------------------------------------------
# BÚSQUEDA POR NOMBRE
# -----------------------------------------------

# >>> NUEVO
@app.get("/fhir/Patient/search", dependencies=[Depends(verify_api_key)])
def search_patients(name: str):

    db = load_db()

    results = [
        p for p in db["patients"].values()
        if name.lower() in p["family_name"].lower()
        or name.lower() in p["given_name"].lower()
    ]

    return results

# -----------------------------------------------
# CREAR PACIENTE
# -----------------------------------------------

@app.post("/fhir/Patient", dependencies=[Depends(verify_api_key)])
def create_patient(patient: Patient):

    db = load_db()

    if patient.id in db["patients"]:
        raise HTTPException(400, "El paciente ya existe")

    db["patients"][patient.id] = patient.dict()
    save_db(db)

    log_event("CREATE", "Patient", patient.id)  # >>> NUEVO

    return {"mensaje": "Paciente creado correctamente"}

# -----------------------------------------------
# ACTUALIZAR PACIENTE COMPLETO
# -----------------------------------------------

@app.put("/fhir/Patient/{patient_id}", dependencies=[Depends(verify_api_key)])
def update_patient(patient_id: str, patient: Patient):

    db = load_db()

    if patient_id not in db["patients"]:
        raise HTTPException(404, "Paciente no encontrado")

    db["patients"][patient_id] = patient.dict()
    save_db(db)

    log_event("PUT", "Patient", patient_id)  # >>> NUEVO

    return {"mensaje": "Paciente actualizado"}

# -----------------------------------------------
# PATCH PARCIAL
# -----------------------------------------------

# >>> NUEVO
@app.patch("/fhir/Patient/{patient_id}", dependencies=[Depends(verify_api_key)])
def patch_patient(patient_id: str, updates: PatientUpdate):

    db = load_db()

    if patient_id not in db["patients"]:
        raise HTTPException(404, "Paciente no encontrado")

    patient = db["patients"][patient_id]
    update_data = updates.dict(exclude_unset=True)

    for key, value in update_data.items():
        patient[key] = value

    db["patients"][patient_id] = patient
    save_db(db)

    log_event("PATCH", "Patient", patient_id)

    return {"mensaje": "Paciente actualizado parcialmente"}

# -----------------------------------------------
# ELIMINAR PACIENTE
# -----------------------------------------------

@app.delete("/fhir/Patient/{patient_id}", dependencies=[Depends(verify_api_key)])
def delete_patient(patient_id: str):

    db = load_db()

    if patient_id not in db["patients"]:
        raise HTTPException(404, "Paciente no encontrado")

    del db["patients"][patient_id]

    db["observations"] = [
        obs for obs in db["observations"]
        if obs["patient_id"] != patient_id
    ]

    save_db(db)

    log_event("DELETE", "Patient", patient_id)  # >>> NUEVO

    return {"mensaje": "Paciente y observaciones eliminadas"}

# -----------------------------------------------
# LISTAR OBSERVACIONES POR PACIENTE
# -----------------------------------------------

@app.get("/fhir/Observation/{patient_id}", dependencies=[Depends(verify_api_key)])
def get_observations(patient_id: str):

    db = load_db()

    obs = [
        o for o in db["observations"]
        if o["patient_id"] == patient_id
    ]

    return obs

# -----------------------------------------------
# CREAR OBSERVACIÓN
# -----------------------------------------------

@app.post("/fhir/Observation", dependencies=[Depends(verify_api_key)])
def create_observation(observation: Observation):

    db = load_db()

    if observation.patient_id not in db["patients"]:
        raise HTTPException(404, "Paciente no existe")

    new_obs = observation.dict()
    new_obs["id"] = str(uuid.uuid4())

    db["observations"].append(new_obs)
    save_db(db)

    log_event("CREATE", "Observation", new_obs["id"])  # >>> NUEVO

    return {"mensaje": "Observación registrada"}

# -----------------------------------------------
# VER LOGS CLÍNICOS
# -----------------------------------------------

# >>> NUEVO
@app.get("/logs", dependencies=[Depends(verify_api_key)])
def get_logs():
    db = load_db()
    return db["logs"]






# ===============================================
# SERVIDOR CENTRAL FHIR-LITE PARA TALLER HCD v3.1
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
    version="3.1",
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

def initialize_db():
    if not os.path.exists(DATABASE_FILE):
        data = {
            "patients": {},
            "observations": [],
            "logs": []
        }
        save_db(data)

### CAMBIO CRÍTICO 1: Manejo de errores en load_db ###
# Antes: json.load(f) fallaba si el archivo estaba corrupto o vacío.
# Ahora: Si hay basura en el JSON, devuelve una estructura limpia en lugar de colapsar (Error 500).
def load_db():
    initialize_db()
    try:
        with open(DATABASE_FILE, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                return {"patients": {}, "observations": [], "logs": []}
            return json.loads(content)
    except (json.JSONDecodeError, FileNotFoundError, Exception):
        # Reinicia la estructura en memoria si el archivo físico está roto
        return {"patients": {}, "observations": [], "logs": []}

def save_db(data):
    with open(DATABASE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

# -----------------------------------------------
# LOGS CLÍNICOS (AUDITORÍA)
# -----------------------------------------------

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

    @validator("gender")
    def validate_gender(cls, v):
        if v not in ["male", "female", "other"]:
            raise ValueError("Género inválido")
        return v

    @validator("birthDate")
    def validate_birthdate(cls, v):
        try:
            if datetime.fromisoformat(v).date() > date.today():
                raise ValueError("Fecha de nacimiento futura no permitida")
        except ValueError:
            raise ValueError("Formato de fecha inválido (debe ser YYYY-MM-DD)")
        return v

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

@app.get("/fhir/Patient/search", dependencies=[Depends(verify_api_key)])
def search_patients(name: str):
    db = load_db()
    results = [
        p for p in db["patients"].values()
        if name.lower() in p["family_name"].lower()
        or name.lower() in p["given_name"].lower()
    ]
    return results

@app.post("/fhir/Patient", dependencies=[Depends(verify_api_key)])
def create_patient(patient: Patient):
    db = load_db()
    if patient.id in db["patients"]:
        raise HTTPException(400, "El paciente ya existe")
    db["patients"][patient.id] = patient.dict()
    save_db(db)
    log_event("CREATE", "Patient", patient.id)
    return {"mensaje": "Paciente creado correctamente"}

@app.put("/fhir/Patient/{patient_id}", dependencies=[Depends(verify_api_key)])
def update_patient(patient_id: str, patient: Patient):
    db = load_db()
    if patient_id not in db["patients"]:
        raise HTTPException(404, "Paciente no encontrado")
    db["patients"][patient_id] = patient.dict()
    save_db(db)
    log_event("PUT", "Patient", patient_id)
    return {"mensaje": "Paciente actualizado"}

### CAMBIO CRÍTICO 2: Validación en PATCH ###
# Antes: Mezclaba datos y guardaba sin validar, dejando basura como "string" en la DB.
# Ahora: Valida el objeto final contra el modelo Patient antes de escribir.
@app.patch("/fhir/Patient/{patient_id}", dependencies=[Depends(verify_api_key)])
def patch_patient(patient_id: str, updates: PatientUpdate):
    db = load_db()
    if patient_id not in db["patients"]:
        raise HTTPException(404, "Paciente no encontrado")

    patient_data = db["patients"][patient_id]
    update_data = updates.dict(exclude_unset=True)

    # Aplicar cambios
    for key, value in update_data.items():
        patient_data[key] = value

    # Validar integridad clínica del resultado
    try:
        Patient(**patient_data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error en validación clínica: {str(e)}")

    db["patients"][patient_id] = patient_data
    save_db(db)
    log_event("PATCH", "Patient", patient_id)
    return {"mensaje": "Paciente actualizado parcialmente"}

@app.delete("/fhir/Patient/{patient_id}", dependencies=[Depends(verify_api_key)])
def delete_patient(patient_id: str):
    db = load_db()
    if patient_id not in db["patients"]:
        raise HTTPException(404, "Paciente no encontrado")
    del db["patients"][patient_id]
    db["observations"] = [o for o in db["observations"] if o["patient_id"] != patient_id]
    save_db(db)
    log_event("DELETE", "Patient", patient_id)
    return {"mensaje": "Paciente y observaciones eliminadas"}

@app.get("/fhir/Observation/{patient_id}", dependencies=[Depends(verify_api_key)])
def get_observations(patient_id: str):
    db = load_db()
    obs = [o for o in db["observations"] if o["patient_id"] == patient_id]
    return obs

@app.post("/fhir/Observation", dependencies=[Depends(verify_api_key)])
def create_observation(observation: Observation):
    db = load_db()
    if observation.patient_id not in db["patients"]:
        raise HTTPException(404, "Paciente no existe")
    new_obs = observation.dict()
    new_obs["id"] = str(uuid.uuid4())
    db["observations"].append(new_obs)
    save_db(db)
    log_event("CREATE", "Observation", new_obs["id"])
    return {"mensaje": "Observación registrada"}

@app.get("/logs", dependencies=[Depends(verify_api_key)])
def get_logs():
    db = load_db()
    return db["logs"]






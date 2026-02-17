# ===============================================
# SERVIDOR CENTRAL FHIR-LITE PARA TALLER HCD v3.2
# ===============================================

from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, validator
from typing import Optional
import json
import os
import uuid
from datetime import datetime, date

# -----------------------------------------------
# CONFIGURACIÓN GENERAL
# -----------------------------------------------

app = FastAPI(
    title="Servidor Central FHIR-Lite",
    version="3.2",
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

def get_empty_db():
    """Retorna estructura vacía de DB"""
    return {"patients": {}, "observations": [], "logs": []}

def initialize_db():
    """Crea el archivo DB si no existe"""
    if not os.path.exists(DATABASE_FILE):
        save_db(get_empty_db())

def load_db():
    """Carga DB con manejo robusto de errores"""
    try:
        # Intentar cargar el archivo
        if not os.path.exists(DATABASE_FILE):
            initialize_db()
            
        with open(DATABASE_FILE, "r", encoding="utf-8") as f:
            content = f.read().strip()
            
            # Si está vacío, devolver estructura limpia
            if not content:
                clean_db = get_empty_db()
                save_db(clean_db)
                return clean_db
            
            # Intentar parsear JSON
            db = json.loads(content)
            
            # Validar estructura mínima
            if not isinstance(db, dict):
                raise ValueError("DB no es un diccionario")
            
            # Asegurar que existan las claves necesarias
            if "patients" not in db:
                db["patients"] = {}
            if "observations" not in db:
                db["observations"] = []
            if "logs" not in db:
                db["logs"] = []
                
            return db
            
    except (json.JSONDecodeError, ValueError, KeyError, Exception) as e:
        # Si hay cualquier error, reiniciar DB y registrar en logs
        print(f"⚠️ Error al cargar DB: {str(e)}. Reiniciando...")
        clean_db = get_empty_db()
        save_db(clean_db)
        return clean_db

def save_db(data):
    """Guarda DB con validación"""
    try:
        # Validar estructura antes de guardar
        if not isinstance(data, dict):
            raise ValueError("Los datos deben ser un diccionario")
        
        # Escribir con formato legible
        with open(DATABASE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
            
    except Exception as e:
        print(f"❌ Error al guardar DB: {str(e)}")
        raise HTTPException(500, f"Error al guardar en base de datos: {str(e)}")

# -----------------------------------------------
# LOGS CLÍNICOS (AUDITORÍA)
# -----------------------------------------------

def log_event(action, resource, resource_id):
    """Registra evento con manejo de errores"""
    try:
        db = load_db()
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "action": action,
            "resource": resource,
            "resource_id": resource_id
        }
        db["logs"].append(log_entry)
        save_db(db)
    except Exception as e:
        print(f"⚠️ Error al registrar log: {str(e)}")

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

@app.get("/")
def root():
    """Endpoint de salud del servicio"""
    return {
        "status": "ok",
        "message": "Servidor FHIR-Lite activo",
        "version": "3.2"
    }

@app.get("/health")
def health_check():
    """Verifica que la DB sea accesible"""
    try:
        db = load_db()
        return {
            "status": "healthy",
            "patients": len(db.get("patients", {})),
            "observations": len(db.get("observations", [])),
            "logs": len(db.get("logs", []))
        }
    except Exception as e:
        raise HTTPException(500, f"Error de salud: {str(e)}")

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
    return {"mensaje": "Observación registrada", "id": new_obs["id"]}

@app.get("/logs", dependencies=[Depends(verify_api_key)])
def get_logs():
    db = load_db()
    return db["logs"]

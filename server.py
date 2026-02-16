
# ===============================================
# SERVIDOR CENTRAL FHIR-LITE PARA TALLER HCD
# ===============================================

from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
import json
import os
import uuid
from datetime import datetime

# -----------------------------------------------
# CONFIGURACIÓN GENERAL
# -----------------------------------------------

app = FastAPI(
    title="Servidor Central FHIR-Lite",
    version="2.0",
    description="Nodo de interoperabilidad académica"
)

# Permite conexiones externas (todos los estudiantes)
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

def load_db():
    with open(DATABASE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_db(data):
    with open(DATABASE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

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
# LISTAR PACIENTES
# -----------------------------------------------

@app.get("/fhir/Patient", dependencies=[Depends(verify_api_key)])
def get_patients():
    db = load_db()
    return list(db["patients"].values())

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

    return {"mensaje": "Paciente creado correctamente"}

# -----------------------------------------------
# ACTUALIZAR PACIENTE
# -----------------------------------------------

@app.put("/fhir/Patient/{patient_id}", dependencies=[Depends(verify_api_key)])
def update_patient(patient_id: str, patient: Patient):

    db = load_db()

    if patient_id not in db["patients"]:
        raise HTTPException(404, "Paciente no encontrado")

    db["patients"][patient_id] = patient.dict()
    save_db(db)

    return {"mensaje": "Paciente actualizado"}

# -----------------------------------------------
# ELIMINAR PACIENTE
# -----------------------------------------------

@app.delete("/fhir/Patient/{patient_id}", dependencies=[Depends(verify_api_key)])
def delete_patient(patient_id: str):

    db = load_db()

    if patient_id not in db["patients"]:
        raise HTTPException(404, "Paciente no encontrado")

    # Eliminar paciente
    del db["patients"][patient_id]

    # Eliminar también sus observaciones asociadas
    db["observations"] = [
        obs for obs in db["observations"]
        if obs["patient_id"] != patient_id
    ]

    save_db(db)

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

    return {"mensaje": "Observación registrada"}
    

# -----------------------------------------------
# EJECUCIÓN DEL SERVIDOR
# -----------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )

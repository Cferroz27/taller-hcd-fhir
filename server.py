# ===============================================
# SERVIDOR CENTRAL FHIR-LITE CON POSTGRESQL v4.0
# ===============================================

from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, validator
from typing import Optional
import os
import uuid
from datetime import datetime, date
import psycopg2
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager

# -----------------------------------------------
# CONFIGURACIÓN GENERAL
# -----------------------------------------------

app = FastAPI(
    title="Servidor Central FHIR-Lite PostgreSQL",
    version="4.0",
    description="Nodo de interoperabilidad académica con persistencia robusta"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_KEY = "seguridad_clinica_2024_xyz"
DATABASE_URL = os.getenv("DATABASE_URL")

# -----------------------------------------------
# CONEXIÓN A BASE DE DATOS
# -----------------------------------------------

@contextmanager
def get_db_connection():
    """Context manager para conexiones seguras"""
    if not DATABASE_URL:
        raise HTTPException(500, "DATABASE_URL no configurada en variables de entorno")
    
    conn = None
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        yield conn
        conn.commit()
    except psycopg2.Error as e:
        if conn:
            conn.rollback()
        raise HTTPException(500, f"Error de base de datos: {str(e)}")
    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(500, f"Error inesperado: {str(e)}")
    finally:
        if conn:
            conn.close()

def initialize_db():
    """Crea las tablas si no existen"""
    with get_db_connection() as conn:
        cur = conn.cursor()
        
        # Tabla de pacientes
        cur.execute("""
            CREATE TABLE IF NOT EXISTS patients (
                id VARCHAR(50) PRIMARY KEY,
                family_name VARCHAR(100) NOT NULL,
                given_name VARCHAR(100) NOT NULL,
                gender VARCHAR(10) NOT NULL CHECK (gender IN ('male', 'female', 'other')),
                birth_date DATE NOT NULL,
                medical_summary TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Tabla de observaciones
        cur.execute("""
            CREATE TABLE IF NOT EXISTS observations (
                id VARCHAR(50) PRIMARY KEY,
                patient_id VARCHAR(50) NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
                category VARCHAR(50) NOT NULL,
                code VARCHAR(50) NOT NULL,
                display VARCHAR(100) NOT NULL,
                value FLOAT NOT NULL,
                unit VARCHAR(20) NOT NULL,
                date DATE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Índice para búsquedas rápidas
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_obs_patient 
            ON observations(patient_id)
        """)
        
        # Tabla de logs
        cur.execute("""
            CREATE TABLE IF NOT EXISTS logs (
                id SERIAL PRIMARY KEY,
                timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                action VARCHAR(20) NOT NULL,
                resource VARCHAR(50) NOT NULL,
                resource_id VARCHAR(50) NOT NULL
            )
        """)
        
        print("✅ Tablas inicializadas correctamente")

# -----------------------------------------------
# EVENTO DE INICIO
# -----------------------------------------------

@app.on_event("startup")
def startup():
    """Se ejecuta al arrancar el servidor"""
    try:
        initialize_db()
        print("🚀 Servidor FHIR-Lite iniciado correctamente")
    except Exception as e:
        print(f"❌ Error al inicializar: {e}")

# -----------------------------------------------
# SEGURIDAD
# -----------------------------------------------

def verify_api_key(x_api_key: str = Header(...)):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="No autorizado")

# -----------------------------------------------
# LOGS CLÍNICOS
# -----------------------------------------------

def log_event(action: str, resource: str, resource_id: str):
    """Registra evento de auditoría"""
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO logs (timestamp, action, resource, resource_id) VALUES (%s, %s, %s, %s)",
                (datetime.utcnow(), action, resource, resource_id)
            )
    except Exception as e:
        print(f"⚠️ Error al registrar log: {e}")

# -----------------------------------------------
# MODELOS PYDANTIC
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
            raise ValueError("Género debe ser 'male', 'female' u 'other'")
        return v

    @validator("birthDate")
    def validate_birthdate(cls, v):
        try:
            birth = datetime.fromisoformat(v).date()
            if birth > date.today():
                raise ValueError("Fecha de nacimiento no puede ser futura")
            if birth < date(1900, 1, 1):
                raise ValueError("Fecha de nacimiento inválida")
        except ValueError as e:
            raise ValueError(f"Fecha inválida: {str(e)}")
        return v

class PatientUpdate(BaseModel):
    family_name: Optional[str] = None
    given_name: Optional[str] = None
    gender: Optional[str] = None
    birthDate: Optional[str] = None
    medical_summary: Optional[str] = None

    @validator("gender")
    def validate_gender(cls, v):
        if v and v not in ["male", "female", "other"]:
            raise ValueError("Género debe ser 'male', 'female' u 'other'")
        return v

class Observation(BaseModel):
    patient_id: str
    category: str
    code: str
    display: str
    value: float
    unit: str
    date: str

    @validator("date")
    def validate_date(cls, v):
        try:
            datetime.fromisoformat(v)
        except ValueError:
            raise ValueError("Formato de fecha inválido (use YYYY-MM-DD)")
        return v

# ===============================================
# ENDPOINTS FHIR
# ===============================================

@app.get("/")
def root():
    """Endpoint de salud del servicio"""
    return {
        "status": "ok",
        "message": "Servidor FHIR-Lite PostgreSQL activo",
        "version": "4.0"
    }

@app.get("/health")
def health_check():
    """Verifica conectividad con la base de datos"""
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) as total FROM patients")
            patients = cur.fetchone()["total"]
            cur.execute("SELECT COUNT(*) as total FROM observations")
            observations = cur.fetchone()["total"]
            cur.execute("SELECT COUNT(*) as total FROM logs")
            logs = cur.fetchone()["total"]
            
        return {
            "status": "healthy",
            "database": "connected",
            "patients": patients,
            "observations": observations,
            "logs": logs
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }

# ─────────────────────────────────────────────
# ENDPOINTS DE PACIENTES
# ─────────────────────────────────────────────

@app.get("/fhir/Patient", dependencies=[Depends(verify_api_key)])
def get_patients(page: int = 1, size: int = 10):
    """Lista paginada de pacientes"""
    with get_db_connection() as conn:
        cur = conn.cursor()
        
        offset = (page - 1) * size
        cur.execute("SELECT COUNT(*) as total FROM patients")
        total = cur.fetchone()["total"]
        
        cur.execute(
            """SELECT id, family_name, given_name, gender, 
                      birth_date as "birthDate", medical_summary
               FROM patients 
               ORDER BY created_at DESC
               LIMIT %s OFFSET %s""",
            (size, offset)
        )
        patients = cur.fetchall()
        
    return {
        "total": total,
        "page": page,
        "size": size,
        "data": [dict(p) for p in patients]
    }

@app.get("/fhir/Patient/search", dependencies=[Depends(verify_api_key)])
def search_patients(name: str):
    """Buscar pacientes por nombre"""
    with get_db_connection() as conn:
        cur = conn.cursor()
        
        cur.execute(
            """SELECT id, family_name, given_name, gender, 
                      birth_date as "birthDate", medical_summary 
               FROM patients 
               WHERE LOWER(family_name) LIKE %s OR LOWER(given_name) LIKE %s
               ORDER BY family_name, given_name""",
            (f"%{name.lower()}%", f"%{name.lower()}%")
        )
        results = cur.fetchall()
        
    return [dict(r) for r in results]

@app.post("/fhir/Patient", dependencies=[Depends(verify_api_key)])
def create_patient(patient: Patient):
    """Crear nuevo paciente"""
    with get_db_connection() as conn:
        cur = conn.cursor()
        
        # Verificar si existe
        cur.execute("SELECT id FROM patients WHERE id = %s", (patient.id,))
        if cur.fetchone():
            raise HTTPException(400, f"El paciente '{patient.id}' ya existe")
        
        # Insertar
        cur.execute(
            """INSERT INTO patients (id, family_name, given_name, gender, birth_date, medical_summary)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (patient.id, patient.family_name, patient.given_name, 
             patient.gender, patient.birthDate, patient.medical_summary)
        )
    
    log_event("CREATE", "Patient", patient.id)
    return {"mensaje": "Paciente creado correctamente", "id": patient.id}

@app.put("/fhir/Patient/{patient_id}", dependencies=[Depends(verify_api_key)])
def update_patient(patient_id: str, patient: Patient):
    """Actualizar paciente completo (reemplaza todos los campos)"""
    with get_db_connection() as conn:
        cur = conn.cursor()
        
        cur.execute("SELECT id FROM patients WHERE id = %s", (patient_id,))
        if not cur.fetchone():
            raise HTTPException(404, f"Paciente '{patient_id}' no encontrado")
        
        cur.execute(
            """UPDATE patients 
               SET family_name=%s, given_name=%s, gender=%s, 
                   birth_date=%s, medical_summary=%s, updated_at=CURRENT_TIMESTAMP
               WHERE id=%s""",
            (patient.family_name, patient.given_name, patient.gender, 
             patient.birthDate, patient.medical_summary, patient_id)
        )
    
    log_event("PUT", "Patient", patient_id)
    return {"mensaje": "Paciente actualizado completamente"}

@app.patch("/fhir/Patient/{patient_id}", dependencies=[Depends(verify_api_key)])
def patch_patient(patient_id: str, updates: PatientUpdate):
    """Actualizar campos específicos del paciente"""
    with get_db_connection() as conn:
        cur = conn.cursor()
        
        cur.execute("SELECT * FROM patients WHERE id = %s", (patient_id,))
        if not cur.fetchone():
            raise HTTPException(404, f"Paciente '{patient_id}' no encontrado")
        
        # Construir query dinámico
        update_fields = []
        update_values = []
        
        for key, value in updates.dict(exclude_unset=True).items():
            field_name = "birth_date" if key == "birthDate" else key
            update_fields.append(f"{field_name} = %s")
            update_values.append(value)
        
        if not update_fields:
            raise HTTPException(400, "No se proporcionaron campos para actualizar")
        
        update_fields.append("updated_at = CURRENT_TIMESTAMP")
        update_values.append(patient_id)
        
        query = f"UPDATE patients SET {', '.join(update_fields)} WHERE id = %s"
        cur.execute(query, update_values)
    
    log_event("PATCH", "Patient", patient_id)
    return {"mensaje": "Paciente actualizado parcialmente"}

@app.delete("/fhir/Patient/{patient_id}", dependencies=[Depends(verify_api_key)])
def delete_patient(patient_id: str):
    """Eliminar paciente y todas sus observaciones"""
    with get_db_connection() as conn:
        cur = conn.cursor()
        
        cur.execute("SELECT id FROM patients WHERE id = %s", (patient_id,))
        if not cur.fetchone():
            raise HTTPException(404, f"Paciente '{patient_id}' no encontrado")
        
        # Contar observaciones
        cur.execute("SELECT COUNT(*) as total FROM observations WHERE patient_id = %s", (patient_id,))
        obs_count = cur.fetchone()["total"]
        
        # Eliminar (CASCADE eliminará observaciones automáticamente)
        cur.execute("DELETE FROM patients WHERE id = %s", (patient_id,))
    
    log_event("DELETE", "Patient", patient_id)
    return {
        "mensaje": f"Paciente '{patient_id}' eliminado",
        "observaciones_eliminadas": obs_count
    }

# ─────────────────────────────────────────────
# ENDPOINTS DE OBSERVACIONES
# ─────────────────────────────────────────────

@app.get("/fhir/Observation/{patient_id}", dependencies=[Depends(verify_api_key)])
def get_observations(patient_id: str):
    """Obtener todas las observaciones de un paciente"""
    with get_db_connection() as conn:
        cur = conn.cursor()
        
        # Verificar que el paciente existe
        cur.execute("SELECT id FROM patients WHERE id = %s", (patient_id,))
        if not cur.fetchone():
            raise HTTPException(404, f"Paciente '{patient_id}' no encontrado")
        
        cur.execute(
            """SELECT id, patient_id, category, code, display, value, unit, 
                      date, created_at
               FROM observations 
               WHERE patient_id = %s
               ORDER BY date DESC, created_at DESC""",
            (patient_id,)
        )
        observations = cur.fetchall()
    
    return [dict(o) for o in observations]

@app.post("/fhir/Observation", dependencies=[Depends(verify_api_key)])
def create_observation(observation: Observation):
    """Crear nueva observación para un paciente"""
    with get_db_connection() as conn:
        cur = conn.cursor()
        
        # Verificar que el paciente existe
        cur.execute("SELECT id FROM patients WHERE id = %s", (observation.patient_id,))
        if not cur.fetchone():
            raise HTTPException(404, f"Paciente '{observation.patient_id}' no existe")
        
        obs_id = str(uuid.uuid4())
        cur.execute(
            """INSERT INTO observations (id, patient_id, category, code, display, value, unit, date)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (obs_id, observation.patient_id, observation.category, observation.code, 
             observation.display, observation.value, observation.unit, observation.date)
        )
    
    log_event("CREATE", "Observation", obs_id)
    return {"mensaje": "Observación registrada correctamente", "id": obs_id}

# ─────────────────────────────────────────────
# ENDPOINTS DE AUDITORÍA
# ─────────────────────────────────────────────

@app.get("/logs", dependencies=[Depends(verify_api_key)])
def get_logs(limit: int = 100):
    """Obtener logs de auditoría"""
    with get_db_connection() as conn:
        cur = conn.cursor()
        
        cur.execute(
            """SELECT id, timestamp, action, resource, resource_id 
               FROM logs 
               ORDER BY timestamp DESC 
               LIMIT %s""",
            (limit,)
        )
        logs = cur.fetchall()
    
    return [dict(log) for log in logs]


from pydantic_settings import BaseSettings
from typing import Dict, List, Any
import os

class Settings(BaseSettings):
    PROJECT_NAME: str = "MahaArogya-Agent"
    PROJECT_TAGLINE: str = "Autonomous Rural Healthcare & Closed-Loop Referral Tracking System"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    
    # Regional Settings (Maharashtra Public Health Department / Arogya Vibhag)
    DEFAULT_STATE: str = "Maharashtra"
    SUPPORTED_LANGUAGES: List[str] = ["mr", "hi", "en"]
    DEFAULT_LANGUAGE: str = "mr"  # Marathi
    
    # SLA Configurations
    REFERRAL_SLA_HOURS: int = 48
    CRITICAL_RUNWAY_DAYS_THRESHOLD: int = 7
    
    # Bhashini & Whisper Service
    BHASHINI_API_KEY: str = os.getenv("BHASHINI_API_KEY", "mock_bhashini_demo_key")
    BHASHINI_USER_ID: str = os.getenv("BHASHINI_USER_ID", "gov_maha_health_dept")
    BHASHINI_PIPELINE_ID: str = os.getenv("BHASHINI_PIPELINE_ID", "asr_translation_tts_pipeline")
    
    # Persistence & Checkpointing
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./maha_arogya.db")
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    
    # Security / Encryption
    QR_SIGNING_SECRET: str = os.getenv("QR_SIGNING_SECRET", "maha-arogya-sih2026-secret-key-998811")
    
    # Districts and Hospitals Registry (Maharashtra)
    DISTRICT_HOSPITAL_REGISTRY: Dict[str, List[Dict[str, Any]]] = {
        "Pune": [
            {
                "hospital_id": "HOSP-PUN-01",
                "name": "Sassoon General Hospital & BJ Medical College",
                "type": "Tertiary / District Civil Hospital",
                "specialties": ["Obstetrics & Gynecology", "Pediatrics", "Cardiology", "General Surgery"],
                "total_beds": 1200,
                "available_emergency_slots": 14,
                "ambulance_helpline": "020-26128000"
            },
            {
                "hospital_id": "HOSP-PUN-02",
                "name": "Sub-District Hospital Baramati",
                "type": "Sub-District Hospital (SDH)",
                "specialties": ["Obstetrics & Gynecology", "General Medicine"],
                "total_beds": 100,
                "available_emergency_slots": 5,
                "ambulance_helpline": "02112-243200"
            }
        ],
        "Nashik": [
            {
                "hospital_id": "HOSP-NSK-01",
                "name": "Nashik District Civil Hospital",
                "type": "District Civil Hospital",
                "specialties": ["Obstetrics & Gynecology", "Pediatrics", "Infectious Diseases"],
                "total_beds": 550,
                "available_emergency_slots": 9,
                "ambulance_helpline": "0253-2572201"
            }
        ],
        "Gadchiroli": [
            {
                "hospital_id": "HOSP-GAD-01",
                "name": "District Hospital Gadchiroli",
                "type": "District Hospital (Tribal Belt)",
                "specialties": ["Obstetrics & Gynecology", "Malaria/Vector Borne", "Emergency Trauma"],
                "total_beds": 300,
                "available_emergency_slots": 6,
                "ambulance_helpline": "07132-222108"
            }
        ],
        "Thane": [
            {
                "hospital_id": "HOSP-THN-01",
                "name": "Chhatrapati Shivaji Maharaj Hospital Kalwa",
                "type": "District Civil Hospital",
                "specialties": ["Obstetrics & Gynecology", "Pediatrics", "Cardiology"],
                "total_beds": 600,
                "available_emergency_slots": 8,
                "ambulance_helpline": "022-25442525"
            }
        ],
        "Chhatrapati Sambhaji Nagar": [
            {
                "hospital_id": "HOSP-CSN-01",
                "name": "Government Medical College & Hospital Aurangabad (GMCH)",
                "type": "Tertiary Medical Center",
                "specialties": ["Obstetrics & Gynecology", "Critical Care", "Neurology"],
                "total_beds": 1170,
                "available_emergency_slots": 12,
                "ambulance_helpline": "0240-2402412"
            }
        ]
    }
    
    # PHC Mock Registry
    PHC_REGISTRY: Dict[str, Dict[str, Any]] = {
        "PHC-PUN-KND": {
            "name": "Khandala Primary Health Centre",
            "district": "Pune",
            "mo_in_charge": "Dr. Vaishali Kulkarni",
            "phone": "+91-9822110011"
        },
        "PHC-GAD-BHM": {
            "name": "Bhamragad Tribal Health Post",
            "district": "Gadchiroli",
            "mo_in_charge": "Dr. Ravindra Meshram",
            "phone": "+91-9422554433"
        },
        "PHC-NSK-TRB": {
            "name": "Trimbak Rural Primary Health Centre",
            "district": "Nashik",
            "mo_in_charge": "Dr. Santosh Patil",
            "phone": "+91-9766332211"
        }
    }

settings = Settings()

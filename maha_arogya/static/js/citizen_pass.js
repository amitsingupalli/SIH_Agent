/**
 * MahaArogya Citizen Vernacular Referral Pass Module
 * Government of Maharashtra - Arogya Vibhag | SIH 2026 PS 133
 * 
 * Capabilities:
 * 1. Ultra-lightweight mobile referral ticket viewer for rural citizens
 * 2. Scannable high-resolution QR code
 * 3. Bilingual Marathi & English one-tap toggle
 * 4. Direct 108 Emergency Ambulance dialer
 * 5. Google Maps navigation link to destination hospital
 */

const CitizenPass = (function () {
    let currentPassData = null;
    let isMarathi = true;

    async function init() {
        const pathParts = window.location.pathname.split("/");
        let token = pathParts[pathParts.length - 1];
        if (!token || token === "pass") {
            const urlParams = new URLSearchParams(window.location.search);
            token = urlParams.get("token") || "REF-4102-EMRG";
        }

        await loadPassData(token);
    }

    async function loadPassData(token) {
        try {
            const res = await fetch(`/api/pass/${token}`);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            currentPassData = data;
            renderPass();
        } catch (e) {
            console.error("Failed to load referral pass data:", e);
        }
    }

    function renderPass() {
        if (!currentPassData) return;
        const d = currentPassData;

        // Header / Urgency
        const urgencyElem = document.getElementById("citizenUrgencyBadge");
        if (urgencyElem) {
            urgencyElem.innerText = isMarathi 
                ? (d.urgency || "तातडीची प्रसूती पूर्व संदर्भ (STAT / High Risk)") 
                : "STAT EMERGENCY OBSTETRIC REFERRAL";
        }

        document.getElementById("citizenPatientName").innerText = d.patient_name || "Sunita Patil (सुनिता पाटील)";
        document.getElementById("citizenPatientId").innerText = `Patient ID: ${d.patient_id || "PAT-4102"} | Ref: ${d.referral_id}`;
        document.getElementById("citizenHospitalName").innerText = d.hospital_name;
        document.getElementById("citizenHospitalAddress").innerText = d.hospital_address || "District Civil Hospital Emergency Hub";
        document.getElementById("citizenReportingWindow").innerText = d.reporting_window || "Within 48 Hours";
        document.getElementById("citizenDoctorName").innerText = d.emergency_doctor || "Dr. Vaishali Kulkarni (CEmONC Medical Officer)";

        // Instructions
        const instElem = document.getElementById("citizenInstructions");
        if (instElem) {
            instElem.innerText = isMarathi 
                ? (d.instructions_vernacular || "हा QR पास जिल्हा रुग्णालयाच्या आपत्कालीन खिडकीवर दाखवा. थेट उपचार सुरू होतील.")
                : (d.instructions_english || "Show this QR pass at the Emergency Desk of the Civil Hospital for direct priority admission.");
        }

        // QR Code display
        const qrContainer = document.getElementById("citizenQrCodeImage");
        if (qrContainer) {
            if (d.qr_image_base64 && d.qr_image_base64.length > 20) {
                const src = d.qr_image_base64.startsWith("data:") 
                    ? d.qr_image_base64 
                    : "data:image/png;base64," + d.qr_image_base64;
                qrContainer.src = src;
            } else {
                // Fallback QR code API
                qrContainer.src = `https://api.qrserver.com/v1/create-qr-code/?size=180x180&data=${encodeURIComponent(d.qr_token || d.referral_id)}`;
            }
        }

        // Action Links
        const gmapsBtn = document.getElementById("citizenGmapsLink");
        if (gmapsBtn) {
            const query = encodeURIComponent(`${d.hospital_name}, Maharashtra`);
            gmapsBtn.href = `https://www.google.com/maps/search/?api=1&query=${query}`;
        }
    }

    function toggleLanguage() {
        isMarathi = !isMarathi;
        const btn = document.getElementById("citizenLangToggleBtn");
        if (btn) {
            btn.innerText = isMarathi ? "English मध्ये वाचा" : "मराठीत वाचा (Marathi)";
        }
        renderPass();
    }

    return {
        init,
        toggleLanguage
    };
})();

// Auto-run if on standalone pass page
if (window.location.pathname.includes("/pass")) {
    document.addEventListener("DOMContentLoaded", CitizenPass.init);
}

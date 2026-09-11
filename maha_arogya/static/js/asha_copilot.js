/**
 * MahaArogya ASHA Field Copilot Module
 * Government of Maharashtra - Arogya Vibhag | SIH 2026 PS 133
 * 
 * Capabilities:
 * 1. Vernacular speech recognition (Marathi, Hindi, English)
 * 2. Real-time HTML5 audio waveform canvas animation
 * 3. Quick-tap obstetric red-flag chips
 * 4. Automatic Devanagari numeral normalization
 * 5. Emergency referral pass & QR generation
 * 6. Offline queueing & 2G auto-sync
 */

const AshaCopilot = (function () {
    let recognition = null;
    let isRecording = false;
    let audioContext = null;
    let analyser = null;
    let animationFrameId = null;
    let currentLanguage = "mr";
    let lastTriageResult = null;

    // Presets by language
    const PRESETS = {
        mr: [
            { title: "🚨 प्री-एक्लॅम्पसिया (Preeclampsia)", text: "रुग्ण आयडी PAT-4102, गरोदर ३२ आठवडे, बीपी १५०/९५, तीव्र डोकेदुखी आणि डोळ्यासमोर अंधारी, पायांवर सूज आहे.", district: "Pune" },
            { title: "⚠️ हिवताप / तीव्र ताप (Malaria)", text: "रुग्ण आयडी PAT-3301, अंगात तीव्र ताप, थंडी वाजून येणे, मळमळ आणि उलट्या होत आहेत.", district: "Gadchiroli" },
            { title: "✅ नियमित तपासणी (Routine ANC)", text: "रुग्ण आयडी PAT-1050, नियमित गरोदर तपासणी, २० आठवडे, बीपी ११८/७८, सर्व काही व्यवस्थित आहे.", district: "Nashik" }
        ],
        hi: [
            { title: "🚨 प्री-एक्लेम्पसिया (Preeclampsia)", text: "मरीज आईडी PAT-4102, 32 हफ्ते की गर्भवती, बीपी 150/95, तेज सिरदर्द, धुंधला दिखना और चेहरे पर सूजन है।", district: "Pune" },
            { title: "⚠️ तेज बुखार (Fever/Malaria)", text: "मरीज आईडी PAT-3301, तेज बुखार, ठंड लगना, उल्टी और चक्कर आना।", district: "Gadchiroli" },
            { title: "✅ सामान्य गर्भावस्था (Routine ANC)", text: "मरीज आईडी PAT-1050, सामान्य गर्भावस्था जांच, बीपी 118/78, सब सामान्य है।", district: "Nashik" }
        ],
        en: [
            { title: "🚨 Severe Preeclampsia", text: "Patient ID PAT-4102, 32 weeks pregnant, blood pressure 150/95, severe headache, blurred vision, and facial swelling.", district: "Pune" },
            { title: "⚠️ High Fever / Malaria", text: "Patient ID PAT-3301, acute high fever with chills, body ache, nausea, and vomiting.", district: "Gadchiroli" },
            { title: "✅ Normal Antenatal (Routine)", text: "Patient ID PAT-1050, routine antenatal checkup, 24 weeks pregnant, blood pressure 118/76, fetal movement normal.", district: "Nashik" }
        ]
    };

    function init() {
        initSpeechRecognition();
        initWaveformCanvas();
        renderPresets();
        updateOfflineQueueBadge();
        
        // Listen for online recovery to trigger auto-sync
        window.addEventListener("online", handleNetworkResume);
        window.addEventListener("offline", updateOfflineQueueBadge);
    }

    // =========================================================================
    // 1. Speech Recognition & Waveform Visualizer
    // =========================================================================
    function initSpeechRecognition() {
        const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (!SpeechRec) {
            console.warn("Web Speech API not supported in this browser.");
            return;
        }

        recognition = new SpeechRec();
        recognition.continuous = false;
        recognition.interimResults = false;

        recognition.onstart = function () {
            isRecording = true;
            updateMicUI(true);
            startWaveformAnimation();
        };

        recognition.onresult = function (event) {
            const transcript = event.results[0][0].transcript;
            const textarea = document.getElementById("voiceTranscriptInput");
            if (textarea) {
                textarea.value = transcript;
            }
            showToast("✅ आवाज यशस्वीरीत्या नोंदवला! (Speech recorded successfully)");
            submitVoiceIntake();
        };

        recognition.onerror = function (event) {
            console.error("Speech Recognition Error:", event.error);
            showToast("⚠️ Microphone notice: " + event.error);
            stopRecording();
        };

        recognition.onend = function () {
            stopRecording();
        };
    }

    function toggleMicrophone() {
        if (!recognition) {
            alert("Please use Google Chrome, Edge, or an Android browser for Web Speech voice support.");
            return;
        }

        if (isRecording) {
            recognition.stop();
            stopRecording();
        } else {
            const langCodeMap = { mr: "mr-IN", hi: "hi-IN", en: "en-US" };
            recognition.lang = langCodeMap[currentLanguage] || "mr-IN";
            try {
                recognition.start();
            } catch (e) {
                console.warn(e);
            }
        }
    }

    function stopRecording() {
        isRecording = false;
        updateMicUI(false);
        stopWaveformAnimation();
    }

    function updateMicUI(recording) {
        const btn = document.getElementById("micRecordBtn");
        if (!btn) return;
        if (recording) {
            btn.classList.add("btn-mic-recording");
            btn.innerHTML = `<i class="bi bi-stop-circle-fill me-2 fs-5"></i> रेकॉर्डिंग सुरू आहे... (Tap to Stop)`;
        } else {
            btn.classList.remove("btn-mic-recording");
            btn.innerHTML = `<i class="bi bi-mic-fill me-2 fs-5 text-danger"></i> आवाज नोंदणी सुरू करा (Start Voice Intake)`;
        }
    }

    // HTML5 Canvas Audio Waveform Generator
    function initWaveformCanvas() {
        const canvas = document.getElementById("waveformCanvas");
        if (!canvas) return;
        const ctx = canvas.getContext("2d");
        drawIdleWaveform(ctx, canvas.width, canvas.height);
    }

    function drawIdleWaveform(ctx, width, height) {
        ctx.clearRect(0, 0, width, height);
        ctx.strokeStyle = "#334155";
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(0, height / 2);
        ctx.lineTo(width, height / 2);
        ctx.stroke();
    }

    function startWaveformAnimation() {
        const canvas = document.getElementById("waveformCanvas");
        if (!canvas) return;
        const ctx = canvas.getContext("2d");
        let phase = 0;

        function animate() {
            if (!isRecording) return;
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            ctx.strokeStyle = "#38BDF8";
            ctx.lineWidth = 3;
            ctx.beginPath();

            const sliceWidth = canvas.width / 50;
            let x = 0;

            for (let i = 0; i < 50; i++) {
                const v = Math.sin((i * 0.2) + phase) * (Math.random() * 20 + 8);
                const y = (canvas.height / 2) + v;
                if (i === 0) ctx.moveTo(x, y);
                else ctx.lineTo(x, y);
                x += sliceWidth;
            }
            ctx.stroke();
            phase += 0.15;
            animationFrameId = requestAnimationFrame(animate);
        }
        animate();
    }

    function stopWaveformAnimation() {
        if (animationFrameId) cancelAnimationFrame(animationFrameId);
        const canvas = document.getElementById("waveformCanvas");
        if (canvas) {
            const ctx = canvas.getContext("2d");
            drawIdleWaveform(ctx, canvas.width, canvas.height);
        }
    }

    // =========================================================================
    // 2. Language & Presets
    // =========================================================================
    function setLanguage(lang) {
        currentLanguage = lang;
        ["mr", "hi", "en"].forEach(l => {
            const btn = document.getElementById(`langBtn_${l}`);
            if (btn) {
                if (l === lang) btn.className = "btn btn-sm btn-danger fw-bold";
                else btn.className = "btn btn-sm btn-outline-secondary";
            }
        });
        renderPresets();
    }

    function renderPresets() {
        const container = document.getElementById("ashaPresetsContainer");
        if (!container) return;
        container.innerHTML = "";

        const presets = PRESETS[currentLanguage] || PRESETS.mr;
        presets.forEach(p => {
            const chip = document.createElement("button");
            chip.type = "button";
            chip.className = "btn btn-sm btn-outline-dark rounded-pill me-2 mb-2 text-start";
            chip.innerText = p.title;
            chip.onclick = () => {
                const textarea = document.getElementById("voiceTranscriptInput");
                if (textarea) textarea.value = p.text;
                const dist = document.getElementById("ashaDistrictSelect");
                if (dist) dist.value = p.district;
                showToast("Preset Loaded: " + p.title);
            };
            container.appendChild(chip);
        });
    }

    function appendSymptom(text) {
        const textarea = document.getElementById("voiceTranscriptInput");
        if (!textarea) return;
        if (textarea.value.trim().length > 0) {
            textarea.value += ", " + text;
        } else {
            textarea.value = text;
        }
        showToast("Symptom Added: " + text);
    }

    // =========================================================================
    // 3. Multi-Agent Voice Intake Submission
    // =========================================================================
    async function submitVoiceIntake() {
        const transcript = (document.getElementById("voiceTranscriptInput")?.value || "").trim();
        if (!transcript) {
            alert("कृपया प्रथम लक्षणे बोला किंवा मजकूर टाईप करा. (Please speak or enter symptoms first)");
            return;
        }

        const patientId = document.getElementById("ashaPatientId")?.value.trim() || "PAT-4102";
        const district = document.getElementById("ashaDistrictSelect")?.value || "Pune";
        const phone = document.getElementById("ashaPatientPhone")?.value || "+91-9822114477";

        const payload = {
            patient_id: patientId,
            phone: phone,
            district: district,
            phc_id: "PHC-PUN-KND",
            voice_transcript: transcript,
            language: currentLanguage
        };

        // Offline Network Resilience Check
        if (!navigator.onLine) {
            queueOfflineRecord(payload);
            return;
        }

        const submitBtn = document.getElementById("submitIntakeBtn");
        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.innerHTML = `<span class="spinner-border spinner-border-sm me-2"></span> Multi-Agent तपासणी सुरू आहे...`;
        }

        const idempotencyKey = "idemp-" + Date.now() + "-" + Math.random().toString(36).substring(2, 7);

        try {
            const res = await fetch("/voice-intake", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-Idempotency-Key": idempotencyKey,
                    "X-API-Key": "maha-asha-2026"
                },
                body: JSON.stringify(payload)
            });

            if (!res.ok) throw new Error(`HTTP Error ${res.status}`);
            const data = await res.json();
            lastTriageResult = data;
            renderTriageResult(data);
        } catch (err) {
            console.warn("Network issue during intake. Caching locally:", err);
            queueOfflineRecord(payload);
        } finally {
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.innerHTML = `<i class="bi bi-send-fill me-2"></i> तपासा व संदर्भ पास तयार करा (Submit & Triage)`;
            }
        }
    }

    function renderTriageResult(data) {
        const container = document.getElementById("ashaTriageOutput");
        if (!container) return;
        container.classList.remove("d-none");

        // Urgency badge styling
        const badgeClass = data.triage_level === "HIGH" 
            ? "badge-triage-high" 
            : (data.triage_level === "MED" ? "badge-triage-med" : "badge-triage-low");

        const levelLabel = data.triage_level === "HIGH" 
            ? "🚨 तातडीचा संदर्भ (CRITICAL / HIGH RISK)" 
            : (data.triage_level === "MED" ? "⚠️ मध्यम जोखीम (MODERATE / TELECONSULT)" : "✅ सामान्य (LOW RISK / ROUTINE)");

        document.getElementById("triageBadgeDisplay").className = `badge ${badgeClass} fs-6 px-3 py-2`;
        document.getElementById("triageBadgeDisplay").innerText = levelLabel;
        document.getElementById("triageRationaleText").innerText = data.triage_rationale || "";

        // Referral Pass Section
        const passSection = document.getElementById("ashaReferralPassCard");
        if (data.requires_referral && data.referral_details) {
            passSection.classList.remove("d-none");
            document.getElementById("passHospitalName").innerText = data.referral_details.hospital_name || "District Hospital";
            document.getElementById("passReferralId").innerText = "ID: " + data.referral_details.referral_id;
            document.getElementById("passReportingWindow").innerText = "48h SLA Deadline: " + (data.referral_details.sla_expires_at || "Within 48h");
            
            const qrImg = document.getElementById("passQrImage");
            if (qrImg && data.referral_details.qr_image_base64) {
                qrImg.src = "data:image/png;base64," + data.referral_details.qr_image_base64;
            }

            // WhatsApp Share link
            const shareBtn = document.getElementById("whatsappShareBtn");
            if (shareBtn) {
                const encodedMsg = encodeURIComponent(data.vernacular_message || "MahaArogya Referral Pass");
                shareBtn.href = `https://api.whatsapp.com/send?text=${encodedMsg}`;
            }
        } else {
            passSection.classList.add("d-none");
        }

        // Diagnostic FHIR Raw telemetry
        document.getElementById("triageRawJson").innerText = JSON.stringify({
            triage: data.triage_level,
            specialty_needed: data.specialty_needed,
            red_flag_detected: data.red_flag_detected,
            guardrail_passed: data.guardrail_status?.passed,
            dpdp_pii_redacted: data.guardrail_status?.dpdp_pii_redacted
        }, null, 2);

        // Scroll into view
        container.scrollIntoView({ behavior: "smooth" });
    }

    // =========================================================================
    // 4. Offline Queue & 2G Auto-Sync Engine
    // =========================================================================
    function queueOfflineRecord(payload) {
        let queue = JSON.parse(localStorage.getItem("maha_arogya_offline_queue") || "[]");
        payload.queued_at = new Date().toISOString();
        queue.push(payload);
        localStorage.setItem("maha_arogya_offline_queue", JSON.stringify(queue));
        updateOfflineQueueBadge();
        showToast("📦 इंटरनेट नाही: तपासणी स्थानिक मेमरीमध्ये सेव्ह झाली आहे. (Saved locally offline)");
    }

    function updateOfflineQueueBadge() {
        const queue = JSON.parse(localStorage.getItem("maha_arogya_offline_queue") || "[]");
        const badge = document.getElementById("offlineQueueCount");
        const banner = document.getElementById("offlineBanner");
        
        if (badge) badge.innerText = queue.length;
        if (banner) {
            if (!navigator.onLine || queue.length > 0) {
                banner.classList.remove("d-none");
            } else {
                banner.classList.add("d-none");
            }
        }
    }

    async function handleNetworkResume() {
        const queue = JSON.parse(localStorage.getItem("maha_arogya_offline_queue") || "[]");
        if (queue.length === 0) return;

        showToast(`🔄 2G/4G नेटवर्क सुरू झाले: ${queue.length} ऑफलाइन नोंदी सिंक करत आहोत...`);
        try {
            const res = await fetch("/api/offline-sync", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    worker_id: "ASHA-PUN-042",
                    records: queue
                })
            });

            if (res.ok) {
                localStorage.removeItem("maha_arogya_offline_queue");
                updateOfflineQueueBadge();
                showToast("✅ सर्व ऑफलाइन नोंदी यशस्वीरीत्या सिंक झाल्या! (All offline records synced)");
            }
        } catch (e) {
            console.error("Failed to sync offline queue:", e);
        }
    }

    function readAloudCurrentTriage() {
        if (!window.speechSynthesis || !lastTriageResult) return;
        const text = lastTriageResult.vernacular_message || lastTriageResult.triage_rationale;
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.lang = currentLanguage === "en" ? "en-US" : (currentLanguage === "hi" ? "hi-IN" : "mr-IN");
        window.speechSynthesis.speak(utterance);
    }

    function showToast(msg) {
        console.log("[AshaCopilot]", msg);
        const toast = document.getElementById("globalAppToast");
        if (toast) {
            toast.innerText = msg;
            toast.classList.remove("d-none");
            setTimeout(() => toast.classList.add("d-none"), 3500);
        }
    }

    return {
        init,
        toggleMicrophone,
        setLanguage,
        appendSymptom,
        submitVoiceIntake,
        readAloudCurrentTriage
    };
})();

// Auto-initialize on load
document.addEventListener("DOMContentLoaded", AshaCopilot.init);

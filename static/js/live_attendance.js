(() => {
    const config = window.liveAttendanceConfig;
    if (!config) {
        return;
    }

    const video = document.getElementById("liveVideo");
    const canvas = document.getElementById("liveCanvas");
    const startButton = document.getElementById("startCameraBtn");
    const stopButton = document.getElementById("stopCameraBtn");
    const scanButton = document.getElementById("scanFaceBtn");
    const status = document.getElementById("recognitionStatus");
    const resultBox = document.getElementById("recognizedStudent");
    const markButton = document.getElementById("markAttendanceBtn");
    const manualForm = document.getElementById("manualMarkForm");
    const manualUsn = document.getElementById("manualUsn");
    const activityLog = document.getElementById("activityLog");

    let stream = null;
    let recognizedStudent = null;
    let recognizedConfidence = null;

    const nowTime = () => new Date().toLocaleTimeString();

    const appendLog = (message, isError = false) => {
        const item = document.createElement("li");
        item.textContent = `[${nowTime()}] ${message}`;
        if (isError) {
            item.style.borderColor = "rgba(255, 93, 115, 0.38)";
        }
        activityLog.prepend(item);
    };

    const setStatus = (message) => {
        status.textContent = message;
    };

    const stopCamera = () => {
        if (!stream) {
            return;
        }
        stream.getTracks().forEach((track) => track.stop());
        stream = null;
        video.srcObject = null;
        scanButton.disabled = true;
        stopButton.disabled = true;
        startButton.disabled = false;
    };

    const startCamera = async () => {
        try {
            stream = await navigator.mediaDevices.getUserMedia({
                video: { width: { ideal: 960 }, height: { ideal: 540 }, facingMode: "user" },
                audio: false,
            });
            video.srcObject = stream;
            startButton.disabled = true;
            stopButton.disabled = false;
            scanButton.disabled = false;
            setStatus("Camera active. Keep one face in frame and press Scan Face.");
            appendLog("Camera started.");
        } catch (error) {
            setStatus("Could not start camera. Check camera permissions.");
            appendLog("Camera permission failed.", true);
        }
    };

    const toFrameDataUrl = () => {
        const width = video.videoWidth || 960;
        const height = video.videoHeight || 540;
        canvas.width = width;
        canvas.height = height;
        const ctx = canvas.getContext("2d");
        ctx.drawImage(video, 0, 0, width, height);
        return canvas.toDataURL("image/jpeg", 0.9);
    };

    const requestJson = async (url, body) => {
        const response = await fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        });
        const result = await response.json();
        return { response, result };
    };

    const scanFace = async () => {
        if (!stream) {
            setStatus("Start camera first.");
            return;
        }

        setStatus("Scanning face...");
        recognizedStudent = null;
        recognizedConfidence = null;
        markButton.disabled = true;
        resultBox.classList.add("hidden");

        try {
            const { response, result } = await requestJson(config.recognizeUrl, {
                subject_id: config.subjectId,
                image_data: toFrameDataUrl(),
            });

            if (!response.ok || result.status === "error") {
                const message = result.message || "Face scan failed.";
                setStatus(message);
                appendLog(message, true);
                return;
            }

            if (result.status === "unknown") {
                setStatus(result.message || "No matching student.");
                appendLog("No matching student found.", true);
                return;
            }

            recognizedStudent = result.student;
            recognizedConfidence = result.confidence;

            resultBox.innerHTML = `
                <strong>${result.student.full_name}</strong><br />
                USN: ${result.student.usn}<br />
                Confidence: ${result.confidence}%<br />
                Engine: ${result.backend}
            `;
            resultBox.classList.remove("hidden");

            if (result.already_marked) {
                markButton.disabled = true;
                setStatus("Attendance already marked for this student today.");
                appendLog(`${result.student.usn} already marked for today.`);
            } else {
                markButton.disabled = false;
                setStatus("Match found. Click Mark Attendance.");
                appendLog(`Recognized ${result.student.usn} with ${result.confidence}% confidence.`);
            }
        } catch (error) {
            setStatus("Network error during face scan.");
            appendLog("Face scan request failed.", true);
        }
    };

    const markAttendance = async () => {
        if (!recognizedStudent) {
            setStatus("Scan a face before marking attendance.");
            return;
        }

        try {
            const { response, result } = await requestJson(config.markUrl, {
                subject_id: config.subjectId,
                student_id: recognizedStudent.id,
                method: "face",
                confidence: recognizedConfidence,
            });

            if (!response.ok || result.status !== "ok") {
                const message = result.message || "Failed to mark attendance.";
                setStatus(message);
                appendLog(message, true);
                return;
            }

            setStatus(result.message || "Attendance marked.");
            appendLog(`Marked ${recognizedStudent.usn} using face scan.`);
            markButton.disabled = true;
        } catch (error) {
            setStatus("Network error while marking attendance.");
            appendLog("Attendance mark request failed.", true);
        }
    };

    const manualMark = async (event) => {
        event.preventDefault();
        const usn = manualUsn.value.trim().toUpperCase();
        if (!usn) {
            setStatus("Enter USN for manual marking.");
            return;
        }

        try {
            const { response, result } = await requestJson(config.manualUrl, {
                subject_id: config.subjectId,
                usn,
            });

            if (!response.ok || result.status !== "ok") {
                const message = result.message || "Manual mark failed.";
                setStatus(message);
                appendLog(message, true);
                return;
            }

            setStatus(result.message || "Attendance marked manually.");
            appendLog(`Manually marked ${usn}.`);
            manualUsn.value = "";
        } catch (error) {
            setStatus("Network error while manual marking.");
            appendLog("Manual attendance request failed.", true);
        }
    };

    startButton.addEventListener("click", startCamera);
    stopButton.addEventListener("click", stopCamera);
    scanButton.addEventListener("click", scanFace);
    markButton.addEventListener("click", markAttendance);
    manualForm.addEventListener("submit", manualMark);

    if (!config.faceEnabled) {
        startButton.disabled = true;
        stopButton.disabled = true;
        scanButton.disabled = true;
        setStatus("Face scan is disabled. Use manual marking or install face dependencies.");
        appendLog("Face pipeline disabled. Manual mode active.");
    }

    window.addEventListener("beforeunload", stopCamera);
})();

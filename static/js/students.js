(() => {
    const modal = document.getElementById("faceModal");
    if (!modal) {
        return;
    }

    const video = document.getElementById("captureVideo");
    const canvas = document.getElementById("captureCanvas");
    const title = document.getElementById("captureTitle");
    const status = document.getElementById("captureStatus");
    const startButton = document.getElementById("startCamBtn");
    const saveButton = document.getElementById("saveFaceBtn");
    const closeButton = document.getElementById("closeFaceModal");
    const captureButtons = document.querySelectorAll(".capture-face");

    let stream = null;
    let studentId = null;

    const endpointForStudent = (id) => {
        return window.faceProfileEndpointTemplate.replace("/0/", `/${id}/`);
    };

    const stopCamera = () => {
        if (!stream) {
            return;
        }
        stream.getTracks().forEach((track) => track.stop());
        stream = null;
        video.srcObject = null;
    };

    const setStatus = (message) => {
        status.textContent = message;
    };

    const openModal = (id, usn) => {
        studentId = Number(id);
        title.textContent = `Capture Face | ${usn}`;
        setStatus("Click Start Camera.");
        saveButton.disabled = true;
        modal.classList.remove("hidden");
        modal.setAttribute("aria-hidden", "false");
    };

    const closeModal = () => {
        stopCamera();
        modal.classList.add("hidden");
        modal.setAttribute("aria-hidden", "true");
        studentId = null;
    };

    const startCamera = async () => {
        try {
            stream = await navigator.mediaDevices.getUserMedia({
                video: { width: { ideal: 960 }, height: { ideal: 540 }, facingMode: "user" },
                audio: false,
            });
            video.srcObject = stream;
            saveButton.disabled = false;
            setStatus("Camera started. Keep one face visible, then click Capture & Save.");
        } catch (error) {
            setStatus("Camera access failed. Allow camera permission and retry.");
        }
    };

    const captureAndSave = async () => {
        if (!stream || !studentId) {
            setStatus("Start camera before capturing.");
            return;
        }

        const width = video.videoWidth || 960;
        const height = video.videoHeight || 540;

        canvas.width = width;
        canvas.height = height;
        const ctx = canvas.getContext("2d");
        ctx.drawImage(video, 0, 0, width, height);

        const payload = {
            image_data: canvas.toDataURL("image/jpeg", 0.9),
        };

        setStatus("Saving face profile...");

        try {
            const response = await fetch(endpointForStudent(studentId), {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
            });
            const result = await response.json();
            if (!response.ok || result.status !== "ok") {
                setStatus(result.message || "Failed to save face profile.");
                return;
            }

            setStatus(result.message || "Face profile saved.");
            window.setTimeout(() => {
                closeModal();
                window.location.reload();
            }, 800);
        } catch (error) {
            setStatus("Network error while saving profile.");
        }
    };

    captureButtons.forEach((button) => {
        button.addEventListener("click", () => {
            openModal(button.dataset.studentId, button.dataset.studentUsn);
        });
    });

    startButton.addEventListener("click", startCamera);
    saveButton.addEventListener("click", captureAndSave);
    closeButton.addEventListener("click", closeModal);

    modal.addEventListener("click", (event) => {
        if (event.target === modal) {
            closeModal();
        }
    });

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && !modal.classList.contains("hidden")) {
            closeModal();
        }
    });
})();

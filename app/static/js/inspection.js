(() => {
    "use strict";

    const page = document.querySelector(
        "[data-inspection-page]"
    );

    if (!page) {
        return;
    }


    /* =====================================================
       ENDPOINT / CSRF
       ===================================================== */

    const runImageUrl =
        page.dataset
            .runImageUrl;

    const csrfToken =
        document.querySelector(
            'meta[name="csrf-token"]'
        )?.content
        ||
        "";


    /* =====================================================
       ELEMENTS
       ===================================================== */

    const modeButtons =
        page.querySelectorAll(
            "[data-inspection-mode]"
        );

    const uploadSections =
        page.querySelectorAll(
            "[data-upload-section]"
        );

    const fileInputs = {
        image:
            page.querySelector(
                '[data-file-input="image"]'
            ),

        video:
            page.querySelector(
                '[data-file-input="video"]'
            ),
    };

    const selectedFileLabels = {
        image:
            page.querySelector(
                '[data-selected-file="image"]'
            ),

        video:
            page.querySelector(
                '[data-selected-file="video"]'
            ),
    };

    const dropzones = {
        image:
            page.querySelector(
                '[data-dropzone="image"]'
            ),

        video:
            page.querySelector(
                '[data-dropzone="video"]'
            ),
    };

    const originalEmpty =
        page.querySelector(
            "[data-original-empty]"
        );

    const imagePreview =
        page.querySelector(
            "[data-image-preview]"
        );

    const videoPreview =
        page.querySelector(
            "[data-video-preview]"
        );

    const mediaBadge =
        page.querySelector(
            "[data-media-badge]"
        );

    const resultEmpty =
        page.querySelector(
            "[data-result-empty]"
        );

    const resultStage =
        page.querySelector(
            "[data-result-stage]"
        );

    const resultCount =
        page.querySelector(
            "[data-result-count]"
        );

    const runButton =
        page.querySelector(
            "[data-run-inspection]"
        );

    const clearButton =
        page.querySelector(
            "[data-clear-inspection]"
        );

    const status =
        page.querySelector(
            "[data-inspection-status]"
        );

    const selectedObjectCard =
        page.querySelector(
            "[data-selected-object-card]"
        );

    const closeObjectButton =
        page.querySelector(
            "[data-close-object]"
        );

    const qualitySummaryEmpty =
        page.querySelector(
            "[data-quality-summary-empty]"
        );

    const qualitySummary =
        page.querySelector(
            "[data-quality-summary]"
        );

    const summaryTotal =
        page.querySelector(
            "[data-summary-total]"
        );

    const summaryNormal =
        page.querySelector(
            "[data-summary-normal]"
        );

    const summaryDefect =
        page.querySelector(
            "[data-summary-defect]"
        );

    const summaryYield =
        page.querySelector(
            "[data-summary-yield]"
        );

    const defectSummaryEmpty =
        page.querySelector(
            "[data-defect-summary-empty]"
        );

    const defectSummary =
        page.querySelector(
            "[data-defect-summary]"
        );


    const loadingBackdrop =
        document.querySelector(
            "[data-inspection-loading]"
        );

    const loadingStage =
        document.querySelector(
            "[data-loading-stage]"
        );

    const progressTrack =
        document.querySelector(
            "[data-progress-track]"
        );

    const progressFill =
        document.querySelector(
            "[data-progress-fill]"
        );

    const progressPercent =
        document.querySelector(
            "[data-progress-percent]"
        );

    const cancelInspectionButton =
        document.querySelector(
            "[data-cancel-inspection]"
        );

    const cropOriginalCanvas =
        page.querySelector(
            "[data-object-crop-original]"
        );

    const cropMaskedCanvas =
        page.querySelector(
            "[data-object-crop-masked]"
        );


    /* =====================================================
       STATE
       ===================================================== */

    let activeMode =
        "image";

    let activeObjectUrl =
        null;

    let lastResult =
        null;

    let activeJobId =
        null;

    let activeJobStatusUrl =
        null;

    let activeJobCancelUrl =
        null;

    let jobPollTimer =
        null;

    let cancelRequested =
        false;


    /* =====================================================
       PERSISTED INSPECTION STATE

       Keeps the most recent completed Inspection result when
       the user navigates to Dashboard / Reports / Analytics
       and later returns to the Inspection page.

       IndexedDB is used instead of localStorage because the
       original image can be several MB and localStorage is
       too small for reliable image/result persistence.

       The persisted state is removed ONLY when the user clicks
       Clear Result. A newly completed inspection replaces the
       previous saved state.
       ===================================================== */

    const inspectionStateDbName =
        "bika-inspection-state-v1";

    const inspectionStateStoreName =
        "inspection-state";

    const inspectionStateKey =
        "active";

    const activeBatchStorageKey =
        "bika-active-inspection-batch";


    const openInspectionStateDb = () =>
        new Promise(
            (resolve, reject) => {

                if (!window.indexedDB) {

                    reject(
                        new Error(
                            "IndexedDB is not available in this browser."
                        )
                    );

                    return;
                }


                const request =
                    window.indexedDB.open(
                        inspectionStateDbName,
                        1
                    );


                request.onupgradeneeded = () => {

                    const database =
                        request.result;


                    if (
                        !database.objectStoreNames.contains(
                            inspectionStateStoreName
                        )
                    ) {

                        database.createObjectStore(
                            inspectionStateStoreName
                        );

                    }

                };


                request.onsuccess = () =>
                    resolve(
                        request.result
                    );


                request.onerror = () =>
                    reject(
                        request.error
                        ||
                        new Error(
                            "Could not open persisted inspection storage."
                        )
                    );

            }
        );


    const writePersistedInspection = async (
        file,
        result
    ) => {

        if (
            !file
            ||
            !result
        ) {
            return;
        }


        const database =
            await openInspectionStateDb();


        try {

            await new Promise(
                (resolve, reject) => {

                    const transaction =
                        database.transaction(
                            inspectionStateStoreName,
                            "readwrite"
                        );

                    const store =
                        transaction.objectStore(
                            inspectionStateStoreName
                        );


                    store.put(
                        {
                            mode: "image",
                            sourceBlob: file,
                            sourceName: file.name || "Inspection image",
                            sourceType: file.type || "image/jpeg",
                            result,
                            savedAt: Date.now(),
                        },
                        inspectionStateKey
                    );


                    transaction.oncomplete = () =>
                        resolve();

                    transaction.onerror = () =>
                        reject(
                            transaction.error
                            ||
                            new Error(
                                "Could not save the current inspection result."
                            )
                        );

                    transaction.onabort = () =>
                        reject(
                            transaction.error
                            ||
                            new Error(
                                "Saving the current inspection result was aborted."
                            )
                        );

                }
            );


            const batchId =
                result.record
                    ?.batch_id;


            if (batchId) {

                window.localStorage.setItem(
                    activeBatchStorageKey,
                    String(
                        batchId
                    )
                );

            }

        } finally {

            database.close();

        }

    };


    const readPersistedInspection = async () => {

        const database =
            await openInspectionStateDb();


        try {

            return await new Promise(
                (resolve, reject) => {

                    const transaction =
                        database.transaction(
                            inspectionStateStoreName,
                            "readonly"
                        );

                    const store =
                        transaction.objectStore(
                            inspectionStateStoreName
                        );

                    const request =
                        store.get(
                            inspectionStateKey
                        );


                    request.onsuccess = () =>
                        resolve(
                            request.result
                            ||
                            null
                        );

                    request.onerror = () =>
                        reject(
                            request.error
                            ||
                            new Error(
                                "Could not restore the previous inspection result."
                            )
                        );

                }
            );

        } finally {

            database.close();

        }

    };


    const removePersistedInspection = async () => {

        window.localStorage.removeItem(
            activeBatchStorageKey
        );


        if (!window.indexedDB) {
            return;
        }


        const database =
            await openInspectionStateDb();


        try {

            await new Promise(
                (resolve, reject) => {

                    const transaction =
                        database.transaction(
                            inspectionStateStoreName,
                            "readwrite"
                        );

                    const store =
                        transaction.objectStore(
                            inspectionStateStoreName
                        );


                    store.delete(
                        inspectionStateKey
                    );


                    transaction.oncomplete = () =>
                        resolve();

                    transaction.onerror = () =>
                        reject(
                            transaction.error
                            ||
                            new Error(
                                "Could not clear the saved inspection result."
                            )
                        );

                    transaction.onabort = () =>
                        reject(
                            transaction.error
                            ||
                            new Error(
                                "Clearing the saved inspection result was aborted."
                            )
                        );

                }
            );

        } finally {

            database.close();

        }

    };


    /* =====================================================
       HELPERS
       ===================================================== */

    const setStatus = (
        message = "",
        type = ""
    ) => {

        if (!status) {
            return;
        }

        status.textContent =
            message;

        status.classList.remove(
            "is-error",
            "is-success"
        );

        if (type) {

            status.classList.add(
                `is-${type}`
            );

        }

    };


    const setProcessing = (
        processing
    ) => {

        if (runButton) {

            runButton.disabled =
                Boolean(
                    processing
                );

            runButton.setAttribute(
                "aria-busy",
                String(
                    Boolean(
                        processing
                    )
                )
            );

        }

        resultStage?.classList.toggle(
            "is-processing",
            Boolean(
                processing
            )
        );

    };


    const revokeActiveObjectUrl = () => {

        if (!activeObjectUrl) {
            return;
        }

        URL.revokeObjectURL(
            activeObjectUrl
        );

        activeObjectUrl =
            null;

    };


    const clearQualitySummary = () => {

        if (qualitySummaryEmpty) {
            qualitySummaryEmpty.hidden =
                false;
        }

        if (qualitySummary) {
            qualitySummary.hidden =
                true;
        }

        if (summaryTotal) {
            summaryTotal.textContent =
                "0";
        }

        if (summaryNormal) {
            summaryNormal.textContent =
                "0";
        }

        if (summaryDefect) {
            summaryDefect.textContent =
                "0";
        }

        if (summaryYield) {
            summaryYield.textContent =
                "—";
        }


        if (defectSummaryEmpty) {

            defectSummaryEmpty.hidden =
                false;

            defectSummaryEmpty.textContent =
                "No defect reason summary yet.";

        }

        if (defectSummary) {

            defectSummary.hidden =
                true;

            defectSummary.innerHTML =
                "";

        }

    };


    const hideMedia = () => {

        revokeActiveObjectUrl();

        if (imagePreview) {

            imagePreview.hidden =
                true;

            imagePreview.removeAttribute(
                "src"
            );

        }

        if (videoPreview) {

            videoPreview.pause();

            videoPreview.hidden =
                true;

            videoPreview.removeAttribute(
                "src"
            );

            videoPreview.load();

        }

        if (originalEmpty) {
            originalEmpty.hidden =
                false;
        }

        if (mediaBadge) {

            mediaBadge.hidden =
                true;

            mediaBadge.textContent =
                "";

        }

    };


    const clearResultArea = () => {

        lastResult =
            null;

        if (resultEmpty) {
            resultEmpty.hidden =
                false;
        }

        if (resultStage) {

            resultStage.hidden =
                true;

            resultStage.innerHTML =
                "";

        }

        if (resultCount) {

            resultCount.hidden =
                true;

            resultCount.textContent =
                "0 objects";

        }

        if (selectedObjectCard) {
            selectedObjectCard.hidden =
                true;
        }

        clearQualitySummary();

    };


    const setMode = (
        mode
    ) => {

        if (
            mode !== "image"
            &&
            mode !== "video"
        ) {
            return;
        }


        activeMode =
            mode;


        modeButtons.forEach(
            (button) => {

                const selected =
                    button.dataset
                        .inspectionMode
                    ===
                    mode;

                button.classList.toggle(
                    "is-active",
                    selected
                );

                button.setAttribute(
                    "aria-selected",
                    String(
                        selected
                    )
                );

            }
        );


        uploadSections.forEach(
            (section) => {

                section.hidden =
                    section.dataset
                        .uploadSection
                    !==
                    mode;

            }
        );


        hideMedia();

        clearResultArea();


        const currentInput =
            fileInputs[
                mode
            ];


        if (
            currentInput
            &&
            currentInput.files
            &&
            currentInput.files[0]
        ) {

            previewFile(
                mode,
                currentInput.files[
                    0
                ]
            );

        }


        setStatus("");

    };


    const isValidImage = (
        file
    ) => {

        const allowed = [
            "image/jpeg",
            "image/png",
            "image/webp",
        ];


        return (
            allowed.includes(
                file.type
            )
        );

    };


    const isValidVideo = (
        file
    ) => {

        if (
            file.type
            &&
            file.type.startsWith(
                "video/"
            )
        ) {
            return true;
        }


        const extension =
            file.name
                .split(".")
                .pop()
                ?.toLowerCase();


        return [
            "mp4",
            "mov",
            "avi",
            "webm",
        ].includes(
            extension
        );

    };


    const validateFile = (
        mode,
        file
    ) => {

        if (!file) {

            return {
                ok: false,
                message:
                    "Please select a file.",
            };

        }


        if (
            mode === "image"
            &&
            !isValidImage(
                file
            )
        ) {

            return {
                ok: false,
                message:
                    "Please select a JPG, JPEG, PNG or WEBP image.",
            };

        }


        if (
            mode === "image"
            &&
            file.size
            >
            10
            *
            1024
            *
            1024
        ) {

            return {
                ok: false,
                message:
                    "Image size must not exceed 10 MB.",
            };

        }


        if (
            mode === "video"
            &&
            !isValidVideo(
                file
            )
        ) {

            return {
                ok: false,
                message:
                    "Please select a supported video file.",
            };

        }


        return {
            ok: true,
            message: "",
        };

    };


    const previewFile = (
        mode,
        file
    ) => {

        const validation =
            validateFile(
                mode,
                file
            );


        if (!validation.ok) {

            setStatus(
                validation.message,
                "error"
            );

            return;

        }


        revokeActiveObjectUrl();


        activeObjectUrl =
            URL.createObjectURL(
                file
            );


        if (originalEmpty) {
            originalEmpty.hidden =
                true;
        }


        if (mode === "image") {

            if (videoPreview) {

                videoPreview.pause();

                videoPreview.hidden =
                    true;

                videoPreview.removeAttribute(
                    "src"
                );

            }


            if (imagePreview) {

                imagePreview.src =
                    activeObjectUrl;

                imagePreview.hidden =
                    false;

            }

        } else {

            if (imagePreview) {

                imagePreview.hidden =
                    true;

                imagePreview.removeAttribute(
                    "src"
                );

            }


            if (videoPreview) {

                videoPreview.src =
                    activeObjectUrl;

                videoPreview.hidden =
                    false;

                videoPreview.load();

            }

        }


        if (
            selectedFileLabels[
                mode
            ]
        ) {

            selectedFileLabels[
                mode
            ].textContent =
                file.name;

        }


        if (mediaBadge) {

            mediaBadge.textContent =
                mode === "image"
                    ? "Image"
                    : "Video";

            mediaBadge.hidden =
                false;

        }


        clearResultArea();


        setStatus(
            "Ready to run inspection.",
            "success"
        );

    };


    const receiveFile = (
        mode,
        file
    ) => {

        const validation =
            validateFile(
                mode,
                file
            );


        if (!validation.ok) {

            setStatus(
                validation.message,
                "error"
            );

            return;

        }


        const input =
            fileInputs[
                mode
            ];


        if (input) {

            try {

                const transfer =
                    new DataTransfer();

                transfer.items.add(
                    file
                );

                input.files =
                    transfer.files;

            } catch (_) {
                // Browser may not allow assignment.
            }

        }


        previewFile(
            mode,
            file
        );

    };


    const selectedFile = () => {

        const input =
            fileInputs[
                activeMode
            ];


        return (
            input
            &&
            input.files
            &&
            input.files[
                0
            ]
        )
            ?
            input.files[
                0
            ]
            :
            null;

    };


    const percent = (
        value
    ) => {

        if (
            value === null
            ||
            value === undefined
            ||
            Number.isNaN(
                Number(
                    value
                )
            )
        ) {
            return "—";
        }


        return (
            `${(
                Number(
                    value
                )
                *
                100
            ).toFixed(
                1
            )}%`
        );

    };


    const sleep = (
        milliseconds
    ) =>
        new Promise(
            (resolve) =>
                window.setTimeout(
                    resolve,
                    milliseconds
                )
        );


    const showLoadingModal = (
        progress = 0,
        stage = "Preparing inspection…"
    ) => {

        cancelRequested =
            false;

        if (loadingBackdrop) {
            loadingBackdrop.hidden =
                false;
        }

        if (cancelInspectionButton) {

            cancelInspectionButton.disabled =
                false;

            cancelInspectionButton.textContent =
                "Cancel Inspection";

        }

        updateLoadingModal(
            progress,
            stage
        );

    };


    const updateLoadingModal = (
        progress,
        stage
    ) => {

        const safeProgress =
            Math.max(
                0,
                Math.min(
                    100,
                    Number(
                        progress
                    )
                    ||
                    0
                )
            );


        if (loadingStage) {
            loadingStage.textContent =
                stage
                ||
                "Running inspection…";
        }


        if (progressFill) {

            progressFill.style.width =
                `${safeProgress}%`;

        }


        if (progressPercent) {

            progressPercent.textContent =
                `${Math.round(
                    safeProgress
                )}%`;

        }


        if (progressTrack) {

            progressTrack.setAttribute(
                "aria-valuenow",
                String(
                    Math.round(
                        safeProgress
                    )
                )
            );

        }

    };


    const hideLoadingModal = () => {

        if (loadingBackdrop) {
            loadingBackdrop.hidden =
                true;
        }

        if (jobPollTimer) {

            window.clearTimeout(
                jobPollTimer
            );

            jobPollTimer =
                null;

        }

        activeJobId =
            null;

        activeJobStatusUrl =
            null;

        activeJobCancelUrl =
            null;

        cancelRequested =
            false;

    };


    const requestHeaders = () => {

        const headers =
            {};


        if (csrfToken) {

            headers[
                "X-CSRFToken"
            ] =
                csrfToken;

        }


        return headers;

    };


    const clearCanvas = (
        canvas
    ) => {

        if (!canvas) {
            return;
        }


        const context =
            canvas.getContext(
                "2d"
            );


        context.clearRect(
            0,
            0,
            canvas.width,
            canvas.height
        );

    };


    const hexToRgba = (
        hex,
        alpha
    ) => {

        const cleaned =
            String(
                hex
                ||
                "#7A7A7A"
            )
            .replace(
                "#",
                ""
            );


        const full =
            cleaned.length
            ===
            3
                ?
                cleaned
                    .split("")
                    .map(
                        (character) =>
                            character
                            +
                            character
                    )
                    .join("")
                :
                cleaned.padEnd(
                    6,
                    "0"
                );


        const number =
            Number.parseInt(
                full.slice(
                    0,
                    6
                ),
                16
            );


        const red =
            (
                number
                >>
                16
            )
            &
            255;

        const green =
            (
                number
                >>
                8
            )
            &
            255;

        const blue =
            number
            &
            255;


        return (
            `rgba(${red}, ${green}, ${blue}, ${alpha})`
        );

    };


    const drawSelectedObjectCrops = (
        object
    ) => {

        if (
            !object
            ||
            !imagePreview
            ||
            !imagePreview.complete
            ||
            !imagePreview.naturalWidth
            ||
            !imagePreview.naturalHeight
        ) {

            clearCanvas(
                cropOriginalCanvas
            );

            clearCanvas(
                cropMaskedCanvas
            );

            return;

        }


        /* -------------------------------------------------
           BACKEND IMAGE SIZE

           Mask / bbox coordinates come from the image that
           PIL + 09b actually processed. Browser natural image
           dimensions are usually identical, but we keep an
           explicit scale so the crop still aligns correctly
           when browser decoding differs.
           ------------------------------------------------- */

        const backendWidth =
            Number(
                lastResult
                ?.image
                ?.width
                ||
                imagePreview.naturalWidth
            );

        const backendHeight =
            Number(
                lastResult
                ?.image
                ?.height
                ||
                imagePreview.naturalHeight
            );


        const sourceScaleX =
            imagePreview.naturalWidth
            /
            backendWidth;

        const sourceScaleY =
            imagePreview.naturalHeight
            /
            backendHeight;


        /* -------------------------------------------------
           USE THE REAL FULL MASK BOUNDING BOX

           The previous version derived the crop from the
           simplified display polygon. That can look too tight.

           The backend now sends pred["box"], which is the real
           kept mask bounding box used by the 09b pipeline.
           ------------------------------------------------- */

        let minX;
        let minY;
        let maxX;
        let maxY;


        if (
            object.bbox
            &&
            Number.isFinite(
                Number(
                    object.bbox.x0
                )
            )
            &&
            Number.isFinite(
                Number(
                    object.bbox.y0
                )
            )
            &&
            Number.isFinite(
                Number(
                    object.bbox.x1
                )
            )
            &&
            Number.isFinite(
                Number(
                    object.bbox.y1
                )
            )
        ) {

            minX =
                Number(
                    object.bbox.x0
                );

            minY =
                Number(
                    object.bbox.y0
                );

            maxX =
                Number(
                    object.bbox.x1
                );

            maxY =
                Number(
                    object.bbox.y1
                );

        } else {

            const allPoints =
                (
                    object.polygons
                    ||
                    []
                )
                .flat();


            if (!allPoints.length) {

                clearCanvas(
                    cropOriginalCanvas
                );

                clearCanvas(
                    cropMaskedCanvas
                );

                return;

            }


            minX =
                Math.min(
                    ...allPoints.map(
                        (point) =>
                            point[0]
                    )
                );

            minY =
                Math.min(
                    ...allPoints.map(
                        (point) =>
                            point[1]
                    )
                );

            maxX =
                Math.max(
                    ...allPoints.map(
                        (point) =>
                            point[0]
                    )
                );

            maxY =
                Math.max(
                    ...allPoints.map(
                        (point) =>
                            point[1]
                    )
                );

        }


        const objectWidth =
            Math.max(
                1,
                maxX
                -
                minX
                +
                1
            );

        const objectHeight =
            Math.max(
                1,
                maxY
                -
                minY
                +
                1
            );


        /*
         * Give the biscuit enough surrounding context so the
         * entire crop is visible instead of touching the frame.
         *
         * 30% of the longer side works for both straight and
         * bent / fractured biscuits.
         */

        const padding =
            Math.max(
                14,
                Math.round(
                    Math.max(
                        objectWidth,
                        objectHeight
                    )
                    *
                    0.30
                )
            );


        minX =
            Math.max(
                0,
                Math.floor(
                    minX
                    -
                    padding
                )
            );

        minY =
            Math.max(
                0,
                Math.floor(
                    minY
                    -
                    padding
                )
            );

        maxX =
            Math.min(
                backendWidth,
                Math.ceil(
                    maxX
                    +
                    padding
                    +
                    1
                )
            );

        maxY =
            Math.min(
                backendHeight,
                Math.ceil(
                    maxY
                    +
                    padding
                    +
                    1
                )
            );


        const cropWidth =
            Math.max(
                1,
                maxX
                -
                minX
            );

        const cropHeight =
            Math.max(
                1,
                maxY
                -
                minY
            );


        /* -------------------------------------------------
           PRESERVE THE REAL CROP ASPECT RATIO

           No forced 1.35:1 frame and no image stretching.
           ------------------------------------------------- */

        const targetWidth =
            420;

        const targetHeight =
            Math.max(
                1,
                Math.round(
                    targetWidth
                    *
                    cropHeight
                    /
                    cropWidth
                )
            );


        [
            cropOriginalCanvas,
            cropMaskedCanvas,
        ].forEach(
            (canvas) => {

                if (!canvas) {
                    return;
                }


                canvas.width =
                    targetWidth;

                canvas.height =
                    targetHeight;

            }
        );


        const sourceX =
            minX
            *
            sourceScaleX;

        const sourceY =
            minY
            *
            sourceScaleY;

        const sourceWidth =
            cropWidth
            *
            sourceScaleX;

        const sourceHeight =
            cropHeight
            *
            sourceScaleY;


        const drawImageCrop = (
            canvas
        ) => {

            if (!canvas) {
                return null;
            }


            const context =
                canvas.getContext(
                    "2d"
                );


            context.clearRect(
                0,
                0,
                canvas.width,
                canvas.height
            );


            context.imageSmoothingEnabled =
                true;

            context.imageSmoothingQuality =
                "high";


            context.drawImage(
                imagePreview,
                sourceX,
                sourceY,
                sourceWidth,
                sourceHeight,
                0,
                0,
                canvas.width,
                canvas.height
            );


            return context;

        };


        drawImageCrop(
            cropOriginalCanvas
        );


        const maskedContext =
            drawImageCrop(
                cropMaskedCanvas
            );


        if (!maskedContext) {
            return;
        }


        const scaleX =
            cropMaskedCanvas.width
            /
            cropWidth;

        const scaleY =
            cropMaskedCanvas.height
            /
            cropHeight;


        (
            object.polygons
            ||
            []
        ).forEach(
            (polygon) => {

                if (
                    !polygon
                    ||
                    polygon.length
                    <
                    3
                ) {
                    return;
                }


                maskedContext.beginPath();


                polygon.forEach(
                    (
                        point,
                        index
                    ) => {

                        const x =
                            (
                                point[0]
                                -
                                minX
                            )
                            *
                            scaleX;

                        const y =
                            (
                                point[1]
                                -
                                minY
                            )
                            *
                            scaleY;


                        if (
                            index
                            ===
                            0
                        ) {

                            maskedContext.moveTo(
                                x,
                                y
                            );

                        } else {

                            maskedContext.lineTo(
                                x,
                                y
                            );

                        }

                    }
                );


                maskedContext.closePath();


                maskedContext.fillStyle =
                    hexToRgba(
                        object.mask_colour,
                        0.46
                    );

                maskedContext.fill();


                maskedContext.strokeStyle =
                    "rgba(255,255,255,0.98)";

                maskedContext.lineWidth =
                    2;

                maskedContext.stroke();

            }
        );

    };


    const renderSelectedObject = (
        object
    ) => {

        if (!object) {
            return;
        }


        const setText = (
            selector,
            value
        ) => {

            const element =
                page.querySelector(
                    selector
                );


            if (element) {

                element.textContent =
                    value
                    ??
                    "—";

            }

        };


        setText(
            "[data-object-id]",
            object.object_id
        );

        setText(
            "[data-object-class]",
            object.display_name
            ||
            object.class_name
        );

        setText(
            "[data-object-class-confidence]",
            percent(
                object.class_confidence
            )
        );

        setText(
            "[data-object-detection-confidence]",
            percent(
                object.detection_confidence
            )
        );

        setText(
            "[data-object-decision]",
            object.decision
        );


        drawSelectedObjectCrops(
            object
        );


        if (selectedObjectCard) {

            selectedObjectCard.hidden =
                false;

        }

    };


    const pollInspectionJob =
        async () => {

            if (
                !activeJobId
                ||
                !activeJobStatusUrl
            ) {
                return;
            }


            try {

                const response =
                    await fetch(
                        activeJobStatusUrl,
                        {
                            method:
                                "GET",

                            cache:
                                "no-store",

                            headers:
                                requestHeaders(),
                        }
                    );


                const data =
                    await response.json();


                if (
                    !response.ok
                    ||
                    !data.ok
                ) {

                    throw new Error(
                        data.message
                        ||
                        "Unable to read inspection progress."
                    );

                }


                updateLoadingModal(
                    data.progress,
                    data.stage
                );


                if (
                    data.status
                    ===
                    "complete"
                ) {

                    const result =
                        data.result;

                    const completedFile =
                        selectedFile();


                    if (completedFile) {

                        try {

                            await writePersistedInspection(
                                completedFile,
                                result
                            );

                        } catch (error) {

                            console.warn(
                                "Inspection completed, but browser state could not be persisted:",
                                error
                            );

                        }

                    }


                    hideLoadingModal();

                    setProcessing(
                        false
                    );

                    renderResult(
                        result
                    );

                    return;

                }


                if (
                    data.status
                    ===
                    "cancelled"
                ) {

                    hideLoadingModal();

                    setProcessing(
                        false
                    );

                    clearResultArea();

                    setStatus(
                        "Inspection cancelled.",
                        "error"
                    );

                    return;

                }


                if (
                    data.status
                    ===
                    "failed"
                ) {

                    throw new Error(
                        data.message
                        ||
                        "Inspection failed."
                    );

                }


                jobPollTimer =
                    window.setTimeout(
                        pollInspectionJob,
                        450
                    );

            } catch (error) {

                hideLoadingModal();

                setProcessing(
                    false
                );

                clearResultArea();

                setStatus(
                    error.message
                    ||
                    "Inspection failed.",
                    "error"
                );

            }

        };


    /* =====================================================
       SUMMARY RENDERING
       ===================================================== */

    const renderSummary = (
        data
    ) => {

        const summary =
            data.summary
            ||
            {};


        if (qualitySummaryEmpty) {
            qualitySummaryEmpty.hidden =
                true;
        }

        if (qualitySummary) {
            qualitySummary.hidden =
                false;
        }

        if (summaryTotal) {
            summaryTotal.textContent =
                String(
                    summary.judged
                    ??
                    0
                );
        }

        if (summaryNormal) {
            summaryNormal.textContent =
                String(
                    summary.normal
                    ??
                    0
                );
        }

        if (summaryDefect) {
            summaryDefect.textContent =
                String(
                    summary.defect
                    ??
                    0
                );
        }

        if (summaryYield) {

            summaryYield.textContent =
                summary.yield_percent
                ===
                null
                ||
                summary.yield_percent
                ===
                undefined

                    ?
                    "—"

                    :
                    `${Number(
                        summary.yield_percent
                    ).toFixed(
                        1
                    )}%`;

        }


        const defects =
            data.defect_counts
            ||
            [];


        const nonZero =
            defects.filter(
                (item) =>
                    Number(
                        item.count
                    )
                    >
                    0
            );


        if (
            !nonZero.length
        ) {

            if (defectSummaryEmpty) {

                defectSummaryEmpty.hidden =
                    false;

                defectSummaryEmpty.textContent =
                    "No defects detected.";

            }

            if (defectSummary) {

                defectSummary.hidden =
                    true;

                defectSummary.innerHTML =
                    "";

            }

            return;

        }


        if (defectSummaryEmpty) {
            defectSummaryEmpty.hidden =
                true;
        }


        if (!defectSummary) {
            return;
        }


        defectSummary.innerHTML =
            "";


        nonZero.forEach(
            (item) => {

                const row =
                    document.createElement(
                        "div"
                    );

                row.className =
                    "inspection-defect-row";


                const dot =
                    document.createElement(
                        "span"
                    );

                dot.className =
                    "inspection-defect-row-dot";

                dot.style.setProperty(
                    "--defect-colour",
                    item.colour
                    ||
                    "#7A7A7A"
                );


                const label =
                    document.createElement(
                        "span"
                    );

                label.className =
                    "inspection-defect-row-label";

                label.textContent =
                    item.display_name
                    ||
                    item.class_name;


                const count =
                    document.createElement(
                        "strong"
                    );

                count.textContent =
                    String(
                        item.count
                    );


                row.append(
                    dot,
                    label,
                    count
                );


                defectSummary.appendChild(
                    row
                );

            }
        );


        defectSummary.hidden =
            false;

    };


    /* =====================================================
       MASK / RESULT RENDERING
       ===================================================== */

    const renderResult = (
        data
    ) => {

        lastResult =
            data;


        if (
            !resultStage
            ||
            !activeObjectUrl
        ) {

            return;

        }


        resultStage.innerHTML =
            "";


        const resultImage =
            document.createElement(
                "img"
            );

        resultImage.className =
            "inspection-result-image";

        resultImage.src =
            activeObjectUrl;

        resultImage.alt =
            "Inspection result with mask overlay";


        const svgNamespace =
            "http://www.w3.org/2000/svg";


        const svg =
            document.createElementNS(
                svgNamespace,
                "svg"
            );

        svg.setAttribute(
            "class",
            "inspection-mask-svg"
        );

        svg.setAttribute(
            "viewBox",
            `0 0 ${data.image.width} ${data.image.height}`
        );

        svg.setAttribute(
            "preserveAspectRatio",
            "xMidYMid meet"
        );


        (
            data.objects
            ||
            []
        ).forEach(
            (object) => {

                const group =
                    document.createElementNS(
                        svgNamespace,
                        "g"
                    );


                group.classList.add(
                    "inspection-mask-object"
                );


                if (
                    !object.in_safe_zone
                ) {

                    group.classList.add(
                        "is-edge"
                    );

                }


                group.dataset.maskObject =
                    "";

                group.dataset.objectId =
                    object.object_id
                    ||
                    "—";

                group.dataset.className =
                    object.display_name
                    ||
                    object.class_name
                    ||
                    "—";

                group.dataset.classConfidence =
                    percent(
                        object.class_confidence
                    );

                group.dataset.detectionConfidence =
                    percent(
                        object.detection_confidence
                    );

                group.dataset.decision =
                    object.decision
                    ||
                    "—";


                group.style.setProperty(
                    "--mask-colour",
                    object.mask_colour
                    ||
                    "#7A7A7A"
                );


                (
                    object.polygons
                    ||
                    []
                ).forEach(
                    (polygonPoints) => {

                        if (
                            !polygonPoints
                            ||
                            polygonPoints.length
                            <
                            3
                        ) {
                            return;
                        }


                        const polygon =
                            document.createElementNS(
                                svgNamespace,
                                "polygon"
                            );


                        polygon.setAttribute(
                            "points",
                            polygonPoints
                                .map(
                                    (point) =>
                                        `${point[0]},${point[1]}`
                                )
                                .join(
                                    " "
                                )
                        );


                        group.appendChild(
                            polygon
                        );

                    }
                );


                if (
                    group.childNodes.length
                    >
                    0
                ) {

                    svg.appendChild(
                        group
                    );

                }

            }
        );


        resultStage.append(
            resultImage,
            svg
        );


        resultStage.hidden =
            false;


        if (resultEmpty) {
            resultEmpty.hidden =
                true;
        }


        if (resultCount) {

            const kept =
                data.summary?.kept
                ??
                0;

            const judged =
                data.summary?.judged
                ??
                0;


            resultCount.textContent =
                `${judged} judged / ${kept} masks`;

            resultCount.hidden =
                false;

        }


        renderSummary(
            data
        );


        const totalMs =
            Number(
                data.timing
                ?.total_ms
                ??
                0
            );


        const warnings =
            data.domain_check
                ?.warnings
                ??
                [];


        let message =
            `Inspection complete · ${data.summary?.judged ?? 0} judged · ${data.summary?.defect ?? 0} defect`;


        if (
            totalMs
            >
            0
        ) {

            message +=
                ` · ${totalMs.toFixed(0)} ms`;

        }


        if (
            warnings.length
        ) {

            message +=
                ` · ${warnings.length} domain warning${warnings.length === 1 ? "" : "s"}`;

        }


        setStatus(
            message,
            "success"
        );

    };


    const restorePersistedInspection = async () => {

        let persisted;


        try {

            persisted =
                await readPersistedInspection();

        } catch (error) {

            console.warn(
                "Could not restore persisted inspection state:",
                error
            );

            return;
        }


        if (
            !persisted
            ||
            !persisted.result
            ||
            !persisted.sourceBlob
        ) {
            return;
        }


        activeMode =
            "image";


        modeButtons.forEach(
            (button) => {

                const selected =
                    button.dataset
                        .inspectionMode
                    ===
                    "image";


                button.classList.toggle(
                    "is-active",
                    selected
                );

                button.setAttribute(
                    "aria-selected",
                    String(
                        selected
                    )
                );

            }
        );


        uploadSections.forEach(
            (section) => {

                section.hidden =
                    section.dataset
                        .uploadSection
                    !==
                    "image";

            }
        );


        revokeActiveObjectUrl();


        activeObjectUrl =
            URL.createObjectURL(
                persisted.sourceBlob
            );


        if (originalEmpty) {
            originalEmpty.hidden =
                true;
        }


        if (videoPreview) {

            videoPreview.pause();
            videoPreview.hidden =
                true;
            videoPreview.removeAttribute(
                "src"
            );

        }


        if (imagePreview) {

            imagePreview.src =
                activeObjectUrl;

            imagePreview.hidden =
                false;

        }


        if (
            selectedFileLabels.image
        ) {

            selectedFileLabels
                .image
                .textContent =
                persisted.sourceName
                ||
                "Previous inspection image";

        }


        if (mediaBadge) {

            mediaBadge.textContent =
                "Image";

            mediaBadge.hidden =
                false;

        }


        renderResult(
            persisted.result
        );

    };


    /* =====================================================
       MODE SWITCH
       ===================================================== */

    modeButtons.forEach(
        (button) => {

            button.addEventListener(
                "click",
                () => {

                    setMode(
                        button.dataset
                            .inspectionMode
                    );

                }
            );

        }
    );


    /* =====================================================
       FILE INPUTS
       ===================================================== */

    Object.entries(
        fileInputs
    ).forEach(
        (
            [
                mode,
                input,
            ]
        ) => {

            input?.addEventListener(
                "change",
                () => {

                    const file =
                        input.files
                        ?.[0];


                    if (file) {

                        previewFile(
                            mode,
                            file
                        );

                    }

                }
            );

        }
    );


    /* =====================================================
       DRAG AND DROP
       ===================================================== */

    Object.entries(
        dropzones
    ).forEach(
        (
            [
                mode,
                zone,
            ]
        ) => {

            if (!zone) {
                return;
            }


            [
                "dragenter",
                "dragover",
            ].forEach(
                (eventName) => {

                    zone.addEventListener(
                        eventName,
                        (event) => {

                            event.preventDefault();

                            zone.classList.add(
                                "is-dragover"
                            );

                        }
                    );

                }
            );


            [
                "dragleave",
                "drop",
            ].forEach(
                (eventName) => {

                    zone.addEventListener(
                        eventName,
                        (event) => {

                            event.preventDefault();

                            zone.classList.remove(
                                "is-dragover"
                            );

                        }
                    );

                }
            );


            zone.addEventListener(
                "drop",
                (event) => {

                    const file =
                        event
                            .dataTransfer
                            ?.files
                            ?.[0];


                    if (file) {

                        receiveFile(
                            mode,
                            file
                        );

                    }

                }
            );

        }
    );


    /* =====================================================
       RUN REAL 09b IMAGE INSPECTION
       ===================================================== */

    runButton?.addEventListener(
        "click",
        async () => {

            const file =
                selectedFile();


            if (!file) {

                setStatus(
                    activeMode
                    ===
                    "image"
                        ?
                        "Please select an image first."
                        :
                        "Please select a video first.",
                    "error"
                );

                return;

            }


            if (
                activeMode
                ===
                "video"
            ) {

                setStatus(
                    "Image inference is connected first. Video frame inference will be added after image parity is verified.",
                    "error"
                );

                return;

            }


            if (!runImageUrl) {

                setStatus(
                    "Inspection API URL is not configured.",
                    "error"
                );

                return;

            }


            const formData =
                new FormData();

            formData.append(
                "file",
                file
            );


            clearResultArea();

            setProcessing(
                true
            );

            showLoadingModal(
                0,
                "Uploading image"
            );


            setStatus(
                "Inspection is running…"
            );


            try {

                const response =
                    await fetch(
                        runImageUrl,
                        {
                            method:
                                "POST",

                            headers:
                                requestHeaders(),

                            body:
                                formData,
                        }
                    );


                const data =
                    await response.json();


                if (
                    !response.ok
                    ||
                    !data.ok
                ) {

                    throw new Error(
                        data.message
                        ||
                        "Inspection could not start."
                    );

                }


                activeJobId =
                    data.job_id;

                activeJobStatusUrl =
                    data.status_url;

                activeJobCancelUrl =
                    data.cancel_url;


                updateLoadingModal(
                    1,
                    "Inspection job started"
                );


                await pollInspectionJob();

            } catch (error) {

                hideLoadingModal();

                setProcessing(
                    false
                );

                clearResultArea();

                setStatus(
                    error.message
                    ||
                    "Inspection failed.",
                    "error"
                );

            }

        }
    );


    cancelInspectionButton?.addEventListener(
        "click",
        async () => {

            if (
                !activeJobId
                ||
                !activeJobCancelUrl
                ||
                cancelRequested
            ) {
                return;
            }


            cancelRequested =
                true;


            cancelInspectionButton.disabled =
                true;

            cancelInspectionButton.textContent =
                "Cancelling…";


            if (loadingStage) {

                loadingStage.textContent =
                    "Cancelling after current GPU stage…";

            }


            try {

                const response =
                    await fetch(
                        activeJobCancelUrl,
                        {
                            method:
                                "POST",

                            headers:
                                requestHeaders(),
                        }
                    );


                const data =
                    await response.json();


                if (
                    !response.ok
                    ||
                    !data.ok
                ) {

                    throw new Error(
                        data.message
                        ||
                        "Could not cancel inspection."
                    );

                }

            } catch (error) {

                cancelRequested =
                    false;

                cancelInspectionButton.disabled =
                    false;

                cancelInspectionButton.textContent =
                    "Cancel Inspection";

                setStatus(
                    error.message
                    ||
                    "Could not cancel inspection.",
                    "error"
                );

            }

        }
    );


    /* =====================================================
       CLEAR
       ===================================================== */

    clearButton?.addEventListener(
        "click",
        async () => {

            if (
                activeJobId
                &&
                activeJobCancelUrl
            ) {

                try {

                    await fetch(
                        activeJobCancelUrl,
                        {
                            method:
                                "POST",

                            headers:
                                requestHeaders(),
                        }
                    );

                } catch (_) {
                    // Best-effort cancellation during Clear Result.
                }

            }

            hideLoadingModal();


            try {

                await removePersistedInspection();

            } catch (error) {

                console.warn(
                    "Could not clear persisted inspection state:",
                    error
                );

            }


            Object.values(
                fileInputs
            ).forEach(
                (input) => {

                    if (input) {
                        input.value =
                            "";
                    }

                }
            );


            if (
                selectedFileLabels.image
            ) {

                selectedFileLabels
                    .image
                    .textContent =
                    "No image selected.";

            }


            if (
                selectedFileLabels.video
            ) {

                selectedFileLabels
                    .video
                    .textContent =
                    "No video selected.";

            }


            hideMedia();

            clearResultArea();

            setStatus("");

        }
    );


    /* =====================================================
       CLICK MASK → OBJECT DETAILS
       ===================================================== */

    page.addEventListener(
        "click",
        (event) => {

            const target =
                event.target.closest(
                    "[data-mask-object]"
                );


            if (!target) {
                return;
            }


            page
                .querySelectorAll(
                    "[data-mask-object]"
                )
                .forEach(
                    (item) => {

                        item.classList.remove(
                            "is-selected"
                        );

                    }
                );


            target.classList.add(
                "is-selected"
            );


            const objectId =
                target.dataset
                    .objectId;


            const selectedObject =
                (
                    lastResult
                    ?.objects
                    ||
                    []
                )
                .find(
                    (object) =>
                        object.object_id
                        ===
                        objectId
                );


            if (selectedObject) {

                renderSelectedObject(
                    selectedObject
                );

            }

        }
    );


    closeObjectButton?.addEventListener(
        "click",
        () => {

            if (selectedObjectCard) {

                selectedObjectCard.hidden =
                    true;

            }

            clearCanvas(
                cropOriginalCanvas
            );

            clearCanvas(
                cropMaskedCanvas
            );


            page
                .querySelectorAll(
                    "[data-mask-object]"
                )
                .forEach(
                    (item) => {

                        item.classList.remove(
                            "is-selected"
                        );

                    }
                );

        }
    );


    /* =====================================================
       RESTORE LAST COMPLETED RESULT
       ===================================================== */

    restorePersistedInspection();


    /* =====================================================
       CLEANUP
       ===================================================== */

    window.addEventListener(
        "beforeunload",
        revokeActiveObjectUrl
    );

})();

(() => {
    "use strict";

    /* =====================================================
       PAGE
       ===================================================== */

    const page =
        document.querySelector(
            "[data-about-system-page]"
        );

    if (!page) {
        return;
    }


    /* =====================================================
       CSRF
       ===================================================== */

    const csrfToken =
        document.querySelector(
            'meta[name="csrf-token"]'
        )?.content || "";


    /* =====================================================
       TOAST
       ===================================================== */

    const toast =
        page.querySelector(
            "[data-about-toast]"
        );

    const toastText =
        page.querySelector(
            "[data-about-toast-text]"
        );

    let toastTimer = null;


    function showToast(
        message,
        type = "info"
    ) {
        if (
            !toast
            ||
            !toastText
        ) {
            return;
        }

        toastText.textContent =
            message;

        toast.dataset.type =
            type;

        toast.hidden =
            false;

        window.clearTimeout(
            toastTimer
        );

        toastTimer =
            window.setTimeout(
                () => {
                    toast.hidden = true;
                },
                3200
            );
    }


    /* =====================================================
       POST JSON
       ===================================================== */

    async function postJson(
        url,
        payload
    ) {
        if (!url) {
            throw new Error(
                "This action is not configured."
            );
        }

        const response =
            await fetch(
                url,
                {
                    method: "POST",

                    headers: {
                        "Content-Type":
                            "application/json",

                        "X-CSRFToken":
                            csrfToken,
                    },

                    credentials:
                        "same-origin",

                    body:
                        JSON.stringify(
                            payload
                        ),
                }
            );

        let result = {};

        try {
            result =
                await response.json();
        }
        catch (_error) {
            result = {};
        }

        if (
            !response.ok
            ||
            !result.ok
        ) {
            throw new Error(
                result.message
                ||
                "Unable to save this setting."
            );
        }

        return result;
    }


    /* =====================================================
       STORAGE PROGRESS BAR
       ===================================================== */

    function initialiseStorageProgress() {
        page
            .querySelectorAll(
                ".about-progress[data-storage-percent]"
            )
            .forEach(
                (progress) => {
                    const bar =
                        progress.querySelector(
                            "span"
                        );

                    if (!bar) {
                        return;
                    }

                    let percent =
                        Number(
                            progress.dataset
                                .storagePercent
                        );

                    if (
                        !Number.isFinite(
                            percent
                        )
                    ) {
                        percent = 0;
                    }

                    percent =
                        Math.max(
                            0,
                            Math.min(
                                100,
                                percent
                            )
                        );

                    bar.style.width =
                        `${percent}%`;
                }
            );
    }

    initialiseStorageProgress();


    /* =====================================================
       DATA RETENTION
       ===================================================== */

    page
        .querySelectorAll(
            "[data-retention-policy]"
        )
        .forEach(
            (button) => {
                button.addEventListener(
                    "click",
                    async () => {
                        const policy =
                            button.dataset
                                .retentionPolicy;

                        if (!policy) {
                            return;
                        }

                        const previous =
                            page.querySelector(
                                "[data-retention-policy].is-selected"
                            );

                        page
                            .querySelectorAll(
                                "[data-retention-policy]"
                            )
                            .forEach(
                                (item) => {
                                    item.classList.remove(
                                        "is-selected"
                                    );
                                }
                            );

                        button.classList.add(
                            "is-selected"
                        );

                        button.disabled = true;

                        try {
                            const result =
                                await postJson(
                                    page.dataset
                                        .retentionUrl,
                                    {
                                        policy:
                                            policy,
                                    }
                                );

                            showToast(
                                result.message
                                ||
                                "Retention policy saved.",
                                "success"
                            );
                        }
                        catch (error) {
                            button.classList.remove(
                                "is-selected"
                            );

                            previous
                                ?.classList.add(
                                    "is-selected"
                                );

                            showToast(
                                error.message,
                                "error"
                            );
                        }
                        finally {
                            button.disabled = false;
                        }
                    }
                );
            }
        );


    /* =====================================================
       BACKUP TYPE
       ===================================================== */

    page
        .querySelectorAll(
            "[data-backup-type]"
        )
        .forEach(
            (button) => {
                button.addEventListener(
                    "click",
                    () => {
                        page
                            .querySelectorAll(
                                "[data-backup-type]"
                            )
                            .forEach(
                                (item) => {
                                    item.classList.remove(
                                        "is-selected"
                                    );
                                }
                            );

                        button.classList.add(
                            "is-selected"
                        );
                    }
                );
            }
        );


    /* =====================================================
       MODEL MANAGEMENT
       ===================================================== */

    const modelSwitchUrl =
        page.dataset
            .modelSwitchUrl
        ||
        "";

    const modelUploadUrl =
        page.dataset
            .modelUploadUrl
        ||
        "";

    const modelVersionPreviewUrl =
        page.dataset
            .modelVersionPreviewUrl
        ||
        "";


    const modelSwitchModal =
        document.querySelector(
            "[data-model-switch-modal]"
        );

    const modelUploadModal =
        document.querySelector(
            "[data-model-upload-modal]"
        );


    const openModelSwitchButton =
        page.querySelector(
            "[data-open-model-switch]"
        );

    const openModelUploadButton =
        page.querySelector(
            "[data-open-model-upload]"
        );


    const closeModelSwitchButton =
        document.querySelector(
            "[data-close-model-switch]"
        );

    const cancelModelSwitchButton =
        document.querySelector(
            "[data-cancel-model-switch]"
        );

    const applyModelSwitchButton =
        document.querySelector(
            "[data-apply-model-switch]"
        );


    const closeModelUploadButton =
        document.querySelector(
            "[data-close-model-upload]"
        );

    const cancelModelUploadButton =
        document.querySelector(
            "[data-cancel-model-upload]"
        );

    const applyModelUploadButton =
        document.querySelector(
            "[data-apply-model-upload]"
        );


    const modelUploadName =
        document.querySelector(
            "[data-model-upload-name]"
        );

    const modelUploadReleaseDate =
        document.querySelector(
            "[data-model-upload-release-date]"
        );

    const modelUploadStageOptions =
        document.querySelectorAll(
            "[data-model-upload-stage]"
        );

    const modelUploadFile =
        document.querySelector(
            "[data-model-upload-file]"
        );

    const modelUploadDescription =
        document.querySelector(
            "[data-model-upload-description]"
        );

    const generatedVersion =
        document.querySelector(
            "[data-model-generated-version]"
        );

    const generatedVersionHelp =
        document.querySelector(
            "[data-model-generated-version-help]"
        );

    const generatedVersionCard =
        document.querySelector(
            "[data-generated-version-card]"
        );


    let versionPreviewTimer =
        null;

    let versionPreviewController =
        null;


    function openModelModal(
        modal
    ) {
        if (!modal) {
            return;
        }

        modal.hidden =
            false;

        document.body.classList.add(
            "about-modal-open"
        );
    }


    function closeModelModal(
        modal
    ) {
        if (modal) {
            modal.hidden =
                true;
        }

        document.body.classList.remove(
            "about-modal-open"
        );
    }


    function localTodayIso() {
        const now =
            new Date();

        const year =
            now.getFullYear();

        const month =
            String(
                now.getMonth()
                +
                1
            ).padStart(
                2,
                "0"
            );

        const day =
            String(
                now.getDate()
            ).padStart(
                2,
                "0"
            );

        return (
            `${year}-${month}-${day}`
        );
    }


    function selectedModelStage() {
        return (
            Array.from(
                modelUploadStageOptions
            )
            .find(
                (
                    option
                ) =>
                    option.checked
            )
            ?.value
            ||
            ""
        );
    }


    function resetModelUploadForm() {
        if (modelUploadName) {
            modelUploadName.value =
                (
                    modelUploadName.dataset
                        .defaultValue
                    ||
                    "BIKA Biscuit Inspection Model"
                );
        }

        if (modelUploadReleaseDate) {
            modelUploadReleaseDate.value =
                localTodayIso();
        }

        modelUploadStageOptions.forEach(
            (
                option
            ) => {
                option.checked =
                    (
                        option.value
                        ===
                        "production_candidate"
                    );
            }
        );

        if (modelUploadFile) {
            modelUploadFile.value =
                "";
        }

        if (modelUploadDescription) {
            modelUploadDescription.value =
                "";
        }

        if (generatedVersion) {
            generatedVersion.textContent =
                "—";
        }

        if (generatedVersionHelp) {
            generatedVersionHelp.textContent =
                (
                    "Generated automatically from the "
                    +
                    "release date and revision."
                );
        }

        generatedVersionCard
            ?.classList.remove(
                "is-error"
            );
    }


    async function refreshGeneratedVersion() {
        const releaseDate =
            modelUploadReleaseDate
                ?.value
            ||
            "";

        if (
            !releaseDate
            ||
            !modelVersionPreviewUrl
        ) {
            if (generatedVersion) {
                generatedVersion.textContent =
                    "—";
            }

            return;
        }

        if (versionPreviewController) {
            versionPreviewController.abort();
        }

        versionPreviewController =
            new AbortController();

        if (generatedVersion) {
            generatedVersion.textContent =
                "Generating…";
        }

        if (generatedVersionHelp) {
            generatedVersionHelp.textContent =
                (
                    "Checking existing revisions "
                    +
                    "for this release date."
                );
        }

        generatedVersionCard
            ?.classList.remove(
                "is-error"
            );

        try {
            const url =
                new URL(
                    modelVersionPreviewUrl,
                    window.location.origin
                );

            url.searchParams.set(
                "release_date",
                releaseDate
            );

            const response =
                await fetch(
                    url.toString(),
                    {
                        method:
                            "GET",
                        credentials:
                            "same-origin",
                        cache:
                            "no-store",
                        signal:
                            versionPreviewController.signal,
                    }
                );

            const result =
                await response.json();

            if (
                !response.ok
                ||
                !result.ok
            ) {
                throw new Error(
                    result.message
                    ||
                    "Unable to generate the next model version."
                );
            }

            if (generatedVersion) {
                generatedVersion.textContent =
                    result.version;
            }

            if (generatedVersionHelp) {
                generatedVersionHelp.textContent =
                    (
                        "Generated automatically · "
                        +
                        "immutable after upload."
                    );
            }
        }

        catch (error) {
            if (
                error.name
                ===
                "AbortError"
            ) {
                return;
            }

            if (generatedVersion) {
                generatedVersion.textContent =
                    "Unavailable";
            }

            if (generatedVersionHelp) {
                generatedVersionHelp.textContent =
                    (
                        error.message
                        ||
                        "Unable to generate version."
                    );
            }

            generatedVersionCard
                ?.classList.add(
                    "is-error"
                );
        }
    }


    function scheduleVersionPreview() {
        window.clearTimeout(
            versionPreviewTimer
        );

        versionPreviewTimer =
            window.setTimeout(
                refreshGeneratedVersion,
                160
            );
    }


    openModelSwitchButton
        ?.addEventListener(
            "click",
            () => {
                openModelModal(
                    modelSwitchModal
                );
            }
        );


    closeModelSwitchButton
        ?.addEventListener(
            "click",
            () => {
                closeModelModal(
                    modelSwitchModal
                );
            }
        );


    cancelModelSwitchButton
        ?.addEventListener(
            "click",
            () => {
                closeModelModal(
                    modelSwitchModal
                );
            }
        );


    applyModelSwitchButton
        ?.addEventListener(
            "click",
            async () => {
                const selected =
                    modelSwitchModal
                        ?.querySelector(
                            "[data-model-version-option]:checked"
                        );

                if (!selected) {
                    showToast(
                        "Please select a model version.",
                        "error"
                    );
                    return;
                }

                applyModelSwitchButton.disabled =
                    true;

                applyModelSwitchButton.textContent =
                    "Switching…";

                try {
                    const result =
                        await postJson(
                            modelSwitchUrl,
                            {
                                version:
                                    selected.value,
                            }
                        );

                    showToast(
                        result.message
                        ||
                        "Model version switched.",
                        "success"
                    );

                    window.setTimeout(
                        () => {
                            window.location.reload();
                        },
                        450
                    );
                }

                catch (error) {
                    showToast(
                        error.message
                        ||
                        "Unable to switch model version.",
                        "error"
                    );

                    applyModelSwitchButton.disabled =
                        false;

                    applyModelSwitchButton.textContent =
                        "Switch Version";
                }
            }
        );


    openModelUploadButton
        ?.addEventListener(
            "click",
            () => {
                resetModelUploadForm();

                openModelModal(
                    modelUploadModal
                );

                window.setTimeout(
                    () => {
                        modelUploadName
                            ?.focus();

                        refreshGeneratedVersion();
                    },
                    60
                );
            }
        );


    closeModelUploadButton
        ?.addEventListener(
            "click",
            () => {
                closeModelModal(
                    modelUploadModal
                );
            }
        );


    cancelModelUploadButton
        ?.addEventListener(
            "click",
            () => {
                closeModelModal(
                    modelUploadModal
                );
            }
        );


    modelUploadReleaseDate
        ?.addEventListener(
            "input",
            scheduleVersionPreview
        );


    modelUploadReleaseDate
        ?.addEventListener(
            "change",
            refreshGeneratedVersion
        );


    applyModelUploadButton
        ?.addEventListener(
            "click",
            async () => {
                const modelName =
                    modelUploadName
                        ?.value
                        .trim()
                    ||
                    "";

                const releaseDate =
                    modelUploadReleaseDate
                        ?.value
                    ||
                    "";

                const stage =
                    selectedModelStage();

                const description =
                    modelUploadDescription
                        ?.value
                        .trim()
                    ||
                    "";

                const file =
                    modelUploadFile
                        ?.files
                        ?.[0]
                    ||
                    null;

                if (
                    modelName.length
                    <
                    3
                ) {
                    showToast(
                        "Please enter a model name.",
                        "error"
                    );

                    modelUploadName
                        ?.focus();

                    return;
                }

                if (!releaseDate) {
                    showToast(
                        "Please select a release date.",
                        "error"
                    );

                    modelUploadReleaseDate
                        ?.focus();

                    return;
                }

                if (!stage) {
                    showToast(
                        "Please select a model stage.",
                        "error"
                    );

                    return;
                }

                if (!file) {
                    showToast(
                        "Please select a model package ZIP.",
                        "error"
                    );

                    return;
                }

                if (
                    !file.name
                        .toLowerCase()
                        .endsWith(
                            ".zip"
                        )
                ) {
                    showToast(
                        "Model package must be a ZIP file.",
                        "error"
                    );

                    return;
                }

                const formData =
                    new FormData();

                formData.append(
                    "model_name",
                    modelName
                );

                formData.append(
                    "release_date",
                    releaseDate
                );

                formData.append(
                    "stage",
                    stage
                );

                formData.append(
                    "description",
                    description
                );

                formData.append(
                    "package",
                    file
                );

                applyModelUploadButton.disabled =
                    true;

                applyModelUploadButton.textContent =
                    "Uploading…";

                try {
                    const response =
                        await fetch(
                            modelUploadUrl,
                            {
                                method:
                                    "POST",
                                headers: {
                                    "X-CSRFToken":
                                        csrfToken,
                                },
                                credentials:
                                    "same-origin",
                                body:
                                    formData,
                            }
                        );

                    let result = {};

                    try {
                        result =
                            await response.json();
                    }

                    catch (_error) {
                        result = {};
                    }

                    if (
                        !response.ok
                        ||
                        !result.ok
                    ) {
                        throw new Error(
                            result.message
                            ||
                            "Unable to upload model package."
                        );
                    }

                    showToast(
                        result.message
                        ||
                        "Model uploaded successfully.",
                        "success"
                    );

                    window.setTimeout(
                        () => {
                            window.location.reload();
                        },
                        650
                    );
                }

                catch (error) {
                    showToast(
                        error.message
                        ||
                        "Unable to upload model package.",
                        "error"
                    );

                    applyModelUploadButton.disabled =
                        false;

                    applyModelUploadButton.textContent =
                        "Upload Model";
                }
            }
        );


    /* =====================================================
       DESTINATION
       ===================================================== */

    const destinationModal =
        document.querySelector(
            "[data-destination-modal]"
        );

    const destinationLabel =
        page.querySelector(
            "[data-destination-label]"
        );

    const openDestinationButton =
        page.querySelector(
            "[data-open-destination]"
        );

    const closeDestinationButton =
        document.querySelector(
            "[data-close-destination]"
        );

    const cancelDestinationButton =
        document.querySelector(
            "[data-cancel-destination]"
        );

    const applyDestinationButton =
        document.querySelector(
            "[data-apply-destination]"
        );

    const customDestinationWrap =
        document.querySelector(
            "[data-custom-destination-wrap]"
        );

    const customDestinationInput =
        document.querySelector(
            "[data-custom-destination]"
        );

    const destinationOptions =
        Array.from(
            document.querySelectorAll(
                "[data-destination-option]"
            )
        );

    let selectedDestination =
        destinationLabel
            ?.textContent
            .trim()
        ||
        "Local Storage (Default)";

    const standardDestinations =
        new Set([
            "Local Storage (Default)",
            "Project Backup Folder",
        ]);


    function updateCustomDestinationVisibility() {
        const selectedOption =
            destinationModal
                ?.querySelector(
                    "[data-destination-option]:checked"
                );

        const isCustom =
            (
                selectedOption?.value
                ===
                "Custom Server Folder"
            );

        if (
            customDestinationWrap
        ) {
            customDestinationWrap.hidden =
                !isCustom;
        }

        if (
            isCustom
            &&
            customDestinationInput
        ) {
            window.setTimeout(
                () => {
                    customDestinationInput
                        .focus();
                },
                50
            );
        }
    }


    function openDestinationModal() {
        if (
            !destinationModal
        ) {
            showToast(
                "Destination selector is not available.",
                "error"
            );

            return;
        }

        let matched = false;

        destinationOptions.forEach(
            (option) => {
                const shouldSelect =
                    (
                        option.value
                        ===
                        selectedDestination
                    );

                option.checked =
                    shouldSelect;

                if (
                    shouldSelect
                ) {
                    matched = true;
                }
            }
        );

        if (
            !matched
            &&
            !standardDestinations.has(
                selectedDestination
            )
        ) {
            const customOption =
                destinationModal.querySelector(
                    '[data-destination-option][value="Custom Server Folder"]'
                );

            if (
                customOption
            ) {
                customOption.checked = true;
            }

            if (
                customDestinationInput
            ) {
                customDestinationInput.value =
                    (
                        selectedDestination
                        ===
                        "Custom Server Folder"
                    )
                        ? ""
                        : selectedDestination;
            }
        }

        updateCustomDestinationVisibility();

        destinationModal.hidden =
            false;

        document.body.classList.add(
            "about-modal-open"
        );
    }


    function closeDestinationModal() {
        if (
            destinationModal
        ) {
            destinationModal.hidden =
                true;
        }

        document.body.classList.remove(
            "about-modal-open"
        );
    }


    openDestinationButton
        ?.addEventListener(
            "click",
            openDestinationModal
        );

    closeDestinationButton
        ?.addEventListener(
            "click",
            closeDestinationModal
        );

    cancelDestinationButton
        ?.addEventListener(
            "click",
            closeDestinationModal
        );

    destinationOptions.forEach(
        (option) => {
            option.addEventListener(
                "change",
                updateCustomDestinationVisibility
            );
        }
    );

    applyDestinationButton
        ?.addEventListener(
            "click",
            () => {
                const option =
                    destinationModal
                        ?.querySelector(
                            "[data-destination-option]:checked"
                        );

                if (!option) {
                    showToast(
                        "Please select a backup destination.",
                        "error"
                    );

                    return;
                }

                let destination =
                    option.value;

                if (
                    destination
                    ===
                    "Custom Server Folder"
                ) {
                    destination =
                        customDestinationInput
                            ?.value
                            .trim()
                        ||
                        "";

                    if (!destination) {
                        showToast(
                            "Please enter a custom backup folder.",
                            "error"
                        );

                        customDestinationInput
                            ?.focus();

                        return;
                    }
                }

                selectedDestination =
                    destination;

                if (
                    destinationLabel
                ) {
                    destinationLabel.textContent =
                        selectedDestination;
                }

                closeDestinationModal();

                showToast(
                    "Destination updated. Click Save Schedule to save the setting.",
                    "info"
                );
            }
        );


    /* =====================================================
       BACKUP SCHEDULE
       ===================================================== */

    const scheduleModal =
        document.querySelector(
            "[data-schedule-modal]"
        );

    const scheduleLabel =
        page.querySelector(
            "[data-schedule-label]"
        );

    const openScheduleButton =
        page.querySelector(
            "[data-open-schedule]"
        );

    const closeScheduleButton =
        document.querySelector(
            "[data-close-schedule]"
        );

    const cancelScheduleButton =
        document.querySelector(
            "[data-cancel-schedule]"
        );

    const applyScheduleButton =
        document.querySelector(
            "[data-apply-schedule]"
        );

    const scheduleFrequency =
        document.querySelector(
            "[data-schedule-frequency]"
        );

    const scheduleWeekday =
        document.querySelector(
            "[data-schedule-weekday]"
        );

    const scheduleMonthDay =
        document.querySelector(
            "[data-schedule-month-day]"
        );

    const scheduleTime =
        document.querySelector(
            "[data-schedule-time]"
        );

    const weeklyDayWrap =
        document.querySelector(
            "[data-weekly-day-wrap]"
        );

    const monthlyDayWrap =
        document.querySelector(
            "[data-monthly-day-wrap]"
        );

    let selectedSchedule =
        scheduleLabel
            ?.textContent
            .trim()
        ||
        "Weekly, Sunday 02:00";


    function updateScheduleFields() {
        const frequency =
            scheduleFrequency
                ?.value
            ||
            "weekly";

        if (
            weeklyDayWrap
        ) {
            weeklyDayWrap.hidden =
                (
                    frequency
                    !==
                    "weekly"
                );
        }

        if (
            monthlyDayWrap
        ) {
            monthlyDayWrap.hidden =
                (
                    frequency
                    !==
                    "monthly"
                );
        }
    }


    function loadScheduleIntoModal() {
        if (
            !scheduleFrequency
            ||
            !scheduleTime
        ) {
            return;
        }

        const value =
            selectedSchedule.trim();

        let match =
            value.match(
                /^Daily,\s*(\d{2}:\d{2})$/i
            );

        if (match) {
            scheduleFrequency.value =
                "daily";

            scheduleTime.value =
                match[1];

            updateScheduleFields();

            return;
        }

        match =
            value.match(
                /^Weekly,\s*([A-Za-z]+)\s+(\d{2}:\d{2})$/i
            );

        if (match) {
            scheduleFrequency.value =
                "weekly";

            if (
                scheduleWeekday
            ) {
                const weekday =
                    (
                        match[1]
                            .charAt(0)
                            .toUpperCase()
                        +
                        match[1]
                            .slice(1)
                            .toLowerCase()
                    );

                scheduleWeekday.value =
                    weekday;
            }

            scheduleTime.value =
                match[2];

            updateScheduleFields();

            return;
        }

        match =
            value.match(
                /^Monthly,\s*Day\s+(\d{1,2})\s+(\d{2}:\d{2})$/i
            );

        if (match) {
            scheduleFrequency.value =
                "monthly";

            if (
                scheduleMonthDay
            ) {
                scheduleMonthDay.value =
                    match[1];
            }

            scheduleTime.value =
                match[2];

            updateScheduleFields();

            return;
        }

        scheduleFrequency.value =
            "weekly";

        if (
            scheduleWeekday
        ) {
            scheduleWeekday.value =
                "Sunday";
        }

        scheduleTime.value =
            "02:00";

        updateScheduleFields();
    }


    function openScheduleModal() {
        if (
            !scheduleModal
        ) {
            showToast(
                "Schedule selector is not available.",
                "error"
            );

            return;
        }

        loadScheduleIntoModal();

        scheduleModal.hidden =
            false;

        document.body.classList.add(
            "about-modal-open"
        );
    }


    function closeScheduleModal() {
        if (
            scheduleModal
        ) {
            scheduleModal.hidden =
                true;
        }

        document.body.classList.remove(
            "about-modal-open"
        );
    }


    openScheduleButton
        ?.addEventListener(
            "click",
            openScheduleModal
        );

    closeScheduleButton
        ?.addEventListener(
            "click",
            closeScheduleModal
        );

    cancelScheduleButton
        ?.addEventListener(
            "click",
            closeScheduleModal
        );

    scheduleFrequency
        ?.addEventListener(
            "change",
            updateScheduleFields
        );

    applyScheduleButton
        ?.addEventListener(
            "click",
            () => {
                const frequency =
                    scheduleFrequency
                        ?.value
                    ||
                    "weekly";

                const time =
                    scheduleTime
                        ?.value
                    ||
                    "";

                if (!time) {
                    showToast(
                        "Please select a backup time.",
                        "error"
                    );

                    scheduleTime
                        ?.focus();

                    return;
                }

                if (
                    frequency
                    ===
                    "daily"
                ) {
                    selectedSchedule =
                        `Daily, ${time}`;
                }
                else if (
                    frequency
                    ===
                    "weekly"
                ) {
                    const weekday =
                        scheduleWeekday
                            ?.value
                        ||
                        "Sunday";

                    selectedSchedule =
                        (
                            `Weekly, `
                            +
                            `${weekday} `
                            +
                            `${time}`
                        );
                }
                else {
                    const monthDay =
                        scheduleMonthDay
                            ?.value
                        ||
                        "1";

                    selectedSchedule =
                        (
                            `Monthly, Day `
                            +
                            `${monthDay} `
                            +
                            `${time}`
                        );
                }

                if (
                    scheduleLabel
                ) {
                    scheduleLabel.textContent =
                        selectedSchedule;
                }

                closeScheduleModal();

                showToast(
                    "Schedule updated. Click Save Schedule to save the setting.",
                    "info"
                );
            }
        );


    /* =====================================================
       CLOSE MODALS WHEN CLICKING BACKDROP
       ===================================================== */

    destinationModal
        ?.addEventListener(
            "click",
            (event) => {
                if (
                    event.target
                    ===
                    destinationModal
                ) {
                    closeDestinationModal();
                }
            }
        );

    scheduleModal
        ?.addEventListener(
            "click",
            (event) => {
                if (
                    event.target
                    ===
                    scheduleModal
                ) {
                    closeScheduleModal();
                }
            }
        );


    /* =====================================================
       ESCAPE KEY
       ===================================================== */

    document.addEventListener(
        "keydown",
        (event) => {
            if (
                event.key
                !==
                "Escape"
            ) {
                return;
            }

            if (
                destinationModal
                &&
                !destinationModal.hidden
            ) {
                closeDestinationModal();

                return;
            }

            if (
                scheduleModal
                &&
                !scheduleModal.hidden
            ) {
                closeScheduleModal();
            }
        }
    );


    /* =====================================================
       SAVE BACKUP SETTINGS
       ===================================================== */

    const saveBackupSettingsButton =
        page.querySelector(
            "[data-save-backup-settings]"
        );


    saveBackupSettingsButton
        ?.addEventListener(
            "click",
            async (event) => {
                const button =
                    event.currentTarget;

                const selectedType =
                    page.querySelector(
                        "[data-backup-type].is-selected"
                    )?.dataset.backupType;

                const autoEnabled =
                    Boolean(
                        page.querySelector(
                            "[data-auto-backup]"
                        )?.checked
                    );

                if (
                    !selectedType
                ) {
                    showToast(
                        "Please select a backup type.",
                        "error"
                    );

                    return;
                }

                if (
                    !selectedDestination
                ) {
                    showToast(
                        "Please select a backup destination.",
                        "error"
                    );

                    return;
                }

                if (
                    autoEnabled
                    &&
                    !selectedSchedule
                ) {
                    showToast(
                        "Please select an automatic backup schedule.",
                        "error"
                    );

                    return;
                }

                button.disabled =
                    true;

                try {
                    const result =
                        await postJson(
                            page.dataset
                                .backupSettingsUrl,
                            {
                                backup_type:
                                    selectedType,

                                auto_enabled:
                                    autoEnabled,

                                destination:
                                    selectedDestination,

                                schedule:
                                    selectedSchedule,
                            }
                        );

                    showToast(
                        result.message
                        ||
                        "Backup settings saved.",
                        "success"
                    );
                }
                catch (error) {
                    showToast(
                        error.message,
                        "error"
                    );
                }
                finally {
                    button.disabled =
                        false;
                }
            }
        );


    /* =====================================================
       RETENTION PROGRESS BARS
       Keep Jinja out of inline CSS to avoid VS Code CSS lint errors.
       ===================================================== */

    page.querySelectorAll("[data-retention-progress]").forEach(bar => {
        const percentage = Number(bar.dataset.retentionProgress);
        const safePercentage = Number.isFinite(percentage)
            ? Math.max(0, Math.min(100, percentage))
            : 0;
        bar.style.width = `${safePercentage}%`;
    });

    /* =====================================================
       AUDIT FILTER + SEARCH
       ===================================================== */

    let activeAuditFilter = "all";
    let auditPage = 1;
    const auditPageSize = 10;
    const auditSearch = page.querySelector("[data-audit-search]");
    const auditRows = Array.from(page.querySelectorAll("[data-audit-row]"));
    const auditEmpty = page.querySelector("[data-audit-empty]");
    const auditPageSummary = page.querySelector("[data-audit-page-summary]");
    const auditPageButtons = page.querySelector("[data-audit-page-buttons]");
    const auditPrev = page.querySelector("[data-audit-prev]");
    const auditNext = page.querySelector("[data-audit-next]");

    function applyAuditFilter() {
        const query = (auditSearch?.value || "").trim().toLowerCase();
        const matching = auditRows.filter(row => {
            const category = (row.dataset.auditCategory || "").toLowerCase();
            const searchText = (row.dataset.auditSearchText || "").toLowerCase();
            return (activeAuditFilter === "all" || category === activeAuditFilter)
                && (!query || searchText.includes(query));
        });
        const count = matching.length;
        const pageCount = Math.max(1, Math.ceil(count / auditPageSize));
        auditPage = Math.max(1, Math.min(auditPage, pageCount));
        const offset = (auditPage - 1) * auditPageSize;
        const shown = new Set(matching.slice(offset, offset + auditPageSize));
        auditRows.forEach(row => { row.hidden = !shown.has(row); });
        if (auditEmpty) auditEmpty.classList.toggle("is-hidden", count !== 0);
        if (auditPageSummary) {
            auditPageSummary.textContent = count
                ? `Showing ${offset + 1}–${Math.min(offset + auditPageSize, count)} of ${count} logs`
                : "Showing 0–0 of 0 logs";
        }
        if (auditPrev) auditPrev.disabled = auditPage <= 1;
        if (auditNext) auditNext.disabled = auditPage >= pageCount;
        if (auditPageButtons) {
            auditPageButtons.replaceChildren();
            // Same compact number / ellipsis pagination as Reports.
            function visibleAuditPages(current, total) {
                if (total <= 4) return Array.from({ length: total }, (_, i) => i + 1);
                if (current <= 3) return [1, 2, 3, "…", total];
                if (current >= total - 2) return [1, "…", total - 2, total - 1, total];
                return [1, "…", current, "…", total];
            }
            for (const item of visibleAuditPages(auditPage, pageCount)) {
                if (item === "…") {
                    const ellipsis = document.createElement("span");
                    ellipsis.className = "about-audit-page-ellipsis";
                    ellipsis.setAttribute("aria-hidden", "true");
                    ellipsis.textContent = "…";
                    auditPageButtons.appendChild(ellipsis);
                    continue;
                }
                const n = item;
                const button = document.createElement("button");
                button.type = "button";
                button.textContent = n;
                button.className = "about-audit-page-button" + (n === auditPage ? " is-active" : "");
                button.setAttribute("aria-label", `Go to page ${n}`);
                if (n === auditPage) button.setAttribute("aria-current", "page");
                button.addEventListener("click", () => { auditPage = n; applyAuditFilter(); });
                auditPageButtons.appendChild(button);
            }
        }
    }
    page.querySelectorAll("[data-audit-filter]").forEach(button => {
        button.addEventListener("click", () => {
            activeAuditFilter = (button.dataset.auditFilter || "all").toLowerCase();
            auditPage = 1;
            page.querySelectorAll("[data-audit-filter]").forEach(b => b.classList.toggle("is-selected", b === button));
            applyAuditFilter();
        });
    });
    auditSearch?.addEventListener("input", () => { auditPage = 1; applyAuditFilter(); });
    auditPrev?.addEventListener("click", () => { if (auditPage > 1) { auditPage--; applyAuditFilter(); } });
    auditNext?.addEventListener("click", () => { auditPage++; applyAuditFilter(); });
    applyAuditFilter();

    /* =====================================================
       BUTTONS RESERVED FOR NEXT BACKEND STEP

       Examples:
       - Switch Version
       - Upload New Model
       - Create Backup Now
       - Restore Backup
       - Upload Backup ZIP
       ===================================================== */

    page
        .querySelectorAll(
            "[data-about-coming-soon]"
        )
        .forEach(
            (button) => {
                button.addEventListener(
                    "click",
                    () => {
                        const feature =
                            button.dataset
                                .aboutComingSoon
                            ||
                            "This action";

                        showToast(
                            (
                                `${feature} is available in the interface, `
                                +
                                "but its runtime backend is not connected yet."
                            ),
                            "info"
                        );
                    }
                );
            }
        );


    /* =====================================================
       INITIAL STATE
       ===================================================== */

    updateScheduleFields();
    applyAuditFilter();

})();

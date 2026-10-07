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


    let toastTimer =
        null;


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

                    toast.hidden =
                        true;

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
                    method:
                        "POST",

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


        let result =
            {};


        try {

            result =
                await response.json();

        }

        catch (_error) {

            result =
                {};

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

                        percent =
                            0;

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


                        button.disabled =
                            true;


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

                            button.disabled =
                                false;

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
       DESTINATION MODAL
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


        let matched =
            false;


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

                    matched =
                        true;

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

                customOption.checked =
                    true;

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
       CUSTOM SELECT DROPDOWNS
       ===================================================== */

    const customSelectRecords =
        Array.from(
            document.querySelectorAll(
                "[data-custom-select]"
            )
        )
        .map(
            (select) => {

                const trigger =
                    select.querySelector(
                        "[data-custom-select-trigger]"
                    );


                const menu =
                    select.querySelector(
                        "[data-custom-select-menu]"
                    );


                const label =
                    select.querySelector(
                        "[data-custom-select-label]"
                    );


                const input =
                    select.querySelector(
                        'input[type="hidden"]'
                    );


                const options =
                    Array.from(
                        select.querySelectorAll(
                            ".about-custom-select-option"
                        )
                    );


                return {
                    select,
                    trigger,
                    menu,
                    label,
                    input,
                    options,
                };

            }
        );


    let openCustomSelectRecord =
        null;


    function syncCustomSelectRecord(
        record
    ) {

        if (
            !record
            ||
            !record.input
        ) {
            return;
        }


        const value =
            String(
                record.input.value
                ??
                ""
            );


        let selectedOption =
            null;


        record.options.forEach(
            (option) => {

                const selected =
                    (
                        String(
                            option.dataset.value
                            ??
                            ""
                        )
                        ===
                        value
                    );


                option.classList.toggle(
                    "is-selected",
                    selected
                );


                option.setAttribute(
                    "aria-selected",
                    selected
                        ? "true"
                        : "false"
                );


                if (
                    selected
                ) {

                    selectedOption =
                        option;

                }

            }
        );


        if (
            record.label
            &&
            selectedOption
        ) {

            record.label.textContent =
                selectedOption
                    .textContent
                    .trim();

        }

    }


    function syncAllCustomSelects() {

        customSelectRecords.forEach(
            syncCustomSelectRecord
        );

    }


    function restoreCustomSelectMenu(
        record
    ) {

        if (
            !record?.menu
        ) {
            return;
        }


        record.menu.hidden =
            true;


        record.menu.classList.remove(
            "is-portal"
        );


        record.menu.style.removeProperty(
            "left"
        );


        record.menu.style.removeProperty(
            "top"
        );


        record.menu.style.removeProperty(
            "width"
        );


        record.menu.style.removeProperty(
            "max-height"
        );

    }


    function closeCustomSelect(
        record
    ) {

        if (!record) {
            return;
        }


        record.select.classList.remove(
            "is-open"
        );


        record.trigger
            ?.setAttribute(
                "aria-expanded",
                "false"
            );


        restoreCustomSelectMenu(
            record
        );


        if (
            openCustomSelectRecord
            ===
            record
        ) {

            openCustomSelectRecord =
                null;

        }

    }


    function closeAllCustomSelects(
        except = null
    ) {

        customSelectRecords.forEach(
            (record) => {

                if (
                    record
                    ===
                    except
                ) {
                    return;
                }


                closeCustomSelect(
                    record
                );

            }
        );

    }


    function openCustomSelect(
        record
    ) {

        if (
            !record?.menu
            ||
            !record.trigger
        ) {
            return;
        }


        const wasOpen =
            record.select
                .classList
                .contains(
                    "is-open"
                );


        closeAllCustomSelects(
            record
        );


        if (
            wasOpen
        ) {

            closeCustomSelect(
                record
            );

            return;

        }


        /*
         * If another selector is opened,
         * close the Time panel first,
         * except when this selector is inside
         * the Time panel itself.
         */

        if (
            timePanel
            &&
            !timePanel.hidden
            &&
            !timePanel.contains(
                record.select
            )
        ) {

            closeTimePicker();

        }


        syncCustomSelectRecord(
            record
        );


        /*
         * Keep dropdown inside its
         * own custom-select wrapper.
         */

        if (
            record.menu.parentNode
            !==
            record.select
        ) {

            record.select.appendChild(
                record.menu
            );

        }


        record.select.classList.add(
            "is-open"
        );


        record.trigger.setAttribute(
            "aria-expanded",
            "true"
        );


        record.menu.classList.remove(
            "is-portal"
        );


        record.menu.hidden =
            false;


        openCustomSelectRecord =
            record;

    }


    customSelectRecords.forEach(
        (record) => {

            record.trigger
                ?.addEventListener(
                    "click",
                    (event) => {

                        event.preventDefault();

                        event.stopPropagation();


                        openCustomSelect(
                            record
                        );

                    }
                );


            record.menu
                ?.addEventListener(
                    "click",
                    (event) => {

                        event.stopPropagation();

                    }
                );


            record.options.forEach(
                (option) => {

                    option.addEventListener(
                        "click",
                        (event) => {

                            event.preventDefault();

                            event.stopPropagation();


                            const value =
                                String(
                                    option.dataset.value
                                    ??
                                    ""
                                );


                            if (
                                record.input
                            ) {

                                record.input.value =
                                    value;

                            }


                            syncCustomSelectRecord(
                                record
                            );


                            closeCustomSelect(
                                record
                            );


                            record.input
                                ?.dispatchEvent(
                                    new Event(
                                        "change",
                                        {
                                            bubbles:
                                                true,
                                        }
                                    )
                                );


                            record.trigger
                                ?.focus();

                        }
                    );

                }
            );

        }
    );


    syncAllCustomSelects();


    /* =====================================================
       SCHEDULE MODAL
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


    /*
     * IMPORTANT:
     * This is now a HIDDEN INPUT,
     * NOT input[type="time"].
     */

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


    /* =====================================================
       CUSTOM TIME PICKER
       ===================================================== */

    const timePicker =
        document.querySelector(
            "[data-time-picker]"
        );


    const timeTrigger =
        document.querySelector(
            "[data-time-trigger]"
        );


    const timePanel =
        document.querySelector(
            "[data-time-panel]"
        );


    const timeLabel =
        document.querySelector(
            "[data-time-label]"
        );


    const timeHour =
        document.querySelector(
            "[data-time-hour]"
        );


    const timeMinute =
        document.querySelector(
            "[data-time-minute]"
        );


    const timeDone =
        document.querySelector(
            "[data-time-done]"
        );


    function syncTimePickerFromValue() {

        const value =
            scheduleTime?.value
            ||
            "02:00";


        const match =
            value.match(
                /^(\d{2}):(\d{2})$/
            );


        if (!match) {

            return;

        }


        if (
            timeHour
        ) {

            timeHour.value =
                match[1];

        }


        if (
            timeMinute
        ) {

            timeMinute.value =
                match[2];

        }


        if (
            timeLabel
        ) {

            timeLabel.textContent =
                `${match[1]}:${match[2]}`;

        }


        syncAllCustomSelects();

    }


    function updateFinalTimeValue() {

        const hour =
            timeHour?.value
            ||
            "02";


        const minute =
            timeMinute?.value
            ||
            "00";


        const value =
            `${hour}:${minute}`;


        if (
            scheduleTime
        ) {

            scheduleTime.value =
                value;

        }


        if (
            timeLabel
        ) {

            timeLabel.textContent =
                value;

        }

    }


    function openTimePicker() {

        if (
            !timePanel
        ) {
            return;
        }


        closeAllCustomSelects();


        syncTimePickerFromValue();


        timePanel.hidden =
            false;


        timePicker
            ?.classList
            .add(
                "is-open"
            );


        timeTrigger
            ?.setAttribute(
                "aria-expanded",
                "true"
            );

    }


    function closeTimePicker() {

        closeAllCustomSelects();


        if (
            timePanel
        ) {

            timePanel.hidden =
                true;

        }


        timePicker
            ?.classList
            .remove(
                "is-open"
            );


        timeTrigger
            ?.setAttribute(
                "aria-expanded",
                "false"
            );

    }


    timeTrigger
        ?.addEventListener(
            "click",
            (event) => {

                event.preventDefault();

                event.stopPropagation();


                if (
                    timePanel?.hidden
                ) {

                    openTimePicker();

                }

                else {

                    closeTimePicker();

                }

            }
        );


    timePanel
        ?.addEventListener(
            "click",
            (event) => {

                event.stopPropagation();

            }
        );


    timeHour
        ?.addEventListener(
            "change",
            updateFinalTimeValue
        );


    timeMinute
        ?.addEventListener(
            "change",
            updateFinalTimeValue
        );


    timeDone
        ?.addEventListener(
            "click",
            (event) => {

                event.preventDefault();

                event.stopPropagation();


                updateFinalTimeValue();


                closeTimePicker();

            }
        );


    /* =====================================================
       SCHEDULE FIELD VISIBILITY
       ===================================================== */

    function updateScheduleFields() {

        syncAllCustomSelects();


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


    scheduleFrequency
        ?.addEventListener(
            "change",
            () => {

                updateScheduleFields();

            }
        );


    /* =====================================================
       LOAD SAVED SCHEDULE INTO MODAL
       ===================================================== */

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


        /* =================================================
           DAILY
           Daily, 02:00
           ================================================= */

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

            syncTimePickerFromValue();

            return;

        }


        /* =================================================
           WEEKLY
           Weekly, Sunday 02:00
           ================================================= */

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

                scheduleWeekday.value =
                    (
                        match[1]
                            .charAt(0)
                            .toUpperCase()
                        +
                        match[1]
                            .slice(1)
                            .toLowerCase()
                    );

            }


            scheduleTime.value =
                match[2];


            updateScheduleFields();

            syncTimePickerFromValue();

            return;

        }


        /* =================================================
           MONTHLY
           Monthly, Day 1 02:00
           ================================================= */

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

            syncTimePickerFromValue();

            return;

        }


        /* =================================================
           FALLBACK
           ================================================= */

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

        syncTimePickerFromValue();

    }


    /* =====================================================
       OPEN / CLOSE SCHEDULE MODAL
       ===================================================== */

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

        closeAllCustomSelects();

        closeTimePicker();


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


    /* =====================================================
       APPLY SCHEDULE
       ===================================================== */

    applyScheduleButton
        ?.addEventListener(
            "click",
            () => {

                /*
                 * Make sure the final Hour/Minute
                 * values have been copied into
                 * data-schedule-time.
                 */

                updateFinalTimeValue();


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
       CLICK OUTSIDE CUSTOM CONTROLS
       ===================================================== */

    document.addEventListener(
        "click",
        (event) => {

            /*
             * Custom dropdown
             */

            if (
                openCustomSelectRecord
                &&
                !openCustomSelectRecord
                    .select
                    .contains(
                        event.target
                    )
            ) {

                closeAllCustomSelects();

            }


            /*
             * Custom time panel
             */

            if (
                timePicker
                &&
                timePanel
                &&
                !timePanel.hidden
                &&
                !timePicker.contains(
                    event.target
                )
            ) {

                closeTimePicker();

            }

        }
    );


    /* =====================================================
       MODAL BACKDROP
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
                openCustomSelectRecord
            ) {

                closeAllCustomSelects();

                return;

            }


            if (
                timePanel
                &&
                !timePanel.hidden
            ) {

                closeTimePicker();

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
       AUDIT FILTER + SEARCH
       ===================================================== */

    let activeAuditFilter =
        "all";


    const auditSearch =
        page.querySelector(
            "[data-audit-search]"
        );


    const auditRows =
        Array.from(
            page.querySelectorAll(
                "[data-audit-row]"
            )
        );


    const auditEmpty =
        page.querySelector(
            "[data-audit-empty]"
        );


    function applyAuditFilter() {

        const query =
            (
                auditSearch
                    ?.value
                ||
                ""
            )
                .trim()
                .toLowerCase();


        let visibleCount =
            0;


        auditRows.forEach(
            (row) => {

                const category =
                    (
                        row.dataset
                            .auditCategory
                        ||
                        ""
                    )
                        .toLowerCase();


                const searchText =
                    (
                        row.dataset
                            .auditSearchText
                        ||
                        ""
                    )
                        .toLowerCase();


                const categoryMatch =
                    (
                        activeAuditFilter
                        ===
                        "all"
                    )
                    ||
                    (
                        category
                        ===
                        activeAuditFilter
                    );


                const searchMatch =
                    (
                        !query
                        ||
                        searchText.includes(
                            query
                        )
                    );


                const visible =
                    (
                        categoryMatch
                        &&
                        searchMatch
                    );


                row.hidden =
                    !visible;


                if (
                    visible
                ) {

                    visibleCount +=
                        1;

                }

            }
        );


        if (
            auditEmpty
        ) {

            auditEmpty.classList.toggle(
                "is-hidden",
                visibleCount !== 0
            );

        }

    }


    page
        .querySelectorAll(
            "[data-audit-filter]"
        )
        .forEach(
            (button) => {

                button.addEventListener(
                    "click",
                    () => {

                        activeAuditFilter =
                            (
                                button.dataset
                                    .auditFilter
                                ||
                                "all"
                            )
                                .toLowerCase();


                        page
                            .querySelectorAll(
                                "[data-audit-filter]"
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


                        applyAuditFilter();

                    }
                );

            }
        );


    auditSearch
        ?.addEventListener(
            "input",
            applyAuditFilter
        );


    /* =====================================================
       COMING SOON BUTTONS
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

    syncTimePickerFromValue();

    applyAuditFilter();

})();